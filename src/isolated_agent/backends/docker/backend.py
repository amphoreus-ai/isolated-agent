"""Docker-based isolation backend."""
from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from isolated_agent.core.backend import Backend
from isolated_agent.core.models import BackendConfig, ExecutionResult, Sandbox
from isolated_agent.backends.docker.renderer import (
    render_template,
    copy_static_files,
)

if TYPE_CHECKING:
    from isolated_agent.core.agent import Agent

logger = logging.getLogger(__name__)


class DockerNotFoundError(Exception):
    """Raised when Docker or Docker Compose is not available."""


class DockerBackend(Backend):
    """Docker Compose based isolation backend.

    Orchestrates the full lifecycle of an isolated sandbox:
    render templates -> generate SSH keys -> build images -> start
    containers -> run agent -> tear down.
    """

    def __init__(self, config: BackendConfig | None = None, **kwargs):
        self.config = config or BackendConfig(**kwargs)
        self._check_docker()

    # ------------------------------------------------------------------
    # Public API (matches the Backend ABC contract)
    # ------------------------------------------------------------------

    def setup(self, agent: Agent, workspace_path: Path | str) -> Sandbox:
        """Build and start the Docker containers."""
        workspace_path = Path(workspace_path).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)

        project_name = f"isolated-{uuid.uuid4().hex[:8]}"
        build_dir = Path(tempfile.mkdtemp(prefix="isolated-agent-"))

        try:
            self._render_build_context(build_dir, agent, workspace_path, project_name)
            self._generate_ssh_keys(build_dir)
            self._docker_compose(build_dir, "build", project_name)
            self._docker_compose(build_dir, "up", project_name, "-d", "--wait")
        except Exception:
            try:
                self._docker_compose(
                    build_dir, "down", project_name, "-v", "--remove-orphans"
                )
            except Exception:
                pass
            shutil.rmtree(build_dir, ignore_errors=True)
            raise

        return Sandbox(
            project_name=project_name,
            build_dir=build_dir,
            workspace_path=workspace_path,
        )

    def teardown(self, sandbox: Sandbox) -> None:
        """Stop containers and clean up build artefacts."""
        try:
            self._docker_compose(
                sandbox.build_dir,
                "down",
                sandbox.project_name,
                "-v",
                "--remove-orphans",
                "--timeout",
                "10",
            )
        finally:
            shutil.rmtree(sandbox.build_dir, ignore_errors=True)

    def healthcheck(self, sandbox: Sandbox) -> bool:
        """Verify SSH connectivity from agent to task-env."""
        try:
            result = self._docker_compose_exec(
                sandbox,
                "agent",
                ["ssh", "-o", "ConnectTimeout=5", "task-env", "echo", "ok"],
            )
            return result.exit_code == 0 and "ok" in result.stdout
        except Exception as e:
            logger.warning("Healthcheck failed: %s", e)
            return False

    def run_agent(self, sandbox: Sandbox, agent: Agent, task: str) -> ExecutionResult:
        """Launch the agent inside the sandbox.

        Output is streamed directly to the host terminal (stdout/stderr
        are inherited, not captured) so the caller can watch progress in
        real time.
        """
        cmd = agent.launch_command(task)

        compose_cmd = [
            "docker",
            "compose",
            "-p",
            sandbox.project_name,
            "-f",
            str(sandbox.build_dir / "docker-compose.yml"),
            "exec",
            "-T",
            "agent",
        ] + cmd

        logger.info("Running: %s", " ".join(cmd))

        proc = subprocess.run(
            compose_cmd,
            cwd=str(sandbox.build_dir),
            stdin=subprocess.DEVNULL,  # Close stdin so agent doesn't wait for input
            timeout=None,
        )

        return ExecutionResult(
            exit_code=proc.returncode,
            stdout="",
            stderr="",
        )

    def execute(self, sandbox: Sandbox, command: str) -> ExecutionResult:
        """Execute an arbitrary command in the task-env container."""
        return self._docker_compose_exec(
            sandbox, "task-env", ["bash", "-c", command]
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_docker() -> None:
        """Verify docker and docker compose are available."""
        try:
            subprocess.run(
                ["docker", "compose", "version"],
                capture_output=True,
                check=True,
                timeout=10,
            )
        except FileNotFoundError:
            raise DockerNotFoundError(
                "Docker is not installed. Install Docker Desktop or the docker CLI."
            )
        except subprocess.CalledProcessError:
            raise DockerNotFoundError(
                "Docker Compose is not available. "
                "Install Docker Desktop or the docker-compose-plugin."
            )

    def _render_build_context(
        self,
        build_dir: Path,
        agent: Agent,
        workspace_path: Path,
        project_name: str,
    ) -> None:
        """Render all templates into the build directory."""
        shim = agent.get_shim_config()

        # --- symlink shell snippets (PATH discoverability) ---
        local_cmds = " ".join(shim.tool_symlinks_local)
        local_symlinks = (
            f'for cmd in {local_cmds}; do ln -sf task-run "/usr/local/bin/$cmd"; done'
        )
        usr_cmds = " ".join(shim.tool_symlinks_usr)
        usr_symlinks = (
            f'for cmd in {usr_cmds}; do '
            f'ln -sf /usr/local/bin/task-run "/usr/bin/$cmd"; done'
        )

        # --- environment block ---
        env_str = ""
        if shim.env_vars:
            env_lines = [f"{k}={v}" for k, v in shim.env_vars.items()]
            env_str = "ENV " + " \\\n    ".join(env_lines)

        # --- optional bwrap shim ---
        bwrap_setup = ""
        if shim.shim_bwrap:
            bwrap_setup = (
                "COPY scripts/fake-bwrap.sh /usr/bin/bwrap\n"
                "RUN chmod +x /usr/bin/bwrap"
            )

        # --- package install command (Alpine vs Debian) + gcc for interceptor ---
        if shim.pkg_manager == "apt":
            pkg_install_cmd = (
                f"apt-get update && apt-get install -y --no-install-recommends "
                f"{shim.system_packages} gcc libc6-dev "
                f"&& rm -rf /var/lib/apt/lists/*"
            )
        else:
            pkg_install_cmd = (
                f"apk add --no-cache {shim.system_packages} gcc musl-dev"
            )

        # --- LD_PRELOAD whitelist (binaries that execute locally) ---
        forward_local = ":".join(shim.forward_local) if shim.forward_local else ""

        # --- extra packages for task container ---
        extra_pkgs = " ".join(self.config.extra_tools) if self.config.extra_tools else ""

        # --- Non-root user setup (required by some agents like Claude Code) ---
        # Split into two parts: adduser (before sh replacement) and USER (after)
        user_setup = ""
        user_directive = ""
        if shim.run_as_user:
            u = shim.run_as_user
            user_setup = (
                f"RUN adduser -D -h {shim.home_dir} {u} "
                f"&& cp -r /root/.ssh {shim.home_dir}/.ssh "
                f"&& chown -R {u}:{u} {shim.home_dir}/.ssh "
                f"&& chmod 700 {shim.home_dir}/.ssh "
                f"&& chmod 600 {shim.home_dir}/.ssh/id_ed25519 "
                f"&& chmod 600 {shim.home_dir}/.ssh/config "
                f"&& chown -R {u}:{u} {shim.home_dir} {shim.tmp_dir} "
                f"/workspace "
                f"/usr/local/bin/task-* /usr/local/bin/sh-wrapper "
                f"/usr/local/bin/agent-entrypoint"
            )
            user_directive = f"USER {u}"

        # --- Auth volume mounts (e.g., ~/.codex/auth.json) ---
        vol_lines = []
        for host_path, container_path in shim.auth_mounts.items():
            vol_lines.append(f"      - {host_path}:{container_path}:ro")
        agent_extra_volumes = "\n".join(vol_lines)

        # Shared context keys used across multiple templates
        common_ctx: dict[str, str] = {
            "project_name": project_name,
            "api_key_env": agent.api_key_env,
            "workspace_path": str(workspace_path),
            "home_dir": shim.home_dir,
            "tmp_dir": shim.tmp_dir,
            "forward_local": forward_local,
            "agent_extra_volumes": agent_extra_volumes,
        }

        # -- Agent Dockerfile --
        agent_ctx = {
            **common_ctx,
            "base_image": shim.base_image,
            "pkg_install_cmd": pkg_install_cmd,
            "cli_install_cmd": shim.cli_install_cmd,
            "tool_symlinks_local": local_symlinks,
            "tool_symlinks_usr": usr_symlinks,
            "env_vars": env_str,
            "bwrap_setup": bwrap_setup,
            "user_setup": user_setup,
            "user_directive": user_directive,
            "forward_local": forward_local,
        }
        agent_dockerfile = render_template("Dockerfile.agent.tpl", agent_ctx)
        (build_dir / "Dockerfile.agent").write_text(agent_dockerfile)

        # -- Copy interceptor C source into build context --
        intercept_dir = build_dir / "intercept"
        intercept_dir.mkdir(exist_ok=True)
        src = Path(__file__).parent / "intercept" / "exec_forward.c"
        (intercept_dir / "exec_forward.c").write_text(src.read_text())

        # -- Map agent required tools to apt packages for task container --
        tool_to_apt = {
            "python3": "", "python": "",  # already in python3-full
            "pip": "", "pip3": "",        # already in python3-pip
            "git": "",                    # already in base install
            "curl": "",                   # already in base install
            "node": "nodejs", "npm": "npm", "npx": "",  # npx comes with npm
        }
        required_apt = set()
        for tool in agent.get_required_tools():
            apt_pkg = tool_to_apt.get(tool, tool)
            if apt_pkg:
                required_apt.add(apt_pkg)
        required_apt_str = " ".join(sorted(required_apt))

        # -- Task Dockerfile --
        # NOTE: Dockerfile.task.tpl uses $base_image (not $task_base_image),
        # so we pass the *task* image as "base_image" here.
        task_ctx = {
            **common_ctx,
            "base_image": self.config.task_image,
            "extra_packages": extra_pkgs,
            "required_apt_tools": required_apt_str,
        }
        task_dockerfile = render_template("Dockerfile.task.tpl", task_ctx)
        (build_dir / "Dockerfile.task").write_text(task_dockerfile)

        # -- docker-compose.yml --
        compose = render_template("docker-compose.yml.tpl", common_ctx)
        (build_dir / "docker-compose.yml").write_text(compose)

        # -- entrypoint.sh --
        entrypoint = render_template("entrypoint.sh.tpl", common_ctx)
        scripts_dir = build_dir / "scripts"
        scripts_dir.mkdir(parents=True, exist_ok=True)
        entrypoint_path = scripts_dir / "entrypoint.sh"
        entrypoint_path.write_text(entrypoint)
        entrypoint_path.chmod(0o755)

        # -- Static files (shell scripts, ssh_config) --
        copy_static_files(build_dir)

    @staticmethod
    def _generate_ssh_keys(build_dir: Path) -> None:
        """Generate an ephemeral ed25519 key pair for agent -> task-env SSH."""
        ssh_dir = build_dir / ".ssh"
        ssh_dir.mkdir(mode=0o700, exist_ok=True)

        key_path = ssh_dir / "agent_key"
        subprocess.run(
            [
                "ssh-keygen",
                "-t",
                "ed25519",
                "-f",
                str(key_path),
                "-N",
                "",
                "-q",
            ],
            check=True,
            capture_output=True,
        )

    def _docker_compose(
        self,
        build_dir: Path,
        command: str,
        project_name: str,
        *args: str,
    ) -> subprocess.CompletedProcess[str]:
        """Run a docker compose command."""
        cmd = [
            "docker",
            "compose",
            "-p",
            project_name,
            "-f",
            str(build_dir / "docker-compose.yml"),
            command,
        ] + list(args)

        logger.debug("Running: %s", " ".join(cmd))

        result = subprocess.run(
            cmd,
            cwd=str(build_dir),
            capture_output=True,
            text=True,
            timeout=300,
        )

        if result.returncode != 0:
            logger.error(
                "docker compose %s failed:\n%s", command, result.stderr
            )
            raise RuntimeError(
                f"docker compose {command} failed "
                f"(exit {result.returncode}): {result.stderr[:500]}"
            )

        return result

    def _docker_compose_exec(
        self,
        sandbox: Sandbox,
        service: str,
        cmd: list[str],
    ) -> ExecutionResult:
        """Run a command in a running container via ``docker compose exec``."""
        compose_cmd = [
            "docker",
            "compose",
            "-p",
            sandbox.project_name,
            "-f",
            str(sandbox.build_dir / "docker-compose.yml"),
            "exec",
            "-T",
            service,
        ] + cmd

        result = subprocess.run(
            compose_cmd,
            cwd=str(sandbox.build_dir),
            capture_output=True,
            text=True,
            timeout=60,
        )

        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

"""Local backend — agent runs on host, tools forwarded to a Docker container."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import tempfile
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from isolated_agent.core.backend import Backend
from isolated_agent.core.models import BackendConfig, ExecutionResult, Sandbox
from isolated_agent.backends.docker.renderer import render_template

if TYPE_CHECKING:
    from isolated_agent.core.agent import Agent

logger = logging.getLogger(__name__)

# Generic shim script — forwards tool invocations to the task container.
# Symlinked as python3, git, npm, etc. basename($0) determines the tool.
SHIM_SCRIPT = '#!/bin/bash\n'                                         \
    'set -euo pipefail\n'                                              \
    'TOOL="$(basename "$0")"\n'                                        \
    'CONTAINER="$ISOLATED_CONTAINER"\n'                                \
    'HOST_WS="$ISOLATED_WORKSPACE"\n'                                  \
    'CWD="$(pwd)"\n'                                                   \
    'if [[ "$CWD" == "$HOST_WS"* ]]; then\n'                           \
    '    REL="${CWD#$HOST_WS}"\n'                                      \
    '    REMOTE_CWD="/workspace${REL}"\n'                              \
    'else\n'                                                           \
    '    REMOTE_CWD="/workspace"\n'                                    \
    'fi\n'                                                             \
    'exec docker exec -i -w "$REMOTE_CWD" "$CONTAINER" "$TOOL" "$@"\n'


class LocalBackend(Backend):
    """Runs the agent locally on the host, forwarding tool execution
    to an isolated Docker container via ``docker exec``.

    No agent container, no SSH, no API key passthrough needed —
    the local agent uses its native auth (e.g. macOS Keychain).
    """

    def __init__(self, config: BackendConfig | None = None, **kwargs):
        self.config = config or BackendConfig(**kwargs)
        self._check_docker()

    def setup(self, agent: Agent, workspace_path: Path | str) -> Sandbox:
        workspace_path = Path(workspace_path).resolve()
        workspace_path.mkdir(parents=True, exist_ok=True)

        container_name = f"isolated-task-{uuid.uuid4().hex[:8]}"
        build_dir = Path(tempfile.mkdtemp(prefix="isolated-local-"))

        try:
            self._build_task_image(build_dir, agent, workspace_path, container_name)
            self._start_container(container_name, build_dir, workspace_path)
            self._create_shims(build_dir, agent, container_name, workspace_path)
        except Exception:
            self._cleanup_container(container_name)
            shutil.rmtree(build_dir, ignore_errors=True)
            raise

        return Sandbox(
            project_name=container_name,
            build_dir=build_dir,
            workspace_path=workspace_path,
        )

    def teardown(self, sandbox: Sandbox) -> None:
        try:
            self._cleanup_container(sandbox.project_name)
        finally:
            shutil.rmtree(sandbox.build_dir, ignore_errors=True)

    def healthcheck(self, sandbox: Sandbox) -> bool:
        try:
            result = subprocess.run(
                ["docker", "exec", sandbox.project_name, "python3", "--version"],
                capture_output=True, text=True, timeout=10,
            )
            return result.returncode == 0
        except Exception as e:
            logger.warning("Healthcheck failed: %s", e)
            return False

    def run_agent(self, sandbox: Sandbox, agent: Agent, task: str) -> ExecutionResult:
        cmd = agent.launch_command(task)
        shim_dir = sandbox.build_dir / "shims"

        env = os.environ.copy()
        env["PATH"] = f"{shim_dir}:{env['PATH']}"
        env["ISOLATED_CONTAINER"] = sandbox.project_name
        env["ISOLATED_WORKSPACE"] = str(sandbox.workspace_path)

        logger.info("Running locally: %s", " ".join(cmd))
        proc = subprocess.run(
            cmd,
            cwd=str(sandbox.workspace_path),
            env=env,
            stdin=subprocess.DEVNULL,
            timeout=None,
        )

        return ExecutionResult(exit_code=proc.returncode)

    def execute(self, sandbox: Sandbox, command: str) -> ExecutionResult:
        result = subprocess.run(
            ["docker", "exec", "-w", "/workspace", sandbox.project_name,
             "bash", "-c", command],
            capture_output=True, text=True, timeout=60,
        )
        return ExecutionResult(
            exit_code=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _check_docker() -> None:
        try:
            subprocess.run(
                ["docker", "info"], capture_output=True, check=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.CalledProcessError) as e:
            raise RuntimeError("Docker is not running or not installed.") from e

    def _build_task_image(
        self,
        build_dir: Path,
        agent: Agent,
        workspace_path: Path,
        container_name: str,
    ) -> None:
        extra_pkgs = " ".join(self.config.extra_tools) if self.config.extra_tools else ""

        tool_to_apt = {
            "python3": "", "python": "", "pip": "", "pip3": "",
            "git": "", "curl": "",
            "node": "nodejs", "npm": "npm", "npx": "",
        }
        required_apt = set()
        for tool in agent.get_required_tools():
            apt_pkg = tool_to_apt.get(tool, tool)
            if apt_pkg:
                required_apt.add(apt_pkg)

        # Render task Dockerfile — reuse the same template as DockerBackend
        # but we skip SSH setup since we use docker exec instead
        task_ctx = {
            "base_image": self.config.task_image,
            "extra_packages": extra_pkgs,
            "required_apt_tools": " ".join(sorted(required_apt)),
            "project_name": container_name,
            "api_key_env": getattr(agent, "api_key_env", ""),
            "workspace_path": str(workspace_path),
            "home_dir": "/root",
            "tmp_dir": "/tmp",
            "forward_local": "",
            "agent_extra_volumes": "",
        }
        task_dockerfile = render_template("Dockerfile.task.tpl", task_ctx)
        (build_dir / "Dockerfile.task").write_text(task_dockerfile)

        # Generate a dummy SSH key pair (required by task Dockerfile template)
        ssh_dir = build_dir / ".ssh"
        ssh_dir.mkdir(mode=0o700, exist_ok=True)
        subprocess.run(
            ["ssh-keygen", "-t", "ed25519", "-f", str(ssh_dir / "agent_key"),
             "-N", "", "-q"],
            check=True, capture_output=True,
        )

        # Build
        image_tag = f"{container_name}:latest"
        subprocess.run(
            ["docker", "build", "-t", image_tag, "-f",
             str(build_dir / "Dockerfile.task"), str(build_dir)],
            check=True, capture_output=True, text=True, timeout=300,
        )

    @staticmethod
    def _start_container(
        container_name: str, build_dir: Path, workspace_path: Path,
    ) -> None:
        image_tag = f"{container_name}:latest"
        subprocess.run(
            ["docker", "run", "-d",
             "--name", container_name,
             "--init",
             "-v", f"{workspace_path}:/workspace",
             "-w", "/workspace",
             image_tag,
             "sleep", "infinity"],
            check=True, capture_output=True, text=True, timeout=30,
        )

    @staticmethod
    def _create_shims(
        build_dir: Path,
        agent: Agent,
        container_name: str,
        workspace_path: Path,
    ) -> None:
        shim_dir = build_dir / "shims"
        shim_dir.mkdir(exist_ok=True)

        # Write the generic dispatcher script
        dispatcher = shim_dir / "_dispatcher.sh"
        dispatcher.write_text(SHIM_SCRIPT)
        dispatcher.chmod(0o755)

        # Tools that must run locally (agent runtime, e.g. node for Claude Code)
        shim = agent.get_shim_config()
        local_basenames = {
            Path(p).name for p in shim.forward_local
        }

        # Symlink each tool name to the dispatcher (skip local-only tools)
        for tool in agent.get_required_tools():
            if tool in local_basenames:
                continue
            link = shim_dir / tool
            if not link.exists():
                link.symlink_to("_dispatcher.sh")

    @staticmethod
    def _cleanup_container(container_name: str) -> None:
        subprocess.run(
            ["docker", "rm", "-f", container_name],
            capture_output=True, timeout=30,
        )
        subprocess.run(
            ["docker", "rmi", "-f", f"{container_name}:latest"],
            capture_output=True, timeout=30,
        )

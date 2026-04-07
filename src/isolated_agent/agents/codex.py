"""OpenAI Codex agent adapter."""
import os
from pathlib import Path

from isolated_agent.core.agent import Agent
from isolated_agent.core.models import ShimConfig

CODEX_AUTH = Path.home() / ".codex" / "auth.json"


class CodexAgent(Agent):
    """Agent adapter for OpenAI Codex CLI."""

    name: str = "codex"

    def __init__(
        self,
        api_key_env: str = "OPENAI_API_KEY",
        extra_args: list[str] | None = None,
    ):
        self.api_key_env = api_key_env
        self.extra_args = extra_args or []

    def launch_command(self, task: str) -> list[str]:
        cmd = [
            "codex", "exec",
            task,
        ]
        cmd.extend(self.extra_args)
        return cmd

    def get_env_vars(self) -> dict[str, str]:
        return {self.api_key_env: f"${{{self.api_key_env}:-}}"}

    def get_required_tools(self) -> list[str]:
        return ["python3", "python", "pip", "pip3", "node", "npm", "npx", "git", "curl"]

    def get_shim_config(self) -> ShimConfig:
        auth_mounts = {}
        if CODEX_AUTH.exists():
            auth_mounts[str(CODEX_AUTH)] = "/root/.codex/auth.json"

        return ShimConfig(
            base_image="alpine:3.22",
            system_packages="bash coreutils openssh-client nodejs npm",
            cli_install_cmd=(
                "npm install -g @openai/codex"
                " && sed -i '1s|#!/usr/bin/env node|#!/usr/bin/node|'"
                ' "$(readlink -f /usr/local/bin/codex)"'
            ),
            tool_symlinks_local=[
                "python3", "python", "pip", "pip3", "node", "npm", "npx", "git", "curl"
            ],
            tool_symlinks_usr=[
                "python3", "python", "pip", "pip3", "git", "curl"
            ],
            env_vars={
                "SHELL": "/usr/local/bin/task-shell",
                "HOME": "/workspace/.codex-home",
                "TMPDIR": "/workspace/.tmp",
            },
            shim_bwrap=True,
            home_dir="/workspace/.codex-home",
            tmp_dir="/workspace/.tmp",
            forward_local=["/usr/local/bin/codex", "/usr/bin/node"],
            auth_mounts=auth_mounts,
        )

    def validate(self) -> None:
        has_key = bool(os.environ.get(self.api_key_env))
        has_login = CODEX_AUTH.exists()
        if not has_key and not has_login:
            raise ValueError(
                f"No authentication found. Either:\n"
                f"  - Set {self.api_key_env}: export {self.api_key_env}=your-key\n"
                f"  - Or run: codex login"
            )

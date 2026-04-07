"""Cline CLI coding agent adapter."""
import os

from isolated_agent.core.agent import Agent
from isolated_agent.core.models import ShimConfig


class ClineAgent(Agent):
    """Agent adapter for Cline CLI."""

    name: str = "cline"

    def __init__(
        self,
        api_key_env: str = "ANTHROPIC_API_KEY",
        extra_args: list[str] | None = None,
    ):
        self.api_key_env = api_key_env
        self.extra_args = extra_args or []

    def launch_command(self, task: str) -> list[str]:
        cmd = [
            "cline",
            "-y",
            task,
        ]
        cmd.extend(self.extra_args)
        return cmd

    def get_env_vars(self) -> dict[str, str]:
        return {self.api_key_env: f"${{{self.api_key_env}:-}}"}

    def get_required_tools(self) -> list[str]:
        return ["python3", "python", "pip", "pip3", "node", "npm", "npx", "git", "curl"]

    def get_shim_config(self) -> ShimConfig:
        return ShimConfig(
            base_image="alpine:3.22",
            system_packages="bash coreutils openssh-client nodejs npm",
            cli_install_cmd=(
                "npm install -g cline"
                " && sed -i '1s|#!/usr/bin/env node|#!/usr/bin/node|'"
                ' "$(readlink -f /usr/local/bin/cline)"'
            ),
            tool_symlinks_local=[
                "python3", "python", "pip", "pip3", "node", "npm", "npx", "git", "curl"
            ],
            tool_symlinks_usr=[
                "python3", "python", "pip", "pip3", "git", "curl"
            ],
            env_vars={
                "SHELL": "/usr/local/bin/task-shell",
                "HOME": "/workspace/.cline-home",
                "TMPDIR": "/workspace/.tmp",
            },
            shim_bwrap=False,
            home_dir="/workspace/.cline-home",
            tmp_dir="/workspace/.tmp",
            forward_local=["/usr/local/bin/cline", "/usr/bin/node"],
        )

    def validate(self) -> None:
        if not os.environ.get(self.api_key_env):
            raise ValueError(
                f"Environment variable {self.api_key_env} is not set. "
                f"Set it with: export {self.api_key_env}=your-key"
            )

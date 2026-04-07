"""Aider AI pair programming agent adapter."""
import os

from isolated_agent.core.agent import Agent
from isolated_agent.core.models import ShimConfig


class AiderAgent(Agent):
    """Agent adapter for Aider CLI (aider-chat)."""

    name: str = "aider"

    def __init__(
        self,
        api_key_env: str = "ANTHROPIC_API_KEY",
        extra_args: list[str] | None = None,
    ):
        self.api_key_env = api_key_env
        self.extra_args = extra_args or []

    def launch_command(self, task: str) -> list[str]:
        cmd = [
            "aider",
            "--message", task,
            "--yes-always",
            "--no-auto-commits",
        ]
        cmd.extend(self.extra_args)
        return cmd

    def get_env_vars(self) -> dict[str, str]:
        return {self.api_key_env: f"${{{self.api_key_env}:-}}"}

    def get_required_tools(self) -> list[str]:
        return ["python3", "python", "pip", "pip3", "git", "curl"]

    def get_shim_config(self) -> ShimConfig:
        return ShimConfig(
            base_image="python:3.12-slim-bookworm",
            system_packages="bash coreutils openssh-client git curl ca-certificates",
            cli_install_cmd="pip install --no-cache-dir aider-chat",
            tool_symlinks_local=[
                "python3", "python", "pip", "pip3", "git", "curl"
            ],
            tool_symlinks_usr=[
                "python3", "python", "pip", "pip3", "git", "curl"
            ],
            env_vars={
                "SHELL": "/usr/local/bin/task-shell",
                "HOME": "/workspace/.aider-home",
                "TMPDIR": "/workspace/.tmp",
            },
            shim_bwrap=False,
            home_dir="/workspace/.aider-home",
            tmp_dir="/workspace/.tmp",
            pkg_manager="apt",
            forward_local=["/usr/local/bin/aider"],
        )

    def validate(self) -> None:
        if not os.environ.get(self.api_key_env):
            raise ValueError(
                f"Environment variable {self.api_key_env} is not set. "
                f"Set it with: export {self.api_key_env}=your-key"
            )

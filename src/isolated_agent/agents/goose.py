"""Block Goose AI coding agent adapter."""
import os

from isolated_agent.core.agent import Agent
from isolated_agent.core.models import ShimConfig


class GooseAgent(Agent):
    """Agent adapter for Goose CLI (Block/Linux Foundation)."""

    name: str = "goose"

    def __init__(
        self,
        api_key_env: str = "OPENAI_API_KEY",
        extra_args: list[str] | None = None,
    ):
        self.api_key_env = api_key_env
        self.extra_args = extra_args or []

    def launch_command(self, task: str) -> list[str]:
        cmd = [
            "goose", "run",
            "--no-session",
            "-t", task,
        ]
        cmd.extend(self.extra_args)
        return cmd

    def get_env_vars(self) -> dict[str, str]:
        return {
            self.api_key_env: f"${{{self.api_key_env}:-}}",
            "GOOSE_MODE": "auto",
        }

    def get_required_tools(self) -> list[str]:
        return ["python3", "python", "pip", "pip3", "node", "npm", "git", "curl"]

    def get_shim_config(self) -> ShimConfig:
        return ShimConfig(
            base_image="debian:bookworm-slim",
            system_packages="bash coreutils openssh-client curl ca-certificates",
            cli_install_cmd=(
                "curl -fsSL https://github.com/block/goose/releases/download/"
                "stable/download_cli.sh | GOOSE_INSTALL_DIR=/usr/local/bin bash"
            ),
            tool_symlinks_local=[
                "python3", "python", "pip", "pip3", "node", "npm", "git", "curl"
            ],
            tool_symlinks_usr=[
                "python3", "python", "pip", "pip3", "git", "curl"
            ],
            env_vars={
                "SHELL": "/usr/local/bin/task-shell",
                "HOME": "/workspace/.goose-home",
                "TMPDIR": "/workspace/.tmp",
                "GOOSE_MODE": "auto",
            },
            shim_bwrap=False,
            home_dir="/workspace/.goose-home",
            tmp_dir="/workspace/.tmp",
            pkg_manager="apt",
            forward_local=["/usr/local/bin/goose"],
        )

    def validate(self) -> None:
        if not os.environ.get(self.api_key_env):
            raise ValueError(
                f"Environment variable {self.api_key_env} is not set. "
                f"Set it with: export {self.api_key_env}=your-key"
            )

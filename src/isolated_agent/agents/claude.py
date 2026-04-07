"""Claude Code agent adapter."""
import os

from isolated_agent.core.agent import Agent
from isolated_agent.core.models import ShimConfig


class ClaudeCodeAgent(Agent):
    """Agent adapter for Anthropic Claude Code CLI."""

    name: str = "claude"

    def __init__(self, api_key_env: str = "CLAUDE_API_KEY", extra_args: list[str] | None = None):
        self.api_key_env = api_key_env
        self.extra_args = extra_args or []

    def launch_command(self, task: str) -> list[str]:
        """Return the command to launch Claude Code with the given task."""
        cmd = [
            "claude",
            "-p", task,
            "--dangerously-skip-permissions",
        ]
        cmd.extend(self.extra_args)
        return cmd

    def get_env_vars(self) -> dict[str, str]:
        """Return environment variables to pass to the agent container."""
        return {self.api_key_env: f"${{{self.api_key_env}:-}}"}

    def get_required_tools(self) -> list[str]:
        """Return tools that must be available in the task environment."""
        return ["python3", "python", "pip", "pip3", "node", "npm", "npx", "git", "curl"]

    def get_shim_config(self) -> ShimConfig:
        """Return the shim configuration for Docker template rendering."""
        return ShimConfig(
            base_image="alpine:3.22",
            system_packages="bash coreutils openssh-client nodejs npm",
            cli_install_cmd=(
                'npm install -g @anthropic-ai/claude-code '
                '&& sed -i \'1s|#!/usr/bin/env node|#!/usr/bin/node|\' '
                '"$(readlink -f /usr/local/bin/claude)"'
            ),
            tool_symlinks_local=["python3", "python", "pip", "pip3", "node", "npm", "npx", "git", "curl"],
            tool_symlinks_usr=["python3", "python", "pip", "pip3", "git", "curl"],
            env_vars={
                "SHELL": "/usr/local/bin/task-shell",
                "HOME": "/home/agent",
                "TMPDIR": "/workspace/.tmp",
            },
            shim_bwrap=True,
            home_dir="/home/agent",
            tmp_dir="/workspace/.tmp",
            forward_local=["/usr/local/bin/claude", "/usr/bin/node"],
            run_as_user="agent",
        )

    def validate(self) -> None:
        """Validate that required configuration is available."""
        has_key = (
            os.environ.get(self.api_key_env)
            or os.environ.get("ANTHROPIC_API_KEY")
        )
        if not has_key:
            raise ValueError(
                f"No API key found. Set one of:\n"
                f"  export {self.api_key_env}=<token-from-claude-setup-token>\n"
                f"  export ANTHROPIC_API_KEY=<key-from-console.anthropic.com>"
            )

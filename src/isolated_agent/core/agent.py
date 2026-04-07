"""Agent abstract base class for AI coding agents."""
from abc import ABC, abstractmethod

from isolated_agent.core.models import ShimConfig


class Agent(ABC):
    """Abstract base for AI agent adapters (Claude Code, Codex, etc.)."""

    name: str  # Must be set by subclass

    @abstractmethod
    def launch_command(self, task: str) -> list[str]:
        """Return the CLI command list to launch the agent with the given task."""
        ...

    @abstractmethod
    def get_env_vars(self) -> dict[str, str]:
        """Return environment variables needed by the agent."""
        ...

    @abstractmethod
    def get_required_tools(self) -> list[str]:
        """Return tool names that must be available in the task environment."""
        ...

    @abstractmethod
    def get_shim_config(self) -> ShimConfig:
        """Return the shim configuration for Docker template rendering."""
        ...

    @abstractmethod
    def validate(self) -> None:
        """Validate configuration. Raise ValueError if invalid."""
        ...

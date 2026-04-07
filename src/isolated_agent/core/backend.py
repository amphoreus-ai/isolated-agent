"""Backend abstract base class for isolation environments."""
from __future__ import annotations

from abc import ABC, abstractmethod
from typing import TYPE_CHECKING

from isolated_agent.core.models import BackendConfig, ExecutionResult, Sandbox

if TYPE_CHECKING:
    from isolated_agent.core.agent import Agent


class Backend(ABC):
    """Abstract base for isolation backends (Docker, native, etc.)."""

    def __init__(self, config: BackendConfig | None = None):
        self.config = config or BackendConfig()

    @abstractmethod
    def setup(self, agent: Agent, workspace_path: str) -> Sandbox:
        """Set up the sandbox environment. Returns a Sandbox handle."""
        ...

    @abstractmethod
    def teardown(self, sandbox: Sandbox) -> None:
        """Tear down the sandbox, cleaning up all resources."""
        ...

    @abstractmethod
    def healthcheck(self, sandbox: Sandbox) -> bool:
        """Verify the sandbox is healthy and ready for execution."""
        ...

    @abstractmethod
    def run_agent(self, sandbox: Sandbox, agent: Agent, task: str) -> ExecutionResult:
        """Launch the agent inside the sandbox with the given task. Streams output."""
        ...

    @abstractmethod
    def execute(self, sandbox: Sandbox, command: str) -> ExecutionResult:
        """Execute an arbitrary command inside the sandbox's task environment."""
        ...

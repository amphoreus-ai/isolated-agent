"""isolated-agent: Run AI coding agents in sandboxed Docker environments."""
from isolated_agent.core.session import Session
from isolated_agent.core.agent import Agent
from isolated_agent.core.backend import Backend
from isolated_agent.core.models import (
    AgentConfig,
    BackendConfig,
    ExecutionResult,
    Sandbox,
    SessionResult,
    SessionState,
    ShimConfig,
)
from isolated_agent.core.registry import Registry
from isolated_agent.agents.codex import CodexAgent
from isolated_agent.agents.claude import ClaudeCodeAgent
from isolated_agent.agents.aider import AiderAgent
from isolated_agent.agents.goose import GooseAgent
from isolated_agent.agents.cline import ClineAgent
from isolated_agent.agents.gemini import GeminiAgent
from isolated_agent.agents.amp import AmpAgent
from isolated_agent.agents.opencode import OpenCodeAgent
from isolated_agent.backends.docker.backend import DockerBackend

__version__ = "0.1.0"

__all__ = [
    "Session",
    "Agent",
    "Backend",
    "Registry",
    "CodexAgent",
    "ClaudeCodeAgent",
    "AiderAgent",
    "GooseAgent",
    "ClineAgent",
    "GeminiAgent",
    "AmpAgent",
    "OpenCodeAgent",
    "DockerBackend",
    "AgentConfig",
    "BackendConfig",
    "ExecutionResult",
    "Sandbox",
    "SessionResult",
    "SessionState",
    "ShimConfig",
]

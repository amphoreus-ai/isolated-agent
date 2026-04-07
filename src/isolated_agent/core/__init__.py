"""Core abstractions for isolated-agent."""
from isolated_agent.core.agent import Agent
from isolated_agent.core.backend import Backend
from isolated_agent.core.registry import Registry
from isolated_agent.core.session import Session
from isolated_agent.core.models import (
    AgentConfig,
    BackendConfig,
    ExecutionResult,
    Sandbox,
    SessionResult,
    SessionState,
    ShimConfig,
)

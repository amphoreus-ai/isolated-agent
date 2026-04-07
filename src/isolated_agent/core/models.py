from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from datetime import datetime
from typing import Optional

class SessionState(str, Enum):
    CREATED = "created"
    RUNNING = "running"
    STOPPED = "stopped"
    FAILED = "failed"

@dataclass
class AgentConfig:
    """Configuration for an AI agent."""
    name: str
    api_key_env: str
    base_image: str = "alpine:3.22"
    cli_install_cmd: str = ""
    env_vars: dict[str, str] = field(default_factory=dict)
    required_tools: list[str] = field(default_factory=lambda: ["python3", "node", "git", "npm", "curl", "pip"])
    shim_bwrap: bool = True  # Whether to install bwrap shim
    extra_args: list[str] = field(default_factory=list)

@dataclass
class BackendConfig:
    """Configuration for an isolation backend."""
    task_image: str = "node:20-bookworm-slim"
    extra_tools: list[str] = field(default_factory=list)
    memory_limit: Optional[str] = None
    cpu_limit: Optional[float] = None

@dataclass
class Sandbox:
    """Represents a running sandbox environment."""
    project_name: str
    build_dir: Path
    workspace_path: Path

@dataclass
class ExecutionResult:
    """Result of executing a command in the sandbox."""
    exit_code: int
    stdout: str = ""
    stderr: str = ""

@dataclass
class ShimConfig:
    """Configuration for Docker shim template rendering."""
    base_image: str
    system_packages: str
    cli_install_cmd: str
    tool_symlinks_local: list[str]
    tool_symlinks_usr: list[str]
    env_vars: dict[str, str]
    shim_bwrap: bool
    home_dir: str
    tmp_dir: str
    pkg_manager: str = "apk"  # "apk" for Alpine, "apt" for Debian
    forward_local: list[str] = field(default_factory=list)  # Binaries that run locally (not forwarded)
    auth_mounts: dict[str, str] = field(default_factory=dict)  # host_path -> container_path (read-only)
    run_as_user: str = ""  # Non-empty to create and run as this user (e.g. "agent")


@dataclass
class SessionResult:
    """Result of a completed session."""
    session_id: str
    agent: str
    task: str
    state: SessionState
    exit_code: int
    duration_seconds: float
    log_path: Optional[Path] = None
    error: Optional[str] = None

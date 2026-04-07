"""Session management for isolated agent execution."""
from __future__ import annotations

import time
import uuid
import logging
from pathlib import Path
from typing import TYPE_CHECKING

from isolated_agent.core.models import SessionState, SessionResult

if TYPE_CHECKING:
    from isolated_agent.core.backend import Backend
    from isolated_agent.core.agent import Agent

logger = logging.getLogger(__name__)

LOG_DIR = Path.home() / ".isolated-agent" / "logs"


class SessionError(Exception):
    """Raised when a session operation fails."""
    pass


class Session:
    """Manages the lifecycle of an isolated agent execution.

    Simplified v1: start -> run to completion or failure -> stop.
    No pause/resume.
    """

    def __init__(
        self,
        agent: Agent,
        backend: Backend,
        workspace: str | Path = ".",
    ):
        self.id = f"session-{uuid.uuid4().hex[:8]}"
        self.agent = agent
        self.backend = backend
        self.workspace = Path(workspace).resolve()
        self.state = SessionState.CREATED
        self._sandbox = None
        self._start_time: float | None = None
        self._log_path: Path | None = None

    def _init_log(self) -> Path | None:
        """Create a log file for this session. Returns None if not writable."""
        try:
            LOG_DIR.mkdir(parents=True, exist_ok=True)
            log_path = LOG_DIR / f"{self.id}.log"
            log_path.write_text(
                f"# Session {self.id}\n"
                f"# Agent: {self.agent.name}\n"
                f"# Started: {time.strftime('%Y-%m-%dT%H:%M:%S')}\n\n"
            )
            return log_path
        except OSError:
            logger.debug("Could not create session log (filesystem not writable)")
            return None

    def _append_log(self, msg: str) -> None:
        """Append a message to the session log."""
        if self._log_path:
            with open(self._log_path, "a") as f:
                f.write(msg)

    def run(self, task: str) -> SessionResult:
        """Run the agent with the given task. Blocks until completion.

        Handles the full lifecycle: setup -> healthcheck -> run_agent -> teardown.
        On failure or Ctrl+C, ensures teardown happens.
        """
        if self.state != SessionState.CREATED:
            raise SessionError(f"Cannot run session in state {self.state.value}")

        self._start_time = time.monotonic()
        self._log_path = self._init_log()
        self._append_log(f"Task: {task}\n\n")
        error_msg = None
        exit_code = -1

        try:
            # Setup
            logger.info("Setting up sandbox...")
            self._append_log("[setup] Creating sandbox...\n")
            self.state = SessionState.RUNNING
            self._sandbox = self.backend.setup(self.agent, self.workspace)
            self._append_log("[setup] Sandbox ready.\n")

            # Healthcheck
            logger.info("Running healthcheck...")
            self._append_log("[healthcheck] Verifying connectivity...\n")
            if not self.backend.healthcheck(self._sandbox):
                raise SessionError("Sandbox healthcheck failed")
            self._append_log("[healthcheck] OK.\n")

            # Run agent
            logger.info(f"Launching agent '{self.agent.name}' with task: {task}")
            self._append_log(f"[agent] Launching {self.agent.name}...\n")
            result = self.backend.run_agent(self._sandbox, self.agent, task)
            exit_code = result.exit_code
            self._append_log(f"[agent] Exit code: {exit_code}\n")

            if result.stdout:
                self._append_log(f"[stdout]\n{result.stdout}\n")
            if result.stderr:
                self._append_log(f"[stderr]\n{result.stderr}\n")

            if exit_code == 0:
                self.state = SessionState.STOPPED
            else:
                self.state = SessionState.FAILED
                error_msg = f"Agent exited with code {exit_code}"

        except KeyboardInterrupt:
            logger.info("Session interrupted by user")
            self.state = SessionState.STOPPED
            error_msg = "Interrupted by user"
            self._append_log("[interrupted] User cancelled.\n")

        except Exception as e:
            logger.error(f"Session failed: {e}")
            self.state = SessionState.FAILED
            error_msg = str(e)
            self._append_log(f"[error] {e}\n")

        finally:
            # Always teardown
            if self._sandbox is not None:
                try:
                    logger.info("Tearing down sandbox...")
                    self._append_log("[teardown] Cleaning up...\n")
                    self.backend.teardown(self._sandbox)
                    self._append_log("[teardown] Done.\n")
                except Exception as e:
                    logger.warning(f"Teardown error (non-fatal): {e}")
                    self._append_log(f"[teardown] Error (non-fatal): {e}\n")

        duration = time.monotonic() - self._start_time if self._start_time else 0.0
        self._append_log(f"\n# Duration: {duration:.2f}s\n# Final state: {self.state.value}\n")

        return SessionResult(
            session_id=self.id,
            agent=self.agent.name,
            task=task,
            state=self.state,
            exit_code=exit_code,
            duration_seconds=round(duration, 2),
            log_path=self._log_path,
            error=error_msg,
        )

# isolated-agent

Run any AI coding agent in a sandboxed Docker environment. The agent never knows it's isolated — all execution is transparently forwarded to a separate task container.

Supports **8 agents** out of the box: Claude Code, Codex, Aider, Goose, Cline, Gemini CLI, Amp, OpenCode.

Two backends:
- **`docker`** (default) — both agent and tools run in Docker containers, connected via SSH
- **`local`** — agent runs on your host (using native auth like macOS Keychain), tools forwarded to Docker via `docker exec`

## Install

```bash
pip install -e .
```

## Usage

### CLI

```bash
# Run Claude Code in isolation
isolated-agent run --agent claude "fix the auth bug in login.py"

# Run Codex
isolated-agent run --agent codex "add unit tests for the API"

# Run Aider
isolated-agent run --agent aider "refactor the database layer"

# Any of: claude, codex, aider, goose, cline, gemini, amp, opencode
isolated-agent run --agent <name> "<task>"

# Use local backend — runs your host's agent CLI (no API key needed)
isolated-agent run --agent claude --backend local "fix the auth bug"

# List available agents and backends
isolated-agent agents
isolated-agent backends
```

### Python API

```python
from isolated_agent import Session, DockerBackend, ClaudeCodeAgent

# Docker backend — agent + tools both in containers (needs API key)
session = Session(
    agent=ClaudeCodeAgent(),
    backend=DockerBackend(),
    workspace="./my-project",
)
result = session.run(task="fix the auth bug")
print(f"Exit code: {result.exit_code}, Duration: {result.duration_seconds}s")
```

```python
from isolated_agent import Session, LocalBackend, ClaudeCodeAgent

# Local backend — agent runs on host (uses native auth), tools in container
session = Session(
    agent=ClaudeCodeAgent(),
    backend=LocalBackend(),
    workspace="./my-project",
)
result = session.run(task="fix the auth bug")
```

## How It Works

### Docker Backend (default)

```
┌─────────────────────────────────────────────────┐
│                   Session                        │
│  ┌───────────┐                   ┌────────────┐ │
│  │   Agent    │ ── SSH bridge ──>│  Task Env  │ │
│  │ container  │ <── exit codes ──│ container  │ │
│  │ (Alpine)   │                  │ (Debian)   │ │
│  └───────────┘                   └────────────┘ │
│        │                               │         │
│        └───────── /workspace ──────────┘         │
└─────────────────────────────────────────────────┘
```

1. Docker backend renders templates, generates SSH keys, builds two containers
2. **Agent container** (Alpine) runs the agent CLI with two isolation layers:
   - **Symlinks** — common tools are symlinked to a forwarding script
   - **LD_PRELOAD** — a C library hooks `execve` to catch direct syscalls that bypass symlinks
3. **Task container** (Debian) runs sshd with Python, Node, Git, and all dev tools
4. Every command the agent runs is transparently forwarded to the task container via SSH
5. `/workspace` is the only shared volume

The agent container has **no Docker socket**, **no Docker CLI**, and no way to escape the sandbox.

### Local Backend

```
┌──────────────┐                   ┌────────────────┐
│  Your Host   │                   │  Docker         │
│              │  docker exec      │                 │
│  Agent CLI   │ ───────────────>  │  Task container │
│  (native)    │ <── exit codes ── │  (Debian)       │
│              │                   │                 │
│  PATH shims  │                   │  python3, git,  │
│  python3 ──> │                   │  npm, curl ...  │
│  git ──────> │                   │                 │
└──────────────┘                   └────────────────┘
       │                                  │
       └────────── /workspace ────────────┘
```

1. Starts only a **task container** with dev tools
2. Creates **PATH shims** on the host — lightweight scripts that forward tool calls via `docker exec`
3. Runs the agent CLI **locally** with the shimmed PATH
4. Agent uses its native auth (macOS Keychain, config files) — no API key env var needed
5. Tool execution is isolated in the container; the agent itself runs natively

## Supported Agents

| Agent | CLI | Install | Headless Flag |
|-------|-----|---------|--------------|
| Claude Code | `claude` | npm | `--dangerously-skip-permissions` |
| Codex | `codex` | npm | `--dangerously-bypass-approvals-and-sandbox` |
| Aider | `aider` | pip | `--yes-always --message` |
| Goose | `goose` | binary | `GOOSE_MODE=auto` |
| Cline | `cline` | npm | `-y` |
| Gemini CLI | `gemini` | npm | `--non-interactive` |
| Amp | `amp` | npm | `-x --dangerously-allow-all` |
| OpenCode | `opencode` | npm | `-p` |

## Architecture

### Two-Layer Execution Interception

**Layer 1 — Symlinks (PATH discoverability):** Common tools are symlinked to `task-run`, which forwards via SSH. This makes tools findable by shells doing PATH resolution.

**Layer 2 — LD_PRELOAD (execve interception):** A ~150-line C library (`libexec_forward.so`) hooks `execve` at the libc level. Non-whitelisted binaries are forwarded to task-env via SSH. Catches anything that bypasses the symlink layer.

### Whitelisting

The agent's own CLI binary (e.g., `/usr/local/bin/claude`) and infrastructure binaries (`ssh`, `bash`, `task-run`) execute locally. Everything else is forwarded.

### Template System

Docker artifacts are generated at runtime from `string.Template` files. The shell scripts (`task-run.sh`, `task-shell.sh`, `fake-bwrap.sh`) are agent-agnostic and copied verbatim. Only Dockerfiles, compose config, and entrypoint are templated per agent.

## Adding a Custom Agent

```python
from isolated_agent import Agent, ShimConfig, Session, DockerBackend

class MyAgent(Agent):
    name = "my-agent"

    def __init__(self):
        self.api_key_env = "MY_API_KEY"

    def launch_command(self, task):
        return ["my-agent-cli", "--run", task]

    def get_env_vars(self):
        return {self.api_key_env: f"${{{self.api_key_env}:-}}"}

    def get_required_tools(self):
        return ["python3", "git"]

    def get_shim_config(self):
        return ShimConfig(
            base_image="alpine:3.22",
            system_packages="bash openssh-client nodejs npm",
            cli_install_cmd="npm install -g my-agent-cli",
            tool_symlinks_local=["python3", "git"],
            tool_symlinks_usr=["python3", "git"],
            env_vars={"SHELL": "/usr/local/bin/task-shell",
                      "HOME": "/workspace/.my-agent-home",
                      "TMPDIR": "/workspace/.tmp"},
            shim_bwrap=False,
            home_dir="/workspace/.my-agent-home",
            tmp_dir="/workspace/.tmp",
            forward_local=["/usr/local/bin/my-agent-cli"],
        )

    def validate(self):
        import os
        if not os.environ.get(self.api_key_env):
            raise ValueError(f"{self.api_key_env} not set")

# Use it
session = Session(agent=MyAgent(), backend=DockerBackend(), workspace=".")
result = session.run("do something")
```

## Requirements

- Python 3.11+
- Docker with Compose v2+
- API key for your chosen agent (set as env var) — not needed with `--backend local`

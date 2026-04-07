"""CLI for isolated-agent."""
from __future__ import annotations

import sys
import logging

import click
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

from isolated_agent.core.registry import Registry
from isolated_agent.core.session import Session
from isolated_agent.core.agent import Agent
from isolated_agent.core.backend import Backend
from isolated_agent.core.models import SessionState

# Global registries
agent_registry = Registry[Agent]("agent")
backend_registry = Registry[Backend]("backend")

console = Console()


def _register_builtins() -> None:
    """Register built-in agents and backends."""
    from isolated_agent.agents.codex import CodexAgent
    from isolated_agent.agents.claude import ClaudeCodeAgent
    from isolated_agent.agents.aider import AiderAgent
    from isolated_agent.agents.goose import GooseAgent
    from isolated_agent.agents.cline import ClineAgent
    from isolated_agent.agents.gemini import GeminiAgent
    from isolated_agent.agents.amp import AmpAgent
    from isolated_agent.agents.opencode import OpenCodeAgent
    from isolated_agent.backends.docker.backend import DockerBackend

    agents = [
        ("codex", CodexAgent),
        ("claude", ClaudeCodeAgent),
        ("aider", AiderAgent),
        ("goose", GooseAgent),
        ("cline", ClineAgent),
        ("gemini", GeminiAgent),
        ("amp", AmpAgent),
        ("opencode", OpenCodeAgent),
    ]
    for name, cls in agents:
        try:
            agent_registry.register(name, cls)
        except ValueError:
            pass  # Already registered

    try:
        backend_registry.register("docker", DockerBackend)
    except ValueError:
        pass  # Already registered


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="isolated-agent")
@click.pass_context
def cli(ctx: click.Context) -> None:
    """Run AI coding agents in sandboxed Docker environments."""
    _register_builtins()
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
@click.argument("task")
@click.option("--agent", "-a", required=True, help="Agent to use (e.g., claude, codex)")
@click.option("--backend", "-b", default="docker", help="Backend to use (default: docker)")
@click.option("--workspace", "-w", default=".", help="Workspace directory (default: current dir)")
@click.option("--verbose", "-v", is_flag=True, help="Enable verbose output")
def run(task: str, agent: str, backend: str, workspace: str, verbose: bool) -> None:
    """Run an agent in an isolated sandbox."""
    if verbose:
        logging.basicConfig(level=logging.DEBUG)
    else:
        logging.basicConfig(level=logging.WARNING)

    # Resolve agent class
    try:
        agent_cls = agent_registry.get(agent)
    except KeyError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    # Resolve backend class
    try:
        backend_cls = backend_registry.get(backend)
    except KeyError as exc:
        console.print(f"[red]Error:[/red] {exc}")
        sys.exit(1)

    # Create agent instance and validate configuration (API keys, etc.)
    agent_instance = agent_cls()
    try:
        agent_instance.validate()
    except ValueError as exc:
        console.print(f"[red]Configuration error:[/red] {exc}")
        sys.exit(1)

    # Create backend instance (may fail if Docker is not available)
    try:
        backend_instance = backend_cls()
    except Exception as exc:
        console.print(f"[red]Backend error:[/red] {exc}")
        sys.exit(1)

    # Show session info
    console.print(Panel(
        f"[bold]Agent:[/bold] {agent}\n"
        f"[bold]Backend:[/bold] {backend}\n"
        f"[bold]Workspace:[/bold] {workspace}\n"
        f"[bold]Task:[/bold] {task}",
        title="[bold blue]isolated-agent[/bold blue]",
        border_style="blue",
    ))

    # Create session and run -- session.run() streams output directly to terminal
    session = Session(
        agent=agent_instance,
        backend=backend_instance,
        workspace=workspace,
    )

    result = session.run(task=task)

    # Print result summary
    if result.state == SessionState.STOPPED and result.exit_code == 0:
        console.print(Panel(
            f"[green]Agent completed successfully[/green]\n"
            f"Duration: {result.duration_seconds:.1f}s",
            title="[bold green]Done[/bold green]",
            border_style="green",
        ))
    elif result.state == SessionState.STOPPED:
        # Stopped but non-zero exit (e.g. keyboard interrupt)
        console.print(Panel(
            f"[yellow]Agent stopped[/yellow]\n"
            f"Exit code: {result.exit_code}\n"
            f"Duration: {result.duration_seconds:.1f}s"
            + (f"\n{result.error}" if result.error else ""),
            title="[bold yellow]Stopped[/bold yellow]",
            border_style="yellow",
        ))
    else:
        console.print(Panel(
            f"[red]Agent failed[/red]\n"
            f"Exit code: {result.exit_code}\n"
            f"Duration: {result.duration_seconds:.1f}s"
            + (f"\nError: {result.error}" if result.error else ""),
            title="[bold red]Failed[/bold red]",
            border_style="red",
        ))
        sys.exit(1)


@cli.command("agents")
def list_agents() -> None:
    """List available agents."""
    table = Table(title="Available Agents")
    table.add_column("Name", style="cyan")
    table.add_column("Description")

    descriptions = {
        "codex": "OpenAI Codex CLI",
        "claude": "Anthropic Claude Code CLI",
        "aider": "Aider AI pair programming (Python)",
        "goose": "Block Goose autonomous agent (Rust binary)",
        "cline": "Cline CLI autonomous coding agent",
        "gemini": "Google Gemini CLI coding agent",
        "amp": "Sourcegraph Amp coding agent",
        "opencode": "OpenCode terminal AI coding agent",
    }

    for name in agent_registry.list():
        table.add_row(name, descriptions.get(name, ""))

    console.print(table)


@cli.command("backends")
def list_backends() -> None:
    """List available backends."""
    table = Table(title="Available Backends")
    table.add_column("Name", style="cyan")
    table.add_column("Description")

    descriptions = {
        "docker": "Docker Compose based isolation (two containers + SSH bridge)",
    }

    for name in backend_registry.list():
        table.add_row(name, descriptions.get(name, ""))

    console.print(table)


def main() -> None:
    cli()


if __name__ == "__main__":
    main()

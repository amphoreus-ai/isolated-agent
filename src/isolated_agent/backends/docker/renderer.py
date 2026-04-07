"""Renders Docker templates for agent isolation."""

from dataclasses import dataclass
from pathlib import Path
from string import Template

TEMPLATES_DIR = Path(__file__).parent / "templates"


@dataclass
class TemplateContext:
    """Variables for rendering Docker templates."""

    # Agent Dockerfile
    base_image: str
    system_packages: str
    cli_install_cmd: str
    tool_symlinks_local: str
    tool_symlinks_usr: str
    env_vars: str
    bwrap_setup: str
    # Task Dockerfile
    task_base_image: str
    extra_packages: str
    # Compose
    project_name: str
    api_key_env: str
    workspace_path: str
    memory_limit: str = ""
    cpu_limit: str = ""
    # Entrypoint
    home_dir: str = "/workspace/.agent-home"
    tmp_dir: str = "/workspace/.tmp"


def render_template(template_name: str, context: dict[str, str]) -> str:
    """Render a template file with the given context."""
    template_path = TEMPLATES_DIR / template_name
    template = Template(template_path.read_text())
    return template.safe_substitute(context)


def copy_static_files(dest_dir: Path) -> None:
    """Copy static (non-templated) files to the build directory."""
    static_files = [
        "ssh_config",
        "sh-wrapper.sh",
        "task-run.sh",
        "task-shell.sh",
        "fake-bwrap.sh",
        "exec-in-task.sh",
    ]
    scripts_dir = dest_dir / "scripts"
    scripts_dir.mkdir(parents=True, exist_ok=True)

    for filename in static_files:
        src = TEMPLATES_DIR / filename
        if filename == "ssh_config":
            dst = dest_dir / "ssh_config"
        else:
            dst = scripts_dir / filename
        dst.write_text(src.read_text())
        if filename.endswith(".sh"):
            dst.chmod(0o755)

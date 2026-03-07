"""Utility functions for nanobot."""

import re
from pathlib import Path
from datetime import datetime


def ensure_dir(path: Path) -> Path:
    """Ensure directory exists, return it."""
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_data_path() -> Path:
    """Nanobot data directory. Prefers local workspace if available, else ~/.nanobot."""
    local_config = Path.cwd() / "config.json"
    if local_config.exists():
        # 如果存在本地配置，数据目录默认为当前目录
        return ensure_dir(Path.cwd())
    return ensure_dir(Path.home() / ".nanobot")


def get_workspace_path(workspace: str | None = None) -> Path:
    """Resolve and ensure workspace path. Defaults to ./workspace if local config exists."""
    if workspace:
        path = Path(workspace).expanduser().resolve()
    else:
        local_config = Path.cwd() / "config.json"
        if local_config.exists():
            path = Path.cwd() / "workspace"
        else:
            path = Path.home() / ".nanobot" / "workspace"
    
    return ensure_dir(path)


def timestamp() -> str:
    """Current ISO timestamp."""
    return datetime.now().isoformat()


_UNSAFE_CHARS = re.compile(r'[<>:"/\\|?*]')

def safe_filename(name: str) -> str:
    """Replace unsafe path characters with underscores."""
    return _UNSAFE_CHARS.sub("_", name).strip()


def sync_workspace_templates(workspace: Path, silent: bool = False) -> list[str]:
    """Sync bundled templates to workspace. Only creates missing files."""
    from importlib.resources import files as pkg_files
    try:
        tpl = pkg_files("nanobot") / "templates"
    except Exception:
        return []
    if not tpl.is_dir():
        return []

    added: list[str] = []

    def _write(src, dest: Path):
        if dest.exists():
            return
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(src.read_text(encoding="utf-8") if src else "", encoding="utf-8")
        added.append(str(dest.relative_to(workspace)))

    for item in tpl.iterdir():
        if item.is_file() and item.name.endswith(".md") and item.name != "USER.md":
            _write(item, workspace / item.name)
            
    _write(tpl / "memory" / "guests" / "guest_template.md", workspace / "memory" / "guests" / "guest_template.md")
    _write(tpl / "memory" / "core" / "global.md", workspace / "memory" / "core" / "global.md")
    _write(None, workspace / "memory" / "HISTORY.md")
    (workspace / "skills").mkdir(exist_ok=True)

    if added and not silent:
        from rich.console import Console
        for name in added:
            Console().print(f"  [dim]Created {name}[/dim]")
    return added

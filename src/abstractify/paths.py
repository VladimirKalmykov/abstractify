from __future__ import annotations

from pathlib import Path

DIR_NAME = ".abstractify"
CONFIG_NAME = "config.toml"
DB_NAME = "abstractify.db"


def project_dir(root: Path) -> Path:
    return root / DIR_NAME


def db_path(root: Path) -> Path:
    return project_dir(root) / DB_NAME


def config_path(root: Path) -> Path:
    return project_dir(root) / CONFIG_NAME


def graphs_dir(root: Path) -> Path:
    return project_dir(root) / "graphs"


def snapshots_dir(root: Path) -> Path:
    return project_dir(root) / "snapshots"


def find_project(start: Path | None = None) -> Path:
    """Walk parents looking for `.abstractify/config.toml`."""
    cur = (start or Path.cwd()).resolve()
    for candidate in [cur, *cur.parents]:
        if (candidate / DIR_NAME / CONFIG_NAME).is_file():
            return candidate
    raise FileNotFoundError(
        "No Abstractify project found. Run `abstractify init` in the project root."
    )

"""Abstractify: agent-written abstraction graphs over a project."""

__version__ = "0.1.2"

from abstractify.paths import find_project, project_dir
from abstractify.store import Store

__all__ = ["__version__", "Store", "find_project", "project_dir"]

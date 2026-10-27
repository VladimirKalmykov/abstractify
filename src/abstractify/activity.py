from __future__ import annotations

from pathlib import Path

from abstractify.paths import project_dir

IDLE_SECONDS = 3600
ACTIVITY_NAME = "last_request"


def activity_path(root: Path) -> Path:
    return project_dir(root) / ACTIVITY_NAME


def touch_activity(root: Path) -> None:
    path = activity_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def last_activity(root: Path) -> float:
    path = activity_path(root)
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


class ActivityASGI:
    """Mark last HTTP request time for idle shutdown."""

    def __init__(self, app, root: Path) -> None:
        self.app = app
        self.root = root

    async def __call__(self, scope, receive, send):
        if scope.get("type") == "http":
            touch_activity(self.root)
        await self.app(scope, receive, send)

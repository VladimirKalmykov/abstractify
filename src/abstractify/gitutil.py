from __future__ import annotations

import subprocess
from pathlib import Path


def git_changed_files(root: Path) -> list[str]:
    """Files git reports as modified, staged, or untracked (excluding .abstractify)."""
    try:
        proc = subprocess.run(
            ["git", "status", "--porcelain", "-uall"],
            cwd=root,
            check=True,
            capture_output=True,
            text=True,
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    files: list[str] = []
    for line in proc.stdout.splitlines():
        if len(line) < 4:
            continue
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        path = path.strip().strip('"')
        if path.startswith(".abstractify/") or path == ".abstractify":
            continue
        files.append(path)
    return files

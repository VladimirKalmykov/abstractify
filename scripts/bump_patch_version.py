"""Bump the Abstractify patch version and keep the two copies in sync.

There is no CI, release workflow, or build script in this repo. The git
pre-commit hook runs this once per ordinary commit and stages the result, so
the bump is part of that commit.

pyproject.toml is the package version. src/abstractify/__init__.py repeats it
as __version__ so `abstractify version` matches an editable install without a
reinstall. Both must already be the same X.Y.Z before a bump.

Skip the bump for merge, cherry-pick, and rebase, or set
ABSTRACTIFY_SKIP_VERSION_BUMP=1. A commit that only stages these two version
files is left unchanged.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

PYPROJECT = Path("pyproject.toml")
INIT = Path("src/abstractify/__init__.py")
VERSION_PATHS = {PYPROJECT.as_posix(), INIT.as_posix()}

_PYPROJECT = re.compile(
    r"""^(?P<prefix>version\s*=\s*["'])(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?P<suffix>["'])""",
    re.M,
)
_INIT = re.compile(
    r"""^(?P<prefix>__version__\s*=\s*["'])(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)(?P<suffix>["'])""",
    re.M,
)


def next_patch(version: str) -> str:
    major, minor, patch = _split(version)
    return f"{major}.{minor}.{patch + 1}"


def _split(version: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", version)
    if match is None:
        raise ValueError(f"version must be X.Y.Z, got {version!r}")
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


def _read_version(text: str, pattern: re.Pattern[str], label: str) -> str:
    found = pattern.findall(text)
    if len(found) != 1:
        raise ValueError(f"{label} must contain exactly one X.Y.Z version")
    match = pattern.search(text)
    assert match is not None
    return f"{match.group('major')}.{match.group('minor')}.{match.group('patch')}"


def _write_version(text: str, pattern: re.Pattern[str], version: str) -> str:
    def replace(match: re.Match[str]) -> str:
        return f"{match.group('prefix')}{version}{match.group('suffix')}"

    updated, count = pattern.subn(replace, text, count=1)
    if count != 1:
        raise ValueError("version field was not updated")
    return updated


def _read(path: Path) -> str:
    with path.open(encoding="utf-8", newline="") as handle:
        return handle.read()


def _write(path: Path, text: str) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def apply_bump(root: Path) -> str:
    py_path = root / PYPROJECT
    init_path = root / INIT
    py_text = _read(py_path)
    init_text = _read(init_path)
    py_version = _read_version(py_text, _PYPROJECT, "pyproject.toml")
    init_version = _read_version(init_text, _INIT, "src/abstractify/__init__.py")
    if py_version != init_version:
        raise ValueError(
            f"version mismatch: pyproject.toml is {py_version}, __version__ is {init_version}"
        )
    updated = next_patch(py_version)
    _write(py_path, _write_version(py_text, _PYPROJECT, updated))
    _write(init_path, _write_version(init_text, _INIT, updated))
    return updated


def _skip_requested() -> bool:
    return os.environ.get("ABSTRACTIFY_SKIP_VERSION_BUMP", "").strip().lower() in {
        "1",
        "true",
        "yes",
    }


def _git(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", *args],
        cwd=root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout


def _in_special_git_state(root: Path) -> bool:
    for name in ("MERGE_HEAD", "CHERRY_PICK_HEAD", "REBASE_HEAD"):
        path = Path(_git(root, "rev-parse", "--git-path", name).strip())
        if not path.is_absolute():
            path = root / path
        if path.is_file():
            return True
    return False


def staged_paths(root: Path) -> list[str]:
    raw = _git(root, "diff", "--cached", "--name-only", "-z")
    return [item.replace("\\", "/") for item in raw.split("\0") if item]


def bump_for_commit(root: Path) -> str | None:
    if _skip_requested() or _in_special_git_state(root):
        return None
    staged = staged_paths(root)
    if not staged or set(staged) <= VERSION_PATHS:
        return None
    updated = apply_bump(root)
    _git(root, "add", "--", PYPROJECT.as_posix(), INIT.as_posix())
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Bump the Abstractify patch version.")
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument(
        "--git",
        action="store_true",
        help="Bump only during an ordinary commit and stage the version files",
    )
    args = parser.parse_args(argv)
    root = args.root.resolve()
    try:
        updated = bump_for_commit(root) if args.git else apply_bump(root)
    except (ValueError, subprocess.CalledProcessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    if updated:
        print(updated)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

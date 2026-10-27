from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.bump_patch_version import apply_bump, bump_for_commit, next_patch


def _tree(root: Path, version: str = "0.1.0") -> None:
    (root / "src" / "abstractify").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "abstractify"\nversion = "{version}"\n',
        encoding="utf-8",
    )
    (root / "src" / "abstractify" / "__init__.py").write_text(
        f'__version__ = "{version}"\n',
        encoding="utf-8",
    )


def test_next_patch_increments_only_the_last_number() -> None:
    assert next_patch("0.1.0") == "0.1.1"
    assert next_patch("1.2.9") == "1.2.10"


def test_apply_bump_updates_both_copies(tmp_path: Path) -> None:
    _tree(tmp_path)
    assert apply_bump(tmp_path) == "0.1.1"
    assert 'version = "0.1.1"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    init = (tmp_path / "src" / "abstractify" / "__init__.py").read_text(encoding="utf-8")
    assert '__version__ = "0.1.1"' in init


def test_apply_bump_refuses_mismatched_copies(tmp_path: Path) -> None:
    _tree(tmp_path)
    init = tmp_path / "src" / "abstractify" / "__init__.py"
    init.write_text('__version__ = "0.1.4"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="version mismatch"):
        apply_bump(tmp_path)


def test_git_commit_hook_bumps_and_stages(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    _tree(tmp_path)
    (tmp_path / "README.md").write_text("change\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=tmp_path, check=True, capture_output=True)
    assert bump_for_commit(tmp_path) == "0.1.1"
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines()
    assert "pyproject.toml" in staged
    assert "src/abstractify/__init__.py" in staged


def test_git_hook_skips_version_only_commit(tmp_path: Path) -> None:
    subprocess.run(["git", "init"], cwd=tmp_path, check=True, capture_output=True)
    _tree(tmp_path, "0.1.3")
    subprocess.run(
        ["git", "add", "pyproject.toml", "src/abstractify/__init__.py"],
        cwd=tmp_path,
        check=True,
        capture_output=True,
    )
    assert bump_for_commit(tmp_path) is None
    assert 'version = "0.1.3"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")

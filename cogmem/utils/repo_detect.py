"""Repository and workspace detection utilities."""

from __future__ import annotations

from pathlib import Path
from typing import Optional


def find_repo_root(path: str | Path | None = None) -> Optional[Path]:
    """Walk up from path looking for .git/ directory."""
    current = Path(path or Path.cwd()).resolve()
    for _ in range(50):
        if (current / ".git").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return None


def find_workspace(path: str | Path | None = None) -> Optional[Path]:
    """Walk up from path looking for .cogmem/ directory or multi-repo parent."""
    current = Path(path or Path.cwd()).resolve()

    # First: look for explicit .cogmem/
    check = current
    for _ in range(20):
        if (check / ".cogmem").is_dir():
            return check
        parent = check.parent
        if parent == check:
            break
        check = parent

    # Second: check if parent of current repo has multiple repo siblings
    repo_root = find_repo_root(path)
    if repo_root:
        parent = repo_root.parent
        git_children = [d for d in parent.iterdir()
                        if d.is_dir() and (d / ".git").is_dir()]
        if len(git_children) >= 2:
            return parent

    return None


def detect_repos_in_dir(path: str | Path) -> list[Path]:
    """Find all immediate child directories containing .git/."""
    path = Path(path)
    repos = []
    if not path.is_dir():
        return repos
    for child in sorted(path.iterdir()):
        if child.is_dir() and (child / ".git").is_dir():
            repos.append(child)
    return repos


def detect_repo_for_file(file_path: str | Path) -> Optional[Path]:
    """Find which repo a file belongs to."""
    return find_repo_root(Path(file_path).parent)


def find_project_root(path: str | Path | None = None) -> Path:
    """Find repo root, or fall back to cwd if .memory/ exists, or just cwd."""
    path = Path(path or Path.cwd()).resolve()
    repo = find_repo_root(path)
    if repo:
        return repo
    # Walk up looking for .memory/
    current = path
    for _ in range(20):
        if (current / ".memory").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent
    return path

"""Memory export and import."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

from cogmem.tiers.repo import RepoTier
from cogmem.utils.repo_detect import find_project_root


def export_memory(output_path: str, cwd: str | None = None) -> None:
    """Export repo memory directory to a tarball or directory."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)

    repo = RepoTier(repo_root)
    if not repo.exists:
        raise RuntimeError("Repo memory not initialized.")

    output = Path(output_path)
    if output.suffix in (".tar", ".gz", ".tgz", ".tar.gz"):
        import tarfile
        with tarfile.open(str(output), "w:gz") as tar:
            tar.add(str(repo.dir.root), arcname=".memory")
    else:
        # Copy directory
        if output.exists():
            shutil.rmtree(output)
        shutil.copytree(str(repo.dir.root), str(output))


def import_memory(input_path: str, cwd: str | None = None) -> None:
    """Import memory from a tarball or directory."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)

    input_p = Path(input_path)
    target = repo_root / ".memory"

    if input_p.suffix in (".tar", ".gz", ".tgz", ".tar.gz"):
        import tarfile
        with tarfile.open(str(input_p), "r:*") as tar:
            tar.extractall(str(repo_root))
    elif input_p.is_dir():
        if target.exists():
            shutil.rmtree(target)
        shutil.copytree(str(input_p), str(target))
    else:
        raise RuntimeError(f"Unsupported import format: {input_path}")

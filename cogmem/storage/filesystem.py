"""File-based storage for memory directories."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import frontmatter


REPO_SUBDIRS = ["episodes", "gist", "patterns", "entities", "prospective", "sessions"]
WORKSPACE_SUBDIRS = ["gist", "episodes", "patterns", "prospective"]


class MemoryDir:
    """Manages a .memory/ or .cogmem/ directory."""

    def __init__(self, root: Path):
        self.root = root

    @property
    def exists(self) -> bool:
        return self.root.is_dir()

    def ensure_dirs(self, subdirs: list[str] | None = None) -> None:
        self.root.mkdir(parents=True, exist_ok=True)
        for sub in (subdirs or REPO_SUBDIRS):
            (self.root / sub).mkdir(exist_ok=True)

    # --- Markdown with frontmatter ---

    def read_markdown(self, relpath: str) -> tuple[dict[str, Any], str]:
        path = self.root / relpath
        if not path.exists():
            return {}, ""
        post = frontmatter.load(str(path))
        return dict(post.metadata), post.content

    def write_markdown(self, relpath: str, metadata: dict[str, Any], body: str) -> Path:
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        post = frontmatter.Post(body, **metadata)
        with open(path, "w") as f:
            f.write(frontmatter.dumps(post))
        return path

    # --- JSON ---

    def read_json(self, relpath: str) -> dict[str, Any]:
        path = self.root / relpath
        if not path.exists():
            return {}
        with open(path) as f:
            return json.load(f)

    def write_json(self, relpath: str, data: Any) -> Path:
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=str)
        return path

    # --- Plain text ---

    def read_text(self, relpath: str) -> str:
        path = self.root / relpath
        if not path.exists():
            return ""
        return path.read_text()

    def write_text(self, relpath: str, content: str) -> Path:
        path = self.root / relpath
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        return path

    # --- File listing ---

    def list_files(self, subdir: str, pattern: str = "*.md") -> list[Path]:
        d = self.root / subdir
        if not d.is_dir():
            return []
        return sorted(d.glob(pattern))

    def delete_file(self, relpath: str) -> bool:
        path = self.root / relpath
        if path.exists():
            path.unlink()
            return True
        return False

    def file_exists(self, relpath: str) -> bool:
        return (self.root / relpath).exists()

    def resolve(self, relpath: str) -> Path:
        return self.root / relpath

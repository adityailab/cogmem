"""Workspace-level memory operations — <workspace>/.cogmem/"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cogmem.models import (
    EmotionsFile,
    EmotionTag,
    Episode,
    Gist,
    Pattern,
    Prospective,
    Tier,
    WorkspaceSpatial,
)
from cogmem.storage.filesystem import WORKSPACE_SUBDIRS, MemoryDir
from cogmem.storage.index import KeywordIndex


class WorkspaceTier:
    """Operations on a workspace's .cogmem/ directory."""

    def __init__(self, workspace_path: str | Path):
        self.root = Path(workspace_path)
        self.dir = MemoryDir(self.root / ".cogmem")

    @property
    def exists(self) -> bool:
        return self.dir.exists

    @classmethod
    def init_here(cls) -> "WorkspaceTier":
        ws = cls(Path.cwd())
        ws.init()
        return ws

    @classmethod
    def from_cwd(cls) -> "WorkspaceTier":
        ws_path = detect_workspace(Path.cwd())
        if not ws_path:
            raise click.ClickException("No workspace found. Run `cogmem workspace init` first.")
        return cls(ws_path)

    def init(self) -> None:
        self.dir.ensure_dirs(WORKSPACE_SUBDIRS)
        if not self.dir.file_exists("meta.json"):
            self.dir.write_json("meta.json", {
                "version": "3.1",
                "workspace": True,
                "repos": [],
                "created": _today(),
            })
        if not self.dir.file_exists("emotions.md"):
            self.dir.write_text("emotions.md", "# Emotional Memory\n")

    def add_repo(self, path: str) -> None:
        meta = self.dir.read_json("meta.json")
        repos = meta.get("repos", [])
        repo_path = Path(path)
        name = repo_path.name
        if not any(r.get("name") == name for r in repos):
            repos.append({"name": name, "path": str(path)})
            meta["repos"] = repos
            self.dir.write_json("meta.json", meta)

    def list_repos(self) -> list[dict]:
        meta = self.dir.read_json("meta.json")
        return meta.get("repos", [])

    # --- Episodes ---

    def save_episode(self, ep: Episode) -> None:
        ep.tier = Tier.WORKSPACE
        ep.save(str(self.dir.resolve(f"episodes/{ep.filename}")))

    def list_episodes(self) -> list[Episode]:
        episodes = []
        for f in self.dir.list_files("episodes"):
            try:
                episodes.append(Episode.from_file(str(f)))
            except Exception:
                continue
        return episodes

    # --- Gists ---

    def save_gist(self, gist: Gist) -> None:
        gist.tier = Tier.WORKSPACE
        gist.save(str(self.dir.resolve(f"gist/{gist.filename}")))

    def list_gists(self) -> list[Gist]:
        gists = []
        for f in self.dir.list_files("gist"):
            try:
                gists.append(Gist.from_file(str(f)))
            except Exception:
                continue
        return gists

    def get_platform_gist(self) -> Optional[Gist]:
        path = self.dir.resolve("gist/_platform.md")
        if path.exists():
            return Gist.from_file(str(path))
        return None

    # --- Patterns ---

    def save_pattern(self, pattern: Pattern) -> None:
        pattern.tier = Tier.WORKSPACE
        pattern.save(str(self.dir.resolve(f"patterns/{pattern.filename}")))

    def list_patterns(self) -> list[Pattern]:
        patterns = []
        for f in self.dir.list_files("patterns"):
            try:
                patterns.append(Pattern.from_file(str(f)))
            except Exception:
                continue
        return patterns

    # --- Emotions ---

    def get_emotions(self) -> EmotionsFile:
        path = self.dir.resolve("emotions.md")
        if path.exists():
            return EmotionsFile.from_markdown(path.read_text())
        return EmotionsFile()

    def update_emotion(self, tag: EmotionTag) -> None:
        emotions = self.get_emotions()
        emotions.upsert(tag)
        self.dir.write_text("emotions.md", emotions.to_markdown())

    # --- Spatial ---

    def get_spatial(self) -> Optional[WorkspaceSpatial]:
        text = self.dir.read_text("spatial.md")
        if not text:
            return None
        # Simple parse — workspace spatial is hand-written markdown
        return WorkspaceSpatial(body=text)

    def update_spatial(self, spatial: WorkspaceSpatial) -> None:
        self.dir.write_text("spatial.md", spatial.to_markdown())

    # --- Prospective ---

    def save_prospective(self, p: Prospective) -> None:
        p.tier = Tier.WORKSPACE
        p.save(str(self.dir.resolve(f"prospective/{p.filename}")))

    def list_prospectives(self) -> list[Prospective]:
        items = []
        for f in self.dir.list_files("prospective"):
            try:
                items.append(Prospective.from_file(str(f)))
            except Exception:
                continue
        return items

    # --- Index ---

    def get_index(self) -> KeywordIndex:
        return KeywordIndex.load(self.dir.resolve("keyword_index.json"))

    def save_index(self, index: KeywordIndex) -> None:
        index.save(self.dir.resolve("keyword_index.json"))

    # --- Status ---

    def status(self) -> dict:
        return {
            "workspace": str(self.root),
            "initialized": self.exists,
            "repos": len(self.list_repos()),
            "episodes": len(self.dir.list_files("episodes")),
            "gists": len(self.dir.list_files("gist")),
            "patterns": len(self.dir.list_files("patterns")),
            "emotions": len(self.get_emotions().tags),
        }


def detect_workspace(path: Path) -> Optional[Path]:
    """Walk up from path looking for .cogmem/ directory."""
    current = path.resolve()
    for _ in range(20):
        if (current / ".cogmem").is_dir():
            return current
        parent = current.parent
        if parent == current:
            break
        current = parent

    # Also check: if current dir has multiple child .git/ dirs, it's a workspace
    path = path.resolve()
    git_children = [d for d in path.iterdir() if d.is_dir() and (d / ".git").is_dir()]
    if len(git_children) >= 2:
        return path

    return None


def _today() -> str:
    from datetime import date
    return date.today().isoformat()


# Avoid circular import — lazy import click only when needed
try:
    import click
except ImportError:
    pass

"""Repo-level memory operations — <repo>/.memory/"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cogmem.models import (
    CodeEntity,
    EmotionsFile,
    EmotionTag,
    Episode,
    Gist,
    Pattern,
    Prospective,
    RepoSpatial,
)
from cogmem.storage.filesystem import REPO_SUBDIRS, MemoryDir
from cogmem.storage.index import KeywordIndex


class RepoTier:
    """Operations on a single repo's .memory/ directory."""

    def __init__(self, repo_path: str | Path):
        self.repo_path = Path(repo_path)
        self.dir = MemoryDir(self.repo_path / ".memory")

    @property
    def exists(self) -> bool:
        return self.dir.exists

    def init(self) -> None:
        self.dir.ensure_dirs(REPO_SUBDIRS)
        if not self.dir.file_exists("meta.json"):
            self.dir.write_json("meta.json", {
                "version": "3.1",
                "repo": str(self.repo_path.name),
                "created": _today(),
            })
        if not self.dir.file_exists("emotions.md"):
            EmotionsFile().save(str(self.dir.resolve("emotions.md")))

    # --- Episodes ---

    def save_episode(self, ep: Episode) -> Path:
        return Path(ep.save(str(self.dir.resolve(f"episodes/{ep.filename}"))) or
                     self.dir.resolve(f"episodes/{ep.filename}"))

    def list_episodes(self) -> list[Episode]:
        episodes = []
        for f in self.dir.list_files("episodes"):
            try:
                episodes.append(Episode.from_file(str(f)))
            except Exception:
                continue
        return episodes

    def load_episode(self, filename: str) -> Optional[Episode]:
        path = self.dir.resolve(f"episodes/{filename}")
        if path.exists():
            return Episode.from_file(str(path))
        return None

    # --- Gists ---

    def save_gist(self, gist: Gist) -> None:
        gist.save(str(self.dir.resolve(f"gist/{gist.filename}")))

    def list_gists(self) -> list[Gist]:
        gists = []
        for f in self.dir.list_files("gist"):
            try:
                gists.append(Gist.from_file(str(f)))
            except Exception:
                continue
        return gists

    def load_gist(self, filename: str) -> Optional[Gist]:
        path = self.dir.resolve(f"gist/{filename}")
        if path.exists():
            return Gist.from_file(str(path))
        return None

    def get_codebase_gist(self) -> Optional[Gist]:
        return self.load_gist("_codebase.md")

    # --- Patterns ---

    def save_pattern(self, pattern: Pattern) -> None:
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

    def get_spatial(self) -> Optional[RepoSpatial]:
        path = self.dir.resolve("spatial.md")
        if path.exists():
            return RepoSpatial.from_markdown(path.read_text())
        return None

    def update_spatial(self, spatial: RepoSpatial) -> None:
        self.dir.write_text("spatial.md", spatial.to_markdown())

    # --- Prospective ---

    def save_prospective(self, p: Prospective) -> None:
        p.save(str(self.dir.resolve(f"prospective/{p.filename}")))

    def list_prospectives(self) -> list[Prospective]:
        items = []
        for f in self.dir.list_files("prospective"):
            try:
                items.append(Prospective.from_file(str(f)))
            except Exception:
                continue
        return items

    # --- Entities ---

    def save_entity(self, entity: CodeEntity) -> None:
        entity.save(str(self.dir.resolve(f"entities/{entity.filename}")))

    def list_entities(self) -> list[CodeEntity]:
        entities = []
        for f in self.dir.list_files("entities"):
            try:
                entities.append(CodeEntity.from_file(str(f)))
            except Exception:
                continue
        return entities

    # --- Index ---

    def get_index(self) -> KeywordIndex:
        return KeywordIndex.load(self.dir.resolve("keyword_index.json"))

    def save_index(self, index: KeywordIndex) -> None:
        index.save(self.dir.resolve("keyword_index.json"))

    # --- Meta ---

    def get_meta(self) -> dict:
        return self.dir.read_json("meta.json")

    def update_meta(self, data: dict) -> None:
        meta = self.get_meta()
        meta.update(data)
        self.dir.write_json("meta.json", meta)

    # --- Status ---

    def status(self) -> dict:
        return {
            "repo": self.repo_path.name,
            "initialized": self.exists,
            "episodes": len(self.dir.list_files("episodes")),
            "gists": len(self.dir.list_files("gist")),
            "patterns": len(self.dir.list_files("patterns")),
            "entities": len(self.dir.list_files("entities")),
            "prospectives": len(self.dir.list_files("prospective")),
            "emotions": len(self.get_emotions().tags),
            "index_keywords": len(self.get_index()),
        }


def _today() -> str:
    from datetime import date
    return date.today().isoformat()

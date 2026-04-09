"""Global-level memory operations — ~/.cognitive-memory/"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from cogmem.models import Pattern, Tier
from cogmem.storage.filesystem import MemoryDir


GLOBAL_DIR = Path.home() / ".cognitive-memory"


class GlobalTier:
    """Operations on the global ~/.cognitive-memory/ directory."""

    def __init__(self, root: Path | None = None):
        self.root = root or GLOBAL_DIR
        self.dir = MemoryDir(self.root)

    @property
    def exists(self) -> bool:
        return self.dir.exists

    def init(self) -> None:
        self.dir.root.mkdir(parents=True, exist_ok=True)
        (self.dir.root / "patterns").mkdir(exist_ok=True)
        if not self.dir.file_exists("preferences.json"):
            self.dir.write_json("preferences.json", {
                "transfer_patterns": True,
                "auto_import_on_bootstrap": True,
            })

    # --- Patterns ---

    def save_pattern(self, pattern: Pattern) -> None:
        pattern.tier = Tier.GLOBAL
        pattern.save(str(self.dir.resolve(f"patterns/{pattern.filename}")))

    def list_patterns(self) -> list[Pattern]:
        patterns = []
        for f in self.dir.list_files("patterns"):
            try:
                patterns.append(Pattern.from_file(str(f)))
            except Exception:
                continue
        return patterns

    def has_pattern(self, name: str) -> bool:
        slug = name.lower().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        return self.dir.file_exists(f"patterns/{slug}.md")

    # --- Preferences ---

    def get_preferences(self) -> dict:
        return self.dir.read_json("preferences.json")

    def update_preferences(self, data: dict) -> None:
        prefs = self.get_preferences()
        prefs.update(data)
        self.dir.write_json("preferences.json", prefs)

    # --- Status ---

    def status(self) -> dict:
        return {
            "global_dir": str(self.root),
            "initialized": self.exists,
            "patterns": len(self.dir.list_files("patterns")),
        }

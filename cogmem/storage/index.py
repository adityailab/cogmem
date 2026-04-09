"""Keyword inverted index for fast memory retrieval."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any


class KeywordIndex:
    """Pre-built inverted index mapping keywords to memory file references."""

    def __init__(self, data: dict[str, list[str]] | None = None):
        self._index: dict[str, list[str]] = data or {}

    @classmethod
    def load(cls, path: str | Path) -> "KeywordIndex":
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path) as f:
            return cls(json.load(f))

    def save(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self._index, f, indent=2)

    def add_entry(self, keywords: list[str], file_ref: str) -> None:
        for kw in keywords:
            kw = kw.lower().strip()
            if not kw:
                continue
            if kw not in self._index:
                self._index[kw] = []
            if file_ref not in self._index[kw]:
                self._index[kw].append(file_ref)

    def remove_entry(self, file_ref: str) -> None:
        for kw in list(self._index):
            if file_ref in self._index[kw]:
                self._index[kw].remove(file_ref)
                if not self._index[kw]:
                    del self._index[kw]

    def query(self, keywords: list[str]) -> list[tuple[str, int]]:
        """Return file refs sorted by number of matching keywords."""
        counts: dict[str, int] = {}
        for kw in keywords:
            kw = kw.lower().strip()
            for file_ref in self._index.get(kw, []):
                counts[file_ref] = counts.get(file_ref, 0) + 1
        return sorted(counts.items(), key=lambda x: x[1], reverse=True)

    def all_refs(self) -> set[str]:
        refs: set[str] = set()
        for file_list in self._index.values():
            refs.update(file_list)
        return refs

    @property
    def keywords(self) -> list[str]:
        return list(self._index.keys())

    def __len__(self) -> int:
        return len(self._index)


def extract_keywords(text: str) -> list[str]:
    """Extract meaningful keywords from text for indexing."""
    # Lowercase, split on non-alphanumeric
    words = re.findall(r"[a-z][a-z0-9_]+", text.lower())
    # Filter stop words and very short words
    stop = {"the", "and", "for", "was", "with", "this", "that", "from", "are",
            "but", "not", "have", "has", "had", "will", "been", "were", "they",
            "their", "what", "when", "which", "who", "how", "all", "can",
            "her", "his", "its", "our", "than", "then", "them", "these",
            "some", "could", "other", "into", "more", "also", "any", "only"}
    return [w for w in words if len(w) > 2 and w not in stop]

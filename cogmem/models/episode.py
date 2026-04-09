"""Episodic memory — what happened."""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional
from uuid import uuid4

from pydantic import Field

from cogmem.models.common import (
    EmotionType,
    EpisodeSource,
    MemoryBase,
    Phase,
    Tier,
)


class Episode(MemoryBase):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    date: str = ""  # YYYY-MM-DD
    when: str = ""  # fuzzy: "last Tuesday"
    tier: str = Tier.REPO

    trigger: str = ""
    story: str = ""
    learned: str = ""
    body: str = ""  # full narrative for markdown body

    emotion: str = EmotionType.NEUTRAL
    intensity: float = 0.5

    code_touched: list[str] = Field(default_factory=list)
    repos_involved: Optional[list[str]] = None  # workspace episodes only
    people_involved: list[str] = Field(default_factory=list)
    related_episodes: list[str] = Field(default_factory=list)
    related_patterns: list[str] = Field(default_factory=list)
    triggered_prospective: list[str] = Field(default_factory=list)

    source: str = EpisodeSource.LIVED
    source_confidence: float = 1.0

    strength: float = 1.0
    access_count: int = 0
    last_accessed: Optional[str] = None
    phase: str = Phase.VIVID

    def phase_for_age(self, days: int) -> str:
        if days < 7:
            return Phase.VIVID
        elif days < 30:
            return Phase.CLEAR
        elif days < 90:
            return Phase.FUZZY
        elif days < 180:
            return Phase.FADING
        return Phase.STUB

    def compress(self, level: str) -> str:
        """Return compressed version of the narrative."""
        if level == "full":
            return self.story
        elif level == "summary":
            # Keep first sentence + learned
            first_sentence = self.story.split(". ")[0] + "." if self.story else ""
            return f"{first_sentence} Learned: {self.learned}" if self.learned else first_sentence
        else:  # stub
            return self.learned or self.trigger or self.story[:60]

    def to_markdown(self) -> str:
        self.body = self._build_body()
        return super().to_markdown()

    def _build_body(self) -> str:
        lines = []
        if self.story:
            lines.append(f"## What happened\n{self.story}")
        if self.learned:
            lines.append(f"\n## What I learned\n{self.learned}")
        if self.code_touched:
            lines.append("\n## Code touched")
            for f in self.code_touched:
                lines.append(f"- {f}")
        return "\n".join(lines)

    @property
    def filename(self) -> str:
        slug = self.trigger or self.id
        slug = slug.lower().replace(" ", "-")[:40]
        # Remove non-alphanumeric except hyphens
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        return f"{self.date}_{slug}.md"

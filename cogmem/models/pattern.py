"""Pattern memory — I've seen this before."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import Field

from cogmem.models.common import DangerLevel, MemoryBase, PatternCategory, Tier


class Pattern(MemoryBase):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    name: str = ""
    category: str = PatternCategory.BUG
    tier: str = Tier.REPO

    signature: str = ""    # what it looks like
    consequence: str = ""  # what goes wrong
    response: str = ""     # what to do

    seen_in: list[str] = Field(default_factory=list)
    frequency: int = 1
    last_seen: Optional[str] = None

    trigger_cues: list[str] = Field(default_factory=list)
    related_gists: list[str] = Field(default_factory=list)
    strength: float = 1.0
    danger_level: str = DangerLevel.LOW
    transferable: bool = False
    body: str = ""

    def to_markdown(self) -> str:
        self.body = self._build_body()
        return super().to_markdown()

    def _build_body(self) -> str:
        lines = []
        if self.signature:
            lines.append(f"## Signature\n{self.signature}")
        if self.consequence:
            lines.append(f"\n## Consequence\n{self.consequence}")
        if self.response:
            lines.append(f"\n## Response\n{self.response}")
        if self.seen_in:
            lines.append("\n## Seen in")
            for loc in self.seen_in:
                lines.append(f"- {loc}")
        return "\n".join(lines)

    @property
    def filename(self) -> str:
        slug = self.name.lower().replace(" ", "-")
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        return f"{slug}.md"

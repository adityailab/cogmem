"""Semantic memory / Gist — what I understand."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import Field

from cogmem.models.common import GistScope, Judgment, MemoryBase, Tier


class Gist(MemoryBase):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    scope: str = GistScope.MODULE
    target: str = ""  # what this describes
    tier: str = Tier.REPO

    what_it_does: str = ""
    why_it_exists: str = ""
    how_it_works: str = ""
    key_relationships: str = ""
    judgment: str = Judgment.UNKNOWN

    confidence: float = 0.5
    formed_from: list[str] = Field(default_factory=list)
    contradictions: list[str] = Field(default_factory=list)
    last_updated: Optional[str] = None
    last_verified: Optional[str] = None
    body: str = ""

    def to_markdown(self) -> str:
        self.body = self._build_body()
        return super().to_markdown()

    def _build_body(self) -> str:
        lines = []
        if self.what_it_does:
            lines.append(f"## What it does\n{self.what_it_does}")
        if self.why_it_exists:
            lines.append(f"\n## Why it exists\n{self.why_it_exists}")
        if self.how_it_works:
            lines.append(f"\n## How it works\n{self.how_it_works}")
        if self.key_relationships:
            lines.append(f"\n## Key relationships\n{self.key_relationships}")
        return "\n".join(lines)

    @property
    def filename(self) -> str:
        if self.scope == GistScope.PLATFORM:
            return "_platform.md"
        if self.scope == GistScope.CODEBASE:
            return "_codebase.md"
        slug = self.target.replace("/", "_").replace(" ", "_").lower()
        return f"{slug}.md"

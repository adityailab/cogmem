"""Prospective memory — what to do next time."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import Field

from cogmem.models.common import MemoryBase, Tier


class Prospective(MemoryBase):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    intention: str = ""
    trigger: str = ""         # what activates this
    trigger_type: str = ""    # file_touch | keyword | time
    created_from: str = ""    # episode id
    priority: str = "medium"  # low | medium | high
    completed: bool = False
    tier: str = Tier.REPO
    strength: float = 1.0
    body: str = ""

    def to_markdown(self) -> str:
        self.body = self._build_body()
        return super().to_markdown()

    def _build_body(self) -> str:
        lines = []
        if self.intention:
            lines.append(f"## Intention\n{self.intention}")
        if self.trigger:
            lines.append(f"\n## Trigger\n{self.trigger}")
            if self.trigger_type:
                lines.append(f"Type: {self.trigger_type}")
        return "\n".join(lines)

    @property
    def filename(self) -> str:
        slug = self.intention.lower().replace(" ", "-")[:40]
        slug = "".join(c for c in slug if c.isalnum() or c == "-")
        return f"{slug}.md"

    def matches_context(self, files: list[str], keywords: list[str]) -> bool:
        """Check if current context triggers this prospective memory."""
        if self.completed:
            return False
        if self.trigger_type == "file_touch":
            return any(self.trigger in f for f in files)
        if self.trigger_type == "keyword":
            return any(self.trigger.lower() in kw.lower() for kw in keywords)
        # Default: substring match on trigger
        trigger_lower = self.trigger.lower()
        return any(trigger_lower in f.lower() for f in files) or \
               any(trigger_lower in kw.lower() for kw in keywords)

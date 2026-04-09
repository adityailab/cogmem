"""Code entities — three-zoom level."""

from __future__ import annotations

from typing import Optional
from uuid import uuid4

from pydantic import Field

from cogmem.models.common import MemoryBase


class CodeEntity(MemoryBase):
    id: str = Field(default_factory=lambda: uuid4().hex[:12])
    file_path: str = ""
    name: str = ""
    kind: str = ""  # function | class | method
    signature: str = ""  # ~10 tokens
    summary: str = ""    # ~50 tokens
    # FULL: not stored — Claude reads actual source
    strength: float = 1.0
    body: str = ""

    def to_markdown(self) -> str:
        self.body = self._build_body()
        return super().to_markdown()

    def _build_body(self) -> str:
        lines = []
        if self.signature:
            lines.append(f"```\n{self.signature}\n```")
        if self.summary:
            lines.append(f"\n{self.summary}")
        return "\n".join(lines)

    @property
    def filename(self) -> str:
        slug = f"{self.file_path}_{self.name}".replace("/", "_").replace(".", "_").lower()
        slug = "".join(c for c in slug if c.isalnum() or c == "_")
        return f"{slug}.md"

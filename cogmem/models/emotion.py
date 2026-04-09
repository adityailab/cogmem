"""Emotional memory — how I feel about this code."""

from __future__ import annotations

from typing import Optional

from pydantic import Field

from cogmem.models.common import EmotionType, MemoryBase, RetrievalBias


class EmotionTag(MemoryBase):
    target: str = ""
    emotion: str = EmotionType.NEUTRAL
    intensity: float = 0.5
    reason: str = ""
    source_episodes: list[str] = Field(default_factory=list)
    last_reinforced: Optional[str] = None
    retrieval_bias: str = RetrievalBias.BOOST
    zoom_override: Optional[str] = None  # full | summary | null
    body: str = ""


class EmotionsFile(MemoryBase):
    """Container for all emotion tags in a single emotions.md file."""
    tags: list[EmotionTag] = Field(default_factory=list)
    body: str = ""

    def to_markdown(self) -> str:
        lines = ["# Emotional Memory\n"]
        for tag in self.tags:
            emoji = _emotion_emoji(tag.emotion)
            lines.append(f"## {emoji} {tag.target}")
            lines.append(f"**{tag.emotion.upper()}** (intensity: {tag.intensity})")
            if tag.reason:
                lines.append(f"Reason: {tag.reason}")
            if tag.retrieval_bias != RetrievalBias.BOOST:
                lines.append(f"Bias: {tag.retrieval_bias}")
            lines.append("")
        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, text: str) -> "EmotionsFile":
        tags: list[EmotionTag] = []
        current: dict = {}

        for line in text.split("\n"):
            line = line.strip()
            if line.startswith("## ") and not line.startswith("## #"):
                if current:
                    tags.append(EmotionTag(**current))
                # Parse: ## EMOJI target
                parts = line[3:].strip().split(" ", 1)
                target = parts[-1] if len(parts) > 1 else parts[0]
                current = {"target": target}
            elif line.startswith("**") and current:
                # Parse: **PAIN** (intensity: 0.85)
                try:
                    emotion_str = line.split("**")[1].lower()
                    current["emotion"] = emotion_str
                    if "intensity:" in line:
                        intensity = float(line.split("intensity:")[1].strip().rstrip(")"))
                        current["intensity"] = intensity
                except (IndexError, ValueError):
                    pass
            elif line.startswith("Reason:") and current:
                current["reason"] = line[7:].strip()
            elif line.startswith("Bias:") and current:
                current["retrieval_bias"] = line[5:].strip()

        if current:
            tags.append(EmotionTag(**current))

        return cls(tags=tags)

    def find(self, target: str) -> Optional[EmotionTag]:
        for tag in self.tags:
            if tag.target == target:
                return tag
        return None

    def upsert(self, tag: EmotionTag) -> None:
        for i, existing in enumerate(self.tags):
            if existing.target == tag.target:
                self.tags[i] = tag
                return
        self.tags.append(tag)


def _emotion_emoji(emotion: str) -> str:
    return {
        "pain": "PAIN:",
        "danger": "DANGER:",
        "trust": "TRUST:",
        "pride": "PRIDE:",
        "frustration": "FRUSTRATION:",
        "relief": "RELIEF:",
        "curiosity": "CURIOSITY:",
        "neutral": "",
    }.get(emotion, "")

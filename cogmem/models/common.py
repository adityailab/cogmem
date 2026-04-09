"""Shared enums, base model, and constants."""

from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any

import frontmatter
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    SPATIAL = "spatial"
    PATTERN = "pattern"
    EMOTIONAL = "emotional"
    PROSPECTIVE = "prospective"
    ENTITY = "entity"


class Tier(str, Enum):
    REPO = "repo"
    WORKSPACE = "workspace"
    GLOBAL = "global"


class Phase(str, Enum):
    VIVID = "vivid"      # < 7 days
    CLEAR = "clear"      # 7-30 days
    FUZZY = "fuzzy"      # 30-90 days
    FADING = "fading"    # 90-180 days
    STUB = "stub"        # > 180 days


class EmotionType(str, Enum):
    PAIN = "pain"
    DANGER = "danger"
    TRUST = "trust"
    PRIDE = "pride"
    FRUSTRATION = "frustration"
    RELIEF = "relief"
    CURIOSITY = "curiosity"
    NEUTRAL = "neutral"


class DangerLevel(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TaskType(str, Enum):
    BUGFIX = "bugfix"
    FEATURE = "feature"
    REFACTOR = "refactor"
    UNDERSTAND = "understand"
    PLAN = "plan"
    EXPLORE = "explore"
    CROSS_REPO = "cross_repo"


class RetrievalBias(str, Enum):
    BOOST = "boost"
    DEMOTE = "demote"
    WARN = "warn"


class GistScope(str, Enum):
    PLATFORM = "platform"
    CODEBASE = "codebase"
    MODULE = "module"
    COMPONENT = "component"


class PatternCategory(str, Enum):
    BUG = "bug"
    DESIGN = "design"
    ANTI = "anti"
    SMELL = "smell"
    CROSS_REPO = "cross_repo"


class EpisodeSource(str, Enum):
    LIVED = "lived"
    GIT_INFERRED = "git-inferred"
    AUTO_GENERATED = "auto-generated"


class Judgment(str, Enum):
    FRAGILE = "fragile"
    SOLID = "solid"
    IMPROVING = "improving"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Base model with markdown serialization
# ---------------------------------------------------------------------------

class MemoryBase(BaseModel):
    """Base for all memory models with markdown frontmatter serialization."""

    model_config = {"use_enum_values": True}

    def to_markdown(self) -> str:
        data = self.model_dump(exclude_none=True, mode="json")
        body = data.pop("body", "")
        post = frontmatter.Post(body, **data)
        return frontmatter.dumps(post)

    @classmethod
    def from_markdown(cls, text: str) -> "MemoryBase":
        post = frontmatter.loads(text)
        data = dict(post.metadata)
        data["body"] = post.content
        return cls.model_validate(data)

    @classmethod
    def from_file(cls, path: str) -> "MemoryBase":
        with open(path) as f:
            return cls.from_markdown(f.read())

    def save(self, path: str) -> None:
        from pathlib import Path
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            f.write(self.to_markdown())


# ---------------------------------------------------------------------------
# Budget table (from spec Section 20, Stage 6)
# ---------------------------------------------------------------------------

BUDGET_TABLE: dict[str, dict[str, float]] = {
    "bugfix":     {"episodes": 0.30, "gist": 0.10, "patterns": 0.15, "dangers": 0.15, "entities": 0.20, "spatial": 0.05, "prospective": 0.05},
    "feature":    {"episodes": 0.10, "gist": 0.25, "patterns": 0.15, "dangers": 0.10, "entities": 0.15, "spatial": 0.15, "prospective": 0.10},
    "refactor":   {"episodes": 0.10, "gist": 0.10, "patterns": 0.15, "dangers": 0.10, "entities": 0.40, "spatial": 0.10, "prospective": 0.05},
    "understand": {"episodes": 0.20, "gist": 0.30, "patterns": 0.05, "dangers": 0.05, "entities": 0.15, "spatial": 0.20, "prospective": 0.05},
    "plan":       {"episodes": 0.15, "gist": 0.35, "patterns": 0.15, "dangers": 0.05, "entities": 0.05, "spatial": 0.15, "prospective": 0.10},
    "explore":    {"episodes": 0.10, "gist": 0.30, "patterns": 0.05, "dangers": 0.05, "entities": 0.05, "spatial": 0.35, "prospective": 0.10},
    "cross_repo": {"episodes": 0.25, "gist": 0.20, "patterns": 0.15, "dangers": 0.15, "entities": 0.05, "spatial": 0.15, "prospective": 0.05},
}

# Decay rates from spec Section 22
DECAY_RATES: dict[str, float] = {
    "episode":      0.05,    # half-life ~14 days
    "gist":         0.005,   # half-life ~140 days
    "pattern":      0.01,    # half-life ~70 days
    "emotion":      0.002,   # half-life ~350 days
    "emotion_pain": 0.001,   # half-life ~700 days
    "spatial":      0.003,   # half-life ~230 days
    "prospective":  0.02,    # half-life ~35 days
}

WORKSPACE_DECAY_MULTIPLIER = 0.7

"""Convergence scoring for memory retrieval — Stage 4."""

from __future__ import annotations

import math
from datetime import date, datetime
from typing import Any, Optional

from cogmem.utils.cues import CueSet


def compute_score(
    memory: dict[str, Any],
    cues: CueSet,
    tier_weight: float = 1.0,
    priming_context: Optional[dict] = None,
) -> float:
    """Compute convergence score for a memory match.

    Formula: keyword_match * convergence * emotional * recency * priming * tier
    """
    keyword_score = _keyword_match(memory, cues)
    convergence = _convergence_multiplier(memory, cues)
    emotional = _emotional_weight(memory, cues)
    recency = _recency_weight(memory)
    priming = _priming_bonus(memory, priming_context)

    score = keyword_score * convergence * emotional * recency * priming * tier_weight
    return round(score, 4)


def _keyword_match(memory: dict, cues: CueSet) -> float:
    """Base score from keyword overlap."""
    if not cues.keywords:
        return 0.5  # neutral if no keywords

    memory_text = _memory_text(memory).lower()
    matches = sum(1 for kw in cues.keywords if kw in memory_text)
    return min(matches / max(len(cues.keywords), 1), 1.0)


def _convergence_multiplier(memory: dict, cues: CueSet) -> float:
    """Multiple cue types converging = higher score."""
    convergence = 1.0
    memory_text = _memory_text(memory).lower()

    # File path match
    if cues.file_paths:
        if any(fp in memory_text for fp in cues.file_paths):
            convergence *= 1.5

    # Entity match
    if cues.entities:
        if any(e.lower() in memory_text for e in cues.entities):
            convergence *= 1.3

    # Emotion match
    if cues.emotions:
        mem_emotion = memory.get("emotion", "")
        if mem_emotion in cues.emotions:
            convergence *= 1.4

    return convergence


def _emotional_weight(memory: dict, cues: CueSet) -> float:
    """Emotional memories get priority."""
    intensity = memory.get("intensity", 0.5)
    emotion = memory.get("emotion", "neutral")

    # Pain and danger memories are boosted
    if emotion in ("pain", "danger"):
        return 1.0 + intensity * 0.5
    # If query has emotional cues matching memory
    if emotion in (cues.emotions or []):
        return 1.0 + intensity * 0.3
    return 1.0


def _recency_weight(memory: dict) -> float:
    """Recent memories scored higher via exponential decay."""
    last_accessed = memory.get("last_accessed") or memory.get("date")
    if not last_accessed:
        return 0.5

    try:
        if isinstance(last_accessed, str):
            last_date = datetime.fromisoformat(last_accessed).date()
        else:
            last_date = last_accessed
        days = (date.today() - last_date).days
        return max(math.exp(-0.02 * days), 0.1)
    except (ValueError, TypeError):
        return 0.5


def _priming_bonus(memory: dict, priming_context: Optional[dict]) -> float:
    """Boost for memories related to current working context."""
    if not priming_context:
        return 1.0

    bonus = 1.0
    current_files = priming_context.get("files", [])
    memory_files = memory.get("code_touched", [])

    # If working on same files, prime those memories
    if current_files and memory_files:
        overlap = set(current_files) & set(memory_files)
        if overlap:
            bonus *= 1.3

    return bonus


def _memory_text(memory: dict) -> str:
    """Concatenate all searchable text fields from a memory."""
    parts = []
    for key in ("trigger", "story", "learned", "body", "intention", "signature",
                "consequence", "response", "name", "target", "what_it_does",
                "why_it_exists", "how_it_works", "summary", "reason"):
        val = memory.get(key, "")
        if val:
            parts.append(str(val))
    # Also include code_touched paths
    for f in memory.get("code_touched", []):
        parts.append(f)
    return " ".join(parts)

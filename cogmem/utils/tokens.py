"""Token estimation and budget allocation."""

from __future__ import annotations

from cogmem.models.common import BUDGET_TABLE, TaskType


def estimate_tokens(text: str) -> int:
    """Rough token estimate: ~4 chars per token."""
    return max(len(text) // 4, 1)


def truncate_to_budget(text: str, budget_tokens: int) -> str:
    """Truncate text to fit within a token budget."""
    max_chars = budget_tokens * 4
    if len(text) <= max_chars:
        return text
    return text[:max_chars - 3] + "..."


def allocate_budget(task_type: str, total_budget: int = 3500) -> dict[str, int]:
    """Allocate token budget across memory types for a task type.

    Returns dict mapping memory category to token count.
    """
    table = BUDGET_TABLE.get(task_type, BUDGET_TABLE["understand"])
    return {category: int(pct * total_budget) for category, pct in table.items()}

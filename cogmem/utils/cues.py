"""Cue extraction from queries — Stage 1 of retrieval."""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from cogmem.models.common import TaskType


@dataclass
class CueSet:
    keywords: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)        # function/class names
    file_paths: list[str] = field(default_factory=list)
    emotions: list[str] = field(default_factory=list)
    repo_references: list[str] = field(default_factory=list)
    task_type_hints: list[str] = field(default_factory=list)


# Emotion word mappings
EMOTION_WORDS = {
    "pain": ["pain", "painful", "hurt", "broken", "crash", "fail", "error", "bug",
             "exception", "panic", "oom", "timeout", "deadlock"],
    "danger": ["danger", "dangerous", "risky", "fragile", "brittle", "unstable",
               "volatile", "scary", "careful", "caution", "warning"],
    "frustration": ["frustrating", "frustrated", "annoying", "confusing", "weird",
                    "ugly", "hack", "workaround", "technical debt"],
    "trust": ["solid", "stable", "reliable", "well-tested", "clean", "elegant"],
    "relief": ["fixed", "resolved", "solved", "working", "finally"],
    "curiosity": ["why", "how", "understand", "explore", "investigate", "what"],
}

# Task type word mappings
TASK_WORDS = {
    "bugfix": ["fix", "bug", "debug", "error", "crash", "broken", "issue", "repair",
               "patch", "hotfix", "revert"],
    "feature": ["add", "new", "feature", "implement", "create", "build", "introduce"],
    "refactor": ["refactor", "restructure", "reorganize", "clean", "simplify",
                 "extract", "rename", "move", "split", "merge"],
    "understand": ["understand", "explain", "what", "how", "why", "where", "describe",
                   "overview", "architecture"],
    "plan": ["plan", "design", "approach", "strategy", "proposal", "roadmap"],
    "explore": ["explore", "find", "search", "look", "discover", "navigate", "browse"],
    "cross_repo": ["deploy", "release", "contract", "proto", "schema", "integration",
                   "all services", "cross-repo", "workspace"],
}

# File path patterns
FILE_PATH_RE = re.compile(r"(?:[\w./\\-]+\.(?:py|js|ts|go|rs|java|rb|tsx|jsx|md|json|yaml|yml|toml))")
# CamelCase or snake_case identifiers that look like function/class names
ENTITY_RE = re.compile(r"\b(?:[A-Z][a-zA-Z0-9]+|[a-z_][a-z0-9_]{3,}(?:\.[a-z_][a-z0-9_]+)*)\b")


def extract_cues(query: str) -> CueSet:
    """Extract structured cues from a natural language query."""
    cues = CueSet()
    query_lower = query.lower()
    words = query_lower.split()

    # Extract file paths
    cues.file_paths = FILE_PATH_RE.findall(query)

    # Extract emotions
    for emotion, word_list in EMOTION_WORDS.items():
        if any(w in words for w in word_list):
            cues.emotions.append(emotion)

    # Detect task type hints
    for task_type, word_list in TASK_WORDS.items():
        if any(w in query_lower for w in word_list):
            cues.task_type_hints.append(task_type)

    # Extract potential entity names (CamelCase, snake_case)
    for match in ENTITY_RE.finditer(query):
        candidate = match.group()
        # Filter out common English words
        if candidate.lower() not in _COMMON_WORDS and len(candidate) > 3:
            cues.entities.append(candidate)

    # General keywords (all meaningful words)
    cues.keywords = [w for w in words if len(w) > 2 and w not in _STOP_WORDS]

    return cues


def detect_task_type(query: str) -> str:
    """Detect the most likely task type from query."""
    cues = extract_cues(query)
    if not cues.task_type_hints:
        return TaskType.UNDERSTAND
    # Priority order
    for tt in ["bugfix", "cross_repo", "feature", "refactor", "plan", "explore", "understand"]:
        if tt in cues.task_type_hints:
            return tt
    return TaskType.UNDERSTAND


_STOP_WORDS = {
    "the", "and", "for", "was", "with", "this", "that", "from", "are", "but",
    "not", "have", "has", "had", "will", "been", "were", "they", "their",
    "what", "when", "which", "who", "how", "all", "can", "her", "his", "its",
    "our", "than", "then", "them", "these", "some", "could", "other", "into",
    "more", "also", "any", "only", "just", "about", "like", "would", "should",
    "there", "where", "does", "don", "didn", "isn", "aren",
}

_COMMON_WORDS = {
    "this", "that", "there", "here", "where", "when", "what", "which", "with",
    "from", "have", "been", "were", "they", "their", "them", "some", "other",
    "about", "would", "should", "could", "just", "like", "also", "more",
    "then", "than", "into", "only", "does", "make", "made", "take", "took",
    "come", "came", "look", "find", "know", "think", "want", "need",
}

"""Auto-detect emotion and intensity from text using heuristic classification."""

from __future__ import annotations


# ---------------------------------------------------------------------------
# Weighted keyword dictionaries
# ---------------------------------------------------------------------------

WEIGHTED_KEYWORDS: dict[str, dict[str, float]] = {
    "pain": {
        "crash": 1.0, "outage": 1.0, "broke": 0.9, "down": 0.7, "fail": 0.8,
        "error": 0.7, "exception": 0.6, "timeout": 0.7, "deadlock": 0.9,
        "oom": 0.9, "corrupt": 0.8, "lost": 0.7, "destroy": 0.8, "catastroph": 0.9,
    },
    "danger": {
        "risky": 0.8, "fragile": 0.9, "brittle": 0.8, "unstable": 0.7,
        "volatile": 0.7, "careful": 0.6, "caution": 0.6, "warning": 0.5,
        "scary": 0.7, "complex": 0.4, "tricky": 0.5, "subtle": 0.5,
    },
    "frustration": {
        "annoying": 0.7, "confusing": 0.6, "ugly": 0.5, "hack": 0.7,
        "workaround": 0.6, "technical debt": 0.6, "slow": 0.5, "weird": 0.5,
        "inconsistent": 0.5, "flaky": 0.7, "intermittent": 0.6,
    },
    "trust": {
        "solid": 0.7, "stable": 0.7, "reliable": 0.8, "well-tested": 0.9,
        "clean": 0.6, "elegant": 0.7, "simple": 0.5, "proven": 0.7, "robust": 0.8,
    },
    "pride": {
        "elegant": 0.7, "beautiful": 0.6, "clever": 0.5, "proud": 0.9,
        "nailed": 0.7, "perfect": 0.6, "impressive": 0.6, "great": 0.5,
    },
    "relief": {
        "fixed": 0.7, "resolved": 0.8, "solved": 0.8, "working": 0.6,
        "finally": 0.8, "phew": 0.9, "recovered": 0.7, "restored": 0.6,
    },
    "curiosity": {
        "interesting": 0.6, "wonder": 0.5, "explore": 0.6, "investigate": 0.5,
        "discover": 0.6, "learn": 0.5, "understand": 0.4, "how": 0.3,
        "why": 0.4, "new": 0.3,
    },
}

# ---------------------------------------------------------------------------
# N-gram patterns (substring matches)
# ---------------------------------------------------------------------------

NGRAM_PATTERNS: dict[str, list[tuple[str, float]]] = {
    "pain": [
        ("took down", 0.9), ("went down", 0.9), ("kept crashing", 0.9),
        ("data loss", 1.0), ("rolled back", 0.8), ("had to revert", 0.9),
    ],
    "frustration": [
        ("took forever", 0.8), ("kept breaking", 0.8), ("makes no sense", 0.7),
        ("waste of time", 0.8), ("no documentation", 0.6), ("hard to understand", 0.6),
    ],
    "relief": [
        ("finally works", 0.9), ("turns out", 0.5), ("figured out", 0.7),
        ("now working", 0.7), ("all green", 0.8),
    ],
    "pride": [
        ("works perfectly", 0.8), ("clean solution", 0.7), ("zero bugs", 0.8),
    ],
}

# ---------------------------------------------------------------------------
# Negation handling
# ---------------------------------------------------------------------------

NEGATION_WORDS: set[str] = {
    "not", "no", "never", "without", "dont", "doesn't", "didn't",
    "isn't", "aren't", "wasn't", "weren't", "nothing",
}


# ---------------------------------------------------------------------------
# Internal scoring helpers
# ---------------------------------------------------------------------------

def _weighted_keyword_score(text: str) -> dict[str, float]:
    """Score each emotion based on weighted keyword matches with negation handling."""
    words = text.split()
    scores: dict[str, float] = {emotion: 0.0 for emotion in WEIGHTED_KEYWORDS}

    for emotion, keywords in WEIGHTED_KEYWORDS.items():
        for keyword, weight in keywords.items():
            # Handle multi-word keywords (e.g. "technical debt")
            if " " in keyword:
                if keyword in text:
                    scores[emotion] += weight
                continue

            for i, word in enumerate(words):
                # Check if the word starts with the keyword (handles suffixes like "crashed")
                if word.startswith(keyword) or word == keyword:
                    # Check for negation within 3 words before
                    negated = False
                    start = max(0, i - 3)
                    for j in range(start, i):
                        if words[j] in NEGATION_WORDS:
                            negated = True
                            break
                    if negated:
                        scores[emotion] -= weight
                    else:
                        scores[emotion] += weight

    return scores


def _ngram_pattern_score(text: str) -> dict[str, float]:
    """Score each emotion based on n-gram substring patterns."""
    scores: dict[str, float] = {emotion: 0.0 for emotion in WEIGHTED_KEYWORDS}

    for emotion, patterns in NGRAM_PATTERNS.items():
        for pattern, weight in patterns:
            if pattern in text:
                scores[emotion] += weight

    return scores


def _file_context_bias(
    scores: dict[str, float],
    file_context: dict[str, str] | None,
) -> dict[str, float]:
    """Boost emotions based on existing file emotion tags."""
    if not file_context:
        return scores

    # Build a set of words from file paths for matching
    for filepath, existing_emotion in file_context.items():
        # Extract the filename parts as words for matching
        path_words = set()
        for part in filepath.replace("/", " ").replace("\\", " ").replace(".", " ").replace("_", " ").replace("-", " ").split():
            path_words.add(part.lower())

        # If any path word appears in the scored text context (checked by caller),
        # we boost the emotion. We check the scores dict keys to see if the emotion is valid.
        if existing_emotion in scores:
            scores[existing_emotion] += 0.3

    return scores


def _file_context_bias_with_text(
    scores: dict[str, float],
    file_context: dict[str, str] | None,
    text: str,
) -> dict[str, float]:
    """Boost emotions for files mentioned in text that have existing emotion tags."""
    if not file_context:
        return scores

    for filepath, existing_emotion in file_context.items():
        # Extract meaningful words from filepath
        path_words = set()
        for part in filepath.replace("/", " ").replace("\\", " ").replace(".", " ").replace("_", " ").replace("-", " ").split():
            word = part.lower().strip()
            if len(word) > 2:  # skip very short fragments
                path_words.add(word)

        # Check if any path word appears in text
        for word in path_words:
            if word in text:
                if existing_emotion in scores:
                    scores[existing_emotion] += 0.3
                break  # one boost per file

    return scores


def _estimate_intensity(scores: dict[str, float], winner: str) -> float:
    """Map the winner's score to an intensity in [0.3, 1.0]."""
    winner_score = scores[winner]
    sorted_scores = sorted(scores.values(), reverse=True)
    gap = sorted_scores[0] - sorted_scores[1] if len(sorted_scores) > 1 else sorted_scores[0]

    # Base intensity from absolute score
    if winner_score >= 2.0:
        base = 0.9
    elif winner_score >= 1.5:
        base = 0.8
    elif winner_score >= 1.0:
        base = 0.7
    elif winner_score >= 0.7:
        base = 0.6
    elif winner_score >= 0.4:
        base = 0.5
    else:
        base = 0.4

    # Boost slightly for large gap (clear signal)
    if gap >= 1.0:
        base = min(1.0, base + 0.1)

    return max(0.3, min(1.0, base))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect_emotion(
    text: str,
    file_context: dict[str, str] | None = None,
) -> tuple[str, float]:
    """Auto-detect emotion and intensity from text.

    Args:
        text: The text to classify.
        file_context: Mapping of ``{filepath: existing_emotion}`` for contextual
            biasing.  When a filepath word appears in *text*, the associated
            emotion receives a boost.

    Returns:
        ``(emotion_type, intensity)`` where *emotion_type* is one of:
        ``pain``, ``danger``, ``frustration``, ``trust``, ``pride``,
        ``relief``, ``curiosity``, ``neutral``.
    """
    if not text or not text.strip():
        return ("neutral", 0.3)

    lower = text.lower()

    # 1. Keyword scores
    keyword_scores = _weighted_keyword_score(lower)

    # 2. N-gram pattern scores
    ngram_scores = _ngram_pattern_score(lower)

    # 3. Combine: keyword * 0.6 + ngram * 0.4
    combined: dict[str, float] = {}
    for emotion in keyword_scores:
        combined[emotion] = keyword_scores[emotion] * 0.6 + ngram_scores[emotion] * 0.4

    # 4. File context bias
    combined = _file_context_bias_with_text(combined, file_context, lower)

    # 5. Pick winner
    winner = max(combined, key=lambda e: combined[e])
    if combined[winner] < 0.15:
        return ("neutral", 0.3)

    # 6. Estimate intensity
    intensity = _estimate_intensity(combined, winner)

    return (winner, intensity)

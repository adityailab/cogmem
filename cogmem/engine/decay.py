"""Decay engine — strength-based forgetting with phase transitions."""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date
from pathlib import Path

from cogmem.models import (
    DECAY_RATES,
    WORKSPACE_DECAY_MULTIPLIER,
    Episode,
    Phase,
    Tier,
)
from cogmem.tiers.global_mem import GlobalTier
from cogmem.tiers.repo import RepoTier
from cogmem.tiers.workspace import WorkspaceTier, detect_workspace
from cogmem.utils.repo_detect import find_repo_root


def run_decay(cwd: str | None = None, dry_run: bool = False) -> str:
    """Run decay across all accessible tiers."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    results: list[str] = []

    # Repo tier
    repo_root = find_repo_root(cwd_path)
    if repo_root:
        repo = RepoTier(repo_root)
        if repo.exists:
            msg = _decay_repo(repo, dry_run=dry_run)
            results.append(msg)
    else:
        results.append("No repo found — skipping repo decay.")

    # Workspace tier (decays at 0.7x rate)
    ws_path = detect_workspace(cwd_path)
    if ws_path:
        ws = WorkspaceTier(ws_path)
        if ws.exists:
            msg = _decay_workspace(ws)
            results.append(msg)

    # Global patterns never decay
    results.append("Global: patterns do not decay.")

    return "\n".join(results)


def compute_new_strength(current: float, rate: float, days_elapsed: float) -> float:
    """Exponential decay: strength * exp(-rate * days)."""
    return current * math.exp(-rate * days_elapsed)


def transition_episode_phase(episode: Episode, today: date | None = None) -> bool:
    """Check and apply phase transition. Returns True if transitioned."""
    today = today or date.today()
    if not episode.date:
        return False
    try:
        ep_date = date.fromisoformat(episode.date)
    except ValueError:
        return False

    age_days = (today - ep_date).days
    new_phase = episode.phase_for_age(age_days)

    if new_phase == episode.phase:
        return False

    episode.phase = new_phase
    if new_phase in (Phase.FUZZY, Phase.FADING):
        episode.story = episode.compress("summary")
    elif new_phase == Phase.STUB:
        episode.story = episode.compress("stub")

    return True


# ---------------------------------------------------------------------------
# Internal
# ---------------------------------------------------------------------------

def _decay_repo(repo: RepoTier, dry_run: bool = False) -> str:
    """Apply decay to all memories in a repo."""
    today = date.today()
    stats: dict[str, int] = defaultdict(int)

    # Episodes
    for ep in repo.list_episodes():
        days = _days_since_access(ep.last_accessed, ep.date, today)
        if days <= 0:
            continue
        old_strength = ep.strength
        ep.strength = compute_new_strength(old_strength, DECAY_RATES["episode"], days)
        changed = transition_episode_phase(ep, today)
        if ep.strength != old_strength or changed:
            if not dry_run:
                ep.save(str(repo.dir.resolve(f"episodes/{ep.filename}")))
            stats["episodes"] += 1

    # Patterns
    for pat in repo.list_patterns():
        days = _days_since(pat.last_seen, today)
        if days <= 0:
            continue
        old = pat.strength
        pat.strength = compute_new_strength(old, DECAY_RATES["pattern"], days)
        if pat.strength != old:
            if not dry_run:
                pat.save(str(repo.dir.resolve(f"patterns/{pat.filename}")))
            stats["patterns"] += 1

    # Prospective memories
    for p in repo.list_prospectives():
        if p.completed:
            continue
        days = _days_since(None, today)  # no last_accessed on prospective
        if days <= 0:
            continue
        old = p.strength
        p.strength = compute_new_strength(old, DECAY_RATES["prospective"], days)
        if p.strength != old:
            if not dry_run:
                p.save(str(repo.dir.resolve(f"prospective/{p.filename}")))
            stats["prospectives"] += 1

    # Emotions
    emotions = repo.get_emotions()
    emotion_changed = False
    for tag in emotions.tags:
        days = _days_since(tag.last_reinforced, today)
        if days <= 0:
            continue
        rate = DECAY_RATES["emotion_pain"] if tag.emotion == "pain" else DECAY_RATES["emotion"]
        old = tag.intensity
        tag.intensity = max(0.1, compute_new_strength(old, rate, days))
        if tag.intensity != old:
            emotion_changed = True
            stats["emotions"] += 1
    if emotion_changed and not dry_run:
        repo.dir.write_text("emotions.md", emotions.to_markdown())

    # Entity strength
    for entity in repo.list_entities():
        # Entities decay very slowly — approximate as spatial rate
        old = entity.strength
        entity.strength = compute_new_strength(old, DECAY_RATES["spatial"], 1)
        if entity.strength != old:
            if not dry_run:
                entity.save(str(repo.dir.resolve(f"entities/{entity.filename}")))
            stats["entities"] += 1

    parts = [f"Repo {repo.repo_path.name} decay:"]
    for kind, count in sorted(stats.items()):
        if count:
            parts.append(f"  {count} {kind} decayed")
    if len(parts) == 1:
        parts.append("  Nothing to decay.")
    return "\n".join(parts)


def _decay_workspace(ws: WorkspaceTier) -> str:
    """Apply decay to workspace memories at 0.7x rate."""
    today = date.today()
    stats: dict[str, int] = defaultdict(int)

    # Episodes
    for ep in ws.list_episodes():
        days = _days_since_access(ep.last_accessed, ep.date, today)
        if days <= 0:
            continue
        rate = DECAY_RATES["episode"] * WORKSPACE_DECAY_MULTIPLIER
        old = ep.strength
        ep.strength = compute_new_strength(old, rate, days)
        changed = transition_episode_phase(ep, today)
        if ep.strength != old or changed:
            ep.save(str(ws.dir.resolve(f"episodes/{ep.filename}")))
            stats["episodes"] += 1

    # Patterns
    for pat in ws.list_patterns():
        days = _days_since(pat.last_seen, today)
        if days <= 0:
            continue
        rate = DECAY_RATES["pattern"] * WORKSPACE_DECAY_MULTIPLIER
        old = pat.strength
        pat.strength = compute_new_strength(old, rate, days)
        if pat.strength != old:
            pat.save(str(ws.dir.resolve(f"patterns/{pat.filename}")))
            stats["patterns"] += 1

    # Emotions
    emotions = ws.get_emotions()
    emotion_changed = False
    for tag in emotions.tags:
        days = _days_since(tag.last_reinforced, today)
        if days <= 0:
            continue
        rate = DECAY_RATES["emotion"] * WORKSPACE_DECAY_MULTIPLIER
        old = tag.intensity
        tag.intensity = max(0.1, compute_new_strength(old, rate, days))
        if tag.intensity != old:
            emotion_changed = True
            stats["emotions"] += 1
    if emotion_changed:
        ws.dir.write_text("emotions.md", emotions.to_markdown())

    parts = [f"Workspace decay:"]
    for kind, count in sorted(stats.items()):
        if count:
            parts.append(f"  {count} {kind} decayed (0.7x rate)")
    if len(parts) == 1:
        parts.append("  Nothing to decay.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _days_since_access(
    last_accessed: str | None,
    fallback_date: str | None,
    today: date,
) -> int:
    """Days since last access, falling back to creation date."""
    ref = last_accessed or fallback_date
    if not ref:
        return 0
    try:
        return (today - date.fromisoformat(ref)).days
    except ValueError:
        return 0


def _days_since(date_str: str | None, today: date) -> int:
    """Days since a given date string."""
    if not date_str:
        return 1  # default: decay by 1 day
    try:
        return (today - date.fromisoformat(date_str)).days
    except ValueError:
        return 1

"""Memory corrections — update, mark, and forget."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Optional

from cogmem.models import (
    DangerLevel,
    EmotionTag,
    EmotionType,
    Gist,
    GistScope,
    Judgment,
    Pattern,
    PatternCategory,
    Tier,
)
from cogmem.tiers.repo import RepoTier
from cogmem.utils.repo_detect import find_project_root


def update_memory(
    stable_target: str | None = None,
    danger_target: str | None = None,
    gist_target: str | None = None,
    pattern_name: str | None = None,
    content: str = "",
    cwd: str | None = None,
) -> str:
    """Update or correct memories."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)

    repo = RepoTier(repo_root)
    if not repo.exists:
        return "Repo memory not initialized. Run `cogmem bootstrap` first."

    today = date.today().isoformat()

    if stable_target:
        repo.update_emotion(EmotionTag(
            target=stable_target,
            emotion=EmotionType.TRUST,
            intensity=0.7,
            reason=content or "Manually marked stable",
            last_reinforced=today,
        ))
        return f"Marked {stable_target} as stable (trust)."

    if danger_target:
        repo.update_emotion(EmotionTag(
            target=danger_target,
            emotion=EmotionType.DANGER,
            intensity=0.85,
            reason=content or "Manually marked dangerous",
            last_reinforced=today,
        ))
        return f"Marked {danger_target} as dangerous."

    if gist_target:
        if not content:
            return "Need --content for gist update."
        existing = repo.list_gists()
        for g in existing:
            if g.target.lower() == gist_target.lower():
                g.what_it_does = content
                g.last_updated = today
                repo.save_gist(g)
                return f"Updated gist for {gist_target}."
        # Create new
        gist = Gist(
            scope=GistScope.MODULE,
            target=gist_target,
            tier=Tier.REPO,
            what_it_does=content,
            last_updated=today,
        )
        repo.save_gist(gist)
        return f"Created gist for {gist_target}."

    if pattern_name:
        if not content:
            return "Need --content for pattern creation."
        pattern = Pattern(
            name=pattern_name,
            category=PatternCategory.DESIGN,
            tier=Tier.REPO,
            signature=content,
            last_seen=today,
            strength=0.8,
        )
        repo.save_pattern(pattern)
        return f"Added pattern: {pattern_name}."

    return "No action specified. Use --mark-stable, --mark-dangerous, --update-gist, or --add-pattern."


def forget_memory(target: str, cwd: str | None = None) -> str:
    """Archive or remove a memory by target name."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)

    repo = RepoTier(repo_root)
    if not repo.exists:
        return "Repo memory not initialized."

    # Try to find and remove matching memories
    removed = []

    # Check episodes
    for ep in repo.list_episodes():
        if target.lower() in ep.trigger.lower() or target.lower() in ep.story.lower():
            repo.dir.delete_file(f"episodes/{ep.filename}")
            index = repo.get_index()
            index.remove_entry(f"episodes/{ep.filename}")
            repo.save_index(index)
            removed.append(f"episode: {ep.trigger[:40]}")
            break  # remove first match only

    # Check patterns
    for pat in repo.list_patterns():
        if target.lower() in pat.name.lower():
            repo.dir.delete_file(f"patterns/{pat.filename}")
            removed.append(f"pattern: {pat.name}")
            break

    # Check emotions
    emotions = repo.get_emotions()
    for tag in emotions.tags:
        if target.lower() in tag.target.lower():
            emotions.tags.remove(tag)
            repo.dir.write_text("emotions.md", emotions.to_markdown())
            removed.append(f"emotion: {tag.target}")
            break

    # Check prospective
    for p in repo.list_prospectives():
        if target.lower() in p.intention.lower():
            repo.dir.delete_file(f"prospective/{p.filename}")
            removed.append(f"prospective: {p.intention[:40]}")
            break

    if removed:
        return "Removed:\n" + "\n".join(f"  - {r}" for r in removed)
    return f"No memories found matching '{target}'."

"""Consolidation engine — strengthen, compress, and extract patterns."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from cogmem.models import (
    EmotionTag,
    EmotionType,
    Episode,
    Gist,
    GistScope,
    Pattern,
    PatternCategory,
    Phase,
    Tier,
)
from cogmem.storage.index import extract_keywords
from cogmem.tiers.global_mem import GlobalTier
from cogmem.tiers.repo import RepoTier
from cogmem.tiers.workspace import WorkspaceTier, detect_workspace
from cogmem.utils.repo_detect import find_repo_root


def consolidate(
    scope: str = "full",
    apply_file: str | None = None,
    cwd: str | None = None,
    dry_run: bool = False,
) -> str:
    """Run consolidation across tiers.

    Returns a status message. For workspace consolidation that needs a
    subagent, writes a prompt to .pending/ and returns instructions.
    """
    cwd_path = Path(cwd) if cwd else Path.cwd()
    results: list[str] = []

    if apply_file:
        return consolidate_apply(apply_file, cwd=cwd)

    if scope in ("full", "repo"):
        repo_root = find_repo_root(cwd_path)
        if repo_root:
            msg = consolidate_repo(RepoTier(repo_root), dry_run=dry_run)
            results.append(msg)
        else:
            results.append("No repo found — skipping repo consolidation.")

    if scope in ("full", "workspace"):
        ws_path = detect_workspace(cwd_path)
        if ws_path:
            msg = consolidate_workspace(WorkspaceTier(ws_path))
            results.append(msg)
        else:
            results.append("No workspace found — skipping workspace consolidation.")

    if scope in ("full",):
        msg = consolidate_global()
        results.append(msg)

    return "\n".join(results)


# ---------------------------------------------------------------------------
# Repo consolidation
# ---------------------------------------------------------------------------

def consolidate_repo(repo: RepoTier, dry_run: bool = False) -> str:
    """Five-phase repo consolidation."""
    if not repo.exists:
        return f"Repo {repo.repo_path.name}: not initialized."

    today = date.today()
    stats: dict[str, int] = defaultdict(int)

    # Phase 1 — Episode compression (phase transitions)
    episodes = repo.list_episodes()
    for ep in episodes:
        if not ep.date:
            continue
        try:
            ep_date = date.fromisoformat(ep.date)
        except ValueError:
            continue
        age_days = (today - ep_date).days
        new_phase = ep.phase_for_age(age_days)
        if new_phase != ep.phase:
            old_phase = ep.phase
            ep.phase = new_phase
            # Compress narrative at transition
            if new_phase in (Phase.FUZZY, Phase.FADING):
                ep.story = ep.compress("summary")
            elif new_phase == Phase.STUB:
                ep.story = ep.compress("stub")
            if not dry_run:
                ep.save(str(repo.dir.resolve(f"episodes/{ep.filename}")))
            stats["phase_transitions"] += 1

    # Phase 2 — Pattern extraction (find recurring themes)
    file_counts: Counter = Counter()
    theme_episodes: dict[str, list[Episode]] = defaultdict(list)
    for ep in episodes:
        for f in ep.code_touched:
            file_counts[f] += 1
        # Group by trigger keywords for theme detection
        if ep.trigger:
            key_words = extract_keywords(ep.trigger)
            for kw in key_words[:3]:  # top keywords as theme keys
                theme_episodes[kw].append(ep)

    existing_patterns = {p.name.lower() for p in repo.list_patterns()}
    existing_gists_map = {g.target.lower(): g for g in repo.list_gists()}

    for theme, eps in theme_episodes.items():
        if len(eps) < 3:  # need at least 3 episodes to form a pattern
            continue
        pattern_name = f"recurring-{theme}"
        if pattern_name in existing_patterns:
            continue
        # Check if episodes share files or emotions
        shared_files = _find_shared_files(eps)
        dominant_emotion = _dominant_emotion(eps)
        if not shared_files and dominant_emotion == "neutral":
            continue

        # Find related gists for the affected modules
        related_gist_ids = []
        for f in shared_files[:5]:
            module = Path(f).parts[0] if Path(f).parts else ""
            for g in existing_gists_map.values():
                if g.target.lower() == module.lower() and g.id not in related_gist_ids:
                    related_gist_ids.append(g.id)

        pattern = Pattern(
            name=pattern_name,
            category=PatternCategory.BUG if dominant_emotion in ("pain", "frustration") else PatternCategory.DESIGN,
            tier=Tier.REPO,
            signature=f"Recurring {theme} across {len(eps)} episodes",
            consequence=f"Affects: {', '.join(shared_files[:5])}" if shared_files else "",
            response=f"Pattern detected from {len(eps)} episodes — review for action.",
            seen_in=shared_files[:10],
            frequency=len(eps),
            last_seen=today.isoformat(),
            trigger_cues=[theme],
            related_gists=related_gist_ids,
            strength=min(1.0, 0.3 + 0.1 * len(eps)),
            danger_level="medium" if dominant_emotion in ("pain", "danger") else "low",
        )
        if not dry_run:
            repo.save_pattern(pattern)
        stats["patterns_created"] += 1

    # Phase 2.5 — Write pattern review prompt for LLM subagent
    if theme_episodes and not dry_run:
        pending_dir = repo.dir.resolve(".pending")
        pending_dir.mkdir(parents=True, exist_ok=True)
        prompt = _build_pattern_review_prompt(
            theme_episodes, repo.list_patterns()
        )
        (pending_dir / "pattern_review.md").write_text(prompt)
        stats["prompts_written"] = stats.get("prompts_written", 0) + 1

    # Phase 3 — Gist formation (update existing + write LLM prompts for new)
    module_episodes: dict[str, list[Episode]] = defaultdict(list)
    for ep in episodes:
        for f in ep.code_touched:
            parts = Path(f).parts
            if len(parts) >= 2:
                module = parts[0] if not parts[0].startswith(".") else (parts[1] if len(parts) > 1 else parts[0])
                module_episodes[module].append(ep)

    for module, eps in module_episodes.items():
        if len(eps) < 2:
            continue
        gist_key = module.lower()
        if gist_key in existing_gists_map:
            gist = existing_gists_map[gist_key]
            new_refs = [ep.id for ep in eps if ep.id not in gist.formed_from]
            if new_refs:
                gist.formed_from.extend(new_refs[-5:])
                gist.last_updated = today.isoformat()
                if not dry_run:
                    repo.save_gist(gist)
                stats["gists_updated"] += 1

        # Write LLM prompt for gist generation/update
        if not dry_run and len(eps) >= 3:
            pending_dir = repo.dir.resolve(".pending")
            pending_dir.mkdir(parents=True, exist_ok=True)
            prompt = _build_gist_generation_prompt(
                module, eps, existing_gists_map.get(gist_key)
            )
            (pending_dir / f"gist_{module}.md").write_text(prompt)
            stats["prompts_written"] = stats.get("prompts_written", 0) + 1

    # Phase 4 — Emotional recalibration
    emotions = repo.get_emotions()
    recalibrated = 0
    for tag in emotions.tags:
        if tag.last_reinforced:
            try:
                last = date.fromisoformat(tag.last_reinforced)
                days_stale = (today - last).days
            except ValueError:
                continue
            # Reduce intensity for stale emotions (not reinforced in 30+ days)
            if days_stale > 30 and tag.intensity > 0.3:
                decay_factor = 0.95 ** (days_stale / 30)
                tag.intensity = max(0.2, tag.intensity * decay_factor)
                recalibrated += 1
    if recalibrated:
        if not dry_run:
            repo.dir.write_text("emotions.md", emotions.to_markdown())
        stats["emotions_recalibrated"] = recalibrated

    # Phase 5 — Pruning
    stubs_deleted = 0
    for ep in episodes:
        if ep.phase == Phase.STUB and ep.strength < 0.1:
            # Check if consolidated into a pattern or gist
            has_references = any(
                ep.id in p.seen_in for p in repo.list_patterns()
            )
            if not has_references:
                if not dry_run:
                    repo.dir.delete_file(f"episodes/{ep.filename}")
                    index = repo.get_index()
                    index.remove_entry(f"episodes/{ep.filename}")
                    repo.save_index(index)
                stubs_deleted += 1
    stats["stubs_pruned"] = stubs_deleted

    # Remove orphaned entities (files that no longer exist)
    orphans = 0
    for entity in repo.list_entities():
        full_path = repo.repo_path / entity.file_path
        if not full_path.exists():
            if not dry_run:
                repo.dir.delete_file(f"entities/{entity.filename}")
            orphans += 1
    stats["orphaned_entities"] = orphans

    parts = [f"Repo {repo.repo_path.name} consolidated:"]
    if stats["phase_transitions"]:
        parts.append(f"  {stats['phase_transitions']} episodes transitioned")
    if stats["patterns_created"]:
        parts.append(f"  {stats['patterns_created']} new patterns extracted")
    if stats["gists_updated"]:
        parts.append(f"  {stats['gists_updated']} gists updated")
    if stats["emotions_recalibrated"]:
        parts.append(f"  {stats['emotions_recalibrated']} emotions recalibrated")
    if stats["stubs_pruned"]:
        parts.append(f"  {stats['stubs_pruned']} stubs pruned")
    if stats["orphaned_entities"]:
        parts.append(f"  {stats['orphaned_entities']} orphaned entities removed")
    if len(parts) == 1:
        parts.append("  Nothing to consolidate.")
    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Workspace consolidation
# ---------------------------------------------------------------------------

def consolidate_workspace(ws: WorkspaceTier) -> str:
    """Three-phase workspace consolidation.

    Phase W1 writes a prompt for subagent processing.
    """
    if not ws.exists:
        return "Workspace not initialized."

    today = date.today()
    results: list[str] = []

    # Phase W1 — Cross-repo pattern detection
    # Gather recent episodes from all repos
    repos_info = ws.list_repos()
    all_episodes: list[dict] = []
    for repo_info in repos_info:
        repo_path = Path(repo_info.get("path", ""))
        if not repo_path.is_dir():
            continue
        repo = RepoTier(repo_path)
        if not repo.exists:
            continue
        for ep in repo.list_episodes():
            if ep.phase in (Phase.VIVID, Phase.CLEAR):
                all_episodes.append({
                    "repo": repo_info.get("name", repo_path.name),
                    "trigger": ep.trigger,
                    "emotion": ep.emotion,
                    "files": ep.code_touched[:5],
                    "date": ep.date,
                })

    if all_episodes:
        # Write prompt for subagent
        pending_dir = ws.dir.resolve(".pending")
        pending_dir.mkdir(parents=True, exist_ok=True)
        prompt = _build_consolidation_prompt(all_episodes, repos_info)
        prompt_path = pending_dir / "consolidate_prompt.md"
        prompt_path.write_text(prompt)
        results.append(
            f"Workspace: wrote consolidation prompt to {prompt_path}\n"
            f"  Run consolidation subagent to process {len(all_episodes)} episodes."
        )
    else:
        results.append("Workspace: no recent episodes to consolidate.")

    # Phase W2 — Workspace gist update (check if repo gists changed)
    ws_gists = ws.list_gists()
    if not ws_gists:
        results.append("  No workspace gists to update.")

    # Phase W3 — Cross-repo emotional recalibration
    emotions = ws.get_emotions()
    recalibrated = 0
    for tag in emotions.tags:
        if tag.last_reinforced:
            try:
                last = date.fromisoformat(tag.last_reinforced)
                days_stale = (today - last).days
            except ValueError:
                continue
            if days_stale > 60 and tag.intensity > 0.3:
                decay_factor = 0.95 ** (days_stale / 60)
                tag.intensity = max(0.2, tag.intensity * decay_factor)
                recalibrated += 1
    if recalibrated:
        ws.dir.write_text("emotions.md", emotions.to_markdown())
        results.append(f"  {recalibrated} workspace emotions recalibrated.")

    return "\n".join(results)


# ---------------------------------------------------------------------------
# Global consolidation
# ---------------------------------------------------------------------------

def consolidate_global(cwd: str | None = None) -> str:
    """Promote transferable repo patterns to global tier."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    global_tier = GlobalTier()
    if not global_tier.exists:
        global_tier.init()

    repo_root = find_repo_root(cwd_path)
    if not repo_root:
        return "Global: no repo found to promote patterns from."

    repo = RepoTier(repo_root)
    if not repo.exists:
        return "Global: repo not initialized."

    promoted = 0
    for pattern in repo.list_patterns():
        if pattern.transferable and not global_tier.has_pattern(pattern.name):
            pattern.tier = Tier.GLOBAL
            global_tier.save_pattern(pattern)
            promoted += 1

    if promoted:
        return f"Global: promoted {promoted} transferable patterns."
    return "Global: no new patterns to promote."


# ---------------------------------------------------------------------------
# Apply subagent results
# ---------------------------------------------------------------------------

def consolidate_apply(result_file: str, cwd: str | None = None) -> str:
    """Apply subagent consolidation results."""
    result_path = Path(result_file)
    if not result_path.exists():
        return f"Result file not found: {result_file}"

    try:
        with open(result_path) as f:
            results = json.load(f)
    except (json.JSONDecodeError, ValueError) as e:
        return f"Could not parse result file: {e}"

    cwd_path = Path(cwd) if cwd else Path.cwd()
    ws_path = detect_workspace(cwd_path)
    if not ws_path:
        return "No workspace found to apply results to."

    ws = WorkspaceTier(ws_path)
    applied = 0

    # Apply cross-repo patterns
    for pat_data in results.get("patterns", []):
        pattern = Pattern(
            name=pat_data.get("name", ""),
            category=pat_data.get("category", PatternCategory.CROSS_REPO),
            tier=Tier.WORKSPACE,
            signature=pat_data.get("signature", ""),
            consequence=pat_data.get("consequence", ""),
            response=pat_data.get("response", ""),
            seen_in=pat_data.get("seen_in", []),
            frequency=pat_data.get("frequency", 1),
            last_seen=date.today().isoformat(),
            trigger_cues=pat_data.get("trigger_cues", []),
            strength=pat_data.get("strength", 0.7),
        )
        ws.save_pattern(pattern)
        applied += 1

    # Apply gist updates
    for gist_data in results.get("gists", []):
        gist = Gist(
            scope=gist_data.get("scope", GistScope.PLATFORM),
            target=gist_data.get("target", ""),
            tier=Tier.WORKSPACE,
            what_it_does=gist_data.get("what_it_does", ""),
            why_it_exists=gist_data.get("why_it_exists", ""),
            how_it_works=gist_data.get("how_it_works", ""),
            key_relationships=gist_data.get("key_relationships", ""),
            last_updated=date.today().isoformat(),
        )
        ws.save_gist(gist)
        applied += 1

    # Apply pattern merges (from pattern review prompt)
    for merge in results.get("patterns_to_merge", []):
        from_names = merge.get("from_names", [])
        into = merge.get("into", {})
        if from_names and into:
            # Delete old patterns
            for pat in ws.list_patterns():
                if pat.name in from_names:
                    ws.dir.delete_file(f"patterns/{pat.filename}")
            # Create merged pattern
            pattern = Pattern(
                name=into.get("name", ""),
                category=into.get("category", PatternCategory.CROSS_REPO),
                tier=Tier.WORKSPACE,
                signature=into.get("signature", ""),
                consequence=into.get("consequence", ""),
                response=into.get("response", ""),
                trigger_cues=into.get("trigger_cues", []),
                last_seen=date.today().isoformat(),
                strength=0.8,
            )
            ws.save_pattern(pattern)
            applied += 1

    # Apply pattern updates
    for update in results.get("patterns_to_update", []):
        name = update.get("name", "")
        updates = update.get("updates", {})
        for pat in ws.list_patterns():
            if pat.name == name:
                for key, val in updates.items():
                    if hasattr(pat, key):
                        setattr(pat, key, val)
                ws.save_pattern(pat)
                applied += 1
                break

    # Apply gist updates (match by target for existing gists)
    for gist_data in results.get("gist_updates", []):
        target = gist_data.get("target", "")
        existing = None
        for g in ws.list_gists():
            if g.target.lower() == target.lower():
                existing = g
                break
        if existing:
            for key in ("what_it_does", "why_it_exists", "how_it_works", "key_relationships", "judgment"):
                if key in gist_data:
                    setattr(existing, key, gist_data[key])
            existing.last_updated = date.today().isoformat()
            ws.save_gist(existing)
        else:
            gist = Gist(
                scope=gist_data.get("scope", GistScope.MODULE),
                target=target,
                tier=Tier.WORKSPACE,
                what_it_does=gist_data.get("what_it_does", ""),
                why_it_exists=gist_data.get("why_it_exists", ""),
                how_it_works=gist_data.get("how_it_works", ""),
                key_relationships=gist_data.get("key_relationships", ""),
                judgment=gist_data.get("judgment", "unknown"),
                last_updated=date.today().isoformat(),
            )
            ws.save_gist(gist)
        applied += 1

    # Clean up pending prompts
    pending_dir = ws.dir.resolve(".pending")
    if pending_dir.is_dir():
        for f in pending_dir.glob("*.md"):
            f.unlink()

    return f"Applied {applied} consolidation results."


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _find_shared_files(episodes: list[Episode]) -> list[str]:
    """Find files that appear in multiple episodes."""
    counts: Counter = Counter()
    for ep in episodes:
        for f in ep.code_touched:
            counts[f] += 1
    return [f for f, c in counts.most_common(10) if c >= 2]


def _dominant_emotion(episodes: list[Episode]) -> str:
    """Find the most common non-neutral emotion."""
    emotions: Counter = Counter()
    for ep in episodes:
        if ep.emotion != "neutral":
            emotions[ep.emotion] += 1
    if not emotions:
        return "neutral"
    return emotions.most_common(1)[0][0]


def _build_consolidation_prompt(
    episodes: list[dict],
    repos: list[dict],
) -> str:
    """Build a markdown prompt for the consolidation subagent."""
    lines = [
        "# Workspace Consolidation Task\n",
        "Analyze the following episodes from multiple repos and identify:",
        "1. Cross-repo patterns (recurring themes, shared failures)",
        "2. Workspace gist updates (how repos relate to each other)",
        "3. Danger zones (shared contracts, API boundaries at risk)\n",
        f"## Repos ({len(repos)})\n",
    ]
    for r in repos:
        lines.append(f"- {r.get('name', '?')}: {r.get('path', '?')}")

    lines.append(f"\n## Recent Episodes ({len(episodes)})\n")
    for ep in episodes[:50]:  # cap at 50
        lines.append(
            f"- [{ep['repo']}] {ep['date']}: {ep['trigger']} "
            f"(emotion: {ep['emotion']}, files: {', '.join(ep['files'][:3])})"
        )

    lines.extend([
        "\n## Expected Output Format\n",
        "Return a JSON object with:",
        '```json',
        '{',
        '  "patterns": [{"name": "...", "category": "cross_repo", "signature": "...", "consequence": "...", "response": "...", "seen_in": [...], "frequency": N, "trigger_cues": [...], "strength": 0.7}],',
        '  "gists": [{"scope": "platform", "target": "...", "what_it_does": "...", "why_it_exists": "...", "how_it_works": "...", "key_relationships": "..."}],',
        '  "danger_zones": ["..."]',
        '}',
        '```',
    ])

    return "\n".join(lines)


def _build_pattern_review_prompt(
    theme_episodes: dict[str, list],
    existing_patterns: list,
) -> str:
    """Build prompt for LLM to review episode clusters and suggest better patterns."""
    lines = [
        "# Pattern Review Task\n",
        "Review the following episode clusters and existing patterns.",
        "Suggest improvements: merge overlapping patterns, create new ones from",
        "clusters that keyword matching missed, identify anti-patterns.\n",
    ]

    lines.append("## Existing Patterns\n")
    for pat in existing_patterns:
        lines.append(f"- **{pat.name}** ({pat.category}): {pat.signature}")
        if pat.consequence:
            lines.append(f"  Consequence: {pat.consequence}")
        lines.append(f"  Seen {pat.frequency}x, strength: {pat.strength}")
        lines.append("")

    lines.append("## Episode Clusters by Theme\n")
    for theme, eps in sorted(theme_episodes.items(), key=lambda x: -len(x[1])):
        if len(eps) < 2:
            continue
        lines.append(f"### Theme: {theme} ({len(eps)} episodes)\n")
        for ep in eps[:10]:
            lines.append(f"- [{ep.date}] {ep.trigger}")
            if ep.learned:
                lines.append(f"  Learned: {ep.learned}")
            if ep.emotion != "neutral":
                lines.append(f"  Emotion: {ep.emotion} ({ep.intensity})")
        lines.append("")

    lines.extend([
        "## Expected Output\n",
        "Return a JSON object:",
        "```json",
        "{",
        '  "patterns_to_create": [{"name": "...", "category": "bug|design|anti|smell", "signature": "...", "consequence": "...", "response": "...", "trigger_cues": [...]}],',
        '  "patterns_to_merge": [{"from_names": ["...", "..."], "into": {"name": "...", "signature": "...", "consequence": "...", "response": "..."}}],',
        '  "patterns_to_update": [{"name": "...", "updates": {"signature": "...", "response": "..."}}]',
        "}",
        "```",
    ])

    return "\n".join(lines)


def _build_gist_generation_prompt(
    module: str,
    episodes: list,
    existing_gist=None,
) -> str:
    """Build prompt for LLM to generate/update a module gist."""
    lines = [
        f"# Gist Generation: {module}\n",
        f"Generate a semantic understanding (gist) for the `{module}` module",
        "based on the following episodes.\n",
    ]

    if existing_gist:
        lines.append("## Current Gist\n")
        if existing_gist.what_it_does:
            lines.append(f"What it does: {existing_gist.what_it_does}")
        if existing_gist.why_it_exists:
            lines.append(f"Why it exists: {existing_gist.why_it_exists}")
        if existing_gist.how_it_works:
            lines.append(f"How it works: {existing_gist.how_it_works}")
        if existing_gist.judgment:
            lines.append(f"Judgment: {existing_gist.judgment}")
        lines.append("")

    lines.append(f"## Episodes ({len(episodes)})\n")
    for ep in episodes[:20]:
        lines.append(f"- [{ep.date}] {ep.trigger}")
        if ep.learned:
            lines.append(f"  Learned: {ep.learned}")
        if ep.emotion != "neutral":
            lines.append(f"  Emotion: {ep.emotion} ({ep.intensity})")
        if ep.code_touched:
            lines.append(f"  Files: {', '.join(ep.code_touched[:5])}")
        lines.append("")

    lines.extend([
        "## Expected Output\n",
        "Return a JSON object:",
        "```json",
        "{",
        f'  "target": "{module}",',
        '  "what_it_does": "one sentence",',
        '  "why_it_exists": "one sentence",',
        '  "how_it_works": "2-3 sentences",',
        '  "key_relationships": "what it connects to",',
        '  "judgment": "fragile | solid | improving | unknown"',
        "}",
        "```",
    ])

    return "\n".join(lines)

"""Recall engine — 7-stage retrieval pipeline."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Optional

from cogmem.models import (
    BUDGET_TABLE,
    EmotionsFile,
    Episode,
    Gist,
    Pattern,
    Prospective,
    RepoSpatial,
    Tier,
)
from cogmem.storage.index import KeywordIndex
from cogmem.tiers.global_mem import GlobalTier
from cogmem.tiers.repo import RepoTier
from cogmem.tiers.workspace import WorkspaceTier, detect_workspace
from cogmem.utils.cues import CueSet, detect_task_type, extract_cues
from cogmem.utils.repo_detect import find_project_root, find_repo_root
from cogmem.utils.scoring import compute_score
from cogmem.utils.tokens import allocate_budget, estimate_tokens, truncate_to_budget


def recall(
    query: str,
    repo_only: bool = False,
    workspace_only: bool = False,
    budget: int = 3500,
    cwd: str | None = None,
    task_type: str | None = None,
    files: list[str] | None = None,
) -> str:
    """Full 7-stage recall pipeline."""
    cwd_path = Path(cwd) if cwd else Path.cwd()

    # Stage 1: Cue extraction
    cues = extract_cues(query)
    if files:
        cues.file_paths.extend(files)

    # Stage 2: Determine search scope
    scopes = _determine_scope(cwd_path, cues, repo_only, workspace_only)

    if not scopes:
        return "No memory found. Run `cogmem bootstrap` to initialize."

    # Stage 3: Multi-tier search
    all_matches = []
    for scope_type, scope_path, tier_weight in scopes:
        matches = _search_tier(scope_type, scope_path, cues, tier_weight)
        all_matches.extend(matches)

    if not all_matches:
        return "No relevant memories found."

    # Stage 4: Convergence scoring (already done in _search_tier)
    all_matches.sort(key=lambda m: m["_score"], reverse=True)

    # Stage 5: Task type detection
    effective_task_type = task_type or detect_task_type(query)

    # Stage 6: Budget allocation
    allocation = allocate_budget(effective_task_type, budget)

    # Stage 7: Assembly + metamemory
    return _assemble_output(all_matches, allocation, cues, effective_task_type)


def search_memories(query: str, mem_type: str | None = None, cwd: str | None = None) -> str:
    """Search memories filtered by type."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)
    repo = RepoTier(repo_root)
    if not repo.exists:
        return "No memory found. Run `cogmem bootstrap` first."

    cues = extract_cues(query)
    results = []

    if mem_type in (None, "episodes"):
        for ep in repo.list_episodes():
            if _matches_cues(ep.model_dump(), cues):
                results.append(f"[episode] {ep.date} — {ep.trigger}: {ep.learned}")

    if mem_type in (None, "patterns"):
        for p in repo.list_patterns():
            if _matches_cues(p.model_dump(), cues):
                results.append(f"[pattern] {p.name}: {p.signature}")

    if mem_type in (None, "gist"):
        for g in repo.list_gists():
            if _matches_cues(g.model_dump(), cues):
                results.append(f"[gist] {g.target}: {g.what_it_does}")

    if mem_type in (None, "prospective"):
        for pr in repo.list_prospectives():
            if _matches_cues(pr.model_dump(), cues):
                results.append(f"[intention] {pr.intention} (trigger: {pr.trigger})")

    return "\n".join(results) if results else "No matches found."


def get_dangers(files: list[str], cwd: str | None = None) -> str:
    """Get danger warnings for specific files."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)
    repo = RepoTier(repo_root)
    if not repo.exists:
        return "No memory found."

    emotions = repo.get_emotions()
    warnings = []

    for tag in emotions.tags:
        if tag.emotion in ("pain", "danger"):
            if not files or any(tag.target in f or f in tag.target for f in files):
                warnings.append(f"  {tag.emotion.upper()}: {tag.target} — {tag.reason} (intensity: {tag.intensity})")

    # Also check workspace
    ws_path = detect_workspace(cwd_path)
    if ws_path:
        ws = WorkspaceTier(ws_path)
        ws_emotions = ws.get_emotions()
        for tag in ws_emotions.tags:
            if tag.emotion in ("pain", "danger"):
                warnings.append(f"  {tag.emotion.upper()} [workspace]: {tag.target} — {tag.reason}")

    if not warnings:
        return "No danger warnings."
    return "DANGER WARNINGS:\n" + "\n".join(warnings)


def get_intentions(cwd: str | None = None) -> str:
    """Get pending prospective memories."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)
    repo = RepoTier(repo_root)
    if not repo.exists:
        return "No memory found."

    items = [p for p in repo.list_prospectives() if not p.completed]

    if not items:
        return "No pending intentions."

    lines = ["PENDING INTENTIONS:"]
    for p in items:
        lines.append(f"  [{p.priority}] {p.intention}")
        lines.append(f"    Trigger: {p.trigger}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _determine_scope(
    cwd: Path, cues: CueSet, repo_only: bool, workspace_only: bool
) -> list[tuple[str, Path, float]]:
    """Stage 2: Determine which tiers to search."""
    scopes = []
    repo_root = find_repo_root(cwd)

    if repo_root and not workspace_only:
        repo = RepoTier(repo_root)
        if repo.exists:
            scopes.append(("repo", repo_root, 1.0))
    elif not workspace_only and (cwd / ".memory").is_dir():
        # No git repo but .memory/ exists
        scopes.append(("repo", cwd, 1.0))

    ws_path = detect_workspace(cwd)
    if ws_path and not repo_only:
        ws = WorkspaceTier(ws_path)
        if ws.exists:
            scopes.append(("workspace", ws_path, 0.9))

    if not repo_only and not workspace_only:
        global_tier = GlobalTier()
        if global_tier.exists:
            scopes.append(("global", global_tier.root, 0.8))

    return scopes


def _search_tier(
    scope_type: str, scope_path: Path, cues: CueSet, tier_weight: float
) -> list[dict]:
    """Stage 3: Search a single tier and score results."""
    matches = []

    if scope_type == "repo":
        repo = RepoTier(scope_path)
        index = repo.get_index()

        # Query index
        refs = index.query(cues.keywords)
        indexed_refs = {ref for ref, _ in refs}

        # Load and score episodes
        for ep in repo.list_episodes():
            data = ep.model_dump()
            data["_type"] = "episode"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "repo"
            matches.append(data)

        # Load and score gists
        for g in repo.list_gists():
            data = g.model_dump()
            data["_type"] = "gist"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "repo"
            matches.append(data)

        # Patterns
        for p in repo.list_patterns():
            data = p.model_dump()
            data["_type"] = "pattern"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "repo"
            matches.append(data)

        # Emotions (as dangers)
        emotions = repo.get_emotions()
        for tag in emotions.tags:
            data = tag.model_dump()
            data["_type"] = "danger"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "repo"
            matches.append(data)

        # Entities
        for e in repo.list_entities():
            data = e.model_dump()
            data["_type"] = "entity"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "repo"
            matches.append(data)

        # Prospective
        for p in repo.list_prospectives():
            if not p.completed:
                data = p.model_dump()
                data["_type"] = "prospective"
                data["_score"] = compute_score(data, cues, tier_weight)
                data["_tier"] = "repo"
                matches.append(data)

        # Spatial
        spatial = repo.get_spatial()
        if spatial:
            data = spatial.model_dump()
            data["_type"] = "spatial"
            data["_score"] = 0.3 * tier_weight  # baseline
            data["_tier"] = "repo"
            matches.append(data)

    elif scope_type == "workspace":
        ws = WorkspaceTier(scope_path)

        for ep in ws.list_episodes():
            data = ep.model_dump()
            data["_type"] = "episode"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "workspace"
            matches.append(data)

        for g in ws.list_gists():
            data = g.model_dump()
            data["_type"] = "gist"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "workspace"
            matches.append(data)

        for p in ws.list_patterns():
            data = p.model_dump()
            data["_type"] = "pattern"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "workspace"
            matches.append(data)

        emotions = ws.get_emotions()
        for tag in emotions.tags:
            data = tag.model_dump()
            data["_type"] = "danger"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "workspace"
            matches.append(data)

    elif scope_type == "global":
        gt = GlobalTier(scope_path)
        for p in gt.list_patterns():
            data = p.model_dump()
            data["_type"] = "pattern"
            data["_score"] = compute_score(data, cues, tier_weight)
            data["_tier"] = "global"
            matches.append(data)

    return matches


def _matches_cues(data: dict, cues: CueSet) -> bool:
    """Quick check if a memory dict matches any cues."""
    from cogmem.utils.scoring import _memory_text
    text = _memory_text(data).lower()
    return any(kw in text for kw in cues.keywords)


def _assemble_output(
    matches: list[dict], allocation: dict[str, int], cues: CueSet, task_type: str
) -> str:
    """Stage 7: Assemble final output within budget."""
    sections: dict[str, list[str]] = {
        "gist": [],
        "episodes": [],
        "patterns": [],
        "dangers": [],
        "entities": [],
        "spatial": [],
        "prospective": [],
    }

    # Map memory types to section names
    type_to_section = {
        "gist": "gist",
        "episode": "episodes",
        "pattern": "patterns",
        "danger": "dangers",
        "entity": "entities",
        "spatial": "spatial",
        "prospective": "prospective",
    }

    for m in matches:
        section = type_to_section.get(m.get("_type", ""), "episodes")
        line = _format_memory_line(m)
        if line:
            sections[section].append(line)

    # Build output within budget
    output_parts = []
    total_used = 0

    section_labels = {
        "gist": "UNDERSTANDING",
        "episodes": "PAST EXPERIENCES",
        "patterns": "PATTERNS",
        "dangers": "DANGER WARNINGS",
        "entities": "CODE ENTITIES",
        "spatial": "SPATIAL MAP",
        "prospective": "REMINDERS",
    }

    for section_key, label in section_labels.items():
        budget = allocation.get(section_key, 0)
        items = sections[section_key]
        if not items or budget == 0:
            continue

        section_text = f"\n--- {label} ---\n"
        used = estimate_tokens(section_text)

        for item in items:
            item_tokens = estimate_tokens(item)
            if used + item_tokens > budget:
                break
            section_text += item + "\n"
            used += item_tokens

        output_parts.append(section_text)
        total_used += used

    # Metamemory footer
    meta = f"\n[Memory: {task_type} mode | {len(matches)} candidates | {total_used}/{sum(allocation.values())} tokens used]"
    output_parts.append(meta)

    return "".join(output_parts)


def _format_memory_line(m: dict) -> str:
    """Format a single memory match as a readable line."""
    mtype = m.get("_type", "")
    tier = m.get("_tier", "")
    tier_tag = f" [{tier}]" if tier != "repo" else ""

    if mtype == "episode":
        return f"  {m.get('date', '?')}{tier_tag} — {m.get('trigger', '')}: {m.get('learned', m.get('story', '')[:80])}"

    if mtype == "gist":
        return f"  {m.get('target', '?')}{tier_tag}: {m.get('what_it_does', '')}"

    if mtype == "pattern":
        return f"  PATTERN{tier_tag}: {m.get('name', '')} — {m.get('signature', '')}"

    if mtype == "danger":
        emotion = m.get("emotion", "danger").upper()
        return f"  {emotion}{tier_tag}: {m.get('target', '')} — {m.get('reason', '')}"

    if mtype == "entity":
        return f"  {m.get('kind', '')} {m.get('name', '')} ({m.get('file_path', '')}): {m.get('summary', '')}"

    if mtype == "spatial":
        landmarks = m.get("landmarks", [])
        if landmarks:
            parts = [f"  {lm.get('path', '')}: {lm.get('description', '')}" for lm in landmarks[:5]]
            return "\n".join(parts)
        return ""

    if mtype == "prospective":
        return f"  REMINDER: {m.get('intention', '')} (trigger: {m.get('trigger', '')})"

    return ""

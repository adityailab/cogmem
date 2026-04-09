"""Encode engine — create and store memories."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from cogmem.models import (
    EmotionTag,
    EmotionType,
    Episode,
    EpisodeSource,
    Phase,
    Tier,
)
from cogmem.storage.index import extract_keywords
from cogmem.tiers.repo import RepoTier
from cogmem.tiers.workspace import WorkspaceTier, detect_workspace
from cogmem.utils.emotion_detect import detect_emotion
from cogmem.utils.repo_detect import detect_repo_for_file, find_project_root, find_repo_root


def encode(
    event: str,
    emotion: str = "neutral",
    intensity: float = 0.5,
    code_touched: list[str] | None = None,
    learned: str = "",
    manual: bool = False,
    cwd: str | None = None,
) -> str:
    """Encode a new episode from an event."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    code_touched = code_touched or []

    # Determine tier based on repos involved
    repos = set()
    for f in code_touched:
        repo = detect_repo_for_file(f)
        if repo:
            repos.add(repo)

    if not repos:
        repo_root = find_repo_root(cwd_path)
        if repo_root:
            repos.add(repo_root)

    if not repos:
        # No git repo — use cwd if .memory/ exists or can be created
        repos.add(cwd_path)

    # Auto-detect emotion if not explicitly set
    if emotion == "neutral" and event:
        file_context: dict[str, str] = {}
        if repos:
            repo_path = next(iter(repos))
            r = RepoTier(repo_path)
            if r.exists:
                for tag in r.get_emotions().tags:
                    file_context[tag.target] = tag.emotion
        emotion, intensity = detect_emotion(event, file_context)

    today = date.today().isoformat()
    trigger = _extract_trigger(event)

    ep = Episode(
        date=today,
        trigger=trigger,
        story=event,
        learned=learned,
        emotion=emotion,
        intensity=intensity,
        code_touched=code_touched,
        source=EpisodeSource.LIVED if not manual else EpisodeSource.AUTO_GENERATED,
        source_confidence=1.0 if not manual else 0.8,
        strength=1.0,
        phase=Phase.VIVID,
    )

    if len(repos) == 1:
        # Single repo episode
        repo_path = repos.pop()
        repo = RepoTier(repo_path)
        if not repo.exists:
            repo.init()
        ep.tier = Tier.REPO
        ep.save(str(repo.dir.resolve(f"episodes/{ep.filename}")))

        # Update index
        index = repo.get_index()
        keywords = extract_keywords(f"{event} {learned} {' '.join(code_touched)}")
        index.add_entry(keywords, f"episodes/{ep.filename}")

        # Update emotions if significant
        if intensity >= 0.6 and emotion != "neutral":
            for f in code_touched:
                repo.update_emotion(EmotionTag(
                    target=f,
                    emotion=emotion,
                    intensity=intensity,
                    reason=learned or trigger,
                    last_reinforced=today,
                ))

        # Post-encode side effects
        notices = _post_encode(repo, ep, keywords, index)
        repo.save_index(index)

        msg = f"Encoded episode: {ep.filename} (repo: {repo_path.name})"
        if notices:
            msg += "\n" + "\n".join(notices)
        return msg

    else:
        # Cross-repo episode -> workspace
        ws_path = detect_workspace(cwd_path)
        if not ws_path:
            # Fall back to first repo
            repo_path = sorted(repos)[0]
            repo = RepoTier(repo_path)
            if not repo.exists:
                repo.init()
            ep.tier = Tier.REPO
            ep.save(str(repo.dir.resolve(f"episodes/{ep.filename}")))
            return f"Encoded episode: {ep.filename} (repo: {repo_path.name}, no workspace)"

        ws = WorkspaceTier(ws_path)
        if not ws.exists:
            ws.init()
        ep.tier = Tier.WORKSPACE
        ep.repos_involved = [r.name for r in repos]
        ep.save(str(ws.dir.resolve(f"episodes/{ep.filename}")))

        # Also index in each repo
        keywords = extract_keywords(f"{event} {learned}")
        for repo_path in repos:
            repo = RepoTier(repo_path)
            if repo.exists:
                index = repo.get_index()
                index.add_entry(keywords, f"workspace:episodes/{ep.filename}")
                repo.save_index(index)

        return f"Encoded cross-repo episode: {ep.filename} (repos: {', '.join(ep.repos_involved)})"


def encode_git(since: str = "7d", cwd: str | None = None) -> str:
    """Parse git log into synthetic episodes."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_repo_root(cwd_path)
    if not repo_root:
        return "Not inside a git repository."

    repo = RepoTier(repo_root)
    if not repo.exists:
        repo.init()

    # Parse git log
    try:
        result = subprocess.run(
            ["git", "log", f"--since={since}", "--format=%H|%s|%an|%ad", "--date=short", "--name-only"],
            cwd=str(repo_root),
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return f"Git error: {result.stderr.strip()}"
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        return f"Git error: {e}"

    commits = _parse_git_log(result.stdout)
    if not commits:
        return f"No commits found in the last {since}."

    # Group commits by theme (simple: by date)
    episodes_created = 0
    index = repo.get_index()

    for commit in commits:
        emotion, intensity = detect_emotion(commit["subject"])

        ep = Episode(
            date=commit["date"],
            trigger=commit["subject"],
            story=commit["subject"],
            learned="",
            emotion=emotion,
            intensity=intensity,
            code_touched=commit["files"],
            people_involved=[commit["author"]] if commit["author"] else [],
            source=EpisodeSource.GIT_INFERRED,
            source_confidence=0.5,
            strength=0.7,
            phase=Phase.VIVID,
        )
        ep.save(str(repo.dir.resolve(f"episodes/{ep.filename}")))

        keywords = extract_keywords(f"{commit['subject']} {' '.join(commit['files'])}")
        index.add_entry(keywords, f"episodes/{ep.filename}")
        episodes_created += 1

    repo.save_index(index)
    return f"Encoded {episodes_created} episodes from git history ({since})."


def hook_encode(tool: str, tool_input_file: str, cwd: str | None = None) -> None:
    """Lightweight hook handler for PostToolUse auto-encoding.

    Appends event to session queue for batch processing.
    """
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)
    repo = RepoTier(repo_root)
    if not repo.exists:
        return

    # Read the tool input to get file path
    try:
        with open(tool_input_file) as f:
            tool_input = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        return

    file_path = tool_input.get("file_path", tool_input.get("path", ""))
    if not file_path:
        return

    # Append to session queue
    session_file = repo.dir.resolve("sessions/current.json")
    session_file.parent.mkdir(parents=True, exist_ok=True)

    events = []
    if session_file.exists():
        try:
            with open(session_file) as f:
                events = json.load(f)
        except json.JSONDecodeError:
            events = []

    events.append({
        "tool": tool,
        "file": file_path,
        "timestamp": datetime.now().isoformat(),
    })

    with open(session_file, "w") as f:
        json.dump(events, f, indent=2)


def encode_annotations(cwd: str | None = None) -> str:
    """Scan source for @memory: annotations and encode them."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_project_root(cwd_path)
    repo = RepoTier(repo_root)
    if not repo.exists:
        repo.init()

    # Grep for @memory: annotations
    try:
        result = subprocess.run(
            ["grep", "-rn", "@memory:", str(repo_root),
             "--include=*.py", "--include=*.js", "--include=*.ts",
             "--include=*.go", "--include=*.rs", "--include=*.java",
             "--include=*.rb"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return "Could not scan for annotations."

    if not result.stdout.strip():
        return "No @memory: annotations found."

    count = 0
    today = date.today().isoformat()
    index = repo.get_index()

    for line in result.stdout.strip().split("\n"):
        match = re.match(r"(.+?):(\d+):.*@memory:\s*(.+)", line)
        if not match:
            continue

        filepath, lineno, content = match.groups()
        rel_path = str(Path(filepath).relative_to(repo_root))
        emotion, intensity = detect_emotion(content.strip())

        ep = Episode(
            date=today,
            trigger=f"annotation in {rel_path}:{lineno}",
            story=content.strip(),
            learned=content.strip(),
            emotion=emotion,
            intensity=intensity,
            code_touched=[rel_path],
            source=EpisodeSource.AUTO_GENERATED,
            source_confidence=0.8,
            strength=0.8,
            phase=Phase.VIVID,
        )
        ep.save(str(repo.dir.resolve(f"episodes/{ep.filename}")))
        keywords = extract_keywords(content)
        index.add_entry(keywords, f"episodes/{ep.filename}")
        count += 1

    repo.save_index(index)
    return f"Encoded {count} annotations as episodes."


# ---------------------------------------------------------------------------
# Post-encode side effects
# ---------------------------------------------------------------------------

def _post_encode(
    repo: RepoTier,
    episode: Episode,
    keywords: list[str],
    index: "KeywordIndex",
) -> list[str]:
    """Run side effects after encoding: prospective completion, pattern matching, cross-refs."""
    notices: list[str] = []
    today = date.today().isoformat()

    # 1. Check prospective memory completion
    for p in repo.list_prospectives():
        if p.completed:
            continue
        if p.matches_context(episode.code_touched, keywords):
            p.completed = True
            p.save(str(repo.dir.resolve(f"prospective/{p.filename}")))
            episode.triggered_prospective.append(p.id)
            notices.append(f"  Completed intention: {p.intention}")

    # 2. Match against existing patterns
    for pat in repo.list_patterns():
        if not pat.trigger_cues:
            continue
        overlap = set(kw.lower() for kw in keywords) & set(c.lower() for c in pat.trigger_cues)
        if overlap:
            pat.frequency += 1
            pat.last_seen = today
            if episode.id not in pat.seen_in:
                pat.seen_in.append(episode.id)
            pat.save(str(repo.dir.resolve(f"patterns/{pat.filename}")))
            if episode.id not in episode.related_patterns:
                episode.related_patterns.append(pat.id)
            notices.append(f"  Matched pattern: {pat.name} (seen {pat.frequency}x)")

    # 3. Cross-reference with related episodes (same files)
    if episode.code_touched:
        file_keywords = []
        for f in episode.code_touched[:5]:
            file_keywords.extend(extract_keywords(f))
        if file_keywords:
            refs = index.query(file_keywords)
            related = []
            for ref, count in refs[:5]:
                if ref.startswith("episodes/") and ref != f"episodes/{episode.filename}":
                    related.append(ref)
            if related:
                episode.related_episodes = related[:3]

    # 4. Link to entities matching touched files
    if episode.code_touched:
        for entity in repo.list_entities():
            if any(entity.file_path in f or f in entity.file_path for f in episode.code_touched):
                if entity.id not in episode.related_entities:
                    episode.related_entities.append(entity.id)
                if len(episode.related_entities) >= 10:
                    break

    # Re-save episode if side effects modified it
    if (episode.triggered_prospective or episode.related_patterns
            or episode.related_episodes or episode.related_entities):
        episode.save(str(repo.dir.resolve(f"episodes/{episode.filename}")))

    return notices


def finalize_session(cwd: str | None = None) -> str:
    """Process queued hook events into episode(s).

    Groups events by temporal proximity (30-min gaps) and creates
    one episode per cluster.
    """
    cwd_path = Path(cwd) if cwd else Path.cwd()
    repo_root = find_repo_root(cwd_path)
    if not repo_root:
        repo_root = cwd_path

    repo = RepoTier(repo_root)
    if not repo.exists:
        return "No memory initialized."

    session_file = repo.dir.resolve("sessions/current.json")
    if not session_file.exists():
        return "No session events to process."

    try:
        with open(session_file) as f:
            events = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return "Could not parse session file."

    if not events:
        return "No session events to process."

    # Cluster events by temporal proximity
    clusters = _cluster_by_time(events)

    today = date.today().isoformat()
    index = repo.get_index()
    created = 0

    for cluster in clusters:
        files = list({ev.get("file", "unknown") for ev in cluster})
        tools = list({ev.get("tool", "") for ev in cluster})
        meta = _cluster_metadata(cluster)
        activity = _infer_activity_type(cluster)

        duration_str = f"{meta['duration_minutes']}m" if meta["duration_minutes"] > 0 else "quick"
        trigger = f"Session: {activity} on {len(files)} files ({duration_str})"
        story = f"Used {', '.join(tools)} on: {', '.join(files[:10])}"
        if meta["start_time"] and meta["end_time"]:
            story += f"\nTime: {meta['start_time']} - {meta['end_time']}"

        emotion, intensity = detect_emotion(story)

        ep = Episode(
            date=today,
            trigger=trigger,
            story=story,
            emotion=emotion,
            intensity=intensity,
            code_touched=files,
            source=EpisodeSource.AUTO_GENERATED,
            source_confidence=0.6,
            strength=0.8,
            phase=Phase.VIVID,
        )
        ep.save(str(repo.dir.resolve(f"episodes/{ep.filename}")))
        keywords = extract_keywords(" ".join(files))
        index.add_entry(keywords, f"episodes/{ep.filename}")
        created += 1

    repo.save_index(index)
    session_file.unlink()

    return f"Finalized session: {created} episodes from {len(events)} events across {len(clusters)} clusters."


def _cluster_by_time(
    events: list[dict],
    gap_threshold_minutes: int = 30,
) -> list[list[dict]]:
    """Group events by temporal proximity.

    Events within gap_threshold_minutes of each other form one cluster.
    """
    if not events:
        return []

    # Sort by timestamp
    def parse_ts(ev: dict) -> datetime:
        ts = ev.get("timestamp", "")
        try:
            return datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            return datetime.now()

    sorted_events = sorted(events, key=parse_ts)

    clusters: list[list[dict]] = [[sorted_events[0]]]
    for ev in sorted_events[1:]:
        prev_ts = parse_ts(clusters[-1][-1])
        curr_ts = parse_ts(ev)
        gap = (curr_ts - prev_ts).total_seconds() / 60

        if gap > gap_threshold_minutes:
            clusters.append([ev])
        else:
            clusters[-1].append(ev)

    return clusters


def _infer_activity_type(events: list[dict]) -> str:
    """Infer activity type from tool names and file patterns."""
    tools = {ev.get("tool", "").lower() for ev in events}
    files = {ev.get("file", "").lower() for ev in events}

    test_files = any("test" in f for f in files)
    if test_files and "write" in tools:
        return "testing"

    if any(f.endswith((".md", ".txt", ".rst")) for f in files):
        return "documenting"

    write_count = sum(1 for ev in events if ev.get("tool", "").lower() in ("write", "edit"))
    read_count = sum(1 for ev in events if ev.get("tool", "").lower() == "read")

    if write_count == 0 and read_count > 0:
        return "exploring"
    if write_count > 3:
        return "coding"

    return "coding"


def _cluster_metadata(cluster: list[dict]) -> dict:
    """Extract start_time, end_time, duration from a cluster."""
    timestamps = []
    for ev in cluster:
        ts = ev.get("timestamp", "")
        try:
            timestamps.append(datetime.fromisoformat(ts))
        except (ValueError, TypeError):
            continue

    if not timestamps:
        return {"start_time": None, "end_time": None, "duration_minutes": 0}

    start = min(timestamps)
    end = max(timestamps)
    duration = int((end - start).total_seconds() / 60)

    return {
        "start_time": start.strftime("%H:%M"),
        "end_time": end.strftime("%H:%M"),
        "duration_minutes": duration,
    }


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_trigger(text: str) -> str:
    """Extract a short trigger from event text."""
    # First sentence or first 60 chars
    first = text.split(". ")[0].split("\n")[0]
    return first[:60]


def _parse_git_log(output: str) -> list[dict]:
    """Parse git log output into structured commits."""
    commits = []
    current: dict | None = None

    for line in output.split("\n"):
        if "|" in line and line.count("|") >= 3:
            if current:
                commits.append(current)
            parts = line.split("|", 3)
            current = {
                "hash": parts[0].strip(),
                "subject": parts[1].strip(),
                "author": parts[2].strip(),
                "date": parts[3].strip() if len(parts) > 3 else date.today().isoformat(),
                "files": [],
            }
        elif current and line.strip():
            current["files"].append(line.strip())

    if current:
        commits.append(current)

    return commits


def _detect_git_emotion(subject: str) -> tuple[str, float]:
    """Detect emotion from git commit subject."""
    subject_lower = subject.lower()

    if any(w in subject_lower for w in ["revert", "hotfix", "urgent", "critical"]):
        return "pain", 0.8
    if any(w in subject_lower for w in ["fix", "bug", "patch", "repair"]):
        return "frustration", 0.6
    if any(w in subject_lower for w in ["refactor", "clean", "simplify"]):
        return "relief", 0.4
    if any(w in subject_lower for w in ["add", "feat", "feature", "new", "implement"]):
        return "curiosity", 0.4
    if any(w in subject_lower for w in ["test", "spec"]):
        return "trust", 0.3

    return "neutral", 0.3

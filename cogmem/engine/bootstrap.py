"""Bootstrap engine — initialize memory from git history and file tree."""

from __future__ import annotations

import ast
import re
import subprocess
from collections import Counter, defaultdict
from datetime import date
from pathlib import Path
from typing import Optional

from cogmem.models import (
    CodeEntity,
    EmotionTag,
    Episode,
    EpisodeSource,
    Gist,
    GistScope,
    Landmark,
    Pattern,
    PatternCategory,
    Phase,
    RepoSpatial,
    SpatialEntry,
    Tier,
    WorkspaceSpatial,
)
from cogmem.storage.index import KeywordIndex, extract_keywords
from cogmem.tiers.global_mem import GlobalTier
from cogmem.tiers.repo import RepoTier
from cogmem.tiers.workspace import WorkspaceTier
from cogmem.utils.repo_detect import detect_repos_in_dir, find_repo_root


def bootstrap(
    months: int = 6,
    workspace_mode: bool = False,
    cwd: str | None = None,
) -> str:
    """Bootstrap memory for a repo or workspace."""
    cwd_path = Path(cwd) if cwd else Path.cwd()

    if workspace_mode:
        return bootstrap_workspace(cwd_path, months=months)

    repo_root = find_repo_root(cwd_path)
    if not repo_root:
        # No git repo — bootstrap in current directory without git history
        return bootstrap_repo(cwd_path, months=0)

    return bootstrap_repo(repo_root, months=months)


def bootstrap_repo(repo_path: Path, months: int = 6) -> str:
    """Initialize memory from a single repo's git history and file tree."""
    repo = RepoTier(repo_path)
    repo.init()

    stats: dict[str, int] = defaultdict(int)

    # Step 1: File tree -> spatial map
    spatial = _build_spatial_map(repo_path)
    repo.update_spatial(spatial)
    stats["spatial"] = len(spatial.surface) + len(spatial.middle) + len(spatial.deep)

    # Step 2: README -> codebase gist
    gist = _build_codebase_gist(repo_path)
    if gist:
        repo.save_gist(gist)
        stats["gists"] = 1

    # Step 3: Module gists — write prompts for subagent
    module_dirs = _find_module_dirs(repo_path)
    pending_dir = repo.dir.resolve(".pending")
    pending_dir.mkdir(parents=True, exist_ok=True)
    for mod_path in module_dirs:
        prompt = _build_module_gist_prompt(repo_path, mod_path)
        prompt_file = pending_dir / f"gist_{mod_path.name}.md"
        prompt_file.write_text(prompt)
        stats["module_prompts"] = stats.get("module_prompts", 0) + 1

    # Step 4: Git log -> synthetic episodes
    episodes = _git_log_to_episodes(repo_path, months=months)
    index = repo.get_index()
    for ep in episodes:
        ep.save(str(repo.dir.resolve(f"episodes/{ep.filename}")))
        keywords = extract_keywords(f"{ep.trigger} {' '.join(ep.code_touched)}")
        index.add_entry(keywords, f"episodes/{ep.filename}")
        stats["episodes"] = stats.get("episodes", 0) + 1

    # Step 5: Commit patterns -> emotional tags
    emotions = _detect_file_emotions(repo_path, episodes)
    for tag in emotions:
        repo.update_emotion(tag)
        stats["emotions"] = stats.get("emotions", 0) + 1

    # Step 6: Code analysis -> entity summaries
    entities = _extract_entities(repo_path)
    for entity in entities:
        repo.save_entity(entity)
        keywords = extract_keywords(f"{entity.name} {entity.file_path} {entity.kind}")
        index.add_entry(keywords, f"entities/{entity.filename}")
        stats["entities"] = stats.get("entities", 0) + 1

    # Step 7: Episode clustering -> initial patterns
    patterns = _cluster_episodes_to_patterns(episodes)
    for pat in patterns:
        repo.save_pattern(pat)
        keywords = extract_keywords(f"{pat.name} {pat.signature}")
        index.add_entry(keywords, f"patterns/{pat.filename}")
        stats["patterns"] = stats.get("patterns", 0) + 1

    # Step 8: Save keyword index
    repo.save_index(index)

    # Step 9: Scan @memory: annotations
    annotation_count = _scan_annotations(repo_path, repo, index)
    if annotation_count:
        repo.save_index(index)
        stats["annotations"] = annotation_count

    # Step 10: Import global patterns
    imported = _import_global_patterns(repo)
    stats["global_imported"] = imported

    parts = [f"Bootstrapped {repo_path.name}:"]
    for key, count in sorted(stats.items()):
        if count:
            parts.append(f"  {key}: {count}")
    return "\n".join(parts)


def bootstrap_workspace(workspace_path: Path, months: int = 6) -> str:
    """Bootstrap an entire workspace with multiple repos."""
    results: list[str] = []

    # Step 1: Detect all repos
    repos = detect_repos_in_dir(workspace_path)
    if not repos:
        return "No git repositories found in workspace."

    # Step 2: Bootstrap each repo
    for repo_path in repos:
        msg = bootstrap_repo(repo_path, months=months)
        results.append(msg)

    # Step 3-4: Initialize workspace tier
    ws = WorkspaceTier(workspace_path)
    ws.init()

    for repo_path in repos:
        ws.add_repo(str(repo_path))

    # Step 3: Write prompt for cross-repo analysis (subagent)
    pending_dir = ws.dir.resolve(".pending")
    pending_dir.mkdir(parents=True, exist_ok=True)
    prompt = _build_workspace_analysis_prompt(workspace_path, repos)
    (pending_dir / "workspace_analysis_prompt.md").write_text(prompt)

    # Step 4: Create minimal workspace gist
    platform_gist = Gist(
        scope=GistScope.PLATFORM,
        target=workspace_path.name,
        tier=Tier.WORKSPACE,
        what_it_does=f"Workspace with {len(repos)} repos: {', '.join(r.name for r in repos)}",
        last_updated=date.today().isoformat(),
    )
    ws.save_gist(platform_gist)

    # Step 4.5: Auto-detect cross-repo dependencies
    from cogmem.utils.deps import detect_cross_repo_deps, build_service_topology
    all_deps = []
    for repo_path in repos:
        deps = detect_cross_repo_deps(repo_path, repos)
        all_deps.extend(deps)
    if all_deps:
        topology = build_service_topology(all_deps, [r.name for r in repos])
        ws.update_spatial(topology)
        results.append(f"  Detected {len(all_deps)} cross-repo dependencies")

    # Step 5: Find cross-repo episodes (correlated by time)
    cross_eps = _find_cross_repo_episodes(repos, months)
    for ep in cross_eps:
        ws.save_episode(ep)

    # Step 6-7: Build workspace index
    ws_index = ws.get_index()
    for ep in cross_eps:
        keywords = extract_keywords(f"{ep.trigger} {' '.join(ep.code_touched)}")
        ws_index.add_entry(keywords, f"episodes/{ep.filename}")
    ws.save_index(ws_index)

    results.append(
        f"Workspace bootstrapped: {len(repos)} repos, "
        f"{len(cross_eps)} cross-repo episodes"
    )
    return "\n".join(results)


# ---------------------------------------------------------------------------
# Step 1: Spatial map
# ---------------------------------------------------------------------------

def _build_spatial_map(repo_path: Path) -> RepoSpatial:
    """Walk directory tree and classify into surface/middle/deep."""
    surface: list[SpatialEntry] = []
    middle: list[SpatialEntry] = []
    deep: list[SpatialEntry] = []
    landmarks: list[Landmark] = []

    # Classify top-level entries
    for item in sorted(repo_path.iterdir()):
        if item.name.startswith("."):
            continue
        rel = str(item.relative_to(repo_path))

        if item.is_file():
            desc = _describe_file(item)
            surface.append(SpatialEntry(path=rel, description=desc))
            if item.name.lower() in ("readme.md", "readme.rst", "readme.txt"):
                landmarks.append(Landmark(path=rel, description="Project README", why="main entry point for understanding"))
            elif item.name in ("pyproject.toml", "package.json", "Cargo.toml", "go.mod"):
                landmarks.append(Landmark(path=rel, description="Project manifest", why="defines dependencies and metadata"))
        elif item.is_dir():
            file_count = sum(1 for _ in item.rglob("*") if _.is_file() and not str(_.relative_to(repo_path)).startswith("."))
            desc = f"directory ({file_count} files)"
            if item.name in ("src", "lib", "app", "core", "internal"):
                middle.append(SpatialEntry(path=rel, description=desc, feel="core logic"))
            elif item.name in ("test", "tests", "spec", "specs", "__tests__"):
                surface.append(SpatialEntry(path=rel, description=desc, feel="test suite"))
            elif item.name in ("docs", "doc", "documentation"):
                surface.append(SpatialEntry(path=rel, description=desc, feel="documentation"))
            elif item.name in ("config", "conf", "settings"):
                surface.append(SpatialEntry(path=rel, description=desc, feel="configuration"))
            elif item.name in ("vendor", "node_modules", "venv", ".venv", "dist", "build"):
                deep.append(SpatialEntry(path=rel, description=desc, feel="generated/vendored"))
            else:
                middle.append(SpatialEntry(path=rel, description=desc))

    return RepoSpatial(
        surface=surface,
        middle=middle,
        deep=deep,
        landmarks=landmarks,
    )


def _describe_file(path: Path) -> str:
    """Short description of a file based on name/extension."""
    name = path.name.lower()
    if name in ("readme.md", "readme.rst"):
        return "project documentation"
    if name in ("license", "license.md"):
        return "license file"
    if name in ("pyproject.toml", "setup.py", "setup.cfg"):
        return "Python project config"
    if name in ("package.json",):
        return "Node.js project config"
    if name in ("cargo.toml",):
        return "Rust project config"
    if name in ("go.mod",):
        return "Go project config"
    if name in ("dockerfile", "docker-compose.yml", "docker-compose.yaml"):
        return "container config"
    if name in ("makefile",):
        return "build automation"
    if name.startswith("."):
        return "dotfile"
    return f"{path.suffix or 'file'}"


# ---------------------------------------------------------------------------
# Step 2: Codebase gist from README
# ---------------------------------------------------------------------------

def _build_codebase_gist(repo_path: Path) -> Optional[Gist]:
    """Create a minimal codebase gist from README if present."""
    for name in ("README.md", "README.rst", "README.txt", "README"):
        readme = repo_path / name
        if readme.exists():
            content = readme.read_text(errors="replace")[:2000]
            # Extract first paragraph as description
            paragraphs = content.split("\n\n")
            first_para = ""
            for p in paragraphs:
                stripped = p.strip().lstrip("# ")
                if stripped and not stripped.startswith("[") and len(stripped) > 20:
                    first_para = stripped[:200]
                    break

            return Gist(
                scope=GistScope.CODEBASE,
                target=repo_path.name,
                tier=Tier.REPO,
                what_it_does=first_para or f"Repository: {repo_path.name}",
                last_updated=date.today().isoformat(),
                confidence=0.4,  # low — derived from README, not LLM analysis
            )
    return None


# ---------------------------------------------------------------------------
# Step 3: Module gist prompts
# ---------------------------------------------------------------------------

def _find_module_dirs(repo_path: Path) -> list[Path]:
    """Identify top-level source directories that are likely modules."""
    modules = []
    for item in sorted(repo_path.iterdir()):
        if item.name.startswith(".") or item.name.startswith("_"):
            continue
        if not item.is_dir():
            continue
        if item.name in ("node_modules", "vendor", "venv", ".venv", "dist", "build",
                          "docs", "doc", "test", "tests", ".git"):
            continue
        # Has source files?
        source_exts = {".py", ".js", ".ts", ".go", ".rs", ".java", ".rb", ".tsx", ".jsx"}
        has_source = any(f.suffix in source_exts for f in item.rglob("*") if f.is_file())
        if has_source:
            modules.append(item)
    return modules


def _build_module_gist_prompt(repo_path: Path, mod_path: Path) -> str:
    """Build a prompt for the subagent to generate a module gist."""
    rel = mod_path.relative_to(repo_path)
    files = [str(f.relative_to(repo_path)) for f in sorted(mod_path.rglob("*"))
             if f.is_file() and not f.name.startswith(".")][:30]

    return (
        f"# Generate Module Gist: {rel}\n\n"
        f"Analyze the module at `{rel}` and create a gist with:\n"
        f"- what_it_does: one sentence\n"
        f"- why_it_exists: one sentence\n"
        f"- how_it_works: 2-3 sentences\n"
        f"- key_relationships: what it connects to\n"
        f"- judgment: fragile | solid | improving | unknown\n\n"
        f"## Files in module\n"
        + "\n".join(f"- {f}" for f in files)
    )


# ---------------------------------------------------------------------------
# Step 4: Git log -> synthetic episodes
# ---------------------------------------------------------------------------

def _git_log_to_episodes(repo_path: Path, months: int = 6) -> list[Episode]:
    """Parse git log into synthetic episodes."""
    try:
        result = subprocess.run(
            ["git", "log", f"--since={months} months ago",
             "--format=%H|%s|%an|%ad", "--date=short", "--name-only"],
            cwd=str(repo_path),
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            return []
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return []

    commits = _parse_git_log(result.stdout)
    episodes = []

    for commit in commits:
        emotion, intensity = _detect_git_emotion(commit["subject"])
        ep = Episode(
            date=commit["date"],
            trigger=commit["subject"][:60],
            story=commit["subject"],
            learned="",
            emotion=emotion,
            intensity=intensity,
            code_touched=commit["files"][:20],
            people_involved=[commit["author"]] if commit["author"] else [],
            source=EpisodeSource.GIT_INFERRED,
            source_confidence=0.5,
            strength=0.7,
            phase=Phase.VIVID,
        )
        episodes.append(ep)

    return episodes


def _parse_git_log(output: str) -> list[dict]:
    """Parse git log output."""
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
    """Detect emotion from commit subject."""
    s = subject.lower()
    if any(w in s for w in ["revert", "hotfix", "urgent", "critical"]):
        return "pain", 0.8
    if any(w in s for w in ["fix", "bug", "patch", "repair"]):
        return "frustration", 0.6
    if any(w in s for w in ["refactor", "clean", "simplify"]):
        return "relief", 0.4
    if any(w in s for w in ["add", "feat", "feature", "new", "implement"]):
        return "curiosity", 0.4
    if any(w in s for w in ["test", "spec"]):
        return "trust", 0.3
    return "neutral", 0.3


# ---------------------------------------------------------------------------
# Step 5: Emotional tags from patterns
# ---------------------------------------------------------------------------

def _detect_file_emotions(repo_path: Path, episodes: list[Episode]) -> list[EmotionTag]:
    """Detect emotional tags for files based on git patterns."""
    file_emotions: dict[str, list[tuple[str, float]]] = defaultdict(list)

    for ep in episodes:
        if ep.emotion == "neutral":
            continue
        for f in ep.code_touched:
            file_emotions[f].append((ep.emotion, ep.intensity))

    tags = []
    today = date.today().isoformat()
    for filepath, emo_list in file_emotions.items():
        if len(emo_list) < 2:
            continue
        # Find dominant emotion
        emotion_counts: Counter = Counter()
        total_intensity = 0.0
        for emo, intensity in emo_list:
            emotion_counts[emo] += 1
            total_intensity += intensity

        dominant = emotion_counts.most_common(1)[0][0]
        avg_intensity = total_intensity / len(emo_list)

        if avg_intensity >= 0.4:
            tags.append(EmotionTag(
                target=filepath,
                emotion=dominant,
                intensity=min(1.0, avg_intensity),
                reason=f"Detected from {len(emo_list)} git commits",
                last_reinforced=today,
            ))

    return tags


# ---------------------------------------------------------------------------
# Step 6: Entity extraction
# ---------------------------------------------------------------------------

def _extract_entities(repo_path: Path) -> list[CodeEntity]:
    """Extract function/class signatures from source files."""
    entities: list[CodeEntity] = []

    for py_file in repo_path.rglob("*.py"):
        if any(p.startswith(".") for p in py_file.relative_to(repo_path).parts):
            continue
        if any(p in str(py_file) for p in ["node_modules", "vendor", "venv", ".venv", "dist", "build"]):
            continue
        try:
            rel_path = str(py_file.relative_to(repo_path))
            source = py_file.read_text(errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                sig = f"class {node.name}"
                if node.bases:
                    base_names = []
                    for base in node.bases:
                        if isinstance(base, ast.Name):
                            base_names.append(base.id)
                        elif isinstance(base, ast.Attribute):
                            base_names.append(f"{_attr_name(base)}")
                    sig += f"({', '.join(base_names)})"
                entities.append(CodeEntity(
                    file_path=rel_path,
                    name=node.name,
                    kind="class",
                    signature=sig,
                ))
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                args = []
                for arg in node.args.args:
                    if arg.arg != "self":
                        args.append(arg.arg)
                sig = f"def {node.name}({', '.join(args)})"
                if isinstance(node, ast.AsyncFunctionDef):
                    sig = f"async {sig}"
                entities.append(CodeEntity(
                    file_path=rel_path,
                    name=node.name,
                    kind="method" if _is_method(node) else "function",
                    signature=sig,
                ))

    return entities


def _attr_name(node: ast.Attribute) -> str:
    """Get dotted name from an Attribute node."""
    if isinstance(node.value, ast.Name):
        return f"{node.value.id}.{node.attr}"
    return node.attr


def _is_method(node: ast.FunctionDef | ast.AsyncFunctionDef) -> bool:
    """Check if a function is inside a class (heuristic: has 'self' first arg)."""
    if node.args.args and node.args.args[0].arg == "self":
        return True
    return False


# ---------------------------------------------------------------------------
# Step 7: Episode clustering -> patterns
# ---------------------------------------------------------------------------

def _cluster_episodes_to_patterns(episodes: list[Episode]) -> list[Pattern]:
    """Group episodes by shared files and detect bug patterns."""
    file_episodes: dict[str, list[Episode]] = defaultdict(list)
    for ep in episodes:
        for f in ep.code_touched:
            file_episodes[f].append(ep)

    patterns = []
    today = date.today().isoformat()

    for filepath, eps in file_episodes.items():
        # Need multiple fix-type episodes on the same file
        fix_eps = [e for e in eps if e.emotion in ("pain", "frustration")]
        if len(fix_eps) < 3:
            continue

        name = f"recurring-fixes-{Path(filepath).stem}"
        patterns.append(Pattern(
            name=name,
            category=PatternCategory.BUG,
            tier=Tier.REPO,
            signature=f"File {filepath} has been fixed {len(fix_eps)} times",
            consequence="This file is fragile and frequently breaks.",
            response="Extra care and testing needed when modifying.",
            seen_in=[filepath],
            frequency=len(fix_eps),
            last_seen=today,
            trigger_cues=[filepath, Path(filepath).stem],
            strength=min(1.0, 0.3 + 0.1 * len(fix_eps)),
            danger_level="high" if len(fix_eps) >= 5 else "medium",
        ))

    return patterns


# ---------------------------------------------------------------------------
# Step 9: @memory annotations
# ---------------------------------------------------------------------------

def _scan_annotations(repo_path: Path, repo: RepoTier, index: KeywordIndex) -> int:
    """Grep for @memory: annotations in source."""
    try:
        result = subprocess.run(
            ["grep", "-rn", "@memory:", str(repo_path),
             "--include=*.py", "--include=*.js", "--include=*.ts",
             "--include=*.go", "--include=*.rs", "--include=*.java"],
            capture_output=True, text=True, timeout=30,
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return 0

    if not result.stdout.strip():
        return 0

    count = 0
    today = date.today().isoformat()

    for line in result.stdout.strip().split("\n"):
        match = re.match(r"(.+?):(\d+):.*@memory:\s*(.+)", line)
        if not match:
            continue
        filepath, lineno, content = match.groups()
        try:
            rel_path = str(Path(filepath).relative_to(repo_path))
        except ValueError:
            continue

        ep = Episode(
            date=today,
            trigger=f"annotation in {rel_path}:{lineno}",
            story=content.strip(),
            learned=content.strip(),
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

    return count


# ---------------------------------------------------------------------------
# Step 10: Import global patterns
# ---------------------------------------------------------------------------

def _import_global_patterns(repo: RepoTier) -> int:
    """Copy global patterns to repo if auto_import is enabled."""
    global_tier = GlobalTier()
    if not global_tier.exists:
        return 0

    prefs = global_tier.get_preferences()
    if not prefs.get("auto_import_on_bootstrap", True):
        return 0

    imported = 0
    existing = {p.name.lower() for p in repo.list_patterns()}
    for pattern in global_tier.list_patterns():
        if pattern.name.lower() not in existing:
            pattern.tier = Tier.REPO
            repo.save_pattern(pattern)
            imported += 1

    return imported


# ---------------------------------------------------------------------------
# Workspace: cross-repo episodes
# ---------------------------------------------------------------------------

def _find_cross_repo_episodes(repos: list[Path], months: int) -> list[Episode]:
    """Find commits that happened close in time across repos (same day)."""
    # Gather all commits by date
    date_commits: dict[str, list[dict]] = defaultdict(list)

    for repo_path in repos:
        try:
            result = subprocess.run(
                ["git", "log", f"--since={months} months ago",
                 "--format=%H|%s|%an|%ad", "--date=short"],
                cwd=str(repo_path),
                capture_output=True, text=True, timeout=30,
            )
            if result.returncode != 0:
                continue
        except (subprocess.TimeoutExpired, FileNotFoundError):
            continue

        for line in result.stdout.strip().split("\n"):
            if "|" not in line or line.count("|") < 3:
                continue
            parts = line.split("|", 3)
            d = parts[3].strip() if len(parts) > 3 else ""
            if d:
                date_commits[d].append({
                    "repo": repo_path.name,
                    "subject": parts[1].strip(),
                    "author": parts[2].strip(),
                })

    cross_episodes = []
    today = date.today().isoformat()

    for d, commits in date_commits.items():
        repos_on_date = set(c["repo"] for c in commits)
        if len(repos_on_date) < 2:
            continue

        # Create a cross-repo episode
        subjects = [f"[{c['repo']}] {c['subject']}" for c in commits[:5]]
        ep = Episode(
            date=d,
            trigger=f"Cross-repo activity on {d}",
            story="\n".join(subjects),
            tier=Tier.WORKSPACE,
            repos_involved=sorted(repos_on_date),
            source=EpisodeSource.GIT_INFERRED,
            source_confidence=0.4,
            strength=0.5,
            phase=Phase.CLEAR,
        )
        cross_episodes.append(ep)

    return cross_episodes[:50]  # cap


# ---------------------------------------------------------------------------
# Workspace analysis prompt
# ---------------------------------------------------------------------------

def _build_workspace_analysis_prompt(workspace_path: Path, repos: list[Path]) -> str:
    """Build a prompt for subagent workspace analysis."""
    lines = [
        "# Workspace Analysis Task\n",
        f"Workspace: {workspace_path}\n",
        "## Repos\n",
    ]
    for r in repos:
        readme = r / "README.md"
        desc = ""
        if readme.exists():
            first_line = readme.read_text(errors="replace").split("\n")[0].strip("# ")
            desc = f" — {first_line}"
        lines.append(f"- **{r.name}**{desc}")

    lines.extend([
        "\n## Task\n",
        "1. Identify cross-repo relationships (shared deps, APIs, data flow)",
        "2. Identify shared contracts and danger zones",
        "3. Generate a workspace spatial map",
        "4. Identify deployment topology if apparent",
    ])
    return "\n".join(lines)

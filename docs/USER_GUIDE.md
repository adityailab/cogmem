# cogmem User Guide

**Cognitive Codebase Memory** — a persistent memory system for developers using Claude Code.

cogmem models how a senior developer's brain holds a codebase: through stories, emotions, spatial awareness, and pattern recognition — not just keyword search. It remembers what happened, how you felt about it, and what you planned to do next time.

---

## Table of Contents

1. [Installation](#installation)
2. [Quick Start](#quick-start)
3. [Core Concepts](#core-concepts)
4. [Commands Reference](#commands-reference)
5. [Memory Types](#memory-types)
6. [Three-Tier Architecture](#three-tier-architecture)
7. [Retrieval Pipeline](#retrieval-pipeline)
8. [Claude Code Plugin](#claude-code-plugin)
9. [Multi-Repo Workspaces](#multi-repo-workspaces)
10. [Maintenance](#maintenance)
11. [Advanced Usage](#advanced-usage)
12. [Troubleshooting](#troubleshooting)

---

## Installation

### From PyPI (once published)

```bash
pip install cogmem
```

### From source

```bash
git clone https://github.com/yourusername/cogmem.git
cd cogmem
pip install -e .
```

### Verify installation

```bash
cogmem --version
# cogmem, version 0.1.0
```

If `cogmem` isn't found, add the Python scripts directory to your PATH:

```bash
# macOS
export PATH="$HOME/Library/Python/3.13/bin:$PATH"

# Linux
export PATH="$HOME/.local/bin:$PATH"
```

Add the export line to your `~/.zshrc` or `~/.bashrc` to make it permanent.

You can always use `python3 -m cogmem` as an alternative to the `cogmem` command.

---

## Quick Start

### 1. Bootstrap a repo

Navigate to any git repository and initialize memory:

```bash
cd /path/to/your-repo
cogmem bootstrap
```

This scans your git history and source code to create:
- A spatial map of your file tree
- Code entity signatures (classes, functions)
- Synthetic episodes from commit history
- Emotional tags for frequently-fixed files
- A keyword index for fast retrieval

Output:
```
Bootstrapped my-project:
  episodes: 47
  entities: 203
  patterns: 2
  emotions: 5
  spatial: 12
```

### 2. Recall before working

Before starting any task, ask cogmem what it knows:

```bash
cogmem recall "fix the auth timeout bug"
```

Output:
```
--- UNDERSTANDING ---
  auth: Handles user authentication and session management

--- PAST EXPERIENCES ---
  2026-01-15 — Fixed auth timeout: Connection pool exhaustion
  2026-02-03 — Auth session leak: Sessions not cleaned up on logout

--- DANGER WARNINGS ---
  PAIN: auth/login.py — Caused production outage (intensity: 0.85)

--- PATTERNS ---
  PATTERN: pool-exhaustion — Connection pool runs out under load

--- REMINDERS ---
  REMINDER: Add rate limiting to login (trigger: auth/login.py)

[Memory: bugfix mode | 234 candidates | 1847/3500 tokens used]
```

### 3. Encode what you learn

After solving a bug or learning something important:

```bash
cogmem encode \
  --event "Race condition in the queue processor caused duplicate jobs" \
  --emotion pain \
  --intensity 0.8 \
  --files queue/worker.py queue/dispatcher.py \
  --learned "Must acquire lock before dequeuing — use Redis BRPOPLPUSH for atomicity"
```

### 4. Mark important files

```bash
cogmem update --mark-dangerous auth/login.py --content "Caused two outages — handle with care"
cogmem update --mark-stable core/utils.py --content "Well tested, 100% coverage"
```

### 5. Check status

```bash
cogmem status
```

```
Repo: my-project
  Episodes:    52
  Gists:       8
  Patterns:    4
  Entities:    203
  Prospective: 3
  Emotions:    12
  Index keys:  891
```

---

## Core Concepts

cogmem is built on six cognitive principles:

| Principle | What it means |
|-----------|--------------|
| **Stories, not structures** | Memory is narrative-based. Episodes capture what happened, not just facts. |
| **Intent, not implementation** | Gists store *what code does and why*, not line-by-line details. |
| **Association, not search** | Retrieval is cue-driven — multiple signals converge to surface relevant memories. |
| **Emotion is the priority system** | Painful code is remembered vividly. Danger tags boost retrieval priority. |
| **Forgetting is expertise** | Details fade but patterns persist. Old episodes compress; important patterns strengthen. |
| **Memory breathes** | Output adapts to your current task — bugfix mode emphasizes past experiences and dangers; explore mode emphasizes spatial maps. |

---

## Commands Reference

### Retrieval

| Command | Description |
|---------|-------------|
| `cogmem recall <query>` | Recall relevant memories for a task |
| `cogmem recall <query> --repo-only` | Search only the current repo |
| `cogmem recall <query> --workspace-only` | Search only workspace-level memories |
| `cogmem recall <query> --budget 5000` | Customize token budget (default: 3500) |
| `cogmem search <query>` | Search memories by keyword |
| `cogmem search <query> --type episodes` | Filter by type: episodes, patterns, gist, prospective |
| `cogmem dangers` | Show all danger warnings |
| `cogmem dangers auth/login.py` | Show dangers for specific files |
| `cogmem intentions` | Show pending prospective memories (reminders) |

### Encoding

| Command | Description |
|---------|-------------|
| `cogmem encode --event "..." --learned "..."` | Encode a new episode |
| `cogmem encode --event "..." --emotion pain --intensity 0.8` | Encode with emotion |
| `cogmem encode --event "..." --files path/to/file.py` | Associate files with the episode |
| `cogmem encode --manual "..."` | Encode a manual note (lower confidence) |
| `cogmem encode-git` | Create episodes from recent git history (last 7 days) |
| `cogmem encode-git --since 30d` | Scan further back |
| `cogmem encode-annotations` | Scan source for `@memory:` comments |
| `cogmem hook-encode <tool> <file>` | Hook handler (used by Claude Code auto-encoding) |

### Corrections

| Command | Description |
|---------|-------------|
| `cogmem update --mark-dangerous <path>` | Tag a file/path as dangerous |
| `cogmem update --mark-stable <path>` | Tag a file/path as stable/trusted |
| `cogmem update --update-gist <target> --content "..."` | Update a module's gist |
| `cogmem update --add-pattern <name> --content "..."` | Add a named pattern |
| `cogmem forget <target>` | Remove memories matching a target |

### Maintenance

| Command | Description |
|---------|-------------|
| `cogmem consolidate` | Run full consolidation (compress, extract patterns, prune) |
| `cogmem consolidate --scope repo` | Consolidate repo tier only |
| `cogmem consolidate --scope workspace` | Consolidate workspace tier only |
| `cogmem decay` | Run strength decay on all memories |
| `cogmem status` | Show memory health |
| `cogmem status --repo` | Repo status only |

### Lifecycle

| Command | Description |
|---------|-------------|
| `cogmem bootstrap` | Initialize memory from git history and file tree |
| `cogmem bootstrap --months 12` | Scan more history (default: 6 months) |
| `cogmem bootstrap --workspace` | Bootstrap entire multi-repo workspace |
| `cogmem export <path>` | Export memory to a directory or tarball |
| `cogmem import <path>` | Import memory from a backup |

### Workspace

| Command | Description |
|---------|-------------|
| `cogmem workspace init` | Create `.cogmem/` in the current directory |
| `cogmem workspace add-repo <path>` | Register a repo in the workspace |
| `cogmem workspace status` | Show cross-repo workspace health |

---

## Memory Types

cogmem uses six cognitive memory types, each serving a different purpose:

### 1. Episodic Memory — "What happened"

Episodes are narrative records of events: debugging sessions, discoveries, incidents, decisions.

```
Date: 2026-01-15
Trigger: Fixed auth timeout
Emotion: pain (0.8)

## What happened
The login endpoint was timing out under load. Traced to connection pool
exhaustion — we were opening connections but not returning them on error paths.

## What I learned
Always use context managers for DB connections. The pool max was also set
too low for production traffic.
```

Episodes have a **lifecycle**. They start vivid and compress over time:

| Phase | Age | Detail level | Tokens |
|-------|-----|-------------|--------|
| Vivid | < 7 days | Full narrative | ~200 |
| Clear | 7-30 days | Full narrative | ~200 |
| Fuzzy | 30-90 days | Summary only | ~50 |
| Fading | 90-180 days | Summary only | ~50 |
| Stub | > 180 days | One-line takeaway | ~15 |

### 2. Semantic/Gist Memory — "What I understand"

Gists capture understanding at four levels:

| Level | Scope | Example | Tokens |
|-------|-------|---------|--------|
| 0 | Platform | "Microservice e-commerce platform with 12 services" | ~300 |
| 1 | Codebase | "Payment service handling Stripe + internal ledger" | ~200 |
| 2 | Module | "auth/ handles JWT validation and session management" | ~100 |
| 3 | Component | "TokenRefresher retries 3x with exponential backoff" | ~50 |

### 3. Spatial Memory — "Where things live"

For repos: surface (entry points, configs), middle (core logic), deep (internals), landmarks (key files), neighborhoods (what connects to what).

For workspaces: service topology, data flow, shared contracts, danger zones.

### 4. Pattern Memory — "I've seen this before"

Patterns capture recurring issues with a signature (what it looks like), consequence (what goes wrong), and response (what to do):

```
Pattern: pool-exhaustion
Category: bug
Signature: Connection pool runs out under load
Consequence: Request timeouts and 503 errors
Response: Increase pool size or add connection recycling
Seen in: auth/login.py, api/handler.py
Frequency: 3
Danger: high
```

### 5. Emotional Memory — "How I feel about this code"

Emotion types: **pain**, **danger**, **trust**, **pride**, **frustration**, **relief**, **curiosity**.

Emotional tags influence retrieval — painful code is always surfaced as a warning. Files tagged with danger get boosted in recall results.

### 6. Prospective Memory — "What to do next time"

Future-triggered intentions that fire when you touch specific files or encounter keywords:

```
Intention: Add rate limiting to login endpoint
Trigger: auth/login.py (file_touch)
Priority: high
```

---

## Three-Tier Architecture

Memory is stored at three levels:

### Repo Tier (`<repo>/.memory/`)

90% of all memory lives here. Contains all six memory types plus code entities. This is the primary working memory for a single codebase.

**Directory structure:**
```
.memory/
  episodes/       # What happened
  gist/           # What I understand
  patterns/       # Recurring issues
  entities/       # Code signatures
  prospective/    # Future reminders
  sessions/       # Auto-encoding queue
  spatial.md      # Where things live
  emotions.md     # How I feel about files
  keyword_index.json
  meta.json
```

### Workspace Tier (`<workspace>/.cogmem/`)

Cross-repo context for multi-repo projects. Only exists when you explicitly create it. Contains episodes, gists, patterns, and emotions that span multiple repos.

### Global Tier (`~/.cognitive-memory/`)

Universal patterns and preferences that survive project deletion. Global patterns never decay. When a pattern in a repo is marked `transferable`, it gets promoted to the global tier during consolidation.

---

## Retrieval Pipeline

When you run `cogmem recall`, a 7-stage pipeline processes your query:

### Stage 1 — Cue Extraction
Parses your query into structured cues: keywords, file paths, entity names, emotions, and task type hints.

`"fix the auth timeout bug"` becomes:
- Keywords: `[fix, auth, timeout, bug]`
- Emotions: `[pain]`
- Task type hints: `[bugfix]`

### Stage 2 — Scope Determination
Identifies which tiers to search based on your location and query.

| Tier | Weight |
|------|--------|
| Current repo | 1.0 |
| Workspace | 0.9 |
| Global | 0.8 |
| Other repo in workspace | 0.7 |

### Stage 3 — Multi-Tier Search
Queries the keyword index and loads matching memories from each tier.

### Stage 4 — Convergence Scoring
Each memory gets a score based on:
- **Keyword match** — How many cue words appear in the memory
- **Convergence** — Multiple cue types matching (file + keyword + emotion) gets a multiplier
- **Emotional weight** — Pain/danger memories are boosted
- **Recency** — Recently accessed memories score higher
- **Priming** — Memories about files you're currently working on get a bonus
- **Tier adjustment** — Applied from Stage 2 weights

### Stage 5 — Task Type Detection
Classifies the task as bugfix, feature, refactor, understand, plan, explore, or cross_repo.

### Stage 6 — Budget Allocation
Distributes the token budget (~3500) across memory types based on task type:

| Task Type | Episodes | Gist | Patterns | Dangers | Entities | Spatial | Prospective |
|-----------|----------|------|----------|---------|----------|---------|-------------|
| bugfix | 30% | 10% | 15% | 15% | 20% | 5% | 5% |
| feature | 10% | 25% | 15% | 10% | 15% | 15% | 10% |
| refactor | 10% | 10% | 15% | 10% | 40% | 10% | 5% |
| understand | 20% | 30% | 5% | 5% | 15% | 20% | 5% |
| explore | 10% | 30% | 5% | 5% | 5% | 35% | 10% |

### Stage 7 — Assembly
Formats the output into sections (Understanding, Past Experiences, Danger Warnings, Patterns, Code Entities, Spatial Map, Reminders) with a metamemory footer showing token usage and confidence.

---

## Claude Code Plugin

To use cogmem as a Claude Code plugin, copy the `.claude/` directory into your repo:

```bash
cp -r /path/to/cogmem/.claude /path/to/your-repo/.claude
```

This gives you three integration points:

### Auto-Recall Skill

Before any coding task, Claude Code automatically runs `cogmem recall` to fetch relevant context. This happens transparently — no action needed.

### Auto-Encode Hooks

Every time Claude Code writes or edits a file, a PostToolUse hook fires `cogmem hook-encode`, which queues the event for batch encoding. Your coding sessions are captured automatically.

### Slash Commands

Use these in Claude Code conversations:

| Command | Action |
|---------|--------|
| `/recall [query]` | Recall relevant memories |
| `/remember [what]` | Encode a new memory |
| `/forget [target]` | Remove a memory |
| `/memory-status` | Show memory health |
| `/mark-dangerous [path]` | Flag a file as dangerous |
| `/mark-stable [path]` | Flag a file as stable |
| `/workspace-status` | Show cross-repo status |
| `/cross-repo [query]` | Search workspace-level memories |

### Consolidation Subagent

The consolidation skill runs as a forked Explore agent. It compresses old episodes, extracts patterns, updates gists, and prunes stale memories.

---

## Multi-Repo Workspaces

If you work across multiple repos (microservices, monorepo with sub-projects):

### Setup

```bash
cd /path/to/workspace  # parent directory containing your repos
cogmem workspace init
cogmem workspace add-repo ./frontend
cogmem workspace add-repo ./backend
cogmem workspace add-repo ./shared-lib
cogmem bootstrap --workspace
```

### What workspace memory captures

- **Cross-repo episodes** — Commits that happened on the same day across repos
- **Service topology** — How repos relate to each other
- **Shared contracts** — API boundaries and shared dependencies
- **Cross-repo patterns** — Issues that recur across services
- **Workspace-level dangers** — Fragile integration points

### Querying across repos

```bash
cogmem recall "API contract between frontend and backend"
cogmem recall "deploy" --workspace-only
```

### Workspace decay

Workspace memories decay at **0.7x** the normal rate — cross-repo knowledge is harder to rebuild and more valuable to preserve.

---

## Maintenance

### Regular maintenance

Run these periodically (weekly is a good cadence):

```bash
# Compress old episodes, extract patterns, update gists, prune stubs
cogmem consolidate

# Apply strength-based decay
cogmem decay
```

### What consolidation does

1. **Episode compression** — Transitions episodes through phases (vivid → clear → fuzzy → fading → stub), compressing the narrative at each step
2. **Pattern extraction** — Finds recurring themes across episodes and creates pattern memories
3. **Gist updates** — Updates module gists with references to new episodes
4. **Emotional recalibration** — Reduces intensity of emotions that haven't been reinforced recently
5. **Pruning** — Deletes stub episodes with very low strength that have been consolidated into patterns
6. **Orphan cleanup** — Removes entity records for files that no longer exist

### What decay does

Applies exponential decay to memory strength based on time since last access:

| Memory Type | Half-life |
|------------|-----------|
| Episodes | ~14 days |
| Prospective | ~35 days |
| Patterns | ~70 days |
| Gists | ~140 days |
| Spatial | ~230 days |
| Emotions | ~350 days |
| Pain emotions | ~700 days |
| Global patterns | Never decay |

### Source annotations

You can embed memory hints directly in your source code:

```python
# @memory: This function is fragile — the order of operations matters
#          because the cache invalidation must happen BEFORE the DB write
def update_user(user_id, data):
    ...
```

Then scan them:

```bash
cogmem encode-annotations
```

---

## Advanced Usage

### Custom emotion encoding

Encode with specific emotions to influence future recall:

```bash
# This file caused pain — will show as a danger warning
cogmem encode --event "Outage from race condition" --emotion pain --intensity 0.9 --files worker.py

# This was a good experience — builds trust
cogmem encode --event "Clean refactor of auth module" --emotion pride --intensity 0.7 --files auth/
```

### Export and backup

```bash
# Export to a directory
cogmem export ./memory-backup

# Export to a tarball
cogmem export ./memory-backup.tar.gz

# Import on another machine
cogmem import ./memory-backup.tar.gz
```

### Forget specific memories

```bash
# Remove by topic
cogmem forget "auth timeout"

# Remove by pattern name
cogmem forget "pool-exhaustion"
```

### Encode from extended git history

```bash
# Bootstrap from 12 months of history
cogmem bootstrap --months 12

# Or incrementally add recent git history
cogmem encode-git --since 30d
```

---

## Troubleshooting

### "Not inside a git repository"

cogmem requires a git repo. Initialize one:

```bash
git init
cogmem bootstrap
```

### "command not found: cogmem"

Add the Python scripts directory to your PATH:

```bash
# Find where pip installed it
python3 -c "import sysconfig; print(sysconfig.get_path('scripts', 'posix_user'))"

# Add that to PATH
export PATH="<output from above>:$PATH"
```

Or use `python3 -m cogmem` as an alternative.

### Recall returns too many entities, not enough context

This happens in freshly bootstrapped repos. Add richer memories:

```bash
# Encode meaningful events
cogmem encode --event "..." --learned "..."

# Add gists for key modules
cogmem update --update-gist auth --content "Handles JWT validation, session management, and OAuth2 flows"

# Run consolidation to extract patterns
cogmem consolidate
```

### Memory directory is too large

Run consolidation and decay to compress and prune:

```bash
cogmem consolidate
cogmem decay
```

Stub episodes with very low strength are automatically pruned during consolidation.

### Nested git repos

If your project has embedded git repos (submodules, vendored repos), cogmem may detect the wrong repo root. Use explicit paths:

```bash
cogmem encode --event "..." --files path/relative/to/correct/repo
```

---

## File Structure Reference

```
<repo>/.memory/
  episodes/           # Episodic memories (markdown with frontmatter)
  gist/               # Semantic gists (_codebase.md, module.md, etc.)
  patterns/           # Pattern memories
  entities/           # Code entity signatures
  prospective/        # Future-triggered intentions
  sessions/           # Auto-encoding session queue
  .pending/           # Prompts for subagent processing
  spatial.md          # Spatial map of the repo
  emotions.md         # Emotional tags for files
  keyword_index.json  # Inverted index for fast retrieval
  meta.json           # Repo metadata

<workspace>/.cogmem/
  episodes/           # Cross-repo episodes
  gist/               # Workspace-level gists (_platform.md)
  patterns/           # Cross-repo patterns
  prospective/        # Workspace-level intentions
  spatial.md          # Service topology
  emotions.md         # Cross-repo emotional tags
  keyword_index.json
  meta.json

~/.cognitive-memory/
  patterns/           # Universal transferable patterns
  preferences.json    # Global settings
```

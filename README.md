# cogmem

**Cognitive Codebase Memory** — a persistent memory system that models how a senior developer's brain holds a codebase.

cogmem gives your coding assistant (Claude Code) long-term memory across sessions. It remembers what happened, how you felt about it, where things live, what patterns keep recurring, and what you planned to do next time.

![Brain Visualization](images/Screenshot%202026-04-09%20at%202.27.51%E2%80%AFAM.png)

## Why

Every time you start a new coding session, your AI assistant starts from scratch. It doesn't remember:
- That `auth/login.py` caused two production outages
- That the connection pool pattern keeps recurring
- That you planned to add rate limiting next time you touched the login code
- How the services connect across your repos

cogmem fixes this. It builds up a cognitive model of your codebase through six memory types — the same way an experienced developer holds knowledge in their head.

## Install

```bash
pip install git+https://github.com/adityailab/cogmem.git
```

Or from source:

```bash
git clone https://github.com/adityailab/cogmem.git
cd cogmem
pip install -e .
```

## Quick Start

```bash
cd /path/to/your-project

# 1. Initialize memory from your codebase
cogmem bootstrap

# 2. Recall context before working on something
cogmem recall "fix the auth timeout bug"

# 3. Encode what you learned
cogmem encode --event "Race condition in queue" --emotion pain --intensity 0.8 \
  --files queue/worker.py --learned "Must lock before dequeue"

# 4. Mark files
cogmem update --mark-dangerous auth/login.py --content "Caused two outages"

# 5. Visualize your memory as an interactive brain map
cogmem visualize
```

## Six Memory Types

| Type | What it stores | Example |
|------|---------------|---------|
| **Episodic** | What happened — debugging sessions, discoveries, incidents | "The login endpoint timed out because the connection pool was exhausted" |
| **Semantic/Gist** | What code does and why, at four zoom levels | "auth/ handles JWT validation and session management" |
| **Spatial** | Where things live — file tree topology, landmarks | Surface (configs), middle (core logic), deep (internals) |
| **Pattern** | Recurring issues and deja vu moments | "This file has been fixed 5 times — it's fragile" |
| **Emotional** | How you feel about code — pain, danger, trust | "PAIN: auth/login.py — caused production outage (0.85)" |
| **Prospective** | What to do next time a trigger fires | "Add rate limiting when you touch auth/login.py" |

Episodes compress over time: **vivid** (< 7d) -> **clear** (7-30d) -> **fuzzy** (30-90d) -> **fading** (90-180d) -> **stub** (> 180d). Details fade but patterns persist — just like human memory.

## Three-Tier Architecture

```
~/.cognitive-memory/          # Global — universal patterns, never decay
<workspace>/.cogmem/          # Workspace — cross-repo context (0.7x decay)
<repo>/.memory/               # Repo — full cognitive model (90% of memory)
```

- **Repo tier**: All six memory types + code entities. One per git repo.
- **Workspace tier**: Cross-repo episodes, shared patterns, service topology. For multi-repo projects.
- **Global tier**: Transferable patterns and preferences. Survives project deletion.

## Retrieval Pipeline

`cogmem recall` runs a 7-stage pipeline:

1. **Cue extraction** — parse keywords, file paths, emotions, task type from your query
2. **Scope determination** — which tiers to search (repo, workspace, global)
3. **Multi-tier search** — query keyword indices across tiers
4. **Convergence scoring** — rank by keyword match x emotional weight x recency x context
5. **Task type detection** — bugfix, feature, refactor, understand, plan, explore
6. **Budget allocation** — distribute ~3500 tokens across memory types per task type
7. **Assembly** — format output with sections and metamemory footer

Different task types get different memory mixes:

| Task | Episodes | Gist | Patterns | Dangers | Entities | Spatial |
|------|----------|------|----------|---------|----------|---------|
| Bugfix | 30% | 10% | 15% | 15% | 20% | 5% |
| Feature | 10% | 25% | 15% | 10% | 15% | 15% |
| Refactor | 10% | 10% | 15% | 10% | 40% | 10% |
| Understand | 20% | 30% | 5% | 5% | 15% | 20% |

## Brain Visualization

```bash
cogmem visualize
```

Opens an interactive D3.js visualization in your browser:

- **7 brain regions** — episodic, semantic, spatial, pattern, emotional, prospective, entity
- **Click nodes** to highlight connections (additive — build up a trace)
- **Click edges** to highlight the connection and its endpoints
- **Double-click** to remove from selection
- **Search** to filter memories by text
- **Legend** to toggle memory types
- Pain/danger nodes **pulse** to draw attention

## Claude Code Plugin

Copy `.claude/` into any repo to integrate with Claude Code:

```bash
cp -r /path/to/cogmem/.claude /path/to/your-repo/.claude
```

This gives you:
- **Auto-recall** — memory is fetched before coding tasks (skill)
- **Auto-encode** — file edits are captured automatically (hooks)
- **Slash commands** — `/recall`, `/remember`, `/forget`, `/memory-status`, `/mark-dangerous`, `/mark-stable`, `/workspace-status`, `/cross-repo`

## Multi-Repo Workspaces

```bash
cd /path/to/workspace
cogmem workspace init
cogmem workspace add-repo ./frontend
cogmem workspace add-repo ./backend
cogmem bootstrap --workspace
```

Workspace memory captures cross-repo episodes, shared contracts, service topology, and cross-repo patterns. Workspace memories decay at 0.7x the normal rate.

## Commands

### Retrieval
```bash
cogmem recall <query>              # Recall relevant memories
cogmem recall <query> --repo-only  # Repo tier only
cogmem search <query> --type episodes
cogmem dangers [files...]          # Show danger warnings
cogmem intentions                  # Show pending reminders
```

### Encoding
```bash
cogmem encode --event "..." --emotion pain --intensity 0.8 --files path.py --learned "..."
cogmem encode-git                  # Episodes from git history
cogmem encode-git --since 30d
cogmem encode-annotations          # Scan @memory: comments in source
```

### Corrections
```bash
cogmem update --mark-dangerous <path> --content "reason"
cogmem update --mark-stable <path>
cogmem update --update-gist <module> --content "what it does"
cogmem update --add-pattern <name> --content "signature"
cogmem forget <target>
```

### Maintenance
```bash
cogmem consolidate      # Compress, extract patterns, prune
cogmem decay            # Apply strength-based decay
cogmem status           # Memory health
cogmem visualize        # Interactive brain map
```

### Lifecycle
```bash
cogmem bootstrap               # Init from git history + file tree
cogmem bootstrap --months 12   # More history
cogmem bootstrap --workspace   # Multi-repo
cogmem export ./backup.tar.gz
cogmem import ./backup.tar.gz
```

## Memory Decay

Memories fade naturally, just like human memory:

| Type | Half-life |
|------|-----------|
| Episodes | ~14 days |
| Prospective | ~35 days |
| Patterns | ~70 days |
| Gists | ~140 days |
| Spatial | ~230 days |
| Emotions | ~350 days |
| Pain emotions | ~700 days |
| Global patterns | Never |

## Source Annotations

Embed memory hints in your code:

```python
# @memory: This function is fragile — order of operations matters
#          because cache invalidation must happen BEFORE the DB write
def update_user(user_id, data):
    ...
```

Then: `cogmem encode-annotations`

## Design Principles

1. **Stories, not structures** — episodes are the primary unit
2. **Intent, not implementation** — store what code does and why
3. **Association, not search** — cue-driven retrieval with convergence scoring
4. **Emotion is the priority system** — painful code is always surfaced
5. **Forgetting is expertise** — details fade but patterns persist
6. **Memory breathes** — output adapts to your current task

## License

MIT

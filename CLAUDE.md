# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**cogmem** (Cognitive Codebase Memory) is a Claude Code plugin that models how a senior developer's brain holds a codebase. It provides persistent memory across sessions using six cognitive memory systems (episodic, semantic/gist, spatial, pattern, emotional, prospective) organized in three tiers (repo, workspace, global).

The project is currently in the **specification phase** — no code has been implemented yet. The full spec lives in `docs/cogmem_spec_v3.2_clean.txt`.

## Architecture

### Delivery Model
cogmem is delivered as a **Claude Code plugin** using four extension points:
- **Skills** — Auto-recall memory before coding tasks (`.claude/skills/memory/SKILL.md`)
- **Hooks** — Auto-encode on PostToolUse for Write/Edit (`.claude/hooks.json`)
- **Slash Commands** — Developer control (`/recall`, `/remember`, `/forget`, `/memory-status`, etc.)
- **Subagent** — Consolidation via forked Explore agent

### Three-Tier Memory Hierarchy
1. **Repo** (`<repo>/.memory/`) — 90% of memory. Full cognitive model for one codebase.
2. **Workspace** (`<workspace>/.cogmem/`) — Cross-repo context. Only exists for multi-repo workspaces.
3. **Global** (`~/.cognitive-memory/`) — Universal patterns and developer preferences. Survives project deletion.

### Engine (cogmem CLI, Python)
Planned package structure under `cogmem/`:
- `engine/` — Core algorithms: `recall.py`, `encode.py`, `consolidate.py`, `decay.py`, `bootstrap.py`
- `models/` — Data classes: episode, gist, pattern, emotion, spatial, prospective, entity
- `tiers/` — Tier-specific operations: `repo.py`, `workspace.py`, `global_mem.py`
- `storage/` — Filesystem I/O and keyword index management
- `utils/` — Cue extraction, scoring, repo detection, token counting

### Key Algorithms
- **Retrieval**: 7-stage pipeline — cue extraction → scope determination → multi-tier search → convergence scoring → task type detection → budget allocation → assembly with metamemory. Budget is ~3500 tokens allocated by memory type per task type (bugfix, feature, refactor, etc.).
- **Encoding**: Detects repo boundaries from touched files, places episodes at repo or workspace tier, updates emotions and keyword indices.
- **Consolidation**: Repo (nightly→monthly phases), workspace (weekly/biweekly/monthly), global (monthly pattern promotion).
- **Forgetting**: Strength-based decay with half-lives per memory type. Workspace decays at 0.7x rate. Global patterns never decay.

### Six Cognitive Principles
Stories not structures. Intent not implementation. Association not search. Emotion is the priority system. Forgetting is expertise. Memory breathes.

## Implementation Roadmap (from spec)
1. Core data model + single-repo bootstrap
2. Encoding (encode, encode-git, hook-encode)
3. Retrieval (cue extraction → convergence scoring → budget allocation)
4. Consolidation + decay
5. Multi-repo workspace support
6. Claude Code plugin packaging
7. Global memory + polish

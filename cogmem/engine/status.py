"""Status reporting for memory health."""

from __future__ import annotations

import json
from pathlib import Path

from cogmem.tiers.repo import RepoTier
from cogmem.tiers.workspace import WorkspaceTier, detect_workspace
from cogmem.tiers.global_mem import GlobalTier
from cogmem.utils.repo_detect import find_project_root, find_repo_root


def show_status(
    repo_only: bool = False,
    workspace_only: bool = False,
    cwd: str | None = None,
) -> str:
    """Show memory health status."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    sections: list[str] = []

    if not workspace_only:
        repo_root = find_project_root(cwd_path)
        if repo_root:
            repo = RepoTier(repo_root)
            if repo.exists:
                s = repo.status()
                sections.append(
                    f"Repo: {s['repo']}\n"
                    f"  Episodes:    {s['episodes']}\n"
                    f"  Gists:       {s['gists']}\n"
                    f"  Patterns:    {s['patterns']}\n"
                    f"  Entities:    {s['entities']}\n"
                    f"  Prospective: {s['prospectives']}\n"
                    f"  Emotions:    {s['emotions']}\n"
                    f"  Index keys:  {s['index_keywords']}"
                )
            else:
                sections.append(f"Repo: {repo_root.name} (not initialized)")
        else:
            sections.append("No repo found.")

    if not repo_only:
        ws_path = detect_workspace(cwd_path)
        if ws_path:
            ws = WorkspaceTier(ws_path)
            if ws.exists:
                s = ws.status()
                sections.append(
                    f"Workspace: {s['workspace']}\n"
                    f"  Repos:     {s['repos']}\n"
                    f"  Episodes:  {s['episodes']}\n"
                    f"  Gists:     {s['gists']}\n"
                    f"  Patterns:  {s['patterns']}\n"
                    f"  Emotions:  {s['emotions']}"
                )

        g = GlobalTier()
        if g.exists:
            s = g.status()
            sections.append(
                f"Global: {s['global_dir']}\n"
                f"  Patterns: {s['patterns']}"
            )

    return "\n\n".join(sections) if sections else "No memory stores found."


def show_workspace_status(cwd: str | None = None) -> str:
    """Show cross-repo workspace health."""
    cwd_path = Path(cwd) if cwd else Path.cwd()
    ws_path = detect_workspace(cwd_path)
    if not ws_path:
        return "No workspace found."

    ws = WorkspaceTier(ws_path)
    if not ws.exists:
        return "Workspace not initialized."

    s = ws.status()
    repos = ws.list_repos()
    lines = [
        f"Workspace: {ws_path}",
        f"Repos: {len(repos)}",
    ]
    for r in repos:
        name = r.get("name", "?")
        path = r.get("path", "?")
        repo = RepoTier(path)
        if repo.exists:
            rs = repo.status()
            lines.append(f"  {name}: {rs['episodes']} episodes, {rs['patterns']} patterns")
        else:
            lines.append(f"  {name}: not initialized")

    lines.extend([
        f"Cross-repo episodes: {s['episodes']}",
        f"Workspace patterns:  {s['patterns']}",
        f"Workspace gists:     {s['gists']}",
    ])

    return "\n".join(lines)

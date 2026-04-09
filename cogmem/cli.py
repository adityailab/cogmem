"""cogmem CLI — all commands."""

import click

from cogmem import __version__


@click.group()
@click.version_option(version=__version__, prog_name="cogmem")
def cli():
    """Cognitive Codebase Memory — a human memory system for Claude Code."""


# ---------------------------------------------------------------------------
# Retrieval
# ---------------------------------------------------------------------------

@cli.command()
@click.argument("query")
@click.option("--repo-only", is_flag=True, help="Search repo tier only.")
@click.option("--workspace-only", is_flag=True, help="Search workspace tier only.")
@click.option("--budget", default=3500, help="Token budget for output.")
def recall(query, repo_only, workspace_only, budget):
    """Recall relevant memories for a query."""
    from cogmem.engine.recall import recall as do_recall

    result = do_recall(query, repo_only=repo_only, workspace_only=workspace_only, budget=budget)
    click.echo(result)


@cli.command()
@click.argument("query")
@click.option("--type", "mem_type", help="Memory type to search.")
def search(query, mem_type):
    """Search memories by type."""
    from cogmem.engine.recall import search_memories

    result = search_memories(query, mem_type=mem_type)
    click.echo(result)


@cli.command()
@click.argument("files", nargs=-1)
def dangers(files):
    """Show danger warnings for files."""
    from cogmem.engine.recall import get_dangers

    result = get_dangers(list(files))
    click.echo(result)


@cli.command()
def intentions():
    """Show pending prospective memories."""
    from cogmem.engine.recall import get_intentions

    result = get_intentions()
    click.echo(result)


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

EMOTION_CHOICES = ["pain", "danger", "trust", "pride", "frustration", "relief", "curiosity", "neutral"]


@cli.command()
@click.option("--event", help="Event description.")
@click.option("--manual", help="Manual memory text.")
@click.option("--emotion", default="neutral", type=click.Choice(EMOTION_CHOICES), help="Emotion type.")
@click.option("--intensity", default=0.5, type=click.FloatRange(0.0, 1.0), help="Emotion intensity 0-1.")
@click.option("--files", multiple=True, help="Files involved.")
@click.option("--learned", default="", help="Key takeaway.")
def encode(event, manual, emotion, intensity, files, learned):
    """Encode a new memory."""
    from cogmem.engine.encode import encode as do_encode

    result = do_encode(
        event=event or manual or "",
        emotion=emotion,
        intensity=intensity,
        code_touched=list(files),
        learned=learned,
        manual=bool(manual),
    )
    click.echo(result)


@cli.command("encode-git")
@click.option("--since", default="7d", help="How far back to scan.")
def encode_git(since):
    """Encode memories from git history."""
    from cogmem.engine.encode import encode_git as do_encode_git

    result = do_encode_git(since=since)
    click.echo(result)


@cli.command("hook-encode")
@click.argument("tool")
@click.argument("tool_input_file")
def hook_encode(tool, tool_input_file):
    """Hook handler for PostToolUse auto-encoding."""
    from cogmem.engine.encode import hook_encode as do_hook_encode

    do_hook_encode(tool=tool, tool_input_file=tool_input_file)


@cli.command("encode-annotations")
def encode_annotations():
    """Scan source for @memory: annotations."""
    from cogmem.engine.encode import encode_annotations as do_encode_annotations

    result = do_encode_annotations()
    click.echo(result)


@cli.command("encode-session")
def encode_session():
    """Process queued hook events into episodes."""
    from cogmem.engine.encode import finalize_session

    result = finalize_session()
    click.echo(result)


# ---------------------------------------------------------------------------
# Visualization
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--output", "-o", default=None, help="Output path for HTML file.")
@click.option("--no-open", is_flag=True, help="Don't open in browser.")
@click.option("--mode", default="3d", type=click.Choice(["2d", "3d"]), help="Visualization mode.")
def visualize(output, no_open, mode):
    """Open interactive brain visualization of memory."""
    from cogmem.engine.visualize import visualize as do_visualize

    result = do_visualize(output=output, no_open=no_open, mode=mode)
    click.echo(result)


# ---------------------------------------------------------------------------
# Maintenance
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--scope", default="full", type=click.Choice(["full", "repo", "workspace"]))
@click.option("--apply", "apply_file", default=None, help="Apply subagent result file.")
@click.option("--dry-run", is_flag=True, help="Show what would change without writing.")
def consolidate(scope, apply_file, dry_run):
    """Consolidate and strengthen memories."""
    from cogmem.engine.consolidate import consolidate as do_consolidate

    if dry_run:
        click.echo("[DRY RUN] — no changes will be written.\n")
    result = do_consolidate(scope=scope, apply_file=apply_file, dry_run=dry_run)
    click.echo(result)


@cli.command()
@click.option("--dry-run", is_flag=True, help="Show what would change without writing.")
def decay(dry_run):
    """Run decay on all memories."""
    from cogmem.engine.decay import run_decay

    if dry_run:
        click.echo("[DRY RUN] — no changes will be written.\n")
    result = run_decay(dry_run=dry_run)
    click.echo(result)


@cli.command()
@click.option("--repo", "repo_only", is_flag=True, help="Repo status only.")
@click.option("--workspace", "ws_only", is_flag=True, help="Workspace status only.")
def status(repo_only, ws_only):
    """Show memory health status."""
    from cogmem.engine.status import show_status

    result = show_status(repo_only=repo_only, workspace_only=ws_only)
    click.echo(result)


# ---------------------------------------------------------------------------
# Corrections
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--mark-stable", "stable_target", help="Mark a target as stable.")
@click.option("--mark-dangerous", "danger_target", help="Mark a target as dangerous.")
@click.option("--update-gist", "gist_target", help="Target to update gist for.")
@click.option("--add-pattern", "pattern_name", help="Name of pattern to add.")
@click.option("--content", default="", help="Content for gist/pattern update.")
def update(stable_target, danger_target, gist_target, pattern_name, content):
    """Update or correct memories."""
    from cogmem.engine.update import update_memory

    result = update_memory(
        stable_target=stable_target,
        danger_target=danger_target,
        gist_target=gist_target,
        pattern_name=pattern_name,
        content=content,
    )
    click.echo(result)


@cli.command()
@click.argument("target")
def forget(target):
    """Archive or remove a memory."""
    from cogmem.engine.update import forget_memory

    result = forget_memory(target)
    click.echo(result)


# ---------------------------------------------------------------------------
# Lifecycle
# ---------------------------------------------------------------------------

@cli.command()
@click.option("--months", default=6, help="Months of git history to scan.")
@click.option("--workspace", "ws_mode", is_flag=True, help="Bootstrap entire workspace.")
def bootstrap(months, ws_mode):
    """Initialize memory from git history and file tree."""
    from cogmem.engine.bootstrap import bootstrap as do_bootstrap

    result = do_bootstrap(months=months, workspace_mode=ws_mode)
    click.echo(result)


@cli.command("export")
@click.argument("path")
def export_mem(path):
    """Export memory to a file."""
    from cogmem.engine.transfer import export_memory

    export_memory(path)
    click.echo(f"Exported to {path}")


@cli.command("import")
@click.argument("path")
def import_mem(path):
    """Import memory from a file."""
    from cogmem.engine.transfer import import_memory

    import_memory(path)
    click.echo(f"Imported from {path}")


# ---------------------------------------------------------------------------
# Workspace
# ---------------------------------------------------------------------------

@cli.group()
def workspace():
    """Workspace management commands."""


@workspace.command("init")
def workspace_init():
    """Create .cogmem/ in current directory."""
    from cogmem.tiers.workspace import WorkspaceTier

    ws = WorkspaceTier.init_here()
    click.echo(f"Workspace initialized at {ws.root}")


@workspace.command("add-repo")
@click.argument("path")
def workspace_add_repo(path):
    """Register a repo in the workspace."""
    from cogmem.tiers.workspace import WorkspaceTier

    ws = WorkspaceTier.from_cwd()
    ws.add_repo(path)
    click.echo(f"Added repo: {path}")


@workspace.command("status")
def workspace_status():
    """Show cross-repo workspace health."""
    from cogmem.engine.status import show_workspace_status

    result = show_workspace_status()
    click.echo(result)

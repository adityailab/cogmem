"""Brain visualization — interactive memory map."""

from __future__ import annotations

import json
import webbrowser
from datetime import date
from pathlib import Path
from typing import Any

from cogmem.tiers.repo import RepoTier
from cogmem.tiers.workspace import WorkspaceTier, detect_workspace
from cogmem.tiers.global_mem import GlobalTier
from cogmem.utils.repo_detect import find_repo_root


def visualize(cwd: str | None = None, output: str | None = None, no_open: bool = False, mode: str = "3d") -> str:
    """Generate an interactive brain visualization of all memory."""
    cwd_path = Path(cwd) if cwd else Path.cwd()

    nodes: list[dict] = []
    links: list[dict] = []
    regions: list[dict] = []

    # Collect repo memory — check for .memory/ directly, then try git root
    repo_root = find_repo_root(cwd_path)
    if repo_root:
        repo = RepoTier(repo_root)
        if repo.exists:
            _collect_repo(repo, nodes, links, regions)
    elif (cwd_path / ".memory").is_dir():
        # No git repo but .memory/ exists here
        repo = RepoTier(cwd_path)
        _collect_repo(repo, nodes, links, regions)

    # Collect workspace memory
    ws_path = detect_workspace(cwd_path)
    if ws_path:
        ws = WorkspaceTier(ws_path)
        if ws.exists:
            _collect_workspace(ws, nodes, links, regions)

    # Collect global memory
    g = GlobalTier()
    if g.exists:
        _collect_global(g, nodes, links, regions)

    if not nodes:
        return "No memory to visualize. Run `cogmem bootstrap` first."

    # Generate both HTML files so the toggle button works
    graph_data = {"nodes": nodes, "links": links, "regions": regions}
    html_2d = _generate_html(graph_data)
    html_3d = _generate_html_3d(graph_data)

    # Determine base output dir
    if output:
        base_dir = Path(output).parent
        stem = Path(output).stem
    elif (cwd_path / ".memory").is_dir():
        base_dir = cwd_path / ".memory"
        stem = "brain"
    elif repo_root and (repo_root / ".memory").is_dir():
        base_dir = repo_root / ".memory"
        stem = "brain"
    else:
        base_dir = cwd_path
        stem = "brain"

    base_dir.mkdir(parents=True, exist_ok=True)
    path_2d = base_dir / f"{stem}-2d.html"
    path_3d = base_dir / f"{stem}-3d.html"

    path_2d.write_text(html_2d)
    path_3d.write_text(html_3d)

    out_path = path_3d if mode == "3d" else path_2d

    if not no_open:
        webbrowser.open(f"file://{out_path.resolve()}")

    return f"Visualization saved to {out_path}"


# ---------------------------------------------------------------------------
# Data collection
# ---------------------------------------------------------------------------

def _collect_repo(repo: RepoTier, nodes: list, links: list, regions: list) -> None:
    """Collect all repo-tier memory into graph nodes and links."""
    repo_name = repo.repo_path.name
    today = date.today()

    regions.append({"id": "episodic", "label": "Episodic", "color": "#4ECDC4"})
    regions.append({"id": "semantic", "label": "Semantic / Gist", "color": "#45B7D1"})
    regions.append({"id": "spatial", "label": "Spatial", "color": "#96CEB4"})
    regions.append({"id": "pattern", "label": "Pattern", "color": "#FFEAA7"})
    regions.append({"id": "emotional", "label": "Emotional", "color": "#FF6B6B"})
    regions.append({"id": "prospective", "label": "Prospective", "color": "#DDA0DD"})
    regions.append({"id": "entity", "label": "Entities", "color": "#A0AEC0"})

    # Episodes
    episodes = repo.list_episodes()
    for ep in episodes:
        age_days = 0
        if ep.date:
            try:
                age_days = (today - date.fromisoformat(ep.date)).days
            except ValueError:
                pass

        nodes.append({
            "id": f"ep:{ep.id}",
            "label": ep.trigger[:50] or ep.id,
            "region": "episodic",
            "type": "episode",
            "tier": "repo",
            "strength": ep.strength,
            "phase": ep.phase,
            "emotion": ep.emotion,
            "intensity": ep.intensity,
            "date": ep.date,
            "age_days": age_days,
            "story": ep.story[:200],
            "learned": ep.learned[:200],
            "size": _strength_to_size(ep.strength, ep.intensity),
        })

        # Link episodes to related episodes
        for rel in ep.related_episodes:
            links.append({"source": f"ep:{ep.id}", "target": f"ep:{rel}", "type": "related", "strength": 0.5})
        for rel in ep.related_patterns:
            links.append({"source": f"ep:{ep.id}", "target": f"pat:{rel}", "type": "evidence", "strength": 0.6})

        # Link episodes to files they touched (as entity connections)
        for f in ep.code_touched[:5]:
            file_id = f"file:{f}"
            links.append({"source": f"ep:{ep.id}", "target": file_id, "type": "touched", "strength": 0.3})

    # Gists
    for gist in repo.list_gists():
        nodes.append({
            "id": f"gist:{gist.id}",
            "label": gist.target or gist.scope,
            "region": "semantic",
            "type": "gist",
            "tier": "repo",
            "scope": gist.scope,
            "strength": gist.confidence,
            "what": gist.what_it_does[:200],
            "why": gist.why_it_exists[:150],
            "judgment": gist.judgment,
            "size": 8 + gist.confidence * 12,
        })
        # Link gists to episodes they formed from
        for ep_id in gist.formed_from:
            links.append({"source": f"gist:{gist.id}", "target": f"ep:{ep_id}", "type": "formed_from", "strength": 0.4})

    # Patterns
    for pat in repo.list_patterns():
        nodes.append({
            "id": f"pat:{pat.id}",
            "label": pat.name,
            "region": "pattern",
            "type": "pattern",
            "tier": "repo",
            "strength": pat.strength,
            "category": pat.category,
            "danger_level": pat.danger_level,
            "frequency": pat.frequency,
            "signature": pat.signature[:200],
            "consequence": pat.consequence[:150],
            "response": pat.response[:150],
            "size": 6 + pat.frequency * 2 + (8 if pat.danger_level in ("high", "critical") else 0),
        })
        for loc in pat.seen_in:
            links.append({"source": f"pat:{pat.id}", "target": f"file:{loc}", "type": "seen_in", "strength": 0.5})

    # Emotions
    emotions = repo.get_emotions()
    for tag in emotions.tags:
        nodes.append({
            "id": f"emo:{tag.target}",
            "label": f"{tag.emotion.upper()}: {tag.target}",
            "region": "emotional",
            "type": "emotion",
            "tier": "repo",
            "emotion": tag.emotion,
            "intensity": tag.intensity,
            "reason": tag.reason[:150],
            "strength": tag.intensity,
            "size": 5 + tag.intensity * 15,
        })
        # Link emotion to the file
        links.append({"source": f"emo:{tag.target}", "target": f"file:{tag.target}", "type": "feels", "strength": tag.intensity})

    # Spatial landmarks
    spatial = repo.get_spatial()
    if spatial:
        for lm in spatial.landmarks:
            nodes.append({
                "id": f"landmark:{lm.path}",
                "label": f"★ {lm.path}",
                "region": "spatial",
                "type": "landmark",
                "tier": "repo",
                "description": lm.description,
                "why": lm.why,
                "strength": 0.9,
                "size": 10,
            })

        # Surface/middle/deep entries as lighter spatial nodes
        for entry in (spatial.surface + spatial.middle + spatial.deep)[:30]:
            file_id = f"file:{entry.path}"
            if not any(n["id"] == file_id for n in nodes):
                nodes.append({
                    "id": file_id,
                    "label": entry.path,
                    "region": "spatial",
                    "type": "file",
                    "tier": "repo",
                    "description": entry.description,
                    "feel": entry.feel,
                    "strength": 0.4,
                    "size": 4,
                })

    # Prospective
    for p in repo.list_prospectives():
        nodes.append({
            "id": f"pro:{p.id}",
            "label": p.intention[:50],
            "region": "prospective",
            "type": "prospective",
            "tier": "repo",
            "trigger": p.trigger,
            "priority": p.priority,
            "completed": p.completed,
            "strength": p.strength,
            "size": 7 if p.priority == "high" else 5,
        })

    # Entities (sample — limit to avoid overload)
    entities = repo.list_entities()
    # Group by file and take top files
    file_entities: dict[str, list] = {}
    for e in entities:
        file_entities.setdefault(e.file_path, []).append(e)

    entity_count = 0
    for filepath, ents in sorted(file_entities.items(), key=lambda x: -len(x[1])):
        if entity_count > 80:
            break
        file_id = f"file:{filepath}"
        if not any(n["id"] == file_id for n in nodes):
            nodes.append({
                "id": file_id,
                "label": filepath,
                "region": "entity",
                "type": "file",
                "tier": "repo",
                "strength": 0.5,
                "size": 3 + min(len(ents), 5),
            })

        for e in ents[:5]:  # max 5 per file
            eid = f"entity:{e.file_path}:{e.name}"
            nodes.append({
                "id": eid,
                "label": e.name,
                "region": "entity",
                "type": "entity",
                "tier": "repo",
                "kind": e.kind,
                "signature": e.signature,
                "file_path": e.file_path,
                "strength": e.strength,
                "size": 3,
            })
            links.append({"source": eid, "target": file_id, "type": "defined_in", "strength": 0.2})
            entity_count += 1


def _collect_workspace(ws: WorkspaceTier, nodes: list, links: list, regions: list) -> None:
    """Collect workspace-tier memories."""
    for ep in ws.list_episodes():
        nodes.append({
            "id": f"ws:ep:{ep.id}",
            "label": f"[WS] {ep.trigger[:40]}",
            "region": "episodic",
            "type": "episode",
            "tier": "workspace",
            "strength": ep.strength,
            "phase": ep.phase,
            "repos": ep.repos_involved or [],
            "size": _strength_to_size(ep.strength, ep.intensity) + 2,
        })

    for pat in ws.list_patterns():
        nodes.append({
            "id": f"ws:pat:{pat.id}",
            "label": f"[WS] {pat.name}",
            "region": "pattern",
            "type": "pattern",
            "tier": "workspace",
            "strength": pat.strength,
            "size": 10 + pat.frequency,
        })


def _collect_global(g: GlobalTier, nodes: list, links: list, regions: list) -> None:
    """Collect global-tier patterns."""
    for pat in g.list_patterns():
        nodes.append({
            "id": f"global:pat:{pat.id}",
            "label": f"[GLOBAL] {pat.name}",
            "region": "pattern",
            "type": "pattern",
            "tier": "global",
            "strength": 1.0,
            "size": 14,
        })


def _strength_to_size(strength: float, intensity: float = 0.5) -> float:
    """Convert strength and intensity to node size."""
    return 4 + strength * 8 + intensity * 6


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

def _generate_html(data: dict) -> str:
    """Generate a complete self-contained HTML visualization."""
    graph_json = json.dumps(data, default=str)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>cogmem — Brain Visualization</title>
<script src="https://d3js.org/d3.v7.min.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}

body {{
    background: #0a0a1a;
    color: #e0e0e0;
    font-family: 'SF Mono', 'Fira Code', 'Consolas', monospace;
    overflow: hidden;
}}

#canvas-container {{
    width: 100vw;
    height: 100vh;
    position: relative;
}}

svg {{
    width: 100%;
    height: 100%;
}}

/* Brain glow effect */
.brain-bg {{
    fill: none;
    stroke: rgba(78, 205, 196, 0.05);
    stroke-width: 2;
}}

/* Links */
.link {{
    stroke-opacity: 0.15;
    stroke-linecap: round;
}}
.link.touched {{ stroke: #4ECDC4; }}
.link.related {{ stroke: #45B7D1; }}
.link.evidence {{ stroke: #FFEAA7; }}
.link.feels {{ stroke: #FF6B6B; }}
.link.formed_from {{ stroke: #45B7D1; stroke-dasharray: 4,4; }}
.link.defined_in {{ stroke: #A0AEC0; }}
.link.seen_in {{ stroke: #FFEAA7; }}

.link {{
    pointer-events: stroke;
}}
.link:hover {{
    stroke-opacity: 0.8;
    stroke-width: 3;
}}

/* Nodes */
.node circle {{
    stroke-width: 1.5;
    cursor: pointer;
    transition: filter 0.2s;
}}
.node circle:hover {{
    filter: brightness(1.4) drop-shadow(0 0 8px currentColor);
}}
.node text {{
    font-size: 9px;
    fill: #a0a0b0;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.2s;
}}
.node:hover text {{
    opacity: 1;
}}
.node.highlighted text {{
    opacity: 1;
    fill: #ffffff;
}}
.node.highlighted circle {{
    filter: brightness(1.4) drop-shadow(0 0 12px currentColor);
}}
.node.dimmed circle {{
    opacity: 0.1;
}}
.node.dimmed text {{
    opacity: 0;
}}

/* Pulse animation for danger/pain nodes */
@keyframes pulse {{
    0% {{ filter: drop-shadow(0 0 3px currentColor); }}
    50% {{ filter: drop-shadow(0 0 12px currentColor); }}
    100% {{ filter: drop-shadow(0 0 3px currentColor); }}
}}
.node.danger circle {{
    animation: pulse 2s ease-in-out infinite;
}}

/* Region labels */
.region-label {{
    font-size: 11px;
    fill: rgba(255, 255, 255, 0.15);
    text-transform: uppercase;
    letter-spacing: 3px;
    pointer-events: none;
}}

/* Tooltip */
#tooltip {{
    position: fixed;
    background: rgba(20, 20, 40, 0.95);
    border: 1px solid rgba(255, 255, 255, 0.1);
    border-radius: 8px;
    padding: 12px 16px;
    font-size: 12px;
    line-height: 1.5;
    max-width: 350px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    backdrop-filter: blur(10px);
    z-index: 100;
    box-shadow: 0 4px 20px rgba(0, 0, 0, 0.5);
}}
#tooltip.visible {{ opacity: 1; }}
#tooltip .tt-type {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.5;
    margin-bottom: 4px;
}}
#tooltip .tt-title {{
    font-size: 14px;
    font-weight: bold;
    margin-bottom: 6px;
}}
#tooltip .tt-emotion {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: bold;
    margin-bottom: 6px;
}}
#tooltip .tt-body {{
    opacity: 0.7;
    font-size: 11px;
}}
#tooltip .tt-meta {{
    margin-top: 8px;
    font-size: 10px;
    opacity: 0.4;
    border-top: 1px solid rgba(255,255,255,0.1);
    padding-top: 6px;
}}

/* Controls */
#controls {{
    position: fixed;
    top: 20px;
    left: 20px;
    z-index: 50;
}}
#controls h1 {{
    font-size: 18px;
    font-weight: 600;
    color: #4ECDC4;
    margin-bottom: 4px;
    letter-spacing: 2px;
}}
#controls .subtitle {{
    font-size: 11px;
    opacity: 0.4;
    margin-bottom: 16px;
}}

/* Legend */
#legend {{
    position: fixed;
    bottom: 20px;
    left: 20px;
    z-index: 50;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}}
.legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    opacity: 0.5;
    cursor: pointer;
    transition: opacity 0.2s;
}}
.legend-item:hover {{ opacity: 1; }}
.legend-item.active {{ opacity: 1; }}
.legend-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
}}

/* Stats */
#stats {{
    position: fixed;
    top: 20px;
    right: 20px;
    z-index: 50;
    text-align: right;
    font-size: 11px;
    opacity: 0.4;
}}
#stats .stat-row {{
    margin-bottom: 2px;
}}
#stats .stat-value {{
    color: #4ECDC4;
    font-weight: bold;
}}

/* Filter bar */
#filters {{
    position: fixed;
    top: 80px;
    left: 20px;
    z-index: 50;
    display: flex;
    flex-direction: column;
    gap: 6px;
}}
.filter-btn {{
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    color: #e0e0e0;
    padding: 4px 12px;
    border-radius: 14px;
    font-size: 11px;
    font-family: inherit;
    cursor: pointer;
    transition: all 0.2s;
}}
.filter-btn:hover {{
    background: rgba(255,255,255,0.1);
}}
.filter-btn.active {{
    background: rgba(78, 205, 196, 0.2);
    border-color: #4ECDC4;
    color: #4ECDC4;
}}

/* Search */
#search {{
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 50;
}}
#search input {{
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    color: #e0e0e0;
    padding: 8px 16px;
    border-radius: 20px;
    font-size: 12px;
    font-family: inherit;
    width: 280px;
    outline: none;
    transition: all 0.2s;
}}
#search input:focus {{
    border-color: #4ECDC4;
    background: rgba(255,255,255,0.08);
    width: 360px;
}}
#search input::placeholder {{
    color: rgba(255,255,255,0.2);
}}
.mode-btn {{
    display: inline-block;
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-family: inherit;
    color: rgba(255,255,255,0.4);
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    text-decoration: none;
    transition: all 0.2s;
    cursor: pointer;
}}
.mode-btn:hover {{
    color: #e0e0e0;
    background: rgba(255,255,255,0.1);
}}
.mode-btn.active {{
    color: #4ECDC4;
    background: rgba(78,205,196,0.15);
    border-color: #4ECDC4;
    pointer-events: none;
}}
</style>
</head>
<body>

<div id="controls">
    <h1>COGMEM</h1>
    <div class="subtitle">cognitive memory map</div>
    <div id="mode-toggle" style="margin-top:10px;display:flex;gap:4px;">
        <a class="mode-btn active" href="#">2D</a>
        <a class="mode-btn" href="brain-3d.html">3D</a>
    </div>
</div>

<div id="search">
    <input type="text" placeholder="Search memories..." id="search-input">
</div>

<div id="filters"></div>

<div id="stats"></div>

<div id="legend"></div>

<div id="canvas-container">
    <svg id="brain-svg"></svg>
</div>

<div id="tooltip"></div>

<script>
// ---------------------------------------------------------------------------
// Data
// ---------------------------------------------------------------------------
const DATA = {graph_json};

const REGION_COLORS = {{
    episodic:    '#4ECDC4',
    semantic:    '#45B7D1',
    spatial:     '#96CEB4',
    pattern:     '#FFEAA7',
    emotional:   '#FF6B6B',
    prospective: '#DDA0DD',
    entity:      '#A0AEC0',
}};

const EMOTION_COLORS = {{
    pain:        '#FF4444',
    danger:      '#FF6B35',
    frustration: '#FF8C42',
    trust:       '#4ECDC4',
    pride:       '#45B7D1',
    relief:      '#96CEB4',
    curiosity:   '#DDA0DD',
    neutral:     '#666677',
}};

const TIER_LABELS = {{ repo: '', workspace: 'WS', global: 'GLB' }};

// ---------------------------------------------------------------------------
// Setup SVG
// ---------------------------------------------------------------------------
const width = window.innerWidth;
const height = window.innerHeight;
const svg = d3.select('#brain-svg');

// Zoom
const g = svg.append('g');
const zoom = d3.zoom()
    .scaleExtent([0.2, 5])
    .on('zoom', (event) => g.attr('transform', event.transform));
svg.call(zoom);

// Brain background glow — elliptical rings
const brainG = g.append('g').attr('class', 'brain-bg-group');
for (let i = 1; i <= 5; i++) {{
    brainG.append('ellipse')
        .attr('class', 'brain-bg')
        .attr('cx', width / 2)
        .attr('cy', height / 2)
        .attr('rx', 120 * i)
        .attr('ry', 90 * i)
        .style('stroke-opacity', 0.03 + (5 - i) * 0.01);
}}

// ---------------------------------------------------------------------------
// Force simulation
// ---------------------------------------------------------------------------
const nodes = DATA.nodes;
const links = DATA.links.filter(l =>
    nodes.some(n => n.id === l.source) && nodes.some(n => n.id === l.target)
);

// Assign region center positions — spread around a circle like brain lobes
const cx = width / 2, cy = height / 2;
const R = Math.min(width, height) * 0.32;
const regionCenters = {{
    semantic:    {{ x: cx,              y: cy - R * 1.1 }},       // top center (frontal)
    episodic:    {{ x: cx - R * 0.95,   y: cy - R * 0.45 }},     // upper left (temporal)
    spatial:     {{ x: cx + R * 0.95,   y: cy - R * 0.45 }},     // upper right (parietal)
    pattern:     {{ x: cx - R * 1.05,   y: cy + R * 0.5 }},      // lower left
    prospective: {{ x: cx + R * 1.05,   y: cy + R * 0.5 }},      // lower right
    emotional:   {{ x: cx,              y: cy + R * 1.1 }},       // bottom center (limbic)
    entity:      {{ x: cx,              y: cy }},                  // center (core)
}};

// Initialize positions near region centers with spread proportional to count
const regionCounts = {{}};
nodes.forEach(n => {{ regionCounts[n.region] = (regionCounts[n.region] || 0) + 1; }});

nodes.forEach(n => {{
    const center = regionCenters[n.region] || {{ x: cx, y: cy }};
    const count = regionCounts[n.region] || 1;
    const spread = Math.min(200, 40 + Math.sqrt(count) * 18);
    n.x = center.x + (Math.random() - 0.5) * spread;
    n.y = center.y + (Math.random() - 0.5) * spread;
}});

const simulation = d3.forceSimulation(nodes)
    .force('link', d3.forceLink(links).id(d => d.id).distance(50).strength(d => d.strength * 0.2))
    .force('charge', d3.forceManyBody().strength(d => {{
        // Entities repel less so they stay compact; others repel more to spread out
        if (d.region === 'entity') return -15 - d.size * 1.5;
        return -30 - d.size * 4;
    }}))
    .force('center', d3.forceCenter(cx, cy).strength(0.01))
    .force('collision', d3.forceCollide().radius(d => d.size + 3).strength(0.7))
    .force('cluster', clusterForce(0.3))
    .force('regionRepel', regionRepelForce(0.5))
    .alphaDecay(0.015);

function clusterForce(strength) {{
    return function(alpha) {{
        nodes.forEach(n => {{
            const center = regionCenters[n.region];
            if (center) {{
                n.vx += (center.x - n.x) * strength * alpha;
                n.vy += (center.y - n.y) * strength * alpha;
            }}
        }});
    }};
}}

// Push nodes from OTHER regions away from each other's centers
function regionRepelForce(strength) {{
    return function(alpha) {{
        nodes.forEach(n => {{
            Object.entries(regionCenters).forEach(([region, center]) => {{
                if (region === n.region) return;
                const dx = n.x - center.x;
                const dy = n.y - center.y;
                const dist = Math.sqrt(dx * dx + dy * dy) || 1;
                const minDist = R * 0.5;
                if (dist < minDist) {{
                    const force = (minDist - dist) / dist * strength * alpha;
                    n.vx += dx * force;
                    n.vy += dy * force;
                }}
            }});
        }});
    }};
}}

// ---------------------------------------------------------------------------
// Render
// ---------------------------------------------------------------------------

// Links
const linkG = g.append('g').attr('class', 'links');
const LINK_LABELS = {{
    touched: 'touched by',
    related: 'related to',
    evidence: 'evidence for',
    feels: 'emotion about',
    formed_from: 'formed from',
    defined_in: 'defined in',
    seen_in: 'seen in',
}};

const linkElements = linkG.selectAll('line')
    .data(links)
    .enter().append('line')
    .attr('class', d => `link ${{d.type}}`)
    .attr('stroke-width', d => 0.5 + d.strength * 1.5)
    .on('mouseover', function(event, d) {{
        d3.select(this).attr('stroke-opacity', 0.8).attr('stroke-width', 3);
        const srcLabel = (typeof d.source === 'object' ? d.source.label : d.source) || '?';
        const tgtLabel = (typeof d.target === 'object' ? d.target.label : d.target) || '?';
        const relation = LINK_LABELS[d.type] || d.type;
        tooltip.innerHTML = `<div class="tt-type">connection</div>`
            + `<div class="tt-title">${{srcLabel}}</div>`
            + `<div class="tt-body">${{relation}} <strong>${{tgtLabel}}</strong></div>`
            + `<div class="tt-meta">strength: ${{(d.strength || 0).toFixed(2)}}</div>`;
        tooltip.classList.add('visible');
    }})
    .on('mousemove', moveTooltip)
    .on('mouseout', function() {{
        d3.select(this).attr('stroke-opacity', null).attr('stroke-width', d => 0.5 + d.strength * 1.5);
        tooltip.classList.remove('visible');
    }})
    .on('click', function(event, d) {{
        event.stopPropagation();
        const sid = typeof d.source === 'object' ? d.source.id : d.source;
        const tid = typeof d.target === 'object' ? d.target.id : d.target;
        const linkKey = sid + '|' + tid;
        // Single click: add link (nodes become neighbors, not primary)
        selectedLinks.add(linkKey);
        renderSelection();
    }})
    .on('dblclick', function(event, d) {{
        event.stopPropagation();
        const sid = typeof d.source === 'object' ? d.source.id : d.source;
        const tid = typeof d.target === 'object' ? d.target.id : d.target;
        const linkKey = sid + '|' + tid;
        // Double click: remove from selection
        selectedLinks.delete(linkKey);
        renderSelection();
    }});

// Nodes
const nodeG = g.append('g').attr('class', 'nodes');
const nodeElements = nodeG.selectAll('g')
    .data(nodes)
    .enter().append('g')
    .attr('class', d => {{
        let cls = 'node';
        if (d.emotion === 'pain' || d.emotion === 'danger' || d.danger_level === 'high' || d.danger_level === 'critical') cls += ' danger';
        return cls;
    }})
    .call(d3.drag()
        .on('start', dragStarted)
        .on('drag', dragged)
        .on('end', dragEnded))
    .on('mouseover', showTooltip)
    .on('mousemove', moveTooltip)
    .on('mouseout', hideTooltip)
    .on('click', highlightConnected);

nodeElements.append('circle')
    .attr('r', d => d.size || 5)
    .attr('fill', d => {{
        if (d.emotion && d.emotion !== 'neutral' && EMOTION_COLORS[d.emotion]) {{
            return EMOTION_COLORS[d.emotion];
        }}
        return REGION_COLORS[d.region] || '#666';
    }})
    .attr('stroke', d => {{
        if (d.tier === 'workspace') return '#FFD700';
        if (d.tier === 'global') return '#FF69B4';
        return 'rgba(255,255,255,0.1)';
    }})
    .attr('opacity', d => 0.3 + (d.strength || 0.5) * 0.7);

nodeElements.append('text')
    .attr('dx', d => d.size + 4)
    .attr('dy', 3)
    .text(d => d.label);

// Region labels
Object.entries(regionCenters).forEach(([region, pos]) => {{
    g.append('text')
        .attr('class', 'region-label')
        .attr('x', pos.x)
        .attr('y', pos.y - 100)
        .attr('text-anchor', 'middle')
        .text(region.toUpperCase());
}});

// Tick
simulation.on('tick', () => {{
    linkElements
        .attr('x1', d => d.source.x)
        .attr('y1', d => d.source.y)
        .attr('x2', d => d.target.x)
        .attr('y2', d => d.target.y);
    nodeElements
        .attr('transform', d => `translate(${{d.x}},${{d.y}})`);
}});

// ---------------------------------------------------------------------------
// Drag
// ---------------------------------------------------------------------------
function dragStarted(event, d) {{
    if (!event.active) simulation.alphaTarget(0.3).restart();
    d.fx = d.x;
    d.fy = d.y;
}}
function dragged(event, d) {{
    d.fx = event.x;
    d.fy = event.y;
}}
function dragEnded(event, d) {{
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
}}

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------
const tooltip = document.getElementById('tooltip');

function showTooltip(event, d) {{
    let html = `<div class="tt-type">${{d.type}} ${{d.tier !== 'repo' ? '(' + d.tier + ')' : ''}}</div>`;
    html += `<div class="tt-title">${{d.label}}</div>`;

    if (d.emotion && d.emotion !== 'neutral') {{
        const color = EMOTION_COLORS[d.emotion] || '#666';
        html += `<div class="tt-emotion" style="background:${{color}}33;color:${{color}}">${{d.emotion.toUpperCase()}} (${{(d.intensity || 0).toFixed(1)}})</div>`;
    }}

    let body = '';
    if (d.story) body += d.story + '<br>';
    if (d.learned) body += '<strong>Learned:</strong> ' + d.learned + '<br>';
    if (d.what) body += d.what + '<br>';
    if (d.why) body += '<em>' + d.why + '</em><br>';
    if (d.signature) body += '<code>' + d.signature + '</code><br>';
    if (d.consequence) body += '<strong>Risk:</strong> ' + d.consequence + '<br>';
    if (d.response) body += '<strong>Fix:</strong> ' + d.response + '<br>';
    if (d.reason) body += d.reason + '<br>';
    if (d.intention) body += d.intention + '<br>';
    if (d.description) body += d.description + '<br>';

    if (body) html += `<div class="tt-body">${{body}}</div>`;

    let meta = [];
    if (d.strength !== undefined) meta.push(`strength: ${{d.strength.toFixed(2)}}`);
    if (d.phase) meta.push(`phase: ${{d.phase}}`);
    if (d.date) meta.push(d.date);
    if (d.frequency) meta.push(`seen ${{d.frequency}}x`);
    if (d.kind) meta.push(d.kind);
    if (d.judgment) meta.push(d.judgment);
    if (meta.length) html += `<div class="tt-meta">${{meta.join(' · ')}}</div>`;

    tooltip.innerHTML = html;
    tooltip.classList.add('visible');
}}

function moveTooltip(event) {{
    const x = event.clientX + 15;
    const y = event.clientY + 15;
    const rect = tooltip.getBoundingClientRect();
    tooltip.style.left = (x + rect.width > window.innerWidth ? x - rect.width - 30 : x) + 'px';
    tooltip.style.top = (y + rect.height > window.innerHeight ? y - rect.height - 30 : y) + 'px';
}}

function hideTooltip() {{
    tooltip.classList.remove('visible');
}}

// ---------------------------------------------------------------------------
// Additive selection — single click adds, double click removes
// ---------------------------------------------------------------------------
// Primary = explicitly clicked nodes (their connections are shown)
// Neighbor = nodes at other end of primary connections (just highlighted, no cascade)
const primaryNodes = new Set();
const selectedLinks = new Set();

function clearSelection() {{
    primaryNodes.clear();
    selectedLinks.clear();
    renderSelection();
}}

function renderSelection() {{
    const hasPrimary = primaryNodes.size > 0;
    const hasLinks = selectedLinks.size > 0;
    const hasSelection = hasPrimary || hasLinks;

    // Build neighbor set: nodes connected to primary nodes (but not primary themselves)
    const neighborNodes = new Set();
    if (hasPrimary) {{
        links.forEach(l => {{
            const sid = typeof l.source === 'object' ? l.source.id : l.source;
            const tid = typeof l.target === 'object' ? l.target.id : l.target;
            if (primaryNodes.has(sid) && !primaryNodes.has(tid)) neighborNodes.add(tid);
            if (primaryNodes.has(tid) && !primaryNodes.has(sid)) neighborNodes.add(sid);
        }});
    }}
    // Also add nodes from explicitly selected links
    selectedLinks.forEach(lk => {{
        const [s, t] = lk.split('|');
        if (!primaryNodes.has(s)) neighborNodes.add(s);
        if (!primaryNodes.has(t)) neighborNodes.add(t);
    }});

    const allHighlighted = new Set([...primaryNodes, ...neighborNodes]);

    // Links to highlight: only those with at least one PRIMARY end, or explicitly selected
    const highlightedLinkKeys = new Set(selectedLinks);
    if (hasPrimary) {{
        links.forEach(l => {{
            const sid = typeof l.source === 'object' ? l.source.id : l.source;
            const tid = typeof l.target === 'object' ? l.target.id : l.target;
            // Only highlight if at least one end is PRIMARY (not just neighbor)
            if (primaryNodes.has(sid) || primaryNodes.has(tid)) {{
                highlightedLinkKeys.add(sid + '|' + tid);
            }}
        }});
    }}

    nodeElements.attr('class', n => {{
        let cls = 'node';
        if (n.emotion === 'pain' || n.emotion === 'danger') cls += ' danger';
        if (!hasSelection) return cls;
        if (allHighlighted.has(n.id)) cls += ' highlighted';
        else cls += ' dimmed';
        return cls;
    }});

    linkElements.style('stroke-opacity', l => {{
        if (!hasSelection) return null;
        const sid = typeof l.source === 'object' ? l.source.id : l.source;
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        const key = sid + '|' + tid;
        const revKey = tid + '|' + sid;
        if (highlightedLinkKeys.has(key) || highlightedLinkKeys.has(revKey)) {{
            return selectedLinks.has(key) || selectedLinks.has(revKey) ? 0.9 : 0.5;
        }}
        return 0.02;
    }}).attr('stroke-width', l => {{
        if (!hasSelection) return 0.5 + l.strength * 1.5;
        const sid = typeof l.source === 'object' ? l.source.id : l.source;
        const tid = typeof l.target === 'object' ? l.target.id : l.target;
        const key = sid + '|' + tid;
        const revKey = tid + '|' + sid;
        if (selectedLinks.has(key) || selectedLinks.has(revKey)) return 4;
        if (highlightedLinkKeys.has(key) || highlightedLinkKeys.has(revKey)) return 2;
        return 0.5 + l.strength * 1.5;
    }});
}}

function highlightConnected(event, d) {{
    event.stopPropagation();
    // Single click: add as primary node
    primaryNodes.add(d.id);
    renderSelection();
}}

// Double-click node to remove from selection
nodeElements.on('dblclick', function(event, d) {{
    event.stopPropagation();
    primaryNodes.delete(d.id);
    // Also remove links that were only there because of this node
    for (const lk of [...selectedLinks]) {{
        const [s, t] = lk.split('|');
        if (s === d.id || t === d.id) {{
            selectedLinks.delete(lk);
        }}
    }}
    renderSelection();
}});

// Double-click background to clear all
svg.on('click', (event) => {{
    // Single click background: do nothing (preserve selection)
}});
svg.on('dblclick', () => clearSelection());

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
const searchInput = document.getElementById('search-input');
searchInput.addEventListener('input', (e) => {{
    const query = e.target.value.toLowerCase();
    if (!query) {{
        nodeElements.attr('class', n => {{
            let cls = 'node';
            if (n.emotion === 'pain' || n.emotion === 'danger') cls += ' danger';
            return cls;
        }});
        linkElements.style('stroke-opacity', null);
        return;
    }}

    const matches = new Set();
    nodes.forEach(n => {{
        const text = (n.label + ' ' + (n.story || '') + ' ' + (n.learned || '') +
                      ' ' + (n.what || '') + ' ' + (n.signature || '') +
                      ' ' + (n.reason || '')).toLowerCase();
        if (text.includes(query)) matches.add(n.id);
    }});

    nodeElements.attr('class', n => {{
        let cls = 'node';
        if (n.emotion === 'pain' || n.emotion === 'danger') cls += ' danger';
        if (matches.has(n.id)) cls += ' highlighted';
        else if (matches.size > 0) cls += ' dimmed';
        return cls;
    }});
}});

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------
const legend = document.getElementById('legend');
Object.entries(REGION_COLORS).forEach(([region, color]) => {{
    const count = nodes.filter(n => n.region === region).length;
    if (count === 0) return;
    const item = document.createElement('div');
    item.className = 'legend-item active';
    item.innerHTML = `<div class="legend-dot" style="background:${{color}}"></div>${{region}} (${{count}})`;

    let visible = true;
    item.addEventListener('click', () => {{
        visible = !visible;
        item.classList.toggle('active', visible);
        nodeElements.filter(n => n.region === region)
            .style('display', visible ? null : 'none');
        linkElements.each(function(l) {{
            const sid = typeof l.source === 'object' ? l.source.id : l.source;
            const tid = typeof l.target === 'object' ? l.target.id : l.target;
            const sn = nodes.find(n => n.id === sid);
            const tn = nodes.find(n => n.id === tid);
            if ((sn && sn.region === region) || (tn && tn.region === region)) {{
                d3.select(this).style('display', visible ? null : 'none');
            }}
        }});
    }});
    legend.appendChild(item);
}});

// ---------------------------------------------------------------------------
// Stats
// ---------------------------------------------------------------------------
const stats = document.getElementById('stats');
const typeCounts = {{}};
nodes.forEach(n => {{ typeCounts[n.type] = (typeCounts[n.type] || 0) + 1; }});
let statsHtml = `<div class="stat-row"><span class="stat-value">${{nodes.length}}</span> memories</div>`;
statsHtml += `<div class="stat-row"><span class="stat-value">${{links.length}}</span> connections</div>`;
Object.entries(typeCounts).sort((a, b) => b[1] - a[1]).forEach(([type, count]) => {{
    statsHtml += `<div class="stat-row">${{count}} ${{type}}s</div>`;
}});
stats.innerHTML = statsHtml;

// ---------------------------------------------------------------------------
// Keyboard shortcuts
// ---------------------------------------------------------------------------
document.addEventListener('keydown', (e) => {{
    if (e.key === 'Escape') {{
        searchInput.value = '';
        searchInput.dispatchEvent(new Event('input'));
        clearSelection();
    }}
    if (e.key === '/' && document.activeElement !== searchInput) {{
        e.preventDefault();
        searchInput.focus();
    }}
}});

// Initial zoom to fit
setTimeout(() => {{
    const bounds = g.node().getBBox();
    const fullWidth = bounds.width;
    const fullHeight = bounds.height;
    const midX = bounds.x + fullWidth / 2;
    const midY = bounds.y + fullHeight / 2;
    const scale = 0.8 / Math.max(fullWidth / width, fullHeight / height);
    svg.transition().duration(1000).call(
        zoom.transform,
        d3.zoomIdentity.translate(width / 2 - midX * scale, height / 2 - midY * scale).scale(scale)
    );
}}, 2000);

</script>
</body>
</html>"""

    return html


def _generate_html_3d(data: dict) -> str:
    """Generate a 3D brain visualization using Three.js."""
    graph_json = json.dumps(data, default=str)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>cogmem — 3D Brain</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/three@0.128.0/examples/js/controls/OrbitControls.js"></script>
<style>
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{
    background: #050510;
    color: #e0e0e0;
    font-family: 'SF Mono', 'Fira Code', monospace;
    overflow: hidden;
}}
canvas {{ display: block; }}

#ui {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    pointer-events: none;
    z-index: 10;
}}
#ui > * {{ pointer-events: auto; }}

#controls {{
    position: fixed;
    top: 20px;
    left: 20px;
}}
#controls h1 {{
    font-size: 20px;
    font-weight: 600;
    color: #4ECDC4;
    letter-spacing: 3px;
    text-shadow: 0 0 20px rgba(78, 205, 196, 0.5);
}}
#controls .subtitle {{
    font-size: 11px;
    opacity: 0.3;
    margin-top: 2px;
}}

#search {{
    position: fixed;
    top: 20px;
    left: 50%;
    transform: translateX(-50%);
}}
#search input {{
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    color: #e0e0e0;
    padding: 8px 20px;
    border-radius: 20px;
    font-size: 12px;
    font-family: inherit;
    width: 300px;
    outline: none;
    backdrop-filter: blur(10px);
}}
#search input:focus {{
    border-color: #4ECDC4;
    width: 380px;
    box-shadow: 0 0 20px rgba(78, 205, 196, 0.2);
}}
#search input::placeholder {{ color: rgba(255,255,255,0.2); }}

#stats {{
    position: fixed;
    top: 20px;
    right: 20px;
    text-align: right;
    font-size: 11px;
    opacity: 0.4;
}}
#stats .val {{ color: #4ECDC4; font-weight: bold; }}

#tooltip {{
    position: fixed;
    background: rgba(10, 10, 30, 0.95);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 10px;
    padding: 14px 18px;
    font-size: 12px;
    line-height: 1.6;
    max-width: 380px;
    pointer-events: none;
    opacity: 0;
    transition: opacity 0.15s;
    backdrop-filter: blur(15px);
    box-shadow: 0 8px 30px rgba(0,0,0,0.6);
    z-index: 100;
}}
#tooltip.visible {{ opacity: 1; }}
#tooltip .tt-type {{
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 1px;
    opacity: 0.4;
}}
#tooltip .tt-title {{
    font-size: 14px;
    font-weight: bold;
    margin: 4px 0;
}}
#tooltip .tt-emotion {{
    display: inline-block;
    padding: 2px 10px;
    border-radius: 10px;
    font-size: 10px;
    font-weight: bold;
    margin-bottom: 4px;
}}
#tooltip .tt-body {{
    opacity: 0.6;
    font-size: 11px;
}}
#tooltip .tt-meta {{
    margin-top: 8px;
    font-size: 10px;
    opacity: 0.3;
    border-top: 1px solid rgba(255,255,255,0.1);
    padding-top: 6px;
}}

#legend {{
    position: fixed;
    bottom: 20px;
    left: 20px;
    display: flex;
    gap: 16px;
    flex-wrap: wrap;
}}
.legend-item {{
    display: flex;
    align-items: center;
    gap: 6px;
    font-size: 11px;
    opacity: 0.5;
    cursor: pointer;
}}
.legend-item:hover, .legend-item.active {{ opacity: 1; }}
.legend-dot {{
    width: 10px;
    height: 10px;
    border-radius: 50%;
}}

#hint {{
    position: fixed;
    bottom: 20px;
    right: 20px;
    font-size: 10px;
    opacity: 0.2;
}}
.mode-btn {{
    display: inline-block;
    padding: 3px 12px;
    border-radius: 12px;
    font-size: 11px;
    font-family: inherit;
    color: rgba(255,255,255,0.4);
    background: rgba(255,255,255,0.05);
    border: 1px solid rgba(255,255,255,0.1);
    text-decoration: none;
    transition: all 0.2s;
    cursor: pointer;
}}
.mode-btn:hover {{
    color: #e0e0e0;
    background: rgba(255,255,255,0.1);
}}
.mode-btn.active {{
    color: #4ECDC4;
    background: rgba(78,205,196,0.15);
    border-color: #4ECDC4;
    pointer-events: none;
}}
</style>
</head>
<body>
<div id="ui">
    <div id="controls">
        <h1>COGMEM</h1>
        <div class="subtitle">3d cognitive memory</div>
        <div id="mode-toggle" style="margin-top:10px;display:flex;gap:4px;">
            <a class="mode-btn" href="brain-2d.html">2D</a>
            <a class="mode-btn active" href="#">3D</a>
        </div>
    </div>
    <div id="search">
        <input type="text" placeholder="Search memories..." id="search-input">
    </div>
    <div id="stats"></div>
    <div id="legend"></div>
    <div id="hint">drag to rotate / scroll to zoom / click nodes to explore</div>
</div>
<div id="tooltip"></div>

<script>
const DATA = {graph_json};

const REGION_COLORS = {{
    episodic:    0x4ECDC4,
    semantic:    0x45B7D1,
    spatial:     0x96CEB4,
    pattern:     0xFFEAA7,
    emotional:   0xFF6B6B,
    prospective: 0xDDA0DD,
    entity:      0x8090A0,
}};

const REGION_COLORS_CSS = {{
    episodic:    '#4ECDC4',
    semantic:    '#45B7D1',
    spatial:     '#96CEB4',
    pattern:     '#FFEAA7',
    emotional:   '#FF6B6B',
    prospective: '#DDA0DD',
    entity:      '#8090A0',
}};

const EMOTION_COLORS = {{
    pain: 0xFF4444, danger: 0xFF6B35, frustration: 0xFF8C42,
    trust: 0x4ECDC4, pride: 0x45B7D1, relief: 0x96CEB4,
    curiosity: 0xDDA0DD, neutral: 0x556677,
}};

const EMOTION_COLORS_CSS = {{
    pain: '#FF4444', danger: '#FF6B35', frustration: '#FF8C42',
    trust: '#4ECDC4', pride: '#45B7D1', relief: '#96CEB4',
    curiosity: '#DDA0DD', neutral: '#556677',
}};

// ---------------------------------------------------------------------------
// Scene setup
// ---------------------------------------------------------------------------
const scene = new THREE.Scene();
scene.fog = new THREE.FogExp2(0x050510, 0.0015);

const camera = new THREE.PerspectiveCamera(60, window.innerWidth / window.innerHeight, 1, 5000);
camera.position.set(0, 100, 400);

const renderer = new THREE.WebGLRenderer({{ antialias: true, alpha: true }});
renderer.setSize(window.innerWidth, window.innerHeight);
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
document.body.appendChild(renderer.domElement);

const controls = new THREE.OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;
controls.minDistance = 50;
controls.maxDistance = 1500;
controls.autoRotate = false;
controls.autoRotateSpeed = 0.3;

// Lights
scene.add(new THREE.AmbientLight(0x222233, 1));
const pointLight = new THREE.PointLight(0x4ECDC4, 0.8, 800);
pointLight.position.set(0, 200, 0);
scene.add(pointLight);
const pointLight2 = new THREE.PointLight(0xFF6B6B, 0.4, 600);
pointLight2.position.set(-200, -100, 100);
scene.add(pointLight2);

// ---------------------------------------------------------------------------
// Brain shell — translucent ellipsoid
// ---------------------------------------------------------------------------
const brainGeo = new THREE.SphereGeometry(180, 64, 48);
brainGeo.scale(1.2, 1.0, 1.0);
const brainMat = new THREE.MeshPhongMaterial({{
    color: 0x1a1a2e,
    transparent: true,
    opacity: 0.06,
    wireframe: false,
    side: THREE.DoubleSide,
    depthWrite: false,
}});
const brainShell = new THREE.Mesh(brainGeo, brainMat);
scene.add(brainShell);

// Wireframe overlay
const wireGeo = new THREE.SphereGeometry(182, 32, 24);
wireGeo.scale(1.2, 1.0, 1.0);
const wireMat = new THREE.MeshBasicMaterial({{
    color: 0x4ECDC4,
    transparent: true,
    opacity: 0.03,
    wireframe: true,
}});
scene.add(new THREE.Mesh(wireGeo, wireMat));

// ---------------------------------------------------------------------------
// Region centers in 3D — brain-lobe positions
// ---------------------------------------------------------------------------
const R = 120;
const regionCenters3D = {{
    semantic:    new THREE.Vector3(0, R * 0.9, -R * 0.3),       // frontal top
    episodic:    new THREE.Vector3(-R * 0.8, R * 0.2, R * 0.5),  // left temporal
    spatial:     new THREE.Vector3(R * 0.8, R * 0.2, -R * 0.5),  // right parietal
    pattern:     new THREE.Vector3(-R * 0.7, -R * 0.5, -R * 0.4),// left lower
    prospective: new THREE.Vector3(R * 0.7, -R * 0.5, R * 0.4),  // right lower
    emotional:   new THREE.Vector3(0, -R * 0.8, 0),               // bottom (limbic)
    entity:      new THREE.Vector3(0, 0, 0),                      // center (core)
}};

// ---------------------------------------------------------------------------
// Create nodes
// ---------------------------------------------------------------------------
const nodes = DATA.nodes;
const links = DATA.links.filter(l =>
    nodes.some(n => n.id === l.source) && nodes.some(n => n.id === l.target)
);

const nodeMap = {{}};
const nodeMeshes = [];
const nodeGroup = new THREE.Group();
scene.add(nodeGroup);

nodes.forEach((n, i) => {{
    const center = regionCenters3D[n.region] || new THREE.Vector3(0, 0, 0);
    const spread = n.region === 'entity' ? 80 : 50;

    const x = center.x + (Math.random() - 0.5) * spread;
    const y = center.y + (Math.random() - 0.5) * spread;
    const z = center.z + (Math.random() - 0.5) * spread;

    const size = (n.size || 5) * 0.6;
    const color = (n.emotion && n.emotion !== 'neutral' && EMOTION_COLORS[n.emotion])
        ? EMOTION_COLORS[n.emotion]
        : (REGION_COLORS[n.region] || 0x666666);

    const geo = new THREE.SphereGeometry(size, 12, 8);
    const mat = new THREE.MeshPhongMaterial({{
        color: color,
        emissive: color,
        emissiveIntensity: 0.3 + (n.strength || 0.5) * 0.4,
        transparent: true,
        opacity: 0.4 + (n.strength || 0.5) * 0.6,
    }});
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.set(x, y, z);
    mesh.userData = {{ ...n, index: i }};
    nodeGroup.add(mesh);
    nodeMeshes.push(mesh);
    nodeMap[n.id] = mesh;
}});

// Glow sprites for key nodes (emotions, patterns)
const glowTexture = _createGlowTexture();
nodes.forEach((n, i) => {{
    if (n.emotion === 'pain' || n.emotion === 'danger' || n.type === 'pattern') {{
        const color = EMOTION_COLORS[n.emotion] || REGION_COLORS[n.region] || 0xffffff;
        const sprite = new THREE.Sprite(new THREE.SpriteMaterial({{
            map: glowTexture,
            color: color,
            transparent: true,
            opacity: 0.15,
            blending: THREE.AdditiveBlending,
            depthWrite: false,
        }}));
        const size = (n.size || 5) * 3;
        sprite.scale.set(size, size, 1);
        sprite.position.copy(nodeMeshes[i].position);
        nodeGroup.add(sprite);
    }}
}});

function _createGlowTexture() {{
    const canvas = document.createElement('canvas');
    canvas.width = 128;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');
    const gradient = ctx.createRadialGradient(64, 64, 0, 64, 64, 64);
    gradient.addColorStop(0, 'rgba(255,255,255,1)');
    gradient.addColorStop(0.3, 'rgba(255,255,255,0.3)');
    gradient.addColorStop(1, 'rgba(255,255,255,0)');
    ctx.fillStyle = gradient;
    ctx.fillRect(0, 0, 128, 128);
    return new THREE.CanvasTexture(canvas);
}}

// ---------------------------------------------------------------------------
// Create links as lines
// ---------------------------------------------------------------------------
const linkGroup = new THREE.Group();
scene.add(linkGroup);
const linkLines = [];

const linkMeshes = [];

function createTubeLink(srcPos, tgtPos, color, opacity, data) {{
    const dir = new THREE.Vector3().subVectors(tgtPos, srcPos);
    const length = dir.length();
    const mid = new THREE.Vector3().addVectors(srcPos, tgtPos).multiplyScalar(0.5);

    const geo = new THREE.CylinderGeometry(0.4, 0.4, length, 4, 1);
    const mat = new THREE.MeshBasicMaterial({{
        color: color,
        transparent: true,
        opacity: opacity,
        depthWrite: false,
    }});
    const mesh = new THREE.Mesh(geo, mat);
    mesh.position.copy(mid);
    // Align cylinder along the direction
    mesh.quaternion.setFromUnitVectors(
        new THREE.Vector3(0, 1, 0),
        dir.normalize()
    );
    mesh.userData = {{ ...data, _isLink: true }};
    return mesh;
}}

links.forEach(l => {{
    const srcMesh = nodeMap[l.source];
    const tgtMesh = nodeMap[l.target];
    if (!srcMesh || !tgtMesh) return;

    const linkColor = (srcMesh.userData.emotion === 'pain' || tgtMesh.userData.emotion === 'pain')
        ? 0xFF6B6B
        : (srcMesh.userData.emotion === 'danger' || tgtMesh.userData.emotion === 'danger')
        ? 0xFF6B35
        : 0x4ECDC4;
    const opacity = 0.25 + (l.strength || 0.3) * 0.35;

    const tubeMesh = createTubeLink(srcMesh.position, tgtMesh.position, linkColor, opacity, l);
    linkGroup.add(tubeMesh);
    linkMeshes.push(tubeMesh);
    linkLines.push({{ line: tubeMesh, src: srcMesh, tgt: tgtMesh, data: l }});
}});

// ---------------------------------------------------------------------------
// Region labels — 3D text sprites
// ---------------------------------------------------------------------------
Object.entries(regionCenters3D).forEach(([region, pos]) => {{
    const count = nodes.filter(n => n.region === region).length;
    if (count === 0) return;
    const sprite = makeTextSprite(region.toUpperCase(), {{
        fontSize: 14,
        color: REGION_COLORS_CSS[region] || '#ffffff',
        opacity: 0.15,
    }});
    sprite.position.set(pos.x, pos.y + 35, pos.z);
    sprite.scale.set(60, 30, 1);
    scene.add(sprite);
}});

function makeTextSprite(text, opts = {{}}) {{
    const canvas = document.createElement('canvas');
    canvas.width = 512;
    canvas.height = 128;
    const ctx = canvas.getContext('2d');
    ctx.font = `${{opts.fontSize || 14}}px monospace`;
    ctx.textAlign = 'center';
    ctx.fillStyle = opts.color || '#ffffff';
    ctx.globalAlpha = opts.opacity || 0.3;
    ctx.letterSpacing = '4px';
    ctx.fillText(text, 256, 80);
    const tex = new THREE.CanvasTexture(canvas);
    return new THREE.Sprite(new THREE.SpriteMaterial({{
        map: tex,
        transparent: true,
        depthWrite: false,
    }}));
}}

// ---------------------------------------------------------------------------
// Particle field background
// ---------------------------------------------------------------------------
const particleCount = 500;
const particleGeo = new THREE.BufferGeometry();
const positions = new Float32Array(particleCount * 3);
for (let i = 0; i < particleCount * 3; i++) {{
    positions[i] = (Math.random() - 0.5) * 1500;
}}
particleGeo.setAttribute('position', new THREE.BufferAttribute(positions, 3));
const particleMat = new THREE.PointsMaterial({{
    color: 0x4ECDC4,
    size: 1,
    transparent: true,
    opacity: 0.15,
    depthWrite: false,
}});
scene.add(new THREE.Points(particleGeo, particleMat));

// ---------------------------------------------------------------------------
// Raycaster for hover/click
// ---------------------------------------------------------------------------
const raycaster = new THREE.Raycaster();
raycaster.params.Points = {{ threshold: 5 }};
const mouse = new THREE.Vector2();
let hoveredNode = null;
const selectedNodes = new Set();
const tooltip = document.getElementById('tooltip');

const allClickable = [...nodeMeshes, ...linkMeshes];

let hoveredIds = new Set();  // nodes highlighted by hover

function onMouseMove(event) {{
    mouse.x = (event.clientX / window.innerWidth) * 2 - 1;
    mouse.y = -(event.clientY / window.innerHeight) * 2 + 1;

    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(allClickable);

    if (intersects.length > 0) {{
        const mesh = intersects[0].object;
        const d = mesh.userData;

        if (hoveredNode !== mesh) {{
            hoveredNode = mesh;

            // Build hover set — the hovered item + its neighbors
            hoveredIds.clear();
            if (d._isLink) {{
                hoveredIds.add(d.source);
                hoveredIds.add(d.target);
                const srcLabel = nodeMap[d.source] ? nodeMap[d.source].userData.label : d.source;
                const tgtLabel = nodeMap[d.target] ? nodeMap[d.target].userData.label : d.target;
                const LINK_LABELS = {{touched:'touched by',related:'related to',evidence:'evidence for',feels:'emotion about',formed_from:'formed from',defined_in:'defined in',seen_in:'seen in'}};
                showLinkTooltip(srcLabel, LINK_LABELS[d.type] || d.type, tgtLabel, d.strength || 0, event);
            }} else {{
                hoveredIds.add(d.id);
                links.forEach(l => {{
                    if (l.source === d.id) hoveredIds.add(l.target);
                    if (l.target === d.id) hoveredIds.add(l.source);
                }});
                showTooltip(d, event);
            }}
            applyVisuals();
        }} else {{
            moveTooltipTo(event);
        }}
        document.body.style.cursor = 'pointer';
    }} else {{
        if (hoveredNode) {{
            hoveredNode = null;
            hoveredIds.clear();
            applyVisuals();
        }}
        tooltip.classList.remove('visible');
        document.body.style.cursor = 'default';
    }}
}}

function onClick(event) {{
    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(allClickable);
    if (intersects.length > 0) {{
        const mesh = intersects[0].object;
        const d = mesh.userData;
        if (d._isLink) {{
            // Link click: select both endpoints
            selectedNodes.add(d.source);
            selectedNodes.add(d.target);
        }} else {{
            const id = d.id;
            selectedNodes.add(id);
            links.forEach(l => {{
                if (l.source === id) selectedNodes.add(l.target);
                if (l.target === id) selectedNodes.add(l.source);
            }});
        }}
        applySelection();
    }}
}}

function onDblClick(event) {{
    raycaster.setFromCamera(mouse, camera);
    const intersects = raycaster.intersectObjects(allClickable);
    if (intersects.length > 0) {{
        const d = intersects[0].object.userData;
        if (d._isLink) {{
            selectedNodes.delete(d.source);
            selectedNodes.delete(d.target);
        }} else {{
            selectedNodes.delete(d.id);
        }}
        applySelection();
    }} else {{
        selectedNodes.clear();
        applySelection();
    }}
}}

function showLinkTooltip(srcLabel, relation, tgtLabel, strength, event) {{
    tooltip.innerHTML = `<div class="tt-type">connection</div>`
        + `<div class="tt-title">${{srcLabel}}</div>`
        + `<div class="tt-body">${{relation}} <strong>${{tgtLabel}}</strong></div>`
        + `<div class="tt-meta">strength: ${{strength.toFixed(2)}}</div>`;
    tooltip.classList.add('visible');
    moveTooltipTo(event);
}}

function applySelection() {{ applyVisuals(); }}

function applyVisuals() {{
    // Combine click-pinned + hover-temporary selections
    const activeIds = new Set([...selectedNodes, ...hoveredIds]);
    const hasActive = activeIds.size > 0;

    nodeMeshes.forEach(mesh => {{
        const d = mesh.userData;
        const strength = d.strength || 0.5;
        if (!hasActive) {{
            // Default state
            mesh.material.opacity = 0.4 + strength * 0.6;
            mesh.material.emissiveIntensity = 0.3 + strength * 0.4;
            mesh.scale.setScalar(1.0);
        }} else if (selectedNodes.has(d.id)) {{
            // Pinned (clicked) — brightest
            mesh.material.opacity = 0.95;
            mesh.material.emissiveIntensity = 0.9;
            mesh.scale.setScalar(1.15);
        }} else if (hoveredIds.has(d.id)) {{
            // Hover highlight — bright but slightly less than pinned
            mesh.material.opacity = 0.85;
            mesh.material.emissiveIntensity = 0.75;
            mesh.scale.setScalar(1.2);
        }} else {{
            // Dimmed
            mesh.material.opacity = 0.04;
            mesh.material.emissiveIntensity = 0.03;
            mesh.scale.setScalar(1.0);
        }}
    }});

    linkLines.forEach(({{ line, data }}) => {{
        const srcActive = activeIds.has(data.source);
        const tgtActive = activeIds.has(data.target);
        if (!hasActive) {{
            line.material.opacity = 0.25 + (data.strength || 0.3) * 0.35;
        }} else if (srcActive && tgtActive) {{
            // Both ends highlighted — full bright
            line.material.opacity = 0.9;
        }} else if (srcActive || tgtActive) {{
            // One end highlighted — dim connection
            line.material.opacity = 0.15;
        }} else {{
            line.material.opacity = 0.02;
        }}
    }});
}}

window.addEventListener('mousemove', onMouseMove);
window.addEventListener('click', onClick);
window.addEventListener('dblclick', onDblClick);

// ---------------------------------------------------------------------------
// Tooltip
// ---------------------------------------------------------------------------
function showTooltip(d, event) {{
    const emotionColor = EMOTION_COLORS_CSS[d.emotion] || '#666';
    let html = `<div class="tt-type">${{d.type}} ${{d.tier !== 'repo' ? '(' + d.tier + ')' : ''}}</div>`;
    html += `<div class="tt-title">${{d.label}}</div>`;
    if (d.emotion && d.emotion !== 'neutral') {{
        html += `<div class="tt-emotion" style="background:${{emotionColor}}33;color:${{emotionColor}}">${{d.emotion.toUpperCase()}} (${{(d.intensity || 0).toFixed(1)}})</div>`;
    }}
    let body = '';
    if (d.story) body += d.story.substring(0, 200) + '<br>';
    if (d.learned) body += '<strong>Learned:</strong> ' + d.learned.substring(0, 200) + '<br>';
    if (d.what) body += d.what + '<br>';
    if (d.signature) body += '<code>' + d.signature + '</code><br>';
    if (d.consequence) body += '<strong>Risk:</strong> ' + d.consequence + '<br>';
    if (d.reason) body += d.reason + '<br>';
    if (body) html += `<div class="tt-body">${{body}}</div>`;
    let meta = [];
    if (d.strength !== undefined) meta.push('strength: ' + d.strength.toFixed(2));
    if (d.phase) meta.push('phase: ' + d.phase);
    if (d.date) meta.push(d.date);
    if (d.kind) meta.push(d.kind);
    if (meta.length) html += `<div class="tt-meta">${{meta.join(' &middot; ')}}</div>`;
    tooltip.innerHTML = html;
    tooltip.classList.add('visible');
    moveTooltipTo(event);
}}

function moveTooltipTo(event) {{
    const x = event.clientX + 15;
    const y = event.clientY + 15;
    tooltip.style.left = Math.min(x, window.innerWidth - 400) + 'px';
    tooltip.style.top = Math.min(y, window.innerHeight - 200) + 'px';
}}

// ---------------------------------------------------------------------------
// Search
// ---------------------------------------------------------------------------
const searchInput = document.getElementById('search-input');
searchInput.addEventListener('input', (e) => {{
    const q = e.target.value.toLowerCase();
    if (!q) {{ selectedNodes.clear(); applySelection(); return; }}
    selectedNodes.clear();
    nodes.forEach(n => {{
        const text = (n.label + ' ' + (n.story || '') + ' ' + (n.learned || '') +
                      ' ' + (n.what || '') + ' ' + (n.signature || '') + ' ' + (n.reason || '')).toLowerCase();
        if (text.includes(q)) selectedNodes.add(n.id);
    }});
    applySelection();
}});

// ---------------------------------------------------------------------------
// Legend
// ---------------------------------------------------------------------------
const legend = document.getElementById('legend');
Object.entries(REGION_COLORS_CSS).forEach(([region, color]) => {{
    const count = nodes.filter(n => n.region === region).length;
    if (count === 0) return;
    const item = document.createElement('div');
    item.className = 'legend-item active';
    item.innerHTML = `<div class="legend-dot" style="background:${{color}}"></div>${{region}} (${{count}})`;
    let visible = true;
    item.addEventListener('click', () => {{
        visible = !visible;
        item.classList.toggle('active', visible);
        nodeMeshes.forEach(m => {{
            if (m.userData.region === region) m.visible = visible;
        }});
        linkLines.forEach(({{ line, src, tgt }}) => {{
            if (src.userData.region === region || tgt.userData.region === region) {{
                line.visible = visible;
            }}
        }});
    }});
    legend.appendChild(item);
}});

// Stats
const stats = document.getElementById('stats');
const typeCounts = {{}};
nodes.forEach(n => {{ typeCounts[n.type] = (typeCounts[n.type] || 0) + 1; }});
let statsHtml = `<div><span class="val">${{nodes.length}}</span> memories</div>`;
statsHtml += `<div><span class="val">${{links.length}}</span> connections</div>`;
Object.entries(typeCounts).sort((a,b) => b[1]-a[1]).forEach(([t, c]) => {{
    statsHtml += `<div>${{c}} ${{t}}s</div>`;
}});
stats.innerHTML = statsHtml;

// Keyboard
document.addEventListener('keydown', (e) => {{
    if (e.key === 'Escape') {{
        searchInput.value = '';
        selectedNodes.clear();
        applySelection();
        // controls.autoRotate stays off
    }}
    if (e.key === '/' && document.activeElement !== searchInput) {{
        e.preventDefault();
        searchInput.focus();
    }}
}});

// Resize
window.addEventListener('resize', () => {{
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
}});

// ---------------------------------------------------------------------------
// Animation loop
// ---------------------------------------------------------------------------
let time = 0;
function animate() {{
    requestAnimationFrame(animate);
    time += 0.01;

    controls.update();

    // Gentle pulse on danger/pain nodes
    nodeMeshes.forEach(mesh => {{
        const d = mesh.userData;
        if ((d.emotion === 'pain' || d.emotion === 'danger') && !selectedNodes.size) {{
            const pulse = 0.3 + Math.sin(time * 2 + mesh.position.x * 0.1) * 0.15;
            mesh.material.emissiveIntensity = pulse + (d.strength || 0.5) * 0.3;
        }}
    }});

    // Slow brain shell rotation
    brainShell.rotation.y = time * 0.05;

    renderer.render(scene, camera);
}}
animate();
</script>
</body>
</html>"""

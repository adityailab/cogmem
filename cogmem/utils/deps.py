"""Cross-repo dependency detection from imports, package files, and configs."""

from __future__ import annotations

import ast
import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional


@dataclass
class CrossRepoDep:
    source_repo: str
    target_repo: str
    dependency_type: str  # python_import | npm_dep | docker_service | ci_reference
    source_file: str
    detail: str


def detect_cross_repo_deps(
    repo_path: Path,
    sibling_repos: list[Path],
) -> list[CrossRepoDep]:
    """Scan a repo for imports/deps referencing sibling repos."""
    sibling_names = {_normalize_name(r.name) for r in sibling_repos if r != repo_path}
    sibling_name_map = {_normalize_name(r.name): r.name for r in sibling_repos if r != repo_path}

    if not sibling_names:
        return []

    deps: list[CrossRepoDep] = []
    deps.extend(_scan_python_imports(repo_path, sibling_names, sibling_name_map))
    deps.extend(_scan_js_deps(repo_path, sibling_names, sibling_name_map))
    deps.extend(_scan_docker_compose(repo_path, sibling_names, sibling_name_map))
    deps.extend(_scan_ci_configs(repo_path, sibling_names, sibling_name_map))

    return deps


def build_service_topology(
    deps: list[CrossRepoDep],
    repo_names: list[str],
) -> dict:
    """Convert dependency list into spatial data for WorkspaceSpatial."""
    from cogmem.models import DataFlow, ServiceEntry, WorkspaceSpatial

    services = []
    seen_repos = set()
    for name in repo_names:
        services.append(ServiceEntry(name=name, repo=name, role="service"))
        seen_repos.add(name)

    data_flow = []
    danger_zones = []

    for dep in deps:
        data_flow.append(DataFlow(
            from_service=dep.source_repo,
            to_service=dep.target_repo,
            protocol=dep.dependency_type,
            contract=dep.detail,
        ))

    # Identify danger zones: repos with many inbound deps
    inbound_counts: dict[str, int] = {}
    for dep in deps:
        inbound_counts[dep.target_repo] = inbound_counts.get(dep.target_repo, 0) + 1
    for repo, count in inbound_counts.items():
        if count >= 3:
            danger_zones.append(f"{repo} — {count} repos depend on this (high blast radius)")

    return WorkspaceSpatial(
        services=services,
        data_flow=data_flow,
        danger_zones=danger_zones,
    )


# ---------------------------------------------------------------------------
# Scanners
# ---------------------------------------------------------------------------

def _scan_python_imports(
    repo_path: Path,
    sibling_names: set[str],
    name_map: dict[str, str],
) -> list[CrossRepoDep]:
    """Parse Python files for imports matching sibling repo names."""
    deps = []
    repo_name = repo_path.name

    for py_file in repo_path.rglob("*.py"):
        if _should_skip(py_file, repo_path):
            continue
        try:
            source = py_file.read_text(errors="replace")
            tree = ast.parse(source, filename=str(py_file))
        except (SyntaxError, UnicodeDecodeError):
            continue

        rel_path = str(py_file.relative_to(repo_path))

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    target = _match_import(alias.name, sibling_names, name_map)
                    if target:
                        deps.append(CrossRepoDep(
                            source_repo=repo_name,
                            target_repo=target,
                            dependency_type="python_import",
                            source_file=rel_path,
                            detail=f"import {alias.name}",
                        ))
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    target = _match_import(node.module, sibling_names, name_map)
                    if target:
                        deps.append(CrossRepoDep(
                            source_repo=repo_name,
                            target_repo=target,
                            dependency_type="python_import",
                            source_file=rel_path,
                            detail=f"from {node.module} import ...",
                        ))

    return deps


def _scan_js_deps(
    repo_path: Path,
    sibling_names: set[str],
    name_map: dict[str, str],
) -> list[CrossRepoDep]:
    """Parse package.json for dependencies matching sibling repo names."""
    deps = []
    repo_name = repo_path.name
    pkg_file = repo_path / "package.json"

    if not pkg_file.exists():
        return deps

    try:
        pkg = json.loads(pkg_file.read_text())
    except (json.JSONDecodeError, ValueError):
        return deps

    all_deps = {}
    for key in ("dependencies", "devDependencies", "peerDependencies"):
        all_deps.update(pkg.get(key, {}))

    for dep_name, version in all_deps.items():
        # Check direct name match
        normalized = _normalize_name(dep_name.split("/")[-1])  # handle @scope/name
        if normalized in sibling_names:
            target = name_map.get(normalized, dep_name)
            deps.append(CrossRepoDep(
                source_repo=repo_name,
                target_repo=target,
                dependency_type="npm_dep",
                source_file="package.json",
                detail=f"{dep_name}: {version}",
            ))
        # Check file: references
        if version.startswith("file:"):
            ref_path = version[5:]
            ref_name = _normalize_name(Path(ref_path).name)
            if ref_name in sibling_names:
                target = name_map.get(ref_name, ref_path)
                deps.append(CrossRepoDep(
                    source_repo=repo_name,
                    target_repo=target,
                    dependency_type="npm_dep",
                    source_file="package.json",
                    detail=f"{dep_name}: {version}",
                ))

    return deps


def _scan_docker_compose(
    repo_path: Path,
    sibling_names: set[str],
    name_map: dict[str, str],
) -> list[CrossRepoDep]:
    """Parse docker-compose for service references to sibling repos."""
    deps = []
    repo_name = repo_path.name

    for compose_name in ("docker-compose.yml", "docker-compose.yaml", "compose.yml", "compose.yaml"):
        compose_file = repo_path / compose_name
        if not compose_file.exists():
            continue

        content = compose_file.read_text(errors="replace")

        # Simple regex parsing — avoids yaml dependency
        # Look for build contexts referencing sibling repos
        for match in re.finditer(r"build:\s*(?:context:\s*)?['\"]?(\.\./[^\s'\"]+)", content):
            ref_path = match.group(1)
            ref_name = _normalize_name(Path(ref_path).name)
            if ref_name in sibling_names:
                target = name_map.get(ref_name, ref_path)
                deps.append(CrossRepoDep(
                    source_repo=repo_name,
                    target_repo=target,
                    dependency_type="docker_service",
                    source_file=compose_name,
                    detail=f"build context: {ref_path}",
                ))

        # Look for depends_on service names matching sibling repos
        for match in re.finditer(r"depends_on:\s*\n((?:\s+-\s+\S+\n?)+)", content):
            for svc in re.findall(r"-\s+(\S+)", match.group(1)):
                svc_norm = _normalize_name(svc)
                if svc_norm in sibling_names:
                    target = name_map.get(svc_norm, svc)
                    deps.append(CrossRepoDep(
                        source_repo=repo_name,
                        target_repo=target,
                        dependency_type="docker_service",
                        source_file=compose_name,
                        detail=f"depends_on: {svc}",
                    ))

    return deps


def _scan_ci_configs(
    repo_path: Path,
    sibling_names: set[str],
    name_map: dict[str, str],
) -> list[CrossRepoDep]:
    """Parse CI configs for repo references."""
    deps = []
    repo_name = repo_path.name

    # GitHub Actions
    workflows_dir = repo_path / ".github" / "workflows"
    if workflows_dir.is_dir():
        for yml in workflows_dir.glob("*.yml"):
            content = yml.read_text(errors="replace")
            for sib_norm, sib_name in name_map.items():
                if sib_name in content or sib_norm in content:
                    deps.append(CrossRepoDep(
                        source_repo=repo_name,
                        target_repo=sib_name,
                        dependency_type="ci_reference",
                        source_file=f".github/workflows/{yml.name}",
                        detail=f"references {sib_name}",
                    ))

    # GitLab CI
    gitlab_ci = repo_path / ".gitlab-ci.yml"
    if gitlab_ci.exists():
        content = gitlab_ci.read_text(errors="replace")
        for sib_norm, sib_name in name_map.items():
            if sib_name in content or sib_norm in content:
                deps.append(CrossRepoDep(
                    source_repo=repo_name,
                    target_repo=sib_name,
                    dependency_type="ci_reference",
                    source_file=".gitlab-ci.yml",
                    detail=f"references {sib_name}",
                ))

    return deps


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_name(name: str) -> str:
    """Normalize repo/package name for comparison: lowercase, replace hyphens with underscores."""
    return name.lower().replace("-", "_").replace(".", "_")


def _match_import(
    module_name: str,
    sibling_names: set[str],
    name_map: dict[str, str],
) -> Optional[str]:
    """Check if an import module name matches any sibling repo."""
    # Check first component of dotted import
    first = module_name.split(".")[0]
    normalized = _normalize_name(first)
    if normalized in sibling_names:
        return name_map.get(normalized, first)
    return None


def _should_skip(path: Path, repo_root: Path) -> bool:
    """Skip vendored/generated directories."""
    rel = str(path.relative_to(repo_root))
    skip_dirs = {"node_modules", "vendor", "venv", ".venv", "dist", "build",
                  "__pycache__", ".git", ".tox", ".eggs"}
    return any(part in skip_dirs for part in Path(rel).parts)

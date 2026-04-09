"""Spatial memory — where things live."""

from __future__ import annotations

from pydantic import Field

from cogmem.models.common import MemoryBase


class SpatialEntry(MemoryBase):
    path: str = ""
    description: str = ""
    feel: str = ""
    body: str = ""


class Landmark(MemoryBase):
    path: str = ""
    description: str = ""
    why: str = ""
    body: str = ""


class Neighborhood(MemoryBase):
    from_path: str = Field(default="", alias="from")
    to_path: str = Field(default="", alias="to")
    relation: str = ""
    body: str = ""

    model_config = {"populate_by_name": True}


class RepoSpatial(MemoryBase):
    """Repo-level spatial map."""
    surface: list[SpatialEntry] = Field(default_factory=list)
    middle: list[SpatialEntry] = Field(default_factory=list)
    deep: list[SpatialEntry] = Field(default_factory=list)
    landmarks: list[Landmark] = Field(default_factory=list)
    neighborhoods: list[Neighborhood] = Field(default_factory=list)
    body: str = ""

    def to_markdown(self) -> str:
        lines = ["# Spatial Map\n"]

        if self.surface:
            lines.append("## Surface (entry points)")
            for e in self.surface:
                lines.append(f"- **{e.path}** — {e.description}" + (f" ({e.feel})" if e.feel else ""))
            lines.append("")

        if self.middle:
            lines.append("## Middle (core logic)")
            for e in self.middle:
                lines.append(f"- **{e.path}** — {e.description}" + (f" ({e.feel})" if e.feel else ""))
            lines.append("")

        if self.deep:
            lines.append("## Deep (internals)")
            for e in self.deep:
                lines.append(f"- **{e.path}** — {e.description}" + (f" ({e.feel})" if e.feel else ""))
            lines.append("")

        if self.landmarks:
            lines.append("## Landmarks")
            for lm in self.landmarks:
                lines.append(f"- **{lm.path}** — {lm.description} (why: {lm.why})")
            lines.append("")

        if self.neighborhoods:
            lines.append("## Neighborhoods")
            for nb in self.neighborhoods:
                lines.append(f"- {nb.from_path} -> {nb.to_path}: {nb.relation}")
            lines.append("")

        return "\n".join(lines)

    @classmethod
    def from_markdown(cls, text: str) -> "RepoSpatial":
        spatial = cls()
        current_section = None

        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("## Surface"):
                current_section = "surface"
            elif stripped.startswith("## Middle"):
                current_section = "middle"
            elif stripped.startswith("## Deep"):
                current_section = "deep"
            elif stripped.startswith("## Landmarks"):
                current_section = "landmarks"
            elif stripped.startswith("## Neighborhoods"):
                current_section = "neighborhoods"
            elif stripped.startswith("- **") and current_section in ("surface", "middle", "deep"):
                path, rest = _parse_spatial_entry(stripped)
                entry = SpatialEntry(path=path, description=rest)
                getattr(spatial, current_section).append(entry)
            elif stripped.startswith("- **") and current_section == "landmarks":
                path, rest = _parse_spatial_entry(stripped)
                lm = Landmark(path=path, description=rest)
                spatial.landmarks.append(lm)
            elif stripped.startswith("- ") and current_section == "neighborhoods":
                parts = stripped[2:].split(":", 1)
                if len(parts) == 2:
                    arrow_parts = parts[0].split("->")
                    if len(arrow_parts) == 2:
                        spatial.neighborhoods.append(
                            Neighborhood(from_path=arrow_parts[0].strip(),
                                        to_path=arrow_parts[1].strip(),
                                        relation=parts[1].strip())
                        )
        return spatial


class ServiceEntry(MemoryBase):
    name: str = ""
    repo: str = ""
    role: str = ""
    feel: str = ""
    body: str = ""


class DataFlow(MemoryBase):
    from_service: str = Field(default="", alias="from")
    to_service: str = Field(default="", alias="to")
    protocol: str = ""
    contract: str = ""
    body: str = ""

    model_config = {"populate_by_name": True}


class WorkspaceSpatial(MemoryBase):
    """Workspace-level spatial map (service topology)."""
    services: list[ServiceEntry] = Field(default_factory=list)
    data_flow: list[DataFlow] = Field(default_factory=list)
    shared_contracts: list[dict] = Field(default_factory=list)
    deployment: str = ""
    danger_zones: list[str] = Field(default_factory=list)
    body: str = ""

    def to_markdown(self) -> str:
        lines = ["# Workspace Topology\n"]

        if self.services:
            lines.append("## Services")
            for s in self.services:
                lines.append(f"- **{s.name}** ({s.repo}): {s.role}" + (f" — feel: {s.feel}" if s.feel else ""))
            lines.append("")

        if self.data_flow:
            lines.append("## Data Flow")
            for df in self.data_flow:
                lines.append(f"- {df.from_service} -> ({df.protocol}) -> {df.to_service}")
            lines.append("")

        if self.danger_zones:
            lines.append("## Danger Zones")
            for dz in self.danger_zones:
                lines.append(f"- {dz}")
            lines.append("")

        return "\n".join(lines)


def _parse_spatial_entry(line: str) -> tuple[str, str]:
    """Parse '- **path** — description (feel)' into (path, description)."""
    # Remove leading "- **"
    content = line.lstrip("- ").lstrip("*").strip()
    if "**" in content:
        path_part, rest = content.split("**", 1)
        path = path_part.strip()
        desc = rest.lstrip(" —-").strip()
    else:
        path = content
        desc = ""
    return path, desc

"""Tests for the bootstrap engine."""

import pytest
from pathlib import Path

from cogmem.engine.bootstrap import (
    _build_codebase_gist,
    _build_spatial_map,
    _cluster_episodes_to_patterns,
    _detect_file_emotions,
    _extract_entities,
)
from cogmem.models import Episode, EpisodeSource, Phase


@pytest.fixture
def sample_repo(tmp_path):
    """Create a sample repo structure."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "README.md").write_text("# MyApp\n\nA web application for managing widgets.\n\nMore details here.")
    (tmp_path / "pyproject.toml").write_text("[tool.poetry]\nname = 'myapp'")

    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text(
        "class App:\n    def run(self):\n        pass\n\n"
        "def start_server(host, port):\n    app = App()\n    app.run()\n"
    )
    (src / "utils.py").write_text(
        "def format_date(dt):\n    return dt.isoformat()\n"
    )

    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_main.py").write_text("def test_app(): pass")

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "guide.md").write_text("# Guide")

    return tmp_path


class TestSpatialMap:
    def test_classifies_dirs(self, sample_repo):
        spatial = _build_spatial_map(sample_repo)
        surface_paths = [e.path for e in spatial.surface]
        middle_paths = [e.path for e in spatial.middle]

        assert "README.md" in surface_paths
        assert any("tests" in p for p in surface_paths)
        assert any("src" in p for p in middle_paths)

    def test_finds_landmarks(self, sample_repo):
        spatial = _build_spatial_map(sample_repo)
        landmark_paths = [lm.path for lm in spatial.landmarks]
        assert "README.md" in landmark_paths
        assert "pyproject.toml" in landmark_paths


class TestCodebaseGist:
    def test_creates_from_readme(self, sample_repo):
        gist = _build_codebase_gist(sample_repo)
        assert gist is not None
        assert "widget" in gist.what_it_does.lower() or "web" in gist.what_it_does.lower()
        assert gist.scope == "codebase"

    def test_no_readme(self, tmp_path):
        gist = _build_codebase_gist(tmp_path)
        assert gist is None


class TestEntityExtraction:
    def test_extracts_classes_and_functions(self, sample_repo):
        entities = _extract_entities(sample_repo)
        names = [e.name for e in entities]
        assert "App" in names
        assert "start_server" in names
        assert "format_date" in names

    def test_entity_kinds(self, sample_repo):
        entities = _extract_entities(sample_repo)
        app_entity = next(e for e in entities if e.name == "App")
        assert app_entity.kind == "class"

        func_entity = next(e for e in entities if e.name == "start_server")
        assert func_entity.kind == "function"

        method_entity = next(e for e in entities if e.name == "run")
        assert method_entity.kind == "method"


class TestEpisodeClustering:
    def test_detects_recurring_fixes(self):
        episodes = [
            Episode(trigger=f"Fix {i}", emotion="frustration", code_touched=["fragile.py"],
                    source=EpisodeSource.GIT_INFERRED)
            for i in range(5)
        ]
        patterns = _cluster_episodes_to_patterns(episodes)
        assert len(patterns) >= 1
        assert "fragile" in patterns[0].name

    def test_no_patterns_for_few_episodes(self):
        episodes = [
            Episode(trigger="Fix", emotion="frustration", code_touched=["a.py"],
                    source=EpisodeSource.GIT_INFERRED),
        ]
        patterns = _cluster_episodes_to_patterns(episodes)
        assert len(patterns) == 0


class TestFileEmotions:
    def test_detects_pain_files(self, sample_repo):
        episodes = [
            Episode(emotion="pain", intensity=0.8, code_touched=["fragile.py"]),
            Episode(emotion="pain", intensity=0.7, code_touched=["fragile.py"]),
            Episode(emotion="neutral", intensity=0.3, code_touched=["stable.py"]),
        ]
        tags = _detect_file_emotions(sample_repo, episodes)
        assert len(tags) >= 1
        fragile_tag = next((t for t in tags if t.target == "fragile.py"), None)
        assert fragile_tag is not None
        assert fragile_tag.emotion == "pain"

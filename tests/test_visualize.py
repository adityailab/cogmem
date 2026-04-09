"""Tests for the visualize engine — brain visualization."""

import json
import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from cogmem.engine.visualize import visualize, _collect_repo, _generate_html
from cogmem.engine.bootstrap import bootstrap_repo
from cogmem.engine.encode import encode
from cogmem.engine.update import update_memory
from cogmem.tiers.repo import RepoTier


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repo with initialized memory."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "main.py").write_text(
        "class App:\n    def run(self):\n        pass\n"
    )
    (tmp_path / "src" / "utils.py").write_text(
        "def helper():\n    pass\n"
    )
    return tmp_path


@pytest.fixture
def populated_repo(git_repo):
    """Create a repo with various memory types populated."""
    repo = RepoTier(git_repo)
    repo.init()

    # Add an episode
    encode(
        event="Fixed auth timeout",
        emotion="pain",
        intensity=0.7,
        code_touched=[str(git_repo / "src" / "main.py")],
        learned="Connection pool was exhausted",
        cwd=str(git_repo),
    )

    # Add an emotion
    update_memory(danger_target="src/utils.py", cwd=str(git_repo))

    # Add a pattern
    update_memory(
        pattern_name="retry-pattern",
        content="Retry with exponential backoff on transient failures",
        cwd=str(git_repo),
    )

    # Add a gist
    update_memory(
        gist_target="src/main.py",
        content="Main application entry point",
        cwd=str(git_repo),
    )

    return git_repo


class TestCollectRepo:
    def test_collects_episode_nodes(self, populated_repo):
        repo = RepoTier(populated_repo)
        nodes, links, regions = [], [], []
        _collect_repo(repo, nodes, links, regions)

        episode_nodes = [n for n in nodes if n["type"] == "episode"]
        assert len(episode_nodes) >= 1
        assert episode_nodes[0]["region"] == "episodic"
        assert "tier" in episode_nodes[0]

    def test_collects_emotion_nodes(self, populated_repo):
        repo = RepoTier(populated_repo)
        nodes, links, regions = [], [], []
        _collect_repo(repo, nodes, links, regions)

        emotion_nodes = [n for n in nodes if n["type"] == "emotion"]
        assert len(emotion_nodes) >= 1
        assert emotion_nodes[0]["region"] == "emotional"

    def test_collects_pattern_nodes(self, populated_repo):
        repo = RepoTier(populated_repo)
        nodes, links, regions = [], [], []
        _collect_repo(repo, nodes, links, regions)

        pattern_nodes = [n for n in nodes if n["type"] == "pattern"]
        assert len(pattern_nodes) >= 1
        assert pattern_nodes[0]["region"] == "pattern"

    def test_collects_gist_nodes(self, populated_repo):
        repo = RepoTier(populated_repo)
        nodes, links, regions = [], [], []
        _collect_repo(repo, nodes, links, regions)

        gist_nodes = [n for n in nodes if n["type"] == "gist"]
        assert len(gist_nodes) >= 1
        assert gist_nodes[0]["region"] == "semantic"

    def test_collects_correct_regions(self, populated_repo):
        repo = RepoTier(populated_repo)
        nodes, links, regions = [], [], []
        _collect_repo(repo, nodes, links, regions)

        region_ids = {r["id"] for r in regions}
        assert "episodic" in region_ids
        assert "semantic" in region_ids
        assert "spatial" in region_ids
        assert "pattern" in region_ids
        assert "emotional" in region_ids
        assert "prospective" in region_ids
        assert "entity" in region_ids

    def test_node_counts_nonzero(self, populated_repo):
        repo = RepoTier(populated_repo)
        nodes, links, regions = [], [], []
        _collect_repo(repo, nodes, links, regions)

        assert len(nodes) > 0
        assert len(regions) == 7  # all 7 cognitive regions

    def test_links_reference_valid_nodes(self, populated_repo):
        repo = RepoTier(populated_repo)
        nodes, links, regions = [], [], []
        _collect_repo(repo, nodes, links, regions)

        node_ids = {n["id"] for n in nodes}
        for link in links:
            # Source should always be in nodes
            assert link["source"] in node_ids, (
                f"Link source {link['source']} not found in nodes"
            )


class TestGenerateHtml:
    def test_generates_html_with_d3(self):
        data = {
            "nodes": [{"id": "test", "label": "Test", "type": "episode"}],
            "links": [],
            "regions": [{"id": "episodic", "label": "Episodic", "color": "#4ECDC4"}],
        }
        html = _generate_html(data)
        assert "<!DOCTYPE html>" in html
        assert "d3.v7.min.js" in html or "d3js.org" in html
        assert "<script" in html

    def test_html_contains_graph_data(self):
        data = {
            "nodes": [{"id": "ep:test1", "label": "Test Episode"}],
            "links": [],
            "regions": [],
        }
        html = _generate_html(data)
        assert "Test Episode" in html

    def test_html_contains_title(self):
        data = {"nodes": [], "links": [], "regions": []}
        html = _generate_html(data)
        assert "cogmem" in html.lower()

    def test_html_has_style_section(self):
        data = {"nodes": [], "links": [], "regions": []}
        html = _generate_html(data)
        assert "<style>" in html


class TestVisualize:
    @patch("cogmem.engine.visualize.detect_workspace", return_value=None)
    @patch("cogmem.engine.visualize.GlobalTier")
    def test_no_open_saves_file(self, mock_global, mock_ws, populated_repo):
        mock_global_instance = MagicMock()
        mock_global_instance.exists = False
        mock_global.return_value = mock_global_instance

        output_file = populated_repo / "test_output.html"
        result = visualize(
            cwd=str(populated_repo),
            output=str(output_file),
            no_open=True,
        )

        assert output_file.exists()
        assert "saved" in result.lower() or "visualization" in result.lower()

        content = output_file.read_text()
        assert "<!DOCTYPE html>" in content
        assert "d3" in content.lower()

    @patch("cogmem.engine.visualize.detect_workspace", return_value=None)
    @patch("cogmem.engine.visualize.GlobalTier")
    def test_output_contains_memory_data(self, mock_global, mock_ws, populated_repo):
        mock_global_instance = MagicMock()
        mock_global_instance.exists = False
        mock_global.return_value = mock_global_instance

        output_file = populated_repo / "viz_test.html"
        visualize(
            cwd=str(populated_repo),
            output=str(output_file),
            no_open=True,
        )

        content = output_file.read_text()
        # Should contain references to our encoded data
        assert "auth" in content.lower() or "episode" in content.lower()

    @patch("cogmem.engine.visualize.detect_workspace", return_value=None)
    @patch("cogmem.engine.visualize.GlobalTier")
    def test_empty_repo_returns_no_memory_message(self, mock_global, mock_ws, tmp_path):
        mock_global_instance = MagicMock()
        mock_global_instance.exists = False
        mock_global.return_value = mock_global_instance

        # No .git, no .memory — totally empty
        result = visualize(cwd=str(tmp_path), no_open=True)
        assert "no memory" in result.lower()

    @patch("cogmem.engine.visualize.detect_workspace", return_value=None)
    @patch("cogmem.engine.visualize.GlobalTier")
    def test_initialized_but_empty_repo_returns_no_memory(
        self, mock_global, mock_ws, tmp_path
    ):
        mock_global_instance = MagicMock()
        mock_global_instance.exists = False
        mock_global.return_value = mock_global_instance

        # Create .git but don't bootstrap or encode anything
        (tmp_path / ".git").mkdir()
        result = visualize(cwd=str(tmp_path), no_open=True)
        assert "no memory" in result.lower()

    @patch("cogmem.engine.visualize.webbrowser")
    @patch("cogmem.engine.visualize.detect_workspace", return_value=None)
    @patch("cogmem.engine.visualize.GlobalTier")
    def test_default_opens_browser(self, mock_global, mock_ws, mock_wb, populated_repo):
        mock_global_instance = MagicMock()
        mock_global_instance.exists = False
        mock_global.return_value = mock_global_instance

        output_file = populated_repo / "browser_test.html"
        visualize(
            cwd=str(populated_repo),
            output=str(output_file),
            no_open=False,
        )

        mock_wb.open.assert_called_once()

    @patch("cogmem.engine.visualize.detect_workspace", return_value=None)
    @patch("cogmem.engine.visualize.GlobalTier")
    def test_default_output_path_uses_memory_dir(self, mock_global, mock_ws, populated_repo):
        mock_global_instance = MagicMock()
        mock_global_instance.exists = False
        mock_global.return_value = mock_global_instance

        result = visualize(cwd=str(populated_repo), no_open=True)
        assert "brain.html" in result

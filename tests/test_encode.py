"""Tests for the encode engine."""

import json
import pytest
from pathlib import Path

from cogmem.engine.encode import encode, encode_git, hook_encode
from cogmem.tiers.repo import RepoTier


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repo."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "auth" / "login.py").parent.mkdir(parents=True)
    (tmp_path / "auth" / "login.py").write_text("def login(): pass")
    return tmp_path


class TestEncode:
    def test_encode_creates_episode(self, git_repo):
        result = encode(
            event="Fixed the auth timeout",
            emotion="pain",
            intensity=0.8,
            code_touched=[str(git_repo / "auth" / "login.py")],
            learned="Pool was exhausted",
            cwd=str(git_repo),
        )
        assert "Encoded episode" in result
        repo = RepoTier(git_repo)
        episodes = repo.list_episodes()
        assert len(episodes) >= 1
        assert any("auth" in ep.trigger.lower() for ep in episodes)

    def test_encode_updates_index(self, git_repo):
        encode(
            event="Added caching to API",
            code_touched=[str(git_repo / "auth" / "login.py")],
            cwd=str(git_repo),
        )
        repo = RepoTier(git_repo)
        index = repo.get_index()
        results = index.query(["caching"])
        assert len(results) > 0

    def test_encode_high_emotion_creates_tag(self, git_repo):
        encode(
            event="Terrible outage",
            emotion="pain",
            intensity=0.9,
            code_touched=[str(git_repo / "auth" / "login.py")],
            cwd=str(git_repo),
        )
        repo = RepoTier(git_repo)
        emotions = repo.get_emotions()
        pain_tags = [t for t in emotions.tags if t.emotion == "pain"]
        assert len(pain_tags) > 0

    def test_encode_no_repo_still_works(self, tmp_path):
        result = encode(event="test", cwd=str(tmp_path))
        assert "Encoded episode" in result


class TestHookEncode:
    def test_hook_appends_to_session(self, git_repo):
        repo = RepoTier(git_repo)
        repo.init()

        # Create a tool input file
        tool_input = git_repo / "tool_input.json"
        tool_input.write_text(json.dumps({"file_path": "auth/login.py"}))

        hook_encode("Write", str(tool_input), cwd=str(git_repo))

        session_file = git_repo / ".memory" / "sessions" / "current.json"
        assert session_file.exists()
        events = json.loads(session_file.read_text())
        assert len(events) == 1
        assert events[0]["tool"] == "Write"
        assert events[0]["file"] == "auth/login.py"

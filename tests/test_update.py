"""Tests for the update engine — corrections, marking, and forgetting."""

import pytest
from pathlib import Path

from cogmem.engine.update import update_memory, forget_memory
from cogmem.engine.encode import encode
from cogmem.tiers.repo import RepoTier


@pytest.fixture
def git_repo(tmp_path):
    """Create a minimal git repo with initialized memory."""
    (tmp_path / ".git").mkdir()
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "auth.py").write_text("def login(): pass")
    (tmp_path / "src" / "db.py").write_text("def connect(): pass")
    repo = RepoTier(tmp_path)
    repo.init()
    return tmp_path


class TestUpdateMemoryStable:
    def test_stable_target_creates_trust_emotion(self, git_repo):
        result = update_memory(stable_target="src/auth.py", cwd=str(git_repo))
        assert "stable" in result.lower() or "trust" in result.lower()

        repo = RepoTier(git_repo)
        emotions = repo.get_emotions()
        trust_tags = [t for t in emotions.tags if t.emotion == "trust"]
        assert len(trust_tags) >= 1
        assert any("auth" in t.target for t in trust_tags)

    def test_stable_target_with_custom_reason(self, git_repo):
        result = update_memory(
            stable_target="src/auth.py",
            content="Well-tested and reviewed",
            cwd=str(git_repo),
        )
        assert "stable" in result.lower()

        repo = RepoTier(git_repo)
        emotions = repo.get_emotions()
        trust_tags = [t for t in emotions.tags if t.emotion == "trust"]
        assert any("Well-tested" in t.reason for t in trust_tags)

    def test_stable_target_intensity(self, git_repo):
        update_memory(stable_target="src/auth.py", cwd=str(git_repo))
        repo = RepoTier(git_repo)
        emotions = repo.get_emotions()
        trust_tags = [t for t in emotions.tags if t.emotion == "trust"]
        assert trust_tags[0].intensity == 0.7


class TestUpdateMemoryDanger:
    def test_danger_target_creates_danger_emotion(self, git_repo):
        result = update_memory(danger_target="src/db.py", cwd=str(git_repo))
        assert "dangerous" in result.lower()

        repo = RepoTier(git_repo)
        emotions = repo.get_emotions()
        danger_tags = [t for t in emotions.tags if t.emotion == "danger"]
        assert len(danger_tags) >= 1
        assert any("db" in t.target for t in danger_tags)

    def test_danger_target_with_custom_reason(self, git_repo):
        result = update_memory(
            danger_target="src/db.py",
            content="Known race condition",
            cwd=str(git_repo),
        )
        assert "dangerous" in result.lower()

        repo = RepoTier(git_repo)
        emotions = repo.get_emotions()
        danger_tags = [t for t in emotions.tags if t.emotion == "danger"]
        assert any("race condition" in t.reason for t in danger_tags)

    def test_danger_target_intensity(self, git_repo):
        update_memory(danger_target="src/db.py", cwd=str(git_repo))
        repo = RepoTier(git_repo)
        emotions = repo.get_emotions()
        danger_tags = [t for t in emotions.tags if t.emotion == "danger"]
        assert danger_tags[0].intensity == 0.85


class TestUpdateMemoryGist:
    def test_gist_creates_new_gist(self, git_repo):
        result = update_memory(
            gist_target="src/auth.py",
            content="Handles user authentication and session management",
            cwd=str(git_repo),
        )
        assert "gist" in result.lower()

        repo = RepoTier(git_repo)
        gists = repo.list_gists()
        assert len(gists) >= 1
        matching = [g for g in gists if "auth" in g.target.lower()]
        assert len(matching) >= 1
        assert "authentication" in matching[0].what_it_does.lower()

    def test_gist_updates_existing_gist(self, git_repo):
        # Create first gist
        update_memory(
            gist_target="src/auth.py",
            content="Original description",
            cwd=str(git_repo),
        )
        # Update it
        result = update_memory(
            gist_target="src/auth.py",
            content="Updated description with more detail",
            cwd=str(git_repo),
        )
        assert "updated" in result.lower() or "gist" in result.lower()

        repo = RepoTier(git_repo)
        gists = repo.list_gists()
        matching = [g for g in gists if "auth" in g.target.lower()]
        assert len(matching) >= 1
        assert "Updated description" in matching[0].what_it_does

    def test_gist_without_content_fails(self, git_repo):
        result = update_memory(gist_target="src/auth.py", cwd=str(git_repo))
        assert "need" in result.lower() or "content" in result.lower()


class TestUpdateMemoryPattern:
    def test_pattern_creates_new_pattern(self, git_repo):
        result = update_memory(
            pattern_name="retry-with-backoff",
            content="Exponential backoff on transient failures",
            cwd=str(git_repo),
        )
        assert "pattern" in result.lower()

        repo = RepoTier(git_repo)
        patterns = repo.list_patterns()
        assert len(patterns) >= 1
        matching = [p for p in patterns if "retry" in p.name.lower()]
        assert len(matching) >= 1
        assert matching[0].strength == 0.8

    def test_pattern_without_content_fails(self, git_repo):
        result = update_memory(pattern_name="some-pattern", cwd=str(git_repo))
        assert "need" in result.lower() or "content" in result.lower()

    def test_pattern_has_design_category(self, git_repo):
        update_memory(
            pattern_name="factory-method",
            content="Use factory pattern for plugin creation",
            cwd=str(git_repo),
        )
        repo = RepoTier(git_repo)
        patterns = repo.list_patterns()
        matching = [p for p in patterns if "factory" in p.name.lower()]
        assert matching[0].category == "design"


class TestUpdateMemoryNoAction:
    def test_no_action_returns_message(self, git_repo):
        result = update_memory(cwd=str(git_repo))
        assert "no action" in result.lower() or "use" in result.lower()


class TestUpdateMemoryNoRepo:
    def test_uninitialized_repo_returns_error(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = update_memory(stable_target="foo.py", cwd=str(tmp_path))
        assert "not initialized" in result.lower() or "bootstrap" in result.lower()


class TestForgetMemory:
    def test_forget_removes_matching_episode(self, git_repo):
        encode(
            event="Fixed the database timeout bug",
            code_touched=[str(git_repo / "src" / "db.py")],
            cwd=str(git_repo),
        )
        repo = RepoTier(git_repo)
        assert len(repo.list_episodes()) >= 1

        result = forget_memory(target="database timeout", cwd=str(git_repo))
        assert "removed" in result.lower() or "episode" in result.lower()

    def test_forget_removes_matching_pattern(self, git_repo):
        update_memory(
            pattern_name="singleton-abuse",
            content="Over-use of singleton pattern",
            cwd=str(git_repo),
        )
        repo = RepoTier(git_repo)
        assert len(repo.list_patterns()) >= 1

        result = forget_memory(target="singleton", cwd=str(git_repo))
        assert "removed" in result.lower() or "pattern" in result.lower()

    def test_forget_removes_matching_emotion(self, git_repo):
        update_memory(danger_target="src/db.py", cwd=str(git_repo))
        repo = RepoTier(git_repo)
        emotions = repo.get_emotions()
        assert len(emotions.tags) >= 1

        result = forget_memory(target="db.py", cwd=str(git_repo))
        assert "removed" in result.lower() or "emotion" in result.lower()

    def test_forget_nonexistent_returns_message(self, git_repo):
        result = forget_memory(target="nonexistent_thing", cwd=str(git_repo))
        assert "no memories found" in result.lower()

    def test_forget_uninitialized_repo(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = forget_memory(target="anything", cwd=str(tmp_path))
        assert "not initialized" in result.lower()

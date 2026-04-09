"""Tests for the recall engine."""

import pytest
from pathlib import Path

from cogmem.models import (
    EmotionTag,
    Episode,
    EpisodeSource,
    Gist,
    GistScope,
    Pattern,
    PatternCategory,
    Phase,
    Prospective,
    Tier,
)
from cogmem.tiers.repo import RepoTier
from cogmem.engine.recall import recall, search_memories, get_dangers, get_intentions


@pytest.fixture
def repo_with_memory(tmp_path):
    """Create a repo with .git and populated .memory."""
    (tmp_path / ".git").mkdir()
    repo = RepoTier(tmp_path)
    repo.init()

    # Episodes
    repo.save_episode(Episode(
        date="2026-01-10",
        trigger="Fixed auth timeout",
        story="Login endpoint timing out under load",
        learned="Connection pool exhaustion",
        emotion="pain",
        intensity=0.8,
        code_touched=["auth/login.py"],
        source=EpisodeSource.LIVED,
    ))
    repo.save_episode(Episode(
        date="2026-03-01",
        trigger="Added caching layer",
        story="Implemented Redis caching for API responses",
        learned="Cache invalidation strategy matters",
        emotion="curiosity",
        intensity=0.5,
        code_touched=["cache/redis.py"],
        source=EpisodeSource.LIVED,
    ))

    # Gist
    repo.save_gist(Gist(
        scope=GistScope.MODULE,
        target="auth",
        what_it_does="Handles user authentication and session management",
        judgment="solid",
    ))

    # Pattern
    repo.save_pattern(Pattern(
        name="pool-exhaustion",
        category=PatternCategory.BUG,
        signature="Connection pool runs out under load",
        consequence="Request timeouts and 503 errors",
        response="Increase pool size or add connection recycling",
        seen_in=["auth/login.py"],
        trigger_cues=["timeout", "pool", "connection"],
    ))

    # Emotion
    repo.update_emotion(EmotionTag(
        target="auth/login.py",
        emotion="pain",
        intensity=0.85,
        reason="Caused production outage",
    ))

    # Prospective
    repo.save_prospective(Prospective(
        intention="Add rate limiting to login",
        trigger="auth/login.py",
        trigger_type="file_touch",
        priority="high",
    ))

    # Build index
    from cogmem.storage.index import extract_keywords
    index = repo.get_index()
    index.add_entry(["auth", "login", "timeout", "fix"], "episodes/2026-01-10_fixed-auth-timeout.md")
    index.add_entry(["cache", "redis", "caching"], "episodes/2026-03-01_added-caching-layer.md")
    repo.save_index(index)

    return tmp_path


class TestRecall:
    def test_recall_finds_relevant(self, repo_with_memory):
        result = recall("auth login timeout", cwd=str(repo_with_memory))
        assert "auth" in result.lower() or "login" in result.lower()

    def test_recall_with_task_type(self, repo_with_memory):
        result = recall("fix the auth timeout", cwd=str(repo_with_memory), task_type="bugfix")
        assert "bugfix" in result.lower()

    def test_recall_empty_repo(self, tmp_path):
        (tmp_path / ".git").mkdir()
        result = recall("anything", cwd=str(tmp_path))
        assert "bootstrap" in result.lower() or "no" in result.lower()


class TestSearchMemories:
    def test_search_episodes(self, repo_with_memory):
        result = search_memories("auth", cwd=str(repo_with_memory))
        assert "auth" in result.lower()

    def test_search_no_match(self, repo_with_memory):
        result = search_memories("xyznonexistent", cwd=str(repo_with_memory))
        assert "no matches" in result.lower()


class TestGetDangers:
    def test_danger_for_file(self, repo_with_memory):
        result = get_dangers(["auth/login.py"], cwd=str(repo_with_memory))
        assert "PAIN" in result or "pain" in result.lower()

    def test_all_dangers(self, repo_with_memory):
        result = get_dangers([], cwd=str(repo_with_memory))
        assert "auth/login.py" in result


class TestGetIntentions:
    def test_has_intentions(self, repo_with_memory):
        result = get_intentions(cwd=str(repo_with_memory))
        assert "rate limiting" in result.lower()

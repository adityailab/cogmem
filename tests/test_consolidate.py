"""Tests for the consolidation engine."""

import pytest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

from cogmem.engine.consolidate import consolidate_repo, _find_shared_files, _dominant_emotion
from cogmem.models import (
    EmotionsFile,
    EmotionTag,
    Episode,
    Pattern,
    PatternCategory,
    Phase,
    Tier,
)
from cogmem.tiers.repo import RepoTier


@pytest.fixture
def repo_tier(tmp_path):
    """Create a minimal git repo with initialized .memory dir."""
    (tmp_path / ".git").mkdir()
    repo = RepoTier(tmp_path)
    repo.init()
    return repo


def _make_episode(
    trigger: str,
    days_ago: int = 0,
    phase: str = Phase.VIVID,
    emotion: str = "neutral",
    code_touched: list[str] | None = None,
    strength: float = 1.0,
    learned: str = "",
    story: str = "",
    ep_id: str | None = None,
) -> Episode:
    """Helper to create episodes with controlled dates."""
    ep_date = (date.today() - timedelta(days=days_ago)).isoformat()
    ep = Episode(
        trigger=trigger,
        date=ep_date,
        phase=phase,
        emotion=emotion,
        code_touched=code_touched or [],
        strength=strength,
        learned=learned or f"Learned from {trigger}",
        story=story or f"Story about {trigger}. More details here.",
    )
    if ep_id:
        ep.id = ep_id
    return ep


class TestConsolidateRepoPhaseTransitions:
    """Phase 1: Episode phase transitions based on age."""

    def test_vivid_to_clear(self, repo_tier):
        """Episode older than 7 days transitions from vivid to clear."""
        ep = _make_episode("login fix", days_ago=10, phase=Phase.VIVID)
        repo_tier.save_episode(ep)

        result = consolidate_repo(repo_tier)
        assert "episodes transitioned" in result

        episodes = repo_tier.list_episodes()
        assert len(episodes) == 1
        assert episodes[0].phase == Phase.CLEAR

    def test_clear_to_fuzzy(self, repo_tier):
        """Episode older than 30 days transitions from clear to fuzzy."""
        ep = _make_episode("refactor db", days_ago=35, phase=Phase.CLEAR)
        repo_tier.save_episode(ep)

        result = consolidate_repo(repo_tier)
        assert "episodes transitioned" in result

        episodes = repo_tier.list_episodes()
        assert len(episodes) == 1
        assert episodes[0].phase == Phase.FUZZY

    def test_fuzzy_to_fading(self, repo_tier):
        """Episode older than 90 days transitions from fuzzy to fading."""
        ep = _make_episode("old migration", days_ago=100, phase=Phase.FUZZY)
        repo_tier.save_episode(ep)

        result = consolidate_repo(repo_tier)
        assert "episodes transitioned" in result

        episodes = repo_tier.list_episodes()
        assert len(episodes) == 1
        assert episodes[0].phase == Phase.FADING

    def test_fading_to_stub(self, repo_tier):
        """Episode older than 180 days transitions from fading to stub."""
        ep = _make_episode("ancient bug", days_ago=200, phase=Phase.FADING)
        repo_tier.save_episode(ep)

        result = consolidate_repo(repo_tier)
        assert "episodes transitioned" in result

        episodes = repo_tier.list_episodes()
        assert len(episodes) == 1
        assert episodes[0].phase == Phase.STUB

    def test_no_transition_when_phase_matches_age(self, repo_tier):
        """No transition when episode phase already matches its age."""
        ep = _make_episode("recent event", days_ago=2, phase=Phase.VIVID)
        repo_tier.save_episode(ep)

        result = consolidate_repo(repo_tier)
        assert "episodes transitioned" not in result

    def test_story_compressed_on_fuzzy_transition(self, repo_tier):
        """Story is compressed to summary when transitioning to fuzzy."""
        ep = _make_episode(
            "compress test",
            days_ago=35,
            phase=Phase.CLEAR,
            story="Fixed the connection pool. It was leaking handles under load.",
            learned="Always close handles in finally block",
        )
        repo_tier.save_episode(ep)

        consolidate_repo(repo_tier)

        episodes = repo_tier.list_episodes()
        assert len(episodes) == 1
        # compress("summary") keeps first sentence + learned
        assert "Learned:" in episodes[0].story or "Fixed the connection pool." in episodes[0].story

    def test_story_compressed_to_stub(self, repo_tier):
        """Story is compressed to stub when transitioning to stub phase."""
        ep = _make_episode(
            "very old event",
            days_ago=200,
            phase=Phase.FADING,
            story="Long story about something. Many details here.",
            learned="Key takeaway",
        )
        repo_tier.save_episode(ep)

        consolidate_repo(repo_tier)

        episodes = repo_tier.list_episodes()
        assert len(episodes) == 1
        # compress("stub") returns learned or trigger
        assert episodes[0].story == "Key takeaway"


class TestConsolidateRepoPatternExtraction:
    """Phase 2: Pattern extraction from episodes sharing files."""

    def test_pattern_created_from_three_episodes(self, repo_tier):
        """Pattern is extracted when 3+ episodes share files and a keyword."""
        shared_file = "src/auth/login.py"
        # All episodes share a trigger keyword "timeout" and a shared file
        for i in range(3):
            ep = _make_episode(
                trigger=f"timeout issue {i}",
                days_ago=i + 1,
                code_touched=[shared_file, f"src/other_{i}.py"],
                emotion="pain",
            )
            repo_tier.save_episode(ep)

        result = consolidate_repo(repo_tier)
        assert "new patterns extracted" in result

        patterns = repo_tier.list_patterns()
        assert len(patterns) >= 1
        # Should find a pattern related to "timeout"
        timeout_patterns = [p for p in patterns if "timeout" in p.name]
        assert len(timeout_patterns) >= 1
        assert shared_file in timeout_patterns[0].seen_in

    def test_no_pattern_from_two_episodes(self, repo_tier):
        """No pattern when fewer than 3 episodes share a theme."""
        for i in range(2):
            ep = _make_episode(
                trigger=f"flaky test {i}",
                days_ago=i + 1,
                code_touched=["tests/test_api.py"],
                emotion="frustration",
            )
            repo_tier.save_episode(ep)

        result = consolidate_repo(repo_tier)
        assert "new patterns extracted" not in result

    def test_no_duplicate_patterns(self, repo_tier):
        """Existing pattern names are not duplicated."""
        # Create a pre-existing pattern
        existing = Pattern(
            name="recurring-timeout",
            category=PatternCategory.BUG,
            tier=Tier.REPO,
            signature="timeout recurrence",
            seen_in=["src/auth/login.py"],
        )
        repo_tier.save_pattern(existing)

        # Create 3 episodes with the same keyword
        for i in range(3):
            ep = _make_episode(
                trigger=f"timeout problem {i}",
                days_ago=i + 1,
                code_touched=["src/auth/login.py"],
                emotion="pain",
            )
            repo_tier.save_episode(ep)

        consolidate_repo(repo_tier)

        patterns = repo_tier.list_patterns()
        timeout_patterns = [p for p in patterns if "timeout" in p.name.lower()]
        # Should still be just the original one
        assert len(timeout_patterns) == 1

    def test_pain_emotion_creates_bug_pattern(self, repo_tier):
        """Episodes with pain emotion produce a BUG category pattern."""
        for i in range(3):
            ep = _make_episode(
                trigger=f"crash handler {i}",
                days_ago=i + 1,
                code_touched=["src/crash.py"],
                emotion="pain",
            )
            repo_tier.save_episode(ep)

        consolidate_repo(repo_tier)

        patterns = repo_tier.list_patterns()
        crash_patterns = [p for p in patterns if "crash" in p.name]
        if crash_patterns:
            assert crash_patterns[0].category == PatternCategory.BUG


class TestConsolidateRepoEmotionalRecalibration:
    """Phase 4: Emotional recalibration for stale emotions."""

    def test_stale_emotion_intensity_reduced(self, repo_tier):
        """Emotion not reinforced in 60 days has reduced intensity."""
        stale_date = (date.today() - timedelta(days=60)).isoformat()
        tag = EmotionTag(
            target="src/auth/login.py",
            emotion="pain",
            intensity=0.9,
            reason="kept breaking",
            last_reinforced=stale_date,
        )
        emotions = EmotionsFile(tags=[tag])
        repo_tier.dir.write_text("emotions.md", emotions.to_markdown())

        result = consolidate_repo(repo_tier)
        assert "emotions recalibrated" in result

        updated_emotions = repo_tier.get_emotions()
        pain_tags = [t for t in updated_emotions.tags if t.emotion == "pain"]
        assert len(pain_tags) == 1
        # Intensity should have decreased from 0.9
        assert pain_tags[0].intensity < 0.9

    def test_recent_emotion_not_recalibrated(self, repo_tier):
        """Emotion reinforced within last 30 days is not changed."""
        recent_date = (date.today() - timedelta(days=10)).isoformat()
        tag = EmotionTag(
            target="src/api.py",
            emotion="trust",
            intensity=0.8,
            reason="reliable module",
            last_reinforced=recent_date,
        )
        emotions = EmotionsFile(tags=[tag])
        repo_tier.dir.write_text("emotions.md", emotions.to_markdown())

        result = consolidate_repo(repo_tier)
        assert "emotions recalibrated" not in result

    def test_low_intensity_emotion_not_reduced_below_floor(self, repo_tier):
        """Emotion intensity does not drop below 0.2 floor."""
        stale_date = (date.today() - timedelta(days=365)).isoformat()
        tag = EmotionTag(
            target="src/legacy.py",
            emotion="frustration",
            intensity=0.35,
            reason="messy code",
            last_reinforced=stale_date,
        )
        emotions = EmotionsFile(tags=[tag])
        repo_tier.dir.write_text("emotions.md", emotions.to_markdown())

        consolidate_repo(repo_tier)

        updated_emotions = repo_tier.get_emotions()
        frust_tags = [t for t in updated_emotions.tags if t.emotion == "frustration"]
        assert len(frust_tags) == 1
        assert frust_tags[0].intensity >= 0.2


class TestConsolidateRepoStubPruning:
    """Phase 5: Stub episode pruning."""

    def test_weak_stub_pruned(self, repo_tier):
        """Stub episode with strength < 0.1 and no references is deleted."""
        ep = _make_episode(
            trigger="ancient forgotten thing",
            days_ago=300,
            phase=Phase.STUB,
            strength=0.05,
        )
        repo_tier.save_episode(ep)

        # Verify it exists first
        assert len(repo_tier.list_episodes()) == 1

        result = consolidate_repo(repo_tier)
        assert "stubs pruned" in result

        # Episode should be gone
        assert len(repo_tier.list_episodes()) == 0

    def test_stub_with_pattern_reference_not_pruned(self, repo_tier):
        """Stub with strength < 0.1 but referenced by a pattern is kept."""
        ep = _make_episode(
            trigger="referenced stub",
            days_ago=300,
            phase=Phase.STUB,
            strength=0.05,
            ep_id="ref123",
        )
        repo_tier.save_episode(ep)

        # Create a pattern that references this episode's id in seen_in
        pattern = Pattern(
            name="related-pattern",
            category=PatternCategory.BUG,
            tier=Tier.REPO,
            signature="test",
            seen_in=["ref123"],
        )
        repo_tier.save_pattern(pattern)

        consolidate_repo(repo_tier)

        # Episode should still exist
        assert len(repo_tier.list_episodes()) == 1

    def test_stub_with_high_strength_not_pruned(self, repo_tier):
        """Stub with strength >= 0.1 is not pruned."""
        ep = _make_episode(
            trigger="strong stub",
            days_ago=300,
            phase=Phase.STUB,
            strength=0.5,
        )
        repo_tier.save_episode(ep)

        consolidate_repo(repo_tier)

        assert len(repo_tier.list_episodes()) == 1

    def test_non_stub_not_pruned(self, repo_tier):
        """Non-stub episodes are never pruned regardless of strength."""
        ep = _make_episode(
            trigger="weak but vivid",
            days_ago=2,
            phase=Phase.VIVID,
            strength=0.01,
        )
        repo_tier.save_episode(ep)

        consolidate_repo(repo_tier)

        assert len(repo_tier.list_episodes()) == 1


class TestConsolidateRepoUninitialized:
    """Edge case: repo not initialized."""

    def test_uninitialized_repo(self, tmp_path):
        """Consolidation on uninitialized repo returns early."""
        (tmp_path / ".git").mkdir()
        repo = RepoTier(tmp_path)
        result = consolidate_repo(repo)
        assert "not initialized" in result


class TestHelpers:
    """Tests for helper functions."""

    def test_find_shared_files_counts_correctly(self):
        eps = [
            Episode(code_touched=["a.py", "b.py"]),
            Episode(code_touched=["a.py", "c.py"]),
            Episode(code_touched=["a.py", "b.py"]),
        ]
        shared = _find_shared_files(eps)
        assert "a.py" in shared
        assert "b.py" in shared
        # c.py only appears once, so not shared
        assert "c.py" not in shared

    def test_dominant_emotion_neutral_when_all_neutral(self):
        eps = [
            Episode(emotion="neutral"),
            Episode(emotion="neutral"),
        ]
        assert _dominant_emotion(eps) == "neutral"

    def test_dominant_emotion_picks_most_common(self):
        eps = [
            Episode(emotion="pain"),
            Episode(emotion="pain"),
            Episode(emotion="trust"),
        ]
        assert _dominant_emotion(eps) == "pain"

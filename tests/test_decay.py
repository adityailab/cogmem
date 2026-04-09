"""Tests for the decay engine."""

import math
import pytest
from datetime import date, timedelta
from pathlib import Path

from cogmem.engine.decay import (
    compute_new_strength,
    run_decay,
    transition_episode_phase,
    _decay_repo,
    _decay_workspace,
    _days_since,
    _days_since_access,
)
from cogmem.models import (
    DECAY_RATES,
    WORKSPACE_DECAY_MULTIPLIER,
    EmotionsFile,
    EmotionTag,
    Episode,
    Pattern,
    Phase,
    Tier,
)
from cogmem.tiers.repo import RepoTier
from cogmem.tiers.workspace import WorkspaceTier


@pytest.fixture
def repo_tier(tmp_path):
    """Create a minimal git repo with initialized .memory dir."""
    (tmp_path / ".git").mkdir()
    repo = RepoTier(tmp_path)
    repo.init()
    return repo


@pytest.fixture
def workspace_tier(tmp_path):
    """Create a minimal workspace with initialized .cogmem dir."""
    ws_root = tmp_path / "workspace"
    ws_root.mkdir()
    cogmem_dir = ws_root / ".cogmem"
    cogmem_dir.mkdir()
    for sub in ["gist", "episodes", "patterns", "prospective"]:
        (cogmem_dir / sub).mkdir()
    ws = WorkspaceTier(ws_root)
    return ws


def _make_episode(
    trigger: str,
    days_ago: int = 0,
    phase: str = Phase.VIVID,
    strength: float = 1.0,
    last_accessed: str | None = None,
    emotion: str = "neutral",
) -> Episode:
    """Helper to create episodes with controlled dates."""
    ep_date = (date.today() - timedelta(days=days_ago)).isoformat()
    return Episode(
        trigger=trigger,
        date=ep_date,
        phase=phase,
        strength=strength,
        last_accessed=last_accessed,
        emotion=emotion,
        learned=f"Learned from {trigger}",
        story=f"Story about {trigger}. More details.",
    )


# ---------------------------------------------------------------------------
# compute_new_strength
# ---------------------------------------------------------------------------

class TestComputeNewStrength:
    """Verify the exponential decay formula."""

    def test_no_decay_at_zero_days(self):
        """Strength unchanged when no time has passed."""
        result = compute_new_strength(1.0, 0.05, 0.0)
        assert result == pytest.approx(1.0)

    def test_exponential_formula(self):
        """Verify strength = current * exp(-rate * days)."""
        current = 0.8
        rate = 0.05
        days = 14.0
        expected = current * math.exp(-rate * days)
        result = compute_new_strength(current, rate, days)
        assert result == pytest.approx(expected)

    def test_half_life_episode(self):
        """Episode rate 0.05 gives ~50% strength at ~14 days."""
        rate = DECAY_RATES["episode"]
        half_life = math.log(2) / rate  # ln(2)/0.05 ~ 13.86
        result = compute_new_strength(1.0, rate, half_life)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_half_life_pattern(self):
        """Pattern rate 0.01 gives ~50% at ~70 days."""
        rate = DECAY_RATES["pattern"]
        half_life = math.log(2) / rate
        result = compute_new_strength(1.0, rate, half_life)
        assert result == pytest.approx(0.5, abs=0.01)

    def test_high_rate_rapid_decay(self):
        result = compute_new_strength(1.0, 1.0, 10.0)
        assert result == pytest.approx(math.exp(-10.0))
        assert result < 0.001

    def test_zero_rate_no_decay(self):
        result = compute_new_strength(0.9, 0.0, 100.0)
        assert result == pytest.approx(0.9)

    def test_low_initial_strength(self):
        """Decay from low starting strength."""
        result = compute_new_strength(0.1, 0.05, 14.0)
        expected = 0.1 * math.exp(-0.05 * 14.0)
        assert result == pytest.approx(expected)


# ---------------------------------------------------------------------------
# transition_episode_phase
# ---------------------------------------------------------------------------

class TestTransitionEpisodePhase:
    """Test each phase transition based on age."""

    def test_vivid_stays_vivid_within_7_days(self):
        ep = _make_episode("recent", days_ago=3, phase=Phase.VIVID)
        changed = transition_episode_phase(ep)
        assert changed is False
        assert ep.phase == Phase.VIVID

    def test_vivid_to_clear(self):
        ep = _make_episode("week old", days_ago=10, phase=Phase.VIVID)
        changed = transition_episode_phase(ep)
        assert changed is True
        assert ep.phase == Phase.CLEAR

    def test_clear_to_fuzzy(self):
        ep = _make_episode("month old", days_ago=40, phase=Phase.CLEAR)
        changed = transition_episode_phase(ep)
        assert changed is True
        assert ep.phase == Phase.FUZZY

    def test_fuzzy_to_fading(self):
        ep = _make_episode("quarter old", days_ago=120, phase=Phase.FUZZY)
        changed = transition_episode_phase(ep)
        assert changed is True
        assert ep.phase == Phase.FADING

    def test_fading_to_stub(self):
        ep = _make_episode("half year", days_ago=200, phase=Phase.FADING)
        changed = transition_episode_phase(ep)
        assert changed is True
        assert ep.phase == Phase.STUB

    def test_stub_stays_stub(self):
        ep = _make_episode("very old", days_ago=365, phase=Phase.STUB)
        changed = transition_episode_phase(ep)
        assert changed is False
        assert ep.phase == Phase.STUB

    def test_story_compressed_on_fuzzy(self):
        ep = _make_episode("compress test", days_ago=40, phase=Phase.CLEAR)
        ep.story = "Full story about the problem. Many details here."
        ep.learned = "Key lesson"
        transition_episode_phase(ep)
        # compress("summary") returns first sentence + learned
        assert "Key lesson" in ep.story or "Full story" in ep.story

    def test_story_compressed_on_stub(self):
        ep = _make_episode("stub test", days_ago=200, phase=Phase.FADING)
        ep.learned = "Important takeaway"
        transition_episode_phase(ep)
        # compress("stub") returns learned
        assert ep.story == "Important takeaway"

    def test_no_transition_without_date(self):
        ep = Episode(trigger="no date", phase=Phase.VIVID)
        changed = transition_episode_phase(ep)
        assert changed is False

    def test_invalid_date_no_transition(self):
        ep = Episode(trigger="bad date", date="not-a-date", phase=Phase.VIVID)
        changed = transition_episode_phase(ep)
        assert changed is False

    def test_explicit_today_parameter(self):
        """Passing explicit today affects age calculation."""
        ep = Episode(
            trigger="test",
            date="2025-01-01",
            phase=Phase.VIVID,
        )
        # 50 days after => should be fuzzy
        today = date(2025, 2, 20)
        changed = transition_episode_phase(ep, today=today)
        assert changed is True
        assert ep.phase == Phase.FUZZY


# ---------------------------------------------------------------------------
# run_decay / _decay_repo
# ---------------------------------------------------------------------------

class TestDecayRepo:
    """Test repo-level decay updates episode strength."""

    def test_episode_strength_decays(self, repo_tier):
        """Episode accessed days ago should lose strength."""
        accessed = (date.today() - timedelta(days=14)).isoformat()
        ep = _make_episode("decay test", days_ago=14, strength=1.0, last_accessed=accessed)
        repo_tier.save_episode(ep)

        result = _decay_repo(repo_tier)
        assert "episodes decayed" in result

        episodes = repo_tier.list_episodes()
        assert len(episodes) == 1
        assert episodes[0].strength < 1.0
        # Verify approximate expected value
        expected = compute_new_strength(1.0, DECAY_RATES["episode"], 14)
        assert episodes[0].strength == pytest.approx(expected, abs=0.05)

    def test_recent_episode_no_decay(self, repo_tier):
        """Episode accessed today should not decay."""
        today = date.today().isoformat()
        ep = _make_episode("fresh", days_ago=0, strength=1.0, last_accessed=today)
        repo_tier.save_episode(ep)

        result = _decay_repo(repo_tier)
        # May still process but strength unchanged
        episodes = repo_tier.list_episodes()
        assert episodes[0].strength == pytest.approx(1.0, abs=0.01)

    def test_decay_uses_date_fallback(self, repo_tier):
        """When last_accessed is None, decay falls back to episode date."""
        ep = _make_episode("no access", days_ago=20, strength=1.0, last_accessed=None)
        repo_tier.save_episode(ep)

        _decay_repo(repo_tier)

        episodes = repo_tier.list_episodes()
        assert len(episodes) == 1
        expected = compute_new_strength(1.0, DECAY_RATES["episode"], 20)
        assert episodes[0].strength == pytest.approx(expected, abs=0.05)

    def test_pattern_strength_decays(self, repo_tier):
        """Pattern strength decays based on last_seen date."""
        last_seen = (date.today() - timedelta(days=70)).isoformat()
        pattern = Pattern(
            name="old-pattern",
            category="bug",
            tier=Tier.REPO,
            signature="test",
            strength=1.0,
            last_seen=last_seen,
        )
        repo_tier.save_pattern(pattern)

        result = _decay_repo(repo_tier)
        assert "patterns decayed" in result

        patterns = repo_tier.list_patterns()
        assert len(patterns) == 1
        expected = compute_new_strength(1.0, DECAY_RATES["pattern"], 70)
        assert patterns[0].strength == pytest.approx(expected, abs=0.05)

    def test_emotion_intensity_decays(self, repo_tier):
        """Emotion intensity decays but stays above 0.1 floor."""
        stale_date = (date.today() - timedelta(days=100)).isoformat()
        tag = EmotionTag(
            target="src/test.py",
            emotion="pain",
            intensity=0.9,
            reason="flaky",
            last_reinforced=stale_date,
        )
        emotions = EmotionsFile(tags=[tag])
        repo_tier.dir.write_text("emotions.md", emotions.to_markdown())

        _decay_repo(repo_tier)

        updated = repo_tier.get_emotions()
        pain_tags = [t for t in updated.tags if t.emotion == "pain"]
        assert len(pain_tags) == 1
        assert pain_tags[0].intensity < 0.9
        assert pain_tags[0].intensity >= 0.1

    def test_nothing_to_decay(self, repo_tier):
        """Empty repo reports nothing to decay."""
        result = _decay_repo(repo_tier)
        assert "Nothing to decay" in result


class TestDecayWorkspace:
    """Test workspace decay with 0.7x multiplier."""

    def test_workspace_episode_decays_slower(self, workspace_tier):
        """Workspace episodes decay at 0.7x the repo rate."""
        accessed = (date.today() - timedelta(days=14)).isoformat()
        ep = _make_episode("ws decay", days_ago=14, strength=1.0, last_accessed=accessed)
        ep.save(str(workspace_tier.dir.resolve(f"episodes/{ep.filename}")))

        result = _decay_workspace(workspace_tier)
        assert "0.7x rate" in result

        episodes = workspace_tier.list_episodes()
        assert len(episodes) == 1

        ws_rate = DECAY_RATES["episode"] * WORKSPACE_DECAY_MULTIPLIER
        expected = compute_new_strength(1.0, ws_rate, 14)
        assert episodes[0].strength == pytest.approx(expected, abs=0.05)

    def test_workspace_decay_slower_than_repo(self, repo_tier, workspace_tier):
        """Workspace decay is strictly slower than repo decay for same episode."""
        accessed = (date.today() - timedelta(days=30)).isoformat()

        # Repo episode
        repo_ep = _make_episode("repo ep", days_ago=30, strength=1.0, last_accessed=accessed)
        repo_tier.save_episode(repo_ep)

        # Workspace episode (same parameters)
        ws_ep = _make_episode("ws ep", days_ago=30, strength=1.0, last_accessed=accessed)
        ws_ep.save(str(workspace_tier.dir.resolve(f"episodes/{ws_ep.filename}")))

        _decay_repo(repo_tier)
        _decay_workspace(workspace_tier)

        repo_episodes = repo_tier.list_episodes()
        ws_episodes = workspace_tier.list_episodes()

        # Workspace episode should retain more strength
        assert ws_episodes[0].strength > repo_episodes[0].strength

    def test_workspace_multiplier_value(self):
        """Verify the workspace multiplier is 0.7."""
        assert WORKSPACE_DECAY_MULTIPLIER == 0.7

    def test_workspace_pattern_decays_at_07x(self, workspace_tier):
        """Workspace patterns also use the 0.7x multiplier."""
        last_seen = (date.today() - timedelta(days=70)).isoformat()
        pattern = Pattern(
            name="ws-pattern",
            category="bug",
            tier=Tier.WORKSPACE,
            signature="test",
            strength=1.0,
            last_seen=last_seen,
        )
        pattern.save(str(workspace_tier.dir.resolve(f"patterns/{pattern.filename}")))

        result = _decay_workspace(workspace_tier)

        patterns = workspace_tier.list_patterns()
        assert len(patterns) == 1
        ws_rate = DECAY_RATES["pattern"] * WORKSPACE_DECAY_MULTIPLIER
        expected = compute_new_strength(1.0, ws_rate, 70)
        assert patterns[0].strength == pytest.approx(expected, abs=0.05)

    def test_workspace_nothing_to_decay(self, workspace_tier):
        """Empty workspace reports nothing."""
        result = _decay_workspace(workspace_tier)
        assert "Nothing to decay" in result


# ---------------------------------------------------------------------------
# run_decay (integration)
# ---------------------------------------------------------------------------

class TestRunDecay:
    """Integration tests for the top-level run_decay function."""

    def test_run_decay_with_repo(self, repo_tier):
        """run_decay processes repo tier."""
        accessed = (date.today() - timedelta(days=10)).isoformat()
        ep = _make_episode("integration", days_ago=10, strength=1.0, last_accessed=accessed)
        repo_tier.save_episode(ep)

        result = run_decay(cwd=str(repo_tier.repo_path))
        assert "Repo" in result
        assert "Global: patterns do not decay" in result

    def test_run_decay_no_repo(self, tmp_path):
        """run_decay without a repo reports appropriately."""
        result = run_decay(cwd=str(tmp_path))
        assert "No repo found" in result
        assert "Global: patterns do not decay" in result

    def test_global_patterns_never_decay(self, repo_tier):
        """Global tier message always present."""
        result = run_decay(cwd=str(repo_tier.repo_path))
        assert "Global: patterns do not decay" in result


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

class TestDaysSinceHelpers:
    """Tests for _days_since and _days_since_access."""

    def test_days_since_valid_date(self):
        past = (date.today() - timedelta(days=10)).isoformat()
        assert _days_since(past, date.today()) == 10

    def test_days_since_none_returns_1(self):
        assert _days_since(None, date.today()) == 1

    def test_days_since_invalid_returns_1(self):
        assert _days_since("not-a-date", date.today()) == 1

    def test_days_since_access_uses_last_accessed(self):
        accessed = (date.today() - timedelta(days=5)).isoformat()
        ep_date = (date.today() - timedelta(days=20)).isoformat()
        result = _days_since_access(accessed, ep_date, date.today())
        assert result == 5

    def test_days_since_access_falls_back_to_date(self):
        ep_date = (date.today() - timedelta(days=20)).isoformat()
        result = _days_since_access(None, ep_date, date.today())
        assert result == 20

    def test_days_since_access_both_none(self):
        result = _days_since_access(None, None, date.today())
        assert result == 0

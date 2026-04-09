"""Tests for utility modules."""

import math
import pytest
from pathlib import Path

from cogmem.utils.cues import CueSet, detect_task_type, extract_cues
from cogmem.utils.scoring import compute_score
from cogmem.utils.tokens import allocate_budget, estimate_tokens, truncate_to_budget
from cogmem.utils.repo_detect import find_repo_root, detect_repos_in_dir


class TestCueExtraction:
    def test_keywords(self):
        cues = extract_cues("fix the login timeout bug")
        assert "fix" in cues.keywords
        assert "login" in cues.keywords
        assert "timeout" in cues.keywords

    def test_file_paths(self):
        cues = extract_cues("look at auth/login.py")
        assert "auth/login.py" in cues.file_paths

    def test_emotions(self):
        cues = extract_cues("this broken code keeps crashing")
        assert "pain" in cues.emotions

    def test_task_type_hints(self):
        cues = extract_cues("fix the bug in auth")
        assert "bugfix" in cues.task_type_hints

    def test_entities(self):
        cues = extract_cues("the AuthHandler class is broken")
        assert any("AuthHandler" in e for e in cues.entities)

    def test_empty_query(self):
        cues = extract_cues("")
        assert cues.keywords == []
        assert cues.file_paths == []


class TestTaskTypeDetection:
    def test_bugfix(self):
        assert detect_task_type("fix the login bug") == "bugfix"

    def test_feature(self):
        assert detect_task_type("add a new search feature") == "feature"

    def test_refactor(self):
        assert detect_task_type("refactor the auth module") == "refactor"

    def test_understand(self):
        assert detect_task_type("how does the caching work") == "understand"

    def test_default(self):
        assert detect_task_type("hello") == "understand"


class TestScoring:
    def test_keyword_match(self):
        memory = {"trigger": "auth login fix", "story": "fixed auth"}
        cues = CueSet(keywords=["auth", "login"])
        score = compute_score(memory, cues, tier_weight=1.0)
        assert score > 0

    def test_no_keywords_gives_baseline(self):
        memory = {"trigger": "anything"}
        cues = CueSet()
        score = compute_score(memory, cues, tier_weight=1.0)
        assert score >= 0

    def test_tier_weight_affects_score(self):
        memory = {"trigger": "auth login"}
        cues = CueSet(keywords=["auth"])
        score_full = compute_score(memory, cues, tier_weight=1.0)
        score_reduced = compute_score(memory, cues, tier_weight=0.7)
        assert score_full > score_reduced

    def test_pain_emotion_boosted(self):
        memory_pain = {"trigger": "auth", "emotion": "pain", "intensity": 0.8}
        memory_neutral = {"trigger": "auth", "emotion": "neutral", "intensity": 0.5}
        cues = CueSet(keywords=["auth"])
        assert compute_score(memory_pain, cues) > compute_score(memory_neutral, cues)


class TestTokens:
    def test_estimate(self):
        assert estimate_tokens("hello world") >= 1
        assert estimate_tokens("a" * 100) == 25

    def test_truncate_short(self):
        assert truncate_to_budget("hello", 100) == "hello"

    def test_truncate_long(self):
        text = "x" * 1000
        result = truncate_to_budget(text, 10)
        assert len(result) <= 40 + 3
        assert result.endswith("...")

    def test_allocate_budget(self):
        alloc = allocate_budget("bugfix", 3500)
        assert sum(alloc.values()) == 3500
        assert alloc["episodes"] > alloc["spatial"]  # bugfix prioritizes episodes

    def test_allocate_unknown_type(self):
        alloc = allocate_budget("unknown_type", 3500)
        assert sum(alloc.values()) == 3500  # falls back to understand


class TestRepoDetect:
    def test_find_repo_root_in_git(self, tmp_path):
        (tmp_path / ".git").mkdir()
        assert find_repo_root(tmp_path) == tmp_path

    def test_find_repo_root_nested(self, tmp_path):
        (tmp_path / ".git").mkdir()
        subdir = tmp_path / "src" / "deep"
        subdir.mkdir(parents=True)
        assert find_repo_root(subdir) == tmp_path

    def test_find_repo_root_none(self, tmp_path):
        assert find_repo_root(tmp_path / "no_git_here") is None

    def test_detect_repos_in_dir(self, tmp_path):
        for name in ["repo_a", "repo_b", "not_a_repo"]:
            (tmp_path / name).mkdir()
        (tmp_path / "repo_a" / ".git").mkdir()
        (tmp_path / "repo_b" / ".git").mkdir()

        repos = detect_repos_in_dir(tmp_path)
        assert len(repos) == 2
        assert repos[0].name == "repo_a"

"""Tests for memory data models."""

import pytest
from cogmem.models import (
    CodeEntity,
    EmotionsFile,
    EmotionTag,
    Episode,
    EpisodeSource,
    Gist,
    GistScope,
    Judgment,
    Pattern,
    PatternCategory,
    Phase,
    Prospective,
    RepoSpatial,
    SpatialEntry,
    Landmark,
    Tier,
)


class TestEpisode:
    def test_roundtrip(self):
        ep = Episode(
            date="2026-01-15",
            trigger="Fixed auth timeout",
            story="The login endpoint was timing out under load.",
            learned="Connection pool was exhausted.",
            emotion="pain",
            intensity=0.8,
            code_touched=["auth/login.py"],
            source=EpisodeSource.LIVED,
            strength=1.0,
            phase=Phase.VIVID,
        )
        md = ep.to_markdown()
        restored = Episode.from_markdown(md)
        assert restored.trigger == "Fixed auth timeout"
        assert restored.emotion == "pain"
        assert restored.intensity == 0.8
        assert "auth/login.py" in restored.code_touched

    def test_phase_for_age(self):
        ep = Episode()
        assert ep.phase_for_age(0) == Phase.VIVID
        assert ep.phase_for_age(6) == Phase.VIVID
        assert ep.phase_for_age(7) == Phase.CLEAR
        assert ep.phase_for_age(29) == Phase.CLEAR
        assert ep.phase_for_age(30) == Phase.FUZZY
        assert ep.phase_for_age(89) == Phase.FUZZY
        assert ep.phase_for_age(90) == Phase.FADING
        assert ep.phase_for_age(179) == Phase.FADING
        assert ep.phase_for_age(180) == Phase.STUB
        assert ep.phase_for_age(365) == Phase.STUB

    def test_compress_levels(self):
        ep = Episode(
            trigger="auth bug",
            story="The login endpoint was timing out. Users could not sign in.",
            learned="Connection pool was exhausted.",
        )
        assert ep.compress("full") == ep.story
        summary = ep.compress("summary")
        assert "Learned:" in summary
        stub = ep.compress("stub")
        assert len(stub) < len(summary)

    def test_filename(self):
        ep = Episode(date="2026-01-15", trigger="Fixed auth timeout")
        assert ep.filename.startswith("2026-01-15_")
        assert ep.filename.endswith(".md")


class TestGist:
    def test_roundtrip(self):
        gist = Gist(
            scope=GistScope.MODULE,
            target="auth",
            what_it_does="Handles user authentication",
            why_it_exists="Core security feature",
            judgment=Judgment.SOLID,
            confidence=0.9,
        )
        md = gist.to_markdown()
        restored = Gist.from_markdown(md)
        assert restored.target == "auth"
        assert restored.what_it_does == "Handles user authentication"
        assert restored.judgment == Judgment.SOLID

    def test_filename_scopes(self):
        assert Gist(scope=GistScope.PLATFORM).filename == "_platform.md"
        assert Gist(scope=GistScope.CODEBASE).filename == "_codebase.md"
        assert Gist(scope=GistScope.MODULE, target="auth").filename == "auth.md"


class TestPattern:
    def test_roundtrip(self):
        pat = Pattern(
            name="null-pointer-deref",
            category=PatternCategory.BUG,
            signature="Accessing .value without null check",
            consequence="Runtime crash",
            response="Add null guard",
            seen_in=["parser.py", "handler.py"],
            frequency=5,
            strength=0.9,
        )
        md = pat.to_markdown()
        restored = Pattern.from_markdown(md)
        assert restored.name == "null-pointer-deref"
        assert restored.frequency == 5
        assert "parser.py" in restored.seen_in


class TestEmotionTag:
    def test_emotions_file_roundtrip(self):
        ef = EmotionsFile(tags=[
            EmotionTag(target="auth/login.py", emotion="pain", intensity=0.85, reason="Caused outage"),
            EmotionTag(target="core/utils.py", emotion="trust", intensity=0.7, reason="Well tested"),
        ])
        md = ef.to_markdown()
        restored = EmotionsFile.from_markdown(md)
        assert len(restored.tags) == 2
        assert restored.tags[0].target == "auth/login.py"
        assert restored.tags[0].emotion == "pain"
        assert restored.tags[1].emotion == "trust"

    def test_upsert(self):
        ef = EmotionsFile(tags=[
            EmotionTag(target="foo.py", emotion="pain", intensity=0.5),
        ])
        ef.upsert(EmotionTag(target="foo.py", emotion="trust", intensity=0.9))
        assert len(ef.tags) == 1
        assert ef.tags[0].emotion == "trust"

        ef.upsert(EmotionTag(target="bar.py", emotion="danger", intensity=0.8))
        assert len(ef.tags) == 2


class TestProspective:
    def test_roundtrip(self):
        p = Prospective(
            intention="Add rate limiting",
            trigger="auth/login.py",
            trigger_type="file_touch",
            priority="high",
        )
        md = p.to_markdown()
        restored = Prospective.from_markdown(md)
        assert restored.intention == "Add rate limiting"
        assert restored.trigger_type == "file_touch"

    def test_matches_context(self):
        p = Prospective(
            intention="Add rate limiting",
            trigger="auth/login.py",
            trigger_type="file_touch",
        )
        assert p.matches_context(["auth/login.py"], [])
        assert not p.matches_context(["other.py"], [])
        assert not Prospective(intention="x", trigger="y", completed=True).matches_context(["y"], [])


class TestSpatial:
    def test_repo_spatial_roundtrip(self):
        spatial = RepoSpatial(
            surface=[SpatialEntry(path="README.md", description="docs")],
            landmarks=[Landmark(path="main.py", description="entry", why="starts the app")],
        )
        md = spatial.to_markdown()
        assert "README.md" in md
        assert "main.py" in md


class TestCodeEntity:
    def test_roundtrip(self):
        entity = CodeEntity(
            file_path="auth/login.py",
            name="authenticate",
            kind="function",
            signature="def authenticate(user, password)",
            summary="Validates user credentials",
        )
        md = entity.to_markdown()
        restored = CodeEntity.from_markdown(md)
        assert restored.name == "authenticate"
        assert restored.kind == "function"

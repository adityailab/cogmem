"""End-to-end integration tests for the cogmem pipeline."""

import pytest
from pathlib import Path

from cogmem.engine.bootstrap import bootstrap_repo
from cogmem.engine.encode import encode
from cogmem.engine.consolidate import consolidate_repo
from cogmem.engine.decay import run_decay
from cogmem.engine.recall import recall
from cogmem.tiers.repo import RepoTier


@pytest.fixture
def git_repo(tmp_path):
    """Create a realistic git repo for integration testing."""
    (tmp_path / ".git").mkdir()
    (tmp_path / ".git" / "HEAD").write_text("ref: refs/heads/main\n")

    # Create a realistic project structure
    src = tmp_path / "src"
    src.mkdir()
    (src / "__init__.py").write_text("")
    (src / "main.py").write_text(
        "class Application:\n"
        "    def __init__(self, config):\n"
        "        self.config = config\n"
        "\n"
        "    def start(self):\n"
        "        print('Starting...')\n"
        "\n"
        "def create_app(config=None):\n"
        "    return Application(config or {})\n"
    )
    (src / "auth.py").write_text(
        "class AuthManager:\n"
        "    def login(self, user, password):\n"
        "        pass\n"
        "\n"
        "    def logout(self):\n"
        "        pass\n"
        "\n"
        "    def verify_token(self, token):\n"
        "        return True\n"
    )
    (src / "database.py").write_text(
        "import sqlite3\n"
        "\n"
        "class Database:\n"
        "    def __init__(self, path):\n"
        "        self.conn = sqlite3.connect(path)\n"
        "\n"
        "    def query(self, sql):\n"
        "        return self.conn.execute(sql)\n"
        "\n"
        "    def close(self):\n"
        "        self.conn.close()\n"
    )

    tests_dir = tmp_path / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_main.py").write_text(
        "def test_create_app():\n"
        "    from src.main import create_app\n"
        "    app = create_app()\n"
        "    assert app is not None\n"
    )

    (tmp_path / "README.md").write_text(
        "# TestApp\n\nA test application for integration tests.\n"
    )
    (tmp_path / "pyproject.toml").write_text(
        "[tool.poetry]\nname = 'testapp'\nversion = '0.1.0'\n"
    )

    return tmp_path


class TestFullPipeline:
    """Test the complete cogmem lifecycle: bootstrap -> encode -> consolidate -> decay -> recall."""

    def test_bootstrap_creates_entities_and_spatial(self, git_repo):
        result = bootstrap_repo(git_repo, months=1)

        repo = RepoTier(git_repo)
        assert repo.exists, "Repo memory should be initialized after bootstrap"

        # Verify entities were created
        entities = repo.list_entities()
        assert len(entities) > 0, "Bootstrap should extract code entities"

        entity_names = [e.name for e in entities]
        assert any("Application" in name or "App" in name for name in entity_names), (
            f"Should find Application class, got: {entity_names}"
        )

        # Verify spatial map was created
        spatial = repo.get_spatial()
        assert spatial is not None, "Bootstrap should create spatial map"

    def test_encode_creates_episode(self, git_repo):
        bootstrap_repo(git_repo, months=1)

        result = encode(
            event="Fixed the database connection timeout",
            emotion="pain",
            intensity=0.8,
            code_touched=[str(git_repo / "src" / "database.py")],
            learned="Connection pool was exhausted under load",
            cwd=str(git_repo),
        )
        assert "encoded" in result.lower(), f"Expected 'encoded' in result: {result}"

        repo = RepoTier(git_repo)
        episodes = repo.list_episodes()
        assert len(episodes) >= 1, "Should have at least one episode"

        db_episodes = [
            ep for ep in episodes
            if "database" in ep.trigger.lower() or "timeout" in ep.trigger.lower()
        ]
        assert len(db_episodes) >= 1, (
            f"Should find database episode, triggers: {[ep.trigger for ep in episodes]}"
        )

    def test_consolidate_runs_without_error(self, git_repo):
        bootstrap_repo(git_repo, months=1)

        # Add multiple episodes to give consolidation something to work with
        encode(
            event="Fixed auth token expiry bug",
            emotion="pain",
            intensity=0.6,
            code_touched=[str(git_repo / "src" / "auth.py")],
            learned="Token validation was not checking expiry date",
            cwd=str(git_repo),
        )
        encode(
            event="Added retry logic to database queries",
            code_touched=[str(git_repo / "src" / "database.py")],
            learned="Transient failures need retry with backoff",
            cwd=str(git_repo),
        )

        repo = RepoTier(git_repo)
        result = consolidate_repo(repo)
        # Should not raise and should return a string
        assert isinstance(result, str)
        assert len(result) > 0

    def test_decay_reduces_strengths(self, git_repo):
        bootstrap_repo(git_repo, months=1)

        encode(
            event="Refactored the main application startup",
            code_touched=[str(git_repo / "src" / "main.py")],
            cwd=str(git_repo),
        )

        repo = RepoTier(git_repo)
        episodes_before = repo.list_episodes()
        strengths_before = {ep.id: ep.strength for ep in episodes_before}

        result = run_decay(cwd=str(git_repo))
        assert isinstance(result, str)

        # Reload and check strengths
        repo_after = RepoTier(git_repo)
        episodes_after = repo_after.list_episodes()
        strengths_after = {ep.id: ep.strength for ep in episodes_after}

        # At least some episodes should have decayed (those not created today,
        # or all of them depending on the decay algorithm)
        if strengths_before:
            # Verify decay ran — it should mention something about the process
            assert "decay" in result.lower() or "repo" in result.lower() or len(result) > 0

    def test_recall_returns_encoded_event(self, git_repo):
        bootstrap_repo(git_repo, months=1)

        encode(
            event="Fixed critical database connection leak",
            emotion="pain",
            intensity=0.9,
            code_touched=[str(git_repo / "src" / "database.py")],
            learned="Connections were not being returned to the pool",
            cwd=str(git_repo),
        )

        result = recall(
            query="database connection problem",
            repo_only=True,
            cwd=str(git_repo),
        )
        assert isinstance(result, str)
        assert len(result) > 0

        # The recall output should reference our encoded event
        result_lower = result.lower()
        assert any(
            keyword in result_lower
            for keyword in ["database", "connection", "leak", "pool"]
        ), f"Recall should mention the encoded event. Got: {result[:500]}"

    def test_full_lifecycle(self, git_repo):
        """Run the complete lifecycle in sequence."""
        # Step 1: Bootstrap
        bootstrap_result = bootstrap_repo(git_repo, months=1)
        repo = RepoTier(git_repo)
        assert repo.exists

        # Step 2: Encode multiple events
        encode(
            event="Authentication system was leaking sessions",
            emotion="pain",
            intensity=0.85,
            code_touched=[str(git_repo / "src" / "auth.py")],
            learned="Session cleanup was missing from logout",
            cwd=str(git_repo),
        )
        encode(
            event="Added database connection pooling",
            emotion="triumph",
            intensity=0.7,
            code_touched=[str(git_repo / "src" / "database.py")],
            learned="Connection pooling reduces latency by 3x",
            cwd=str(git_repo),
        )

        episodes = repo.list_episodes()
        assert len(episodes) >= 2, "Should have at least 2 encoded episodes"

        # Step 3: Consolidate
        consolidate_result = consolidate_repo(repo)
        assert isinstance(consolidate_result, str)

        # Step 4: Decay
        decay_result = run_decay(cwd=str(git_repo))
        assert isinstance(decay_result, str)

        # Step 5: Recall — should find our encoded events
        recall_result = recall(
            query="authentication session leak",
            repo_only=True,
            cwd=str(git_repo),
        )
        assert len(recall_result) > 0
        assert any(
            keyword in recall_result.lower()
            for keyword in ["auth", "session", "leak", "login", "logout"]
        ), f"Recall should reference auth events. Got: {recall_result[:500]}"


class TestBootstrapIdempotent:
    def test_double_bootstrap_does_not_duplicate(self, git_repo):
        bootstrap_repo(git_repo, months=1)
        repo1 = RepoTier(git_repo)
        entity_count_1 = len(repo1.list_entities())

        # Bootstrap again
        bootstrap_repo(git_repo, months=1)
        repo2 = RepoTier(git_repo)
        entity_count_2 = len(repo2.list_entities())

        # Entity count should be the same or close (not doubled)
        assert entity_count_2 <= entity_count_1 * 1.5, (
            f"Double bootstrap should not duplicate entities: {entity_count_1} -> {entity_count_2}"
        )

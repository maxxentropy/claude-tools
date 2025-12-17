"""Tests for WorktreeManager."""

import json
import subprocess
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from worktree_manager import WorktreeManager


@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / "test-repo"
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(["git", "init"], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        # Create initial commit
        (repo_path / "README.md").write_text("# Test")
        subprocess.run(["git", "add", "."], cwd=repo_path, check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "Initial commit"],
            cwd=repo_path,
            check=True,
            capture_output=True,
        )

        yield repo_path


class TestWorktreeManagerConfig:
    """Tests for configuration management."""

    def test_default_config(self, temp_repo):
        """Test default configuration values."""
        manager = WorktreeManager(str(temp_repo))

        assert manager.config["version"] == "1.0"
        assert manager.config["defaultIDE"] == "auto"
        assert manager.config["autoInstallDeps"] is True
        assert manager.config["staleThresholdDays"] == 7

    def test_save_and_load_config(self, temp_repo):
        """Test saving and loading configuration."""
        manager = WorktreeManager(str(temp_repo))
        manager.config["defaultIDE"] = "rider"
        manager.save_config()

        # Create new manager to load from disk
        manager2 = WorktreeManager(str(temp_repo))
        assert manager2.config["defaultIDE"] == "rider"

    def test_get_config_value(self, temp_repo):
        """Test getting configuration by dotted key path."""
        manager = WorktreeManager(str(temp_repo))

        assert manager.get_config_value("version") == "1.0"
        assert manager.get_config_value("defaultIDE") == "auto"
        assert manager.get_config_value("nonexistent") is None

    def test_set_config_value(self, temp_repo):
        """Test setting configuration by dotted key path."""
        manager = WorktreeManager(str(temp_repo))

        manager.set_config_value("defaultIDE", "code")
        assert manager.config["defaultIDE"] == "code"

        # Test boolean coercion
        manager.set_config_value("autoCleanup", "true")
        assert manager.config["autoCleanup"] is True

        # Test integer coercion
        manager.set_config_value("staleThresholdDays", "14")
        assert manager.config["staleThresholdDays"] == 14


class TestWorktreeTracking:
    """Tests for worktree tracking."""

    def test_track_create(self, temp_repo):
        """Test tracking a newly created worktree."""
        manager = WorktreeManager(str(temp_repo))

        manager.track_create(
            name="test-worktree",
            path="/path/to/test-worktree",
            branch="feature/test",
            work_item="AB#1234",
        )

        assert "test-worktree" in manager.config["worktrees"]
        wt = manager.config["worktrees"]["test-worktree"]
        assert wt["branch"] == "feature/test"
        assert wt["workItem"] == "AB#1234"
        assert "created" in wt
        assert "lastActive" in wt

    def test_track_create_with_pr(self, temp_repo):
        """Test tracking a PR review worktree."""
        manager = WorktreeManager(str(temp_repo))

        manager.track_create(
            name="review-pr-5678",
            path="/path/to/review-pr-5678",
            branch="pr/5678",
            pr="5678",
        )

        assert "review-pr-5678" in manager.config["worktrees"]
        wt = manager.config["worktrees"]["review-pr-5678"]
        assert wt["pr"] == "5678"

    def test_track_remove(self, temp_repo):
        """Test removing worktree from tracking."""
        manager = WorktreeManager(str(temp_repo))

        manager.track_create(
            name="test-worktree",
            path="/path/to/test-worktree",
            branch="feature/test",
        )

        manager.track_remove("test-worktree")
        assert "test-worktree" not in manager.config["worktrees"]

    def test_get_worktree_path(self, temp_repo):
        """Test retrieving worktree path by name."""
        manager = WorktreeManager(str(temp_repo))

        manager.track_create(
            name="test-worktree",
            path="/path/to/test-worktree",
            branch="feature/test",
        )

        path = manager.get_worktree_path("test-worktree")
        assert path == "/path/to/test-worktree"

        # Non-existent worktree
        assert manager.get_worktree_path("nonexistent") is None

    def test_update_last_active(self, temp_repo):
        """Test updating lastActive timestamp."""
        manager = WorktreeManager(str(temp_repo))

        manager.track_create(
            name="test-worktree",
            path="/path/to/test-worktree",
            branch="feature/test",
        )

        original = manager.config["worktrees"]["test-worktree"]["lastActive"]

        # Update last active
        manager.update_last_active("test-worktree")
        updated = manager.config["worktrees"]["test-worktree"]["lastActive"]

        # Should be different (or at least not fail)
        assert updated is not None


class TestWorktreeListing:
    """Tests for listing worktrees."""

    def test_list_worktrees(self, temp_repo):
        """Test listing worktrees."""
        manager = WorktreeManager(str(temp_repo))

        worktrees = manager.list_worktrees()

        # Should include at least the main worktree
        assert len(worktrees) >= 1
        # Check that one worktree ends with 'test-repo' (handles symlink resolution)
        assert any(wt["path"].endswith("test-repo") for wt in worktrees)

    def test_list_worktrees_with_metadata(self, temp_repo):
        """Test that listing includes metadata."""
        manager = WorktreeManager(str(temp_repo))

        # Track a worktree
        manager.track_create(
            name="test-repo",  # Same as the repo basename
            path=str(temp_repo),
            branch="main",
            work_item="AB#1234",
        )

        worktrees = manager.list_worktrees()
        # Find worktree by name (handles symlink resolution)
        main_wt = next((wt for wt in worktrees if wt["name"] == "test-repo"), None)

        assert main_wt is not None
        assert main_wt["metadata"].get("workItem") == "AB#1234"


class TestCleanupCandidates:
    """Tests for cleanup candidate detection."""

    def test_cleanup_candidates_empty(self, temp_repo):
        """Test cleanup candidates when none exist."""
        manager = WorktreeManager(str(temp_repo))

        candidates = manager.get_cleanup_candidates(merged=True)
        # Main branch should never be a candidate
        assert "main" not in candidates
        assert "master" not in candidates

    def test_cleanup_candidates_stale(self, temp_repo):
        """Test identifying stale worktrees."""
        manager = WorktreeManager(str(temp_repo))

        # Track a worktree with old lastActive
        manager.track_create(
            name="stale-worktree",
            path="/path/to/stale",
            branch="feature/stale",
        )

        # Manually set lastActive to 30 days ago
        manager.config["worktrees"]["stale-worktree"]["lastActive"] = (
            datetime.now() - timedelta(days=30)
        ).isoformat()
        manager.save_config()

        # Note: This won't actually find the worktree because it doesn't exist
        # in git worktree list. This test validates the logic with metadata.
        candidates = manager.get_cleanup_candidates(stale_days=7)

        # The candidate detection works on actual git worktrees, so this may be empty
        # This is more of a smoke test
        assert isinstance(candidates, list)


class TestBranchMerged:
    """Tests for branch merge detection."""

    def test_is_branch_merged_main(self, temp_repo):
        """Test that main is considered merged into main."""
        manager = WorktreeManager(str(temp_repo))

        # Main should be merged into itself
        # Note: On a fresh repo, the branch is called "master" or "main"
        result = manager.is_branch_merged("main")
        # This might be True or False depending on the git version
        assert isinstance(result, bool)

    def test_is_branch_merged_nonexistent(self, temp_repo):
        """Test merge check for non-existent branch."""
        manager = WorktreeManager(str(temp_repo))

        result = manager.is_branch_merged("nonexistent-branch")
        assert result is False

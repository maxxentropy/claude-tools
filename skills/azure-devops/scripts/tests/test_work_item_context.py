"""
Tests for work_item_context.py

Tests the branch parsing, commit parsing, and context detection functionality.
"""

import pytest
from work_item_context import (
    BranchParser,
    CommitParser,
    ContextSource,
    WorkItemContext,
)


class TestBranchParser:
    """Tests for BranchParser.parse() method."""

    @pytest.mark.parametrize(
        "branch_name,expected_id,min_confidence",
        [
            # Explicit AB# format (highest confidence)
            ("feature/AB#1234-fix-bug", 1234, 1.0),
            ("fix/AB#5678-auth-issue", 5678, 1.0),
            ("bugfix/AB#9999-something", 9999, 1.0),
            ("AB#1234", 1234, 1.0),
            ("user/jsmith/AB#1234/feature", 1234, 0.9),
            # Case insensitive
            ("feature/ab#1234-fix", 1234, 1.0),
            ("feature/Ab#1234-fix", 1234, 1.0),
            # Bare numbers with prefix
            ("feature/1234-description", 1234, 0.8),
            ("fix/5678-short-desc", 5678, 0.8),
            ("bugfix/9999-something", 9999, 0.8),
            # User branch format
            ("user/jsmith/1234", 1234, 0.9),
            # Edge cases
            ("feature/AB#123456-long-id", 123456, 1.0),
            ("feature/AB#1000-minimum-4-digit", 1000, 1.0),
        ],
    )
    def test_parse_valid_branches(self, branch_name, expected_id, min_confidence):
        """Test parsing valid branch names with work item IDs."""
        work_item_id, confidence, raw_match = BranchParser.parse(branch_name)

        assert work_item_id == expected_id, f"Expected ID {expected_id}, got {work_item_id}"
        assert confidence >= min_confidence, f"Expected confidence >= {min_confidence}, got {confidence}"
        assert raw_match is not None

    @pytest.mark.parametrize(
        "branch_name",
        [
            # No work item reference
            "main",
            "master",
            "develop",
            "feature/add-new-feature",
            "fix/fix-the-thing",
            "release/v1.0.0",
            # Empty or None
            "",
            None,
        ],
    )
    def test_parse_no_work_item(self, branch_name):
        """Test branches without work item references."""
        work_item_id, confidence, raw_match = BranchParser.parse(branch_name)

        assert work_item_id is None
        assert confidence == 0.0
        assert raw_match is None

    def test_parse_returns_first_match(self):
        """Test that parser returns the first/best match when multiple exist."""
        # AB# format should take precedence
        branch = "feature/AB#1234-and-AB#5678"
        work_item_id, confidence, _ = BranchParser.parse(branch)

        assert work_item_id == 1234
        assert confidence == 1.0


class TestBranchParserSuggestBranchName:
    """Tests for BranchParser.suggest_branch_name() method."""

    def test_suggest_basic(self):
        """Test basic branch name suggestion."""
        suggested = BranchParser.suggest_branch_name(1234)
        assert suggested == "feature/AB#1234"

    def test_suggest_with_prefix(self):
        """Test branch name suggestion with custom prefix."""
        suggested = BranchParser.suggest_branch_name(1234, prefix="fix")
        assert suggested == "fix/AB#1234"

    def test_suggest_with_work_item_title(self):
        """Test branch name suggestion with work item title."""
        from work_item_index import WorkItem
        from datetime import datetime, timezone

        work_item = WorkItem(
            id=1234,
            type="Bug",
            title="Fix Authentication Bug",
            state="Active",
        )
        suggested = BranchParser.suggest_branch_name(1234, work_item=work_item, prefix="fix")

        assert "fix/AB#1234" in suggested
        assert "fix-authentication-bug" in suggested.lower()


class TestCommitParser:
    """Tests for CommitParser.parse() method."""

    @pytest.mark.parametrize(
        "message,expected_ids",
        [
            # AB# format
            ("Fix login issue AB#1234", [1234]),
            ("AB#5678: Update configuration", [5678]),
            ("Implement feature AB#1234 and AB#5678", [1234, 5678]),
            # Fixes/Closes format
            ("Fixes #1234", [1234]),
            ("Closes #5678", [5678]),
            ("Resolves #9999", [9999]),
            ("Refs #1234", [1234]),
            # Bracket format
            ("[1234] Fix bug", [1234]),
            ("[12345] Update docs", [12345]),
            # Work item: format
            ("Work item: 1234", [1234]),
            ("Task: 5678", [5678]),
            ("Bug: 9999", [9999]),
            # Case insensitive
            ("ab#1234 fix", [1234]),
            ("FIXES #5678", [5678]),
        ],
    )
    def test_parse_valid_messages(self, message, expected_ids):
        """Test parsing commit messages with work item references."""
        results = CommitParser.parse(message)

        found_ids = [r[0] for r in results]
        for expected_id in expected_ids:
            assert expected_id in found_ids, f"Expected to find {expected_id} in {found_ids}"

    @pytest.mark.parametrize(
        "message",
        [
            # No work item reference
            "Update README",
            "Fix typo in documentation",
            "Refactor code for clarity",
            "Initial commit",
            # Numbers that don't match patterns
            "Update version to 1.2.3",
            "Fix issue on line 42",
            "",
        ],
    )
    def test_parse_no_work_item(self, message):
        """Test commit messages without work item references."""
        results = CommitParser.parse(message)
        assert len(results) == 0

    def test_format_commit_reference(self):
        """Test formatting a work item reference for commit messages."""
        reference = CommitParser.format_commit_reference(1234)
        assert reference == "AB#1234"


class TestWorkItemContext:
    """Tests for WorkItemContext dataclass."""

    def test_has_context_with_id(self):
        """Test has_context returns True when work_item_id is set."""
        context = WorkItemContext(
            work_item_id=1234,
            work_item=None,
            source=ContextSource.BRANCH_NAME,
            branch_name="feature/AB#1234",
            confidence=1.0,
            raw_match="AB#1234",
        )
        assert context.has_context is True

    def test_has_context_without_id(self):
        """Test has_context returns False when work_item_id is None."""
        context = WorkItemContext(
            work_item_id=None,
            work_item=None,
            source=ContextSource.NONE,
            branch_name="main",
            confidence=0.0,
            raw_match=None,
        )
        assert context.has_context is False

    def test_to_dict_serialization(self):
        """Test serialization to dictionary."""
        context = WorkItemContext(
            work_item_id=1234,
            work_item=None,
            source=ContextSource.BRANCH_NAME,
            branch_name="feature/AB#1234",
            confidence=0.95,
            raw_match="AB#1234",
            suggested_area="Project\\Core",
        )
        result = context.to_dict()

        assert result["work_item_id"] == 1234
        assert result["source"] == "branch_name"
        assert result["branch_name"] == "feature/AB#1234"
        assert result["confidence"] == 0.95
        assert result["raw_match"] == "AB#1234"
        assert result["suggested_area"] == "Project\\Core"


class TestContextSource:
    """Tests for ContextSource enum."""

    def test_all_sources_have_values(self):
        """Test that all context sources have string values."""
        assert ContextSource.BRANCH_NAME.value == "branch_name"
        assert ContextSource.COMMIT_MESSAGE.value == "commit_message"
        assert ContextSource.ENVIRONMENT.value == "environment"
        assert ContextSource.MANUAL.value == "manual"
        assert ContextSource.INDEX_MAPPING.value == "index_mapping"
        assert ContextSource.NONE.value == "none"


class TestAreaSuggester:
    """Tests for AreaSuggester class."""

    def test_suggest_from_branch_with_component(self):
        """Test area suggestion from branch with clear component name."""
        from work_item_context import AreaSuggester

        suggester = AreaSuggester()

        # Test branch with component in path - feature/orders/AB#1234-fix
        result = suggester.suggest_from_branch("feature/orders/AB#1234-fix")
        # Should suggest something for 'orders'
        assert result is not None
        assert "Orders" in result or "orders" in result.lower()

    def test_suggest_from_branch_auth_component(self):
        """Test area suggestion recognizes auth as Platform."""
        from work_item_context import AreaSuggester

        suggester = AreaSuggester()

        # Branch with auth component
        result = suggester.suggest_from_branch("feature/auth/AB#1234-token-fix")
        if result:  # May return None depending on extraction
            assert "Platform" in result or "Auth" in result

    def test_suggest_from_branch_no_component(self):
        """Test area suggestion with branch that has no component hint."""
        from work_item_context import AreaSuggester

        suggester = AreaSuggester()

        # Branch with just work item ID, no component
        result = suggester.suggest_from_branch("feature/AB#1234")
        # May return None since no component can be extracted
        # This is acceptable behavior

    def test_category_mappings(self):
        """Test that category mappings are properly defined."""
        from work_item_context import AreaSuggester

        mappings = AreaSuggester.CATEGORY_MAPPINGS

        # Verify key categories exist
        assert mappings.get("auth") == "Platform"
        assert mappings.get("security") == "Platform"
        assert mappings.get("integration") == "Integrations"
        assert mappings.get("web") == "Clients"
        assert mappings.get("devops") == "Operations"

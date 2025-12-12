"""
Tests for commit_msg_hook.py

Tests the git commit-msg hook functionality for auto-linking work items.
"""

import pytest
from commit_msg_hook import (
    has_work_item_reference,
    parse_work_item_from_branch,
    is_exempt_branch,
    format_reference,
    append_reference_to_message,
)


class TestHasWorkItemReference:
    """Tests for has_work_item_reference function."""

    @pytest.mark.parametrize(
        "message",
        [
            "Fix bug AB#1234",
            "AB#5678: Update config",
            "Some change ab#9999",  # case insensitive
            "Multiple AB#1234 and AB#5678",
            "Work on AB#123456",
        ],
    )
    def test_has_reference(self, message):
        """Test messages that contain work item references."""
        assert has_work_item_reference(message) is True

    @pytest.mark.parametrize(
        "message",
        [
            "Fix bug in login",
            "Update README",
            "AB 1234",  # missing #
            "AB1234",  # missing #
            "#1234",  # missing AB
            "",
        ],
    )
    def test_no_reference(self, message):
        """Test messages without work item references."""
        assert has_work_item_reference(message) is False


class TestParseWorkItemFromBranch:
    """Tests for parse_work_item_from_branch function."""

    @pytest.mark.parametrize(
        "branch,expected_id",
        [
            ("feature/AB#1234-fix", 1234),
            ("fix/AB#5678-bug", 5678),
            ("bugfix/1234-issue", 1234),
            ("user/name/AB#9999/feat", 9999),
            ("AB#1234", 1234),
            ("feature/ab#1234-case", 1234),  # case insensitive
        ],
    )
    def test_valid_branches(self, branch, expected_id):
        """Test parsing valid branch names."""
        work_item_id, raw_match = parse_work_item_from_branch(branch)
        assert work_item_id == expected_id
        assert raw_match is not None

    @pytest.mark.parametrize(
        "branch",
        [
            "main",
            "develop",
            "feature/new-feature",
            "fix/something",
            "",
            None,
        ],
    )
    def test_invalid_branches(self, branch):
        """Test branches without work item IDs."""
        work_item_id, raw_match = parse_work_item_from_branch(branch)
        assert work_item_id is None


class TestIsExemptBranch:
    """Tests for is_exempt_branch function."""

    @pytest.mark.parametrize(
        "branch",
        [
            "main",
            "master",
            "develop",
            "release",
            "release/v1.0.0",
            "hotfix/urgent-fix",
            "dependabot/npm-update",
            "renovate/all-dependencies",
            None,
            "",
        ],
    )
    def test_exempt_branches(self, branch):
        """Test branches that should be exempt from work item requirements."""
        assert is_exempt_branch(branch) is True

    @pytest.mark.parametrize(
        "branch",
        [
            "feature/AB#1234-new-feature",
            "fix/AB#5678-bug-fix",
            "user/jsmith/AB#9999",
            "bugfix/issue-123",
            "my-branch",
        ],
    )
    def test_non_exempt_branches(self, branch):
        """Test branches that should NOT be exempt."""
        assert is_exempt_branch(branch) is False


class TestFormatReference:
    """Tests for format_reference function."""

    def test_format_basic(self):
        """Test basic reference formatting."""
        assert format_reference(1234) == "AB#1234"

    def test_format_large_number(self):
        """Test formatting with larger work item IDs."""
        assert format_reference(999999) == "AB#999999"


class TestAppendReferenceToMessage:
    """Tests for append_reference_to_message function."""

    def test_append_simple(self):
        """Test appending reference to simple message."""
        message = "Fix the bug"
        result = append_reference_to_message(message, "AB#1234")

        assert "Fix the bug" in result
        assert "AB#1234" in result
        assert result.endswith("\n")

    def test_append_multiline(self):
        """Test appending reference to multiline message."""
        message = "Fix the bug\n\nThis fixes an important issue."
        result = append_reference_to_message(message, "AB#1234")

        assert "Fix the bug" in result
        assert "This fixes an important issue" in result
        assert "AB#1234" in result

    def test_append_preserves_signed_off_by(self):
        """Test that Signed-off-by lines are preserved after the reference."""
        message = "Fix the bug\n\nSigned-off-by: Dev <dev@example.com>"
        result = append_reference_to_message(message, "AB#1234")

        # Reference should appear before Signed-off-by
        ab_pos = result.find("AB#1234")
        signed_pos = result.find("Signed-off-by:")

        assert ab_pos < signed_pos, "AB#1234 should appear before Signed-off-by"

    def test_append_preserves_co_authored_by(self):
        """Test that Co-authored-by lines are preserved."""
        message = "Fix the bug\n\nCo-authored-by: Other <other@example.com>"
        result = append_reference_to_message(message, "AB#1234")

        ab_pos = result.find("AB#1234")
        coauthor_pos = result.find("Co-authored-by:")

        assert ab_pos < coauthor_pos, "AB#1234 should appear before Co-authored-by"

    def test_append_with_trailing_newline(self):
        """Test message that already has trailing newline."""
        message = "Fix the bug\n"
        result = append_reference_to_message(message, "AB#1234")

        assert "AB#1234" in result
        # Should not have excessive newlines
        assert "\n\n\n\n" not in result

    def test_append_empty_message(self):
        """Test with empty message."""
        message = ""
        result = append_reference_to_message(message, "AB#1234")

        assert "AB#1234" in result

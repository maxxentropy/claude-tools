"""Tests for findings_store.py"""

import json
import tempfile
from pathlib import Path

import pytest

from findings_store import FindingsStore, Finding, Evidence, FINDING_TYPES, SEVERITIES


@pytest.fixture
def temp_store():
    """Create a temporary findings store for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        # Create a fake .git directory so the store thinks it's in a repo
        git_dir = Path(tmpdir) / ".git"
        git_dir.mkdir()

        store = FindingsStore(root_dir=Path(tmpdir))
        yield store


class TestFindingsStore:
    """Tests for FindingsStore class."""

    def test_init_creates_directory(self, temp_store):
        """Store initializes .findings directory."""
        assert temp_store.findings_dir.exists()
        assert temp_store.jsonl_path.exists()
        assert (temp_store.findings_dir / ".gitignore").exists()

    def test_create_finding_returns_id(self, temp_store):
        """Creating a finding returns a valid ID."""
        finding_id = temp_store.create_finding(
            title="Test finding",
            severity="medium"
        )
        assert finding_id.startswith("f-")
        assert len(finding_id) == 10  # f- + 8 hex chars

    def test_create_finding_stores_in_jsonl(self, temp_store):
        """Created findings are stored in JSONL file."""
        temp_store.create_finding(title="Test finding")

        with open(temp_store.jsonl_path) as f:
            lines = f.readlines()

        assert len(lines) == 1
        data = json.loads(lines[0])
        assert data["title"] == "Test finding"

    def test_get_finding_retrieves_by_id(self, temp_store):
        """Get finding by ID."""
        finding_id = temp_store.create_finding(
            title="Test finding",
            severity="high"
        )

        finding = temp_store.get_finding(finding_id)
        assert finding is not None
        assert finding.title == "Test finding"
        assert finding.severity == "high"

    def test_get_finding_returns_none_for_missing(self, temp_store):
        """Get returns None for missing ID."""
        finding = temp_store.get_finding("f-nonexistent")
        assert finding is None

    def test_update_finding_changes_fields(self, temp_store):
        """Update modifies finding fields."""
        finding_id = temp_store.create_finding(title="Original title")

        result = temp_store.update_finding(
            finding_id,
            title="Updated title",
            status="in_progress"
        )

        assert result is True
        finding = temp_store.get_finding(finding_id)
        assert finding.title == "Updated title"
        assert finding.status == "in_progress"
        assert finding.version == 2

    def test_resolve_finding_sets_status(self, temp_store):
        """Resolve marks finding as resolved."""
        finding_id = temp_store.create_finding(title="Bug to fix")

        temp_store.resolve_finding(finding_id, resolution="fixed")

        finding = temp_store.get_finding(finding_id)
        assert finding.status == "resolved"
        assert finding.resolution == "fixed"
        assert finding.resolved_at is not None

    def test_promote_to_ado_links_work_item(self, temp_store):
        """Promote links finding to ADO work item."""
        finding_id = temp_store.create_finding(title="Work to track")

        temp_store.promote_to_ado(finding_id, "AB#1234")

        finding = temp_store.get_finding(finding_id)
        assert finding.status == "promoted"
        assert finding.ado_work_item == "AB#1234"

    def test_query_findings_filters_by_status(self, temp_store):
        """Query filters by status."""
        temp_store.create_finding(title="Open 1")
        temp_store.create_finding(title="Open 2")
        id3 = temp_store.create_finding(title="Resolved")
        temp_store.resolve_finding(id3)

        open_findings = temp_store.query_findings(status="open")
        assert len(open_findings) == 2

        resolved_findings = temp_store.query_findings(status="resolved")
        assert len(resolved_findings) == 1

    def test_query_findings_filters_by_severity(self, temp_store):
        """Query filters by severity."""
        temp_store.create_finding(title="Critical", severity="critical")
        temp_store.create_finding(title="Medium", severity="medium")

        critical = temp_store.query_findings(severity="critical")
        assert len(critical) == 1
        assert critical[0].title == "Critical"

    def test_query_findings_search(self, temp_store):
        """Query searches title and description."""
        temp_store.create_finding(title="N+1 query issue")
        temp_store.create_finding(title="Memory leak", description="Causes N+1 allocations")
        temp_store.create_finding(title="Other issue")

        results = temp_store.query_findings(search="N+1")
        assert len(results) == 2

    def test_get_open_findings(self, temp_store):
        """Get open findings returns only open status."""
        temp_store.create_finding(title="Open")
        id2 = temp_store.create_finding(title="Resolved")
        temp_store.resolve_finding(id2)

        open_findings = temp_store.get_open_findings()
        assert len(open_findings) == 1
        assert open_findings[0].title == "Open"

    def test_get_ready_findings_excludes_blocked(self, temp_store):
        """Ready findings excludes blocked ones."""
        id1 = temp_store.create_finding(title="Ready")
        id2 = temp_store.create_finding(title="Blocked")
        temp_store.update_finding(id2, blocked_by=[id1])

        ready = temp_store.get_ready_findings()
        assert len(ready) == 1
        assert ready[0].title == "Ready"

    def test_statistics(self, temp_store):
        """Statistics returns correct counts."""
        temp_store.create_finding(title="Open", severity="high")
        temp_store.create_finding(title="Open2", severity="medium")
        id3 = temp_store.create_finding(title="Resolved", severity="low")
        temp_store.resolve_finding(id3)

        stats = temp_store.get_statistics()
        assert stats["total"] == 3
        assert stats["by_status"]["open"] == 2
        assert stats["by_status"]["resolved"] == 1
        assert stats["by_severity"]["high"] == 1
        assert stats["by_severity"]["medium"] == 1
        assert stats["by_severity"]["low"] == 1

    def test_compact_reports_savings(self, temp_store):
        """Compact reports lines that would be removed."""
        finding_id = temp_store.create_finding(title="Original")
        # Update multiple times to create extra lines
        temp_store.update_finding(finding_id, title="Update 1")
        temp_store.update_finding(finding_id, title="Update 2")
        temp_store.update_finding(finding_id, title="Update 3")

        stats = temp_store.compact(dry_run=True)
        assert stats["original_lines"] == 4
        assert stats["unique_findings"] == 1
        assert stats["lines_removed"] == 3
        assert stats["dry_run"] is True


class TestEvidence:
    """Tests for Evidence dataclass."""

    def test_to_dict_excludes_none(self):
        """to_dict excludes None values."""
        evidence = Evidence(file="test.py", line=10)
        d = evidence.to_dict()
        assert "file" in d
        assert "line" in d
        assert "snippet" not in d
        assert "function" not in d


class TestFinding:
    """Tests for Finding dataclass."""

    def test_to_dict_includes_evidence(self):
        """to_dict includes evidence when present."""
        finding = Finding(
            id="f-test123",
            title="Test",
            evidence=Evidence(file="test.py", line=10)
        )
        d = finding.to_dict()
        assert d["evidence"]["file"] == "test.py"
        assert d["evidence"]["line"] == 10

    def test_from_dict_creates_finding(self):
        """from_dict creates Finding instance."""
        data = {
            "id": "f-test123",
            "version": 1,
            "title": "Test finding",
            "finding_type": "discovery",
            "category": "other",
            "severity": "medium",
            "status": "open",
            "description": "",
            "evidence": {"file": "test.py", "line": 10},
            "discovered_at": "2025-01-01T00:00:00Z",
            "discovered_by": "claude",
            "tags": ["tag1"],
            "priority": 2,
            "effort": "small",
            "confidence": 0.9,
            "created_at": "2025-01-01T00:00:00Z",
            "updated_at": "2025-01-01T00:00:00Z",
            "related_to": [],
            "blocks": [],
            "blocked_by": [],
            "parent": None,
            "ado_work_item": None,
            "eval_result": None,
            "discovered_during": None,
            "session_id": None,
            "branch": None,
            "commit": None,
            "resolution": None,
            "resolved_at": None,
            "resolved_by": None,
        }

        finding = Finding.from_dict(data)
        assert finding.id == "f-test123"
        assert finding.title == "Test finding"
        assert finding.evidence.file == "test.py"
        assert finding.evidence.line == 10

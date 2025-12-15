"""Tests for findings_store.py"""

import json
import tempfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

import pytest

from findings_store import FindingsStore, Finding, Evidence, FINDING_TYPES, SEVERITIES, parse_duration


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


class TestParseDuration:
    """Tests for parse_duration function."""

    def test_parse_days(self):
        """Parses day durations."""
        assert parse_duration("30d") == timedelta(days=30)
        assert parse_duration("1d") == timedelta(days=1)
        assert parse_duration("365d") == timedelta(days=365)

    def test_parse_weeks(self):
        """Parses week durations."""
        assert parse_duration("2w") == timedelta(weeks=2)
        assert parse_duration("1w") == timedelta(weeks=1)

    def test_parse_hours(self):
        """Parses hour durations."""
        assert parse_duration("6h") == timedelta(hours=6)
        assert parse_duration("24h") == timedelta(hours=24)

    def test_parse_minutes(self):
        """Parses minute durations."""
        assert parse_duration("30m") == timedelta(minutes=30)
        assert parse_duration("90m") == timedelta(minutes=90)

    def test_case_insensitive(self):
        """Handles uppercase units."""
        assert parse_duration("30D") == timedelta(days=30)
        assert parse_duration("2W") == timedelta(weeks=2)

    def test_invalid_format_raises(self):
        """Invalid format raises ValueError."""
        with pytest.raises(ValueError):
            parse_duration("invalid")
        with pytest.raises(ValueError):
            parse_duration("30x")
        with pytest.raises(ValueError):
            parse_duration("abc123")


class TestArchiveOldFindings:
    """Tests for archive_old_findings method."""

    def test_archive_reports_findings_count(self, temp_store):
        """Archive reports how many findings would be archived."""
        # Create some findings that we'll manually backdate
        id1 = temp_store.create_finding(title="Old resolved")
        temp_store.resolve_finding(id1)

        # Manually update the timestamp to be old (use proper format: YYYY-MM-DDTHH:MM:SSZ)
        index = temp_store._load_index()
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        index["findings"][id1]["updated_at"] = old_date
        temp_store._save_index(index)

        result = temp_store.archive_old_findings("30d", dry_run=True)
        assert result["dry_run"] is True
        assert result["findings_to_archive"] == 1

    def test_archive_respects_status_filter(self, temp_store):
        """Archive only affects findings with specified statuses."""
        # Create an open finding
        id1 = temp_store.create_finding(title="Open finding")

        # Backdate it (use proper format: YYYY-MM-DDTHH:MM:SSZ)
        index = temp_store._load_index()
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        index["findings"][id1]["updated_at"] = old_date
        temp_store._save_index(index)

        # Default filter is resolved/wont_fix/promoted, so open should not be archived
        result = temp_store.archive_old_findings("30d", dry_run=True)
        assert result["findings_to_archive"] == 0

    def test_archive_invalid_duration_returns_error(self, temp_store):
        """Invalid duration returns error in result."""
        result = temp_store.archive_old_findings("invalid", dry_run=True)
        assert "error" in result


class TestSummarizeOldFindings:
    """Tests for summarize_old_findings method."""

    def test_summarize_reports_findings_count(self, temp_store):
        """Summarize reports how many findings would be summarized."""
        # Create some findings and backdate them
        id1 = temp_store.create_finding(title="Old finding 1", category="performance")
        id2 = temp_store.create_finding(title="Old finding 2", category="security")

        # Backdate both (use proper format: YYYY-MM-DDTHH:MM:SSZ)
        index = temp_store._load_index()
        old_date = (datetime.now(timezone.utc) - timedelta(days=60)).strftime("%Y-%m-%dT%H:%M:%SZ")
        index["findings"][id1]["created_at"] = old_date
        index["findings"][id2]["created_at"] = old_date
        temp_store._save_index(index)

        result = temp_store.summarize_old_findings("30d", dry_run=True)
        assert result["dry_run"] is True
        assert result["findings_count"] == 2
        assert "summary" in result
        assert result["summary"]["total_findings"] == 2

    def test_summarize_invalid_duration_returns_error(self, temp_store):
        """Invalid duration returns error in result."""
        result = temp_store.summarize_old_findings("invalid", dry_run=True)
        assert "error" in result


class TestSQLiteCache:
    """Tests for SQLite cache functionality."""

    def test_sqlite_cache_initialization(self):
        """SQLite cache initializes and creates database."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()

            store = FindingsStore(root_dir=Path(tmpdir), use_sqlite_cache=True)
            assert store.sqlite_path.exists()

    def test_sqlite_cache_queries(self):
        """SQLite cache supports queries."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()

            store = FindingsStore(root_dir=Path(tmpdir), use_sqlite_cache=True)
            store.create_finding(title="Test 1", severity="high")
            store.create_finding(title="Test 2", severity="low")

            # Query using SQL
            results = store.query_findings_sql(severity="high")
            assert len(results) == 1
            assert results[0].title == "Test 1"

    def test_rebuild_sqlite_cache(self):
        """Rebuild SQLite cache from JSONL."""
        with tempfile.TemporaryDirectory() as tmpdir:
            git_dir = Path(tmpdir) / ".git"
            git_dir.mkdir()

            # Create store without SQLite first
            store = FindingsStore(root_dir=Path(tmpdir), use_sqlite_cache=False)
            store.create_finding(title="Existing finding")

            # Now enable and rebuild
            result = store.rebuild_sqlite_cache()
            assert result["rebuilt"] is True
            assert result["findings_count"] == 1

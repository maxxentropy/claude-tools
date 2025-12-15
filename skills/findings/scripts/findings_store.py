"""
Findings Store - JSONL-based persistent storage for Claude Code findings.

Inspired by beads (https://github.com/steveyegge/beads), this module provides
git-tracked persistent memory for AI coding agents.

Architecture:
- Source of truth: .findings/findings.jsonl (git-tracked, append-friendly)
- Fast queries: .findings/index.json (git-ignored, rebuilt from JSONL)
- SQLite cache: .findings/findings.db (git-ignored, optional speed optimization)
- Session state: .findings/session-context.json (git-ignored)

Usage:
    from findings_store import FindingsStore

    store = FindingsStore()
    finding_id = store.create_finding(
        title="N+1 query in OrderService",
        finding_type="discovery",
        severity="medium",
        file_path="src/Services/OrderService.cs",
        line=145
    )
    store.query_findings(status="open")

    # With SQLite cache for faster queries
    store = FindingsStore(use_sqlite_cache=True)
"""

import hashlib
import json
import os
import re
import sqlite3
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple


# Finding types
FINDING_TYPES = ["discovery", "todo", "question", "note", "tech-debt", "bug"]

# Severity levels (aligned with ADO)
SEVERITIES = ["critical", "high", "medium", "low", "info"]

# Status values
STATUSES = ["open", "in_progress", "resolved", "wont_fix", "promoted"]

# Categories (aligned with eval-framework)
CATEGORIES = [
    "thread-safety", "resource-management", "error-handling",
    "state-management", "external-operations", "api-web-layer",
    "configuration", "code-consistency", "security", "performance",
    "architecture", "testing", "documentation", "other"
]


@dataclass
class Evidence:
    """Location and code evidence for a finding."""
    file: Optional[str] = None
    line: Optional[int] = None
    snippet: Optional[str] = None
    function: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}


@dataclass
class Finding:
    """A persistent finding/discovery from a Claude Code session."""
    # Identity
    id: str
    version: int = 1

    # Classification
    title: str = ""
    finding_type: str = "discovery"
    category: str = "other"
    severity: str = "medium"

    # Content
    description: str = ""
    evidence: Optional[Evidence] = None

    # Context
    discovered_at: str = ""
    discovered_by: str = "claude"
    discovered_during: Optional[str] = None  # e.g., "architecture-review"
    session_id: Optional[str] = None
    branch: Optional[str] = None
    commit: Optional[str] = None

    # Relationships
    related_to: List[str] = field(default_factory=list)
    blocks: List[str] = field(default_factory=list)
    blocked_by: List[str] = field(default_factory=list)
    parent: Optional[str] = None
    ado_work_item: Optional[str] = None  # AB#1234
    eval_result: Optional[str] = None

    # Status
    status: str = "open"
    resolution: Optional[str] = None
    resolved_at: Optional[str] = None
    resolved_by: Optional[str] = None

    # Metadata
    tags: List[str] = field(default_factory=list)
    priority: int = 3  # 1-4 like ADO
    effort: str = "unknown"  # small, medium, large, unknown
    confidence: float = 0.8

    # Timestamps
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        d = asdict(self)
        if self.evidence:
            d["evidence"] = self.evidence.to_dict()
        return d

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Finding":
        """Create Finding from dictionary."""
        evidence_data = data.pop("evidence", None)
        evidence = Evidence(**evidence_data) if evidence_data else None
        return cls(evidence=evidence, **data)


def parse_duration(duration_str: str) -> timedelta:
    """
    Parse a duration string like '30d', '2w', '6h' into a timedelta.

    Supported units: d (days), w (weeks), h (hours), m (minutes)
    """
    match = re.match(r'^(\d+)([dwhmDWHM])$', duration_str.strip())
    if not match:
        raise ValueError(f"Invalid duration format: {duration_str}. Use format like '30d', '2w', '6h'")

    value = int(match.group(1))
    unit = match.group(2).lower()

    if unit == 'd':
        return timedelta(days=value)
    elif unit == 'w':
        return timedelta(weeks=value)
    elif unit == 'h':
        return timedelta(hours=value)
    elif unit == 'm':
        return timedelta(minutes=value)
    else:
        raise ValueError(f"Unknown unit: {unit}")


class FindingsStore:
    """
    Git-tracked persistent storage for findings.

    Storage layout:
        .findings/
        ├── findings.jsonl      # Git-tracked, append-only log
        ├── index.json          # Git-ignored, fast lookup cache
        ├── findings.db         # Git-ignored, SQLite cache (optional)
        └── session-context.json # Git-ignored, current session state
    """

    def __init__(self, root_dir: Optional[Path] = None, use_sqlite_cache: bool = False):
        """
        Initialize the findings store.

        Args:
            root_dir: Project root directory. If None, searches up for .git
            use_sqlite_cache: Enable SQLite cache for faster queries
        """
        self.root_dir = root_dir or self._find_project_root()
        self.findings_dir = self.root_dir / ".findings"
        self.jsonl_path = self.findings_dir / "findings.jsonl"
        self.index_path = self.findings_dir / "index.json"
        self.context_path = self.findings_dir / "session-context.json"
        self.sqlite_path = self.findings_dir / "findings.db"

        self.use_sqlite_cache = use_sqlite_cache
        self._sqlite_conn: Optional[sqlite3.Connection] = None

        self._ensure_initialized()

        if use_sqlite_cache:
            self._init_sqlite_cache()

    def _find_project_root(self) -> Path:
        """Find project root by looking for .git directory."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists():
                return current
            current = current.parent
        return Path.cwd()

    def _ensure_initialized(self) -> None:
        """Ensure .findings directory and files exist."""
        if not self.findings_dir.exists():
            self.findings_dir.mkdir(parents=True)

            # Create .gitignore for local-only files
            gitignore = self.findings_dir / ".gitignore"
            gitignore.write_text("index.json\nsession-context.json\n*.db\n")

            # Create empty JSONL file
            self.jsonl_path.touch()

            # Initialize index
            self._save_index({"findings": {}, "last_rebuild": None})

    def _generate_id(self, title: str, timestamp: str) -> str:
        """Generate hash-based ID for collision resistance."""
        content = f"{title}:{timestamp}:{os.urandom(4).hex()}"
        hash_val = hashlib.sha256(content.encode()).hexdigest()[:8]
        return f"f-{hash_val}"

    def _get_current_branch(self) -> Optional[str]:
        """Get current git branch name."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=self.root_dir
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _get_current_commit(self) -> Optional[str]:
        """Get current git commit hash."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                capture_output=True, text=True, cwd=self.root_dir
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _load_index(self) -> Dict[str, Any]:
        """Load the index from disk, rebuilding if necessary."""
        if not self.index_path.exists():
            return self._rebuild_index()

        try:
            with open(self.index_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return self._rebuild_index()

    def _save_index(self, index: Dict[str, Any]) -> None:
        """Save the index to disk."""
        with open(self.index_path, "w") as f:
            json.dump(index, f, indent=2)

    def _rebuild_index(self) -> Dict[str, Any]:
        """Rebuild index from JSONL file."""
        index = {"findings": {}, "last_rebuild": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}

        if self.jsonl_path.exists():
            with open(self.jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        finding_id = data.get("id")
                        if finding_id:
                            # Upsert - later entries override earlier
                            index["findings"][finding_id] = data
                    except json.JSONDecodeError:
                        continue

        self._save_index(index)
        return index

    def _append_to_jsonl(self, finding: Finding) -> None:
        """Append finding to JSONL file."""
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(finding.to_dict()) + "\n")

    def create_finding(
        self,
        title: str,
        finding_type: str = "discovery",
        severity: str = "medium",
        category: str = "other",
        description: str = "",
        file_path: Optional[str] = None,
        line: Optional[int] = None,
        snippet: Optional[str] = None,
        function: Optional[str] = None,
        discovered_during: Optional[str] = None,
        tags: Optional[List[str]] = None,
        priority: int = 3,
        confidence: float = 0.8,
        ado_work_item: Optional[str] = None,
        eval_result: Optional[str] = None,
    ) -> str:
        """
        Create a new finding.

        Returns:
            The ID of the created finding.
        """
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        finding_id = self._generate_id(title, now)

        evidence = None
        if file_path or line or snippet or function:
            evidence = Evidence(
                file=file_path,
                line=line,
                snippet=snippet,
                function=function
            )

        finding = Finding(
            id=finding_id,
            title=title,
            finding_type=finding_type,
            severity=severity,
            category=category,
            description=description,
            evidence=evidence,
            discovered_at=now,
            discovered_during=discovered_during,
            branch=self._get_current_branch(),
            commit=self._get_current_commit(),
            tags=tags or [],
            priority=priority,
            confidence=confidence,
            ado_work_item=ado_work_item,
            eval_result=eval_result,
            created_at=now,
            updated_at=now,
        )

        # Append to JSONL (source of truth)
        self._append_to_jsonl(finding)

        # Update index
        index = self._load_index()
        index["findings"][finding_id] = finding.to_dict()
        self._save_index(index)

        # Update SQLite cache if enabled
        if self.use_sqlite_cache and self._sqlite_conn:
            self._update_sqlite_cache(finding)

        return finding_id

    def get_finding(self, finding_id: str) -> Optional[Finding]:
        """Get a finding by ID."""
        index = self._load_index()
        data = index["findings"].get(finding_id)
        return Finding.from_dict(data) if data else None

    def update_finding(self, finding_id: str, **updates) -> bool:
        """
        Update a finding.

        Args:
            finding_id: The ID of the finding to update
            **updates: Fields to update

        Returns:
            True if updated, False if not found
        """
        finding = self.get_finding(finding_id)
        if not finding:
            return False

        # Apply updates
        for key, value in updates.items():
            if hasattr(finding, key):
                setattr(finding, key, value)

        finding.version += 1
        finding.updated_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Append updated version to JSONL
        self._append_to_jsonl(finding)

        # Update index
        index = self._load_index()
        index["findings"][finding_id] = finding.to_dict()
        self._save_index(index)

        # Update SQLite cache if enabled
        if self.use_sqlite_cache and self._sqlite_conn:
            self._update_sqlite_cache(finding)

        return True

    def resolve_finding(
        self,
        finding_id: str,
        resolution: str = "fixed",
        resolved_by: str = "claude"
    ) -> bool:
        """Mark a finding as resolved."""
        return self.update_finding(
            finding_id,
            status="resolved",
            resolution=resolution,
            resolved_by=resolved_by,
            resolved_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        )

    def promote_to_ado(self, finding_id: str, work_item_id: str) -> bool:
        """Mark a finding as promoted to ADO."""
        return self.update_finding(
            finding_id,
            status="promoted",
            ado_work_item=work_item_id
        )

    def query_findings(
        self,
        status: Optional[str] = None,
        finding_type: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        branch: Optional[str] = None,
        tag: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> List[Finding]:
        """
        Query findings with filters.

        Args:
            status: Filter by status (open, resolved, etc.)
            finding_type: Filter by type (discovery, todo, etc.)
            severity: Filter by severity
            category: Filter by category
            branch: Filter by branch name
            tag: Filter by tag
            search: Search in title and description
            limit: Maximum results to return

        Returns:
            List of matching findings
        """
        index = self._load_index()
        results = []

        for data in index["findings"].values():
            # Apply filters
            if status and data.get("status") != status:
                continue
            if finding_type and data.get("finding_type") != finding_type:
                continue
            if severity and data.get("severity") != severity:
                continue
            if category and data.get("category") != category:
                continue
            if branch and data.get("branch") != branch:
                continue
            if tag and tag not in data.get("tags", []):
                continue
            if search:
                search_lower = search.lower()
                title = data.get("title", "").lower()
                desc = data.get("description", "").lower()
                if search_lower not in title and search_lower not in desc:
                    continue

            results.append(Finding.from_dict(data))

            if len(results) >= limit:
                break

        # Sort by created_at descending (newest first)
        results.sort(key=lambda f: f.created_at, reverse=True)

        return results

    def get_open_findings(self) -> List[Finding]:
        """Get all open findings."""
        return self.query_findings(status="open")

    def get_ready_findings(self) -> List[Finding]:
        """Get findings that are ready to work on (open, not blocked)."""
        open_findings = self.get_open_findings()
        return [f for f in open_findings if not f.blocked_by]

    def get_blocked_findings(self) -> List[Finding]:
        """Get findings that are blocked."""
        open_findings = self.get_open_findings()
        return [f for f in open_findings if f.blocked_by]

    def get_findings_by_branch(self, branch: Optional[str] = None) -> List[Finding]:
        """Get findings for current or specified branch."""
        branch = branch or self._get_current_branch()
        if not branch:
            return []
        return self.query_findings(branch=branch)

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about findings."""
        index = self._load_index()
        findings = list(index["findings"].values())

        by_status = {}
        by_severity = {}
        by_type = {}
        by_category = {}

        for f in findings:
            status = f.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1

            severity = f.get("severity", "unknown")
            by_severity[severity] = by_severity.get(severity, 0) + 1

            ftype = f.get("finding_type", "unknown")
            by_type[ftype] = by_type.get(ftype, 0) + 1

            category = f.get("category", "other")
            by_category[category] = by_category.get(category, 0) + 1

        return {
            "total": len(findings),
            "by_status": by_status,
            "by_severity": by_severity,
            "by_type": by_type,
            "by_category": by_category,
            "open": by_status.get("open", 0),
            "resolved": by_status.get("resolved", 0),
            "promoted": by_status.get("promoted", 0),
        }

    def compact(self, dry_run: bool = True) -> Dict[str, Any]:
        """
        Compact the JSONL file by removing superseded entries.

        The JSONL is append-only, so updates create duplicate entries.
        This rebuilds the file with only the latest version of each finding.

        Args:
            dry_run: If True, only report what would be compacted

        Returns:
            Statistics about the compaction
        """
        index = self._load_index()
        original_lines = 0
        final_count = len(index["findings"])

        if self.jsonl_path.exists():
            with open(self.jsonl_path) as f:
                original_lines = sum(1 for line in f if line.strip())

        stats = {
            "original_lines": original_lines,
            "unique_findings": final_count,
            "lines_removed": original_lines - final_count,
            "dry_run": dry_run
        }

        if not dry_run and original_lines > final_count:
            # Rewrite JSONL with only current versions
            with open(self.jsonl_path, "w") as f:
                for data in index["findings"].values():
                    f.write(json.dumps(data) + "\n")

        return stats

    def archive_old_findings(
        self,
        older_than: str,
        status_filter: Optional[List[str]] = None,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Archive old findings by marking them as archived.

        This is useful for "memory decay" - reducing noise from old findings
        while preserving them for historical reference.

        Args:
            older_than: Duration string like '30d', '90d', '2w'
            status_filter: Only archive findings with these statuses
                          (default: ['resolved', 'wont_fix', 'promoted'])
            dry_run: If True, only report what would be archived

        Returns:
            Statistics about the archival
        """
        try:
            duration = parse_duration(older_than)
        except ValueError as e:
            return {"error": str(e)}

        cutoff_date = datetime.now(timezone.utc) - duration

        if status_filter is None:
            # By default, only archive closed findings
            status_filter = ["resolved", "wont_fix", "promoted"]

        index = self._load_index()
        to_archive = []

        for finding_id, data in index["findings"].items():
            # Check status filter
            if data.get("status") not in status_filter:
                continue

            # Check age
            updated_at = data.get("updated_at") or data.get("created_at")
            if not updated_at:
                continue

            try:
                # Parse ISO timestamp
                ts = updated_at.replace("Z", "+00:00")
                finding_date = datetime.fromisoformat(ts)
                if finding_date < cutoff_date:
                    to_archive.append({
                        "id": finding_id,
                        "title": data.get("title", "")[:50],
                        "status": data.get("status"),
                        "updated_at": updated_at
                    })
            except (ValueError, TypeError):
                continue

        stats = {
            "older_than": older_than,
            "cutoff_date": cutoff_date.isoformat(),
            "status_filter": status_filter,
            "findings_to_archive": len(to_archive),
            "archived_findings": to_archive[:20],  # Show first 20
            "dry_run": dry_run
        }

        if not dry_run and to_archive:
            # Add "archived" tag to each finding
            for item in to_archive:
                finding = self.get_finding(item["id"])
                if finding:
                    tags = finding.tags.copy()
                    if "archived" not in tags:
                        tags.append("archived")
                    self.update_finding(item["id"], tags=tags)

            stats["archived_count"] = len(to_archive)

        return stats

    def summarize_old_findings(
        self,
        older_than: str,
        dry_run: bool = True
    ) -> Dict[str, Any]:
        """
        Generate a summary of old findings for memory decay.

        Instead of deleting old findings, this creates a summary note
        that captures the key patterns and themes.

        Args:
            older_than: Duration string like '90d', '6m'
            dry_run: If True, only report what would be summarized

        Returns:
            Summary statistics and generated summary
        """
        try:
            duration = parse_duration(older_than)
        except ValueError as e:
            return {"error": str(e)}

        cutoff_date = datetime.now(timezone.utc) - duration
        index = self._load_index()

        old_findings = []
        for finding_id, data in index["findings"].items():
            created_at = data.get("created_at")
            if not created_at:
                continue

            try:
                ts = created_at.replace("Z", "+00:00")
                finding_date = datetime.fromisoformat(ts)
                if finding_date < cutoff_date:
                    old_findings.append(data)
            except (ValueError, TypeError):
                continue

        # Generate summary
        by_category = {}
        by_severity = {}
        by_status = {}

        for f in old_findings:
            cat = f.get("category", "other")
            by_category[cat] = by_category.get(cat, 0) + 1

            sev = f.get("severity", "medium")
            by_severity[sev] = by_severity.get(sev, 0) + 1

            status = f.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1

        summary = {
            "period": f"Before {cutoff_date.strftime('%Y-%m-%d')}",
            "total_findings": len(old_findings),
            "by_category": by_category,
            "by_severity": by_severity,
            "by_status": by_status,
            "top_categories": sorted(
                by_category.items(), key=lambda x: x[1], reverse=True
            )[:5]
        }

        stats = {
            "older_than": older_than,
            "cutoff_date": cutoff_date.isoformat(),
            "findings_count": len(old_findings),
            "summary": summary,
            "dry_run": dry_run
        }

        if not dry_run and old_findings:
            # Create a summary finding
            summary_text = f"""Historical summary of {len(old_findings)} findings from before {cutoff_date.strftime('%Y-%m-%d')}.

By Category: {', '.join(f'{k}: {v}' for k, v in sorted(by_category.items(), key=lambda x: x[1], reverse=True)[:5])}

By Severity: {', '.join(f'{k}: {v}' for k, v in by_severity.items())}

By Status: {', '.join(f'{k}: {v}' for k, v in by_status.items())}
"""
            summary_id = self.create_finding(
                title=f"Historical summary: {len(old_findings)} findings before {cutoff_date.strftime('%Y-%m-%d')}",
                finding_type="note",
                severity="info",
                category="other",
                description=summary_text,
                tags=["summary", "historical", "auto-generated"]
            )
            stats["summary_finding_id"] = summary_id

        return stats

    # ==================== SQLite Cache Methods ====================

    def _init_sqlite_cache(self) -> None:
        """Initialize SQLite cache database."""
        self._sqlite_conn = sqlite3.connect(str(self.sqlite_path))
        self._sqlite_conn.row_factory = sqlite3.Row

        # Create tables
        self._sqlite_conn.executescript("""
            CREATE TABLE IF NOT EXISTS findings (
                id TEXT PRIMARY KEY,
                version INTEGER,
                title TEXT,
                finding_type TEXT,
                category TEXT,
                severity TEXT,
                status TEXT,
                description TEXT,
                file_path TEXT,
                line_number INTEGER,
                branch TEXT,
                ado_work_item TEXT,
                eval_result TEXT,
                priority INTEGER,
                confidence REAL,
                created_at TEXT,
                updated_at TEXT,
                data_json TEXT
            );

            CREATE INDEX IF NOT EXISTS idx_status ON findings(status);
            CREATE INDEX IF NOT EXISTS idx_severity ON findings(severity);
            CREATE INDEX IF NOT EXISTS idx_category ON findings(category);
            CREATE INDEX IF NOT EXISTS idx_branch ON findings(branch);
            CREATE INDEX IF NOT EXISTS idx_created_at ON findings(created_at);
        """)
        self._sqlite_conn.commit()

        # Sync from JSONL if needed
        self._sync_sqlite_from_jsonl()

    def _sync_sqlite_from_jsonl(self) -> None:
        """Sync SQLite cache from JSONL source of truth."""
        if not self._sqlite_conn:
            return

        index = self._load_index()

        # Clear and rebuild
        self._sqlite_conn.execute("DELETE FROM findings")

        for finding_id, data in index["findings"].items():
            evidence = data.get("evidence", {})
            self._sqlite_conn.execute("""
                INSERT OR REPLACE INTO findings
                (id, version, title, finding_type, category, severity, status,
                 description, file_path, line_number, branch, ado_work_item,
                 eval_result, priority, confidence, created_at, updated_at, data_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                finding_id,
                data.get("version", 1),
                data.get("title", ""),
                data.get("finding_type", "discovery"),
                data.get("category", "other"),
                data.get("severity", "medium"),
                data.get("status", "open"),
                data.get("description", ""),
                evidence.get("file") if evidence else None,
                evidence.get("line") if evidence else None,
                data.get("branch"),
                data.get("ado_work_item"),
                data.get("eval_result"),
                data.get("priority", 3),
                data.get("confidence", 0.8),
                data.get("created_at"),
                data.get("updated_at"),
                json.dumps(data)
            ))

        self._sqlite_conn.commit()

    def _update_sqlite_cache(self, finding: Finding) -> None:
        """Update a single finding in SQLite cache."""
        if not self._sqlite_conn:
            return

        data = finding.to_dict()
        evidence = data.get("evidence", {})

        self._sqlite_conn.execute("""
            INSERT OR REPLACE INTO findings
            (id, version, title, finding_type, category, severity, status,
             description, file_path, line_number, branch, ado_work_item,
             eval_result, priority, confidence, created_at, updated_at, data_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            finding.id,
            finding.version,
            finding.title,
            finding.finding_type,
            finding.category,
            finding.severity,
            finding.status,
            finding.description,
            evidence.get("file") if evidence else None,
            evidence.get("line") if evidence else None,
            finding.branch,
            finding.ado_work_item,
            finding.eval_result,
            finding.priority,
            finding.confidence,
            finding.created_at,
            finding.updated_at,
            json.dumps(data)
        ))
        self._sqlite_conn.commit()

    def query_findings_sql(
        self,
        status: Optional[str] = None,
        finding_type: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        branch: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100,
    ) -> List[Finding]:
        """
        Query findings using SQLite for faster performance.

        Falls back to regular query if SQLite not enabled.
        """
        if not self._sqlite_conn:
            return self.query_findings(
                status=status, finding_type=finding_type, severity=severity,
                category=category, branch=branch, search=search, limit=limit
            )

        query = "SELECT data_json FROM findings WHERE 1=1"
        params: List[Any] = []

        if status:
            query += " AND status = ?"
            params.append(status)
        if finding_type:
            query += " AND finding_type = ?"
            params.append(finding_type)
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if category:
            query += " AND category = ?"
            params.append(category)
        if branch:
            query += " AND branch = ?"
            params.append(branch)
        if search:
            query += " AND (title LIKE ? OR description LIKE ?)"
            search_pattern = f"%{search}%"
            params.extend([search_pattern, search_pattern])

        query += " ORDER BY created_at DESC LIMIT ?"
        params.append(limit)

        cursor = self._sqlite_conn.execute(query, params)
        results = []
        for row in cursor:
            data = json.loads(row["data_json"])
            results.append(Finding.from_dict(data))

        return results

    def rebuild_sqlite_cache(self) -> Dict[str, Any]:
        """Rebuild SQLite cache from JSONL."""
        if not self.use_sqlite_cache:
            self.use_sqlite_cache = True
            self._init_sqlite_cache()
        else:
            self._sync_sqlite_from_jsonl()

        count = self._sqlite_conn.execute(
            "SELECT COUNT(*) FROM findings"
        ).fetchone()[0]

        return {
            "rebuilt": True,
            "findings_count": count,
            "sqlite_path": str(self.sqlite_path)
        }


if __name__ == "__main__":
    # Quick test
    store = FindingsStore()
    print(f"Findings directory: {store.findings_dir}")
    print(f"Statistics: {store.get_statistics()}")

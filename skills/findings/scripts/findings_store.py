"""
Findings Store - JSONL-based persistent storage for Claude Code findings.

Inspired by beads (https://github.com/steveyegge/beads), this module provides
git-tracked persistent memory for AI coding agents.

Architecture:
- Source of truth: .findings/findings.jsonl (git-tracked, append-friendly)
- Fast queries: .findings/index.json (git-ignored, rebuilt from JSONL)
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
"""

import hashlib
import json
import os
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any


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


class FindingsStore:
    """
    Git-tracked persistent storage for findings.

    Storage layout:
        .findings/
        ├── findings.jsonl      # Git-tracked, append-only log
        ├── index.json          # Git-ignored, fast lookup cache
        └── session-context.json # Git-ignored, current session state
    """

    def __init__(self, root_dir: Optional[Path] = None):
        """
        Initialize the findings store.

        Args:
            root_dir: Project root directory. If None, searches up for .git
        """
        self.root_dir = root_dir or self._find_project_root()
        self.findings_dir = self.root_dir / ".findings"
        self.jsonl_path = self.findings_dir / "findings.jsonl"
        self.index_path = self.findings_dir / "index.json"
        self.context_path = self.findings_dir / "session-context.json"

        self._ensure_initialized()

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
        index = {"findings": {}, "last_rebuild": datetime.now(timezone.utc).isoformat()}

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
        now = datetime.now(timezone.utc).isoformat() + "Z"
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
        finding.updated_at = datetime.now(timezone.utc).isoformat() + "Z"

        # Append updated version to JSONL
        self._append_to_jsonl(finding)

        # Update index
        index = self._load_index()
        index["findings"][finding_id] = finding.to_dict()
        self._save_index(index)

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
            resolved_at=datetime.now(timezone.utc).isoformat() + "Z"
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


if __name__ == "__main__":
    # Quick test
    store = FindingsStore()
    print(f"Findings directory: {store.findings_dir}")
    print(f"Statistics: {store.get_statistics()}")

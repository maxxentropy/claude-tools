"""
Global Findings Store - Centralized storage for cross-repo findings.

This module provides a global aggregation layer that collects findings from
multiple repositories, enabling cross-repo pattern discovery and search.

Architecture:
    ~/.claude/findings/
    ├── global-findings.jsonl   # All synced findings (NOT git-tracked)
    ├── index.json              # Fast lookup cache
    ├── repositories.json       # Known repos registry
    └── config.yaml             # Sync settings, privacy

The global store is a PERSONAL aggregation layer - it's not git-tracked
and serves to help you find patterns across your projects. The per-repo
.findings/ directories remain the source of truth for team collaboration.

Usage:
    from global_store import GlobalStore

    store = GlobalStore()

    # Sync a local finding to global
    store.sync_finding(finding, source_repo="my-project", source_path="/path/to/repo")

    # Search across all repos
    results = store.search("N+1 query")

    # List all repos with findings
    repos = store.list_repositories()
"""

import hashlib
import json
import os
import re
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any


# Global findings directory
GLOBAL_FINDINGS_DIR = Path.home() / ".claude" / "findings"


@dataclass
class RepoInfo:
    """Information about a tracked repository."""
    name: str                          # Short name (e.g., "claude-tools")
    path: str                          # Absolute path
    remote_url: Optional[str] = None   # Git remote URL if available
    last_synced: Optional[str] = None  # Last sync timestamp
    finding_count: int = 0             # Number of findings from this repo
    registered_at: str = ""            # When first registered

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RepoInfo":
        return cls(**data)


@dataclass
class GlobalFinding:
    """
    A finding in the global store with source tracking.

    Extends the local Finding with fields to track origin.
    """
    # Core identity (from local finding)
    id: str                            # Original local ID
    global_id: str                     # Global unique ID (hash of content + repo)

    # Source tracking
    source_repo: str                   # Repository name
    source_repo_path: str              # Full path to source repo
    source_branch: Optional[str] = None

    # Original finding data (flattened for search)
    title: str = ""
    description: str = ""
    finding_type: str = "discovery"
    category: str = "other"
    severity: str = "medium"
    status: str = "open"

    # Evidence (flattened)
    file_path: Optional[str] = None
    line_number: Optional[int] = None
    function_name: Optional[str] = None

    # Metadata
    tags: List[str] = field(default_factory=list)
    priority: int = 3
    confidence: float = 0.8

    # Relationships
    ado_work_item: Optional[str] = None
    eval_result: Optional[str] = None
    related_global_ids: List[str] = field(default_factory=list)

    # Visibility
    visibility: str = "global"  # global, private

    # Timestamps
    discovered_at: str = ""
    synced_at: str = ""
    updated_at: str = ""

    # Store full original data for reference
    original_data: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "GlobalFinding":
        # Handle missing fields gracefully
        fields = {
            'id', 'global_id', 'source_repo', 'source_repo_path', 'source_branch',
            'title', 'description', 'finding_type', 'category', 'severity', 'status',
            'file_path', 'line_number', 'function_name', 'tags', 'priority',
            'confidence', 'ado_work_item', 'eval_result', 'related_global_ids',
            'visibility', 'discovered_at', 'synced_at', 'updated_at', 'original_data'
        }
        filtered = {k: v for k, v in data.items() if k in fields}
        return cls(**filtered)

    @classmethod
    def from_local_finding(
        cls,
        finding_data: Dict[str, Any],
        source_repo: str,
        source_repo_path: str
    ) -> "GlobalFinding":
        """Create a GlobalFinding from a local finding dict."""
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        # Generate global ID from content + repo
        content = f"{source_repo}:{finding_data.get('id', '')}:{finding_data.get('title', '')}"
        global_id = f"g-{hashlib.sha256(content.encode()).hexdigest()[:12]}"

        # Extract evidence fields
        evidence = finding_data.get("evidence", {}) or {}

        return cls(
            id=finding_data.get("id", ""),
            global_id=global_id,
            source_repo=source_repo,
            source_repo_path=source_repo_path,
            source_branch=finding_data.get("branch"),
            title=finding_data.get("title", ""),
            description=finding_data.get("description", ""),
            finding_type=finding_data.get("finding_type", "discovery"),
            category=finding_data.get("category", "other"),
            severity=finding_data.get("severity", "medium"),
            status=finding_data.get("status", "open"),
            file_path=evidence.get("file"),
            line_number=evidence.get("line"),
            function_name=evidence.get("function"),
            tags=finding_data.get("tags", []),
            priority=finding_data.get("priority", 3),
            confidence=finding_data.get("confidence", 0.8),
            ado_work_item=finding_data.get("ado_work_item"),
            eval_result=finding_data.get("eval_result"),
            visibility="global",
            discovered_at=finding_data.get("discovered_at", now),
            synced_at=now,
            updated_at=now,
            original_data=finding_data,
        )


class GlobalStore:
    """
    Global findings store for cross-repo aggregation.

    This is a personal aggregation layer - findings synced here can be
    searched across all your projects.
    """

    def __init__(self):
        self.base_dir = GLOBAL_FINDINGS_DIR
        self.jsonl_path = self.base_dir / "global-findings.jsonl"
        self.index_path = self.base_dir / "index.json"
        self.repos_path = self.base_dir / "repositories.json"
        self.config_path = self.base_dir / "config.json"

        self._ensure_initialized()
        self._config = self._load_config()

    def _ensure_initialized(self) -> None:
        """Ensure global findings directory exists."""
        if not self.base_dir.exists():
            self.base_dir.mkdir(parents=True)

        if not self.jsonl_path.exists():
            self.jsonl_path.touch()

        if not self.repos_path.exists():
            self._save_repos({})

        if not self.index_path.exists():
            self._save_index({"findings": {}, "by_repo": {}, "last_rebuild": None})

    def _load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON."""
        default_config = {
            "sync": {"auto_push": True, "interval_hours": 4},
            "privacy": {"default_visibility": "global", "exclude_tags": ["private"]},
            "similarity": {"threshold": 0.8},
            "repositories": {"max_tracked": 50, "auto_register": True}
        }

        if not self.config_path.exists():
            return default_config

        try:
            with open(self.config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return default_config

    def _load_index(self) -> Dict[str, Any]:
        """Load the global index."""
        if not self.index_path.exists():
            return self._rebuild_index()

        try:
            with open(self.index_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            return self._rebuild_index()

    def _save_index(self, index: Dict[str, Any]) -> None:
        """Save the global index."""
        with open(self.index_path, "w") as f:
            json.dump(index, f, indent=2)

    def _rebuild_index(self) -> Dict[str, Any]:
        """Rebuild index from JSONL file."""
        index = {
            "findings": {},
            "by_repo": {},
            "last_rebuild": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        }

        if self.jsonl_path.exists():
            with open(self.jsonl_path) as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        data = json.loads(line)
                        global_id = data.get("global_id")
                        if global_id:
                            index["findings"][global_id] = data

                            # Index by repo
                            repo = data.get("source_repo", "unknown")
                            if repo not in index["by_repo"]:
                                index["by_repo"][repo] = []
                            if global_id not in index["by_repo"][repo]:
                                index["by_repo"][repo].append(global_id)
                    except json.JSONDecodeError:
                        continue

        self._save_index(index)
        return index

    def _load_repos(self) -> Dict[str, RepoInfo]:
        """Load repository registry."""
        if not self.repos_path.exists():
            return {}

        try:
            with open(self.repos_path) as f:
                data = json.load(f)
                return {k: RepoInfo.from_dict(v) for k, v in data.items()}
        except (json.JSONDecodeError, IOError):
            return {}

    def _save_repos(self, repos: Dict[str, RepoInfo]) -> None:
        """Save repository registry."""
        data = {k: v.to_dict() for k, v in repos.items()}
        with open(self.repos_path, "w") as f:
            json.dump(data, f, indent=2)

    def _append_to_jsonl(self, finding: GlobalFinding) -> None:
        """Append finding to JSONL file."""
        with open(self.jsonl_path, "a") as f:
            f.write(json.dumps(finding.to_dict()) + "\n")

    # ==================== Repository Management ====================

    def register_repository(
        self,
        name: str,
        path: str,
        remote_url: Optional[str] = None
    ) -> RepoInfo:
        """Register a repository in the global store."""
        repos = self._load_repos()
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        if name in repos:
            # Update existing
            repos[name].path = path
            if remote_url:
                repos[name].remote_url = remote_url
        else:
            # Create new
            repos[name] = RepoInfo(
                name=name,
                path=path,
                remote_url=remote_url,
                registered_at=now
            )

        self._save_repos(repos)
        return repos[name]

    def get_repository(self, name: str) -> Optional[RepoInfo]:
        """Get repository info by name."""
        repos = self._load_repos()
        return repos.get(name)

    def list_repositories(self) -> List[RepoInfo]:
        """List all registered repositories."""
        repos = self._load_repos()
        return list(repos.values())

    def unregister_repository(self, name: str) -> bool:
        """Remove a repository from the registry."""
        repos = self._load_repos()
        if name in repos:
            del repos[name]
            self._save_repos(repos)
            return True
        return False

    # ==================== Finding Operations ====================

    def sync_finding(
        self,
        finding_data: Dict[str, Any],
        source_repo: str,
        source_repo_path: str
    ) -> str:
        """
        Sync a local finding to the global store.

        Returns the global_id.
        """
        # Check privacy settings
        exclude_tags = self._config.get("privacy", {}).get("exclude_tags", [])
        finding_tags = finding_data.get("tags", [])
        if any(tag in exclude_tags for tag in finding_tags):
            # Don't sync private findings
            return ""

        # Create global finding
        global_finding = GlobalFinding.from_local_finding(
            finding_data, source_repo, source_repo_path
        )

        # Check if already exists (upsert)
        index = self._load_index()
        existing = None
        for gid, gdata in index["findings"].items():
            if (gdata.get("source_repo") == source_repo and
                gdata.get("id") == finding_data.get("id")):
                existing = gid
                break

        if existing:
            # Update existing - use same global_id
            global_finding.global_id = existing

        # Append to JSONL
        self._append_to_jsonl(global_finding)

        # Update index
        index["findings"][global_finding.global_id] = global_finding.to_dict()
        if source_repo not in index["by_repo"]:
            index["by_repo"][source_repo] = []
        if global_finding.global_id not in index["by_repo"][source_repo]:
            index["by_repo"][source_repo].append(global_finding.global_id)
        self._save_index(index)

        # Auto-register repo if configured
        if self._config.get("repositories", {}).get("auto_register", True):
            self.register_repository(source_repo, source_repo_path)

        # Update repo stats
        repos = self._load_repos()
        if source_repo in repos:
            repos[source_repo].last_synced = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            repos[source_repo].finding_count = len(index["by_repo"].get(source_repo, []))
            self._save_repos(repos)

        return global_finding.global_id

    def get_finding(self, global_id: str) -> Optional[GlobalFinding]:
        """Get a global finding by ID."""
        index = self._load_index()
        data = index["findings"].get(global_id)
        return GlobalFinding.from_dict(data) if data else None

    def get_finding_by_local_id(self, local_id: str, source_repo: str) -> Optional[GlobalFinding]:
        """Get a global finding by its local ID and repo."""
        index = self._load_index()
        for gid, data in index["findings"].items():
            if data.get("id") == local_id and data.get("source_repo") == source_repo:
                return GlobalFinding.from_dict(data)
        return None

    def query_findings(
        self,
        source_repo: Optional[str] = None,
        status: Optional[str] = None,
        severity: Optional[str] = None,
        category: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 100
    ) -> List[GlobalFinding]:
        """Query global findings with filters."""
        index = self._load_index()
        results = []

        for data in index["findings"].values():
            # Apply filters
            if source_repo and data.get("source_repo") != source_repo:
                continue
            if status and data.get("status") != status:
                continue
            if severity and data.get("severity") != severity:
                continue
            if category and data.get("category") != category:
                continue
            if search:
                search_lower = search.lower()
                title = data.get("title", "").lower()
                desc = data.get("description", "").lower()
                tags = " ".join(data.get("tags", [])).lower()
                if (search_lower not in title and
                    search_lower not in desc and
                    search_lower not in tags):
                    continue

            results.append(GlobalFinding.from_dict(data))

            if len(results) >= limit:
                break

        # Sort by synced_at descending
        results.sort(key=lambda f: f.synced_at, reverse=True)
        return results

    def get_findings_by_repo(self, source_repo: str) -> List[GlobalFinding]:
        """Get all findings from a specific repo."""
        return self.query_findings(source_repo=source_repo)

    def search(self, query: str, limit: int = 50) -> List[GlobalFinding]:
        """Search across all global findings."""
        return self.query_findings(search=query, limit=limit)

    # ==================== Statistics ====================

    def get_statistics(self) -> Dict[str, Any]:
        """Get statistics about global findings."""
        index = self._load_index()
        findings = list(index["findings"].values())

        by_repo = {}
        by_severity = {}
        by_category = {}
        by_status = {}

        for f in findings:
            repo = f.get("source_repo", "unknown")
            by_repo[repo] = by_repo.get(repo, 0) + 1

            severity = f.get("severity", "unknown")
            by_severity[severity] = by_severity.get(severity, 0) + 1

            category = f.get("category", "other")
            by_category[category] = by_category.get(category, 0) + 1

            status = f.get("status", "unknown")
            by_status[status] = by_status.get(status, 0) + 1

        return {
            "total": len(findings),
            "repositories": len(by_repo),
            "by_repo": by_repo,
            "by_severity": by_severity,
            "by_category": by_category,
            "by_status": by_status,
            "open": by_status.get("open", 0),
        }

    # ==================== Similarity Detection ====================

    def find_similar(
        self,
        title: str,
        description: str = "",
        threshold: float = 0.0
    ) -> List[tuple[GlobalFinding, float]]:
        """
        Find similar findings across all repos.

        Returns list of (finding, similarity_score) tuples.
        """
        if threshold == 0.0:
            threshold = self._config.get("similarity", {}).get("threshold", 0.8)

        index = self._load_index()
        results = []

        # Simple word-based similarity
        query_words = set(self._tokenize(title + " " + description))

        for data in index["findings"].values():
            target_words = set(self._tokenize(
                data.get("title", "") + " " + data.get("description", "")
            ))

            if not query_words or not target_words:
                continue

            # Jaccard similarity
            intersection = len(query_words & target_words)
            union = len(query_words | target_words)
            similarity = intersection / union if union > 0 else 0

            if similarity >= threshold:
                results.append((GlobalFinding.from_dict(data), similarity))

        # Sort by similarity descending
        results.sort(key=lambda x: x[1], reverse=True)
        return results

    def _tokenize(self, text: str) -> List[str]:
        """Simple tokenization for similarity matching."""
        # Lowercase, split on non-alphanumeric, filter short words
        words = re.split(r'[^a-zA-Z0-9]+', text.lower())
        return [w for w in words if len(w) > 2]

    # ==================== Compact / Maintenance ====================

    def compact(self, dry_run: bool = True) -> Dict[str, Any]:
        """Compact the JSONL file by removing superseded entries."""
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


def get_repo_name_from_path(path: Path) -> str:
    """Extract repository name from path."""
    # Try to get from git remote
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, cwd=path
        )
        if result.returncode == 0:
            url = result.stdout.strip()
            # Extract repo name from URL
            match = re.search(r'/([^/]+?)(?:\.git)?$', url)
            if match:
                return match.group(1)
    except Exception:
        pass

    # Fall back to directory name
    return path.name


if __name__ == "__main__":
    # Quick test
    store = GlobalStore()
    print(f"Global findings dir: {store.base_dir}")
    print(f"Repositories: {len(store.list_repositories())}")
    print(f"Statistics: {store.get_statistics()}")

#!/usr/bin/env python3
"""
Work Item Index Manager

Local caching layer for Azure DevOps work items to enable:
- Fast lookups without API calls
- Branch-to-work-item mapping
- Context-aware work item suggestions
- Commit tracking per work item

Index Location: .ado/work-items.json
Branch Mappings: .ado/branch-mappings.json
"""

import json
import os
import re
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, field, asdict
from enum import Enum


class IndexStaleness(Enum):
    """How stale is the index?"""
    FRESH = "fresh"           # < 1 hour
    RECENT = "recent"         # 1-24 hours
    STALE = "stale"           # 1-7 days
    VERY_STALE = "very_stale" # > 7 days
    NEVER_SYNCED = "never"    # No sync ever


@dataclass
class WorkItem:
    """A cached work item."""
    id: int
    type: str  # Bug, User Story, Task, Feature, Epic
    title: str
    state: str
    assigned_to: Optional[str] = None
    tags: List[str] = field(default_factory=list)
    priority: Optional[int] = None
    parent_id: Optional[int] = None
    iteration_path: Optional[str] = None
    area_path: Optional[str] = None
    url: Optional[str] = None
    created_date: Optional[str] = None
    changed_date: Optional[str] = None

    # Local tracking (not from ADO)
    local_branch: Optional[str] = None
    local_commits: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkItem':
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def from_ado_response(cls, item: Dict[str, Any], org: str, project: str) -> 'WorkItem':
        """Create WorkItem from Azure DevOps API response."""
        fields = item.get('fields', {})

        # Handle assigned to - can be dict or string
        assigned_to = fields.get('System.AssignedTo')
        if isinstance(assigned_to, dict):
            assigned_to = assigned_to.get('uniqueName') or assigned_to.get('displayName')

        # Parse tags
        tags_str = fields.get('System.Tags', '')
        tags = [t.strip() for t in tags_str.split(';') if t.strip()] if tags_str else []

        return cls(
            id=item['id'],
            type=fields.get('System.WorkItemType', 'Unknown'),
            title=fields.get('System.Title', ''),
            state=fields.get('System.State', 'Unknown'),
            assigned_to=assigned_to,
            tags=tags,
            priority=fields.get('Microsoft.VSTS.Common.Priority'),
            parent_id=fields.get('System.Parent'),
            iteration_path=fields.get('System.IterationPath'),
            area_path=fields.get('System.AreaPath'),
            url=f"https://dev.azure.com/{org}/{project}/_workitems/edit/{item['id']}",
            created_date=fields.get('System.CreatedDate'),
            changed_date=fields.get('System.ChangedDate'),
        )


@dataclass
class BranchMapping:
    """Maps a git branch to a work item."""
    branch_name: str
    work_item_id: int
    linked_at: str
    commits: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'BranchMapping':
        return cls(**data)


@dataclass
class WorkItemIndex:
    """The main index structure."""
    last_sync: Optional[str] = None
    synced_by: Optional[str] = None
    organization: Optional[str] = None
    project: Optional[str] = None
    items: List[WorkItem] = field(default_factory=list)
    branch_mappings: Dict[str, BranchMapping] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            'lastSync': self.last_sync,
            'syncedBy': self.synced_by,
            'organization': self.organization,
            'project': self.project,
            'items': [item.to_dict() for item in self.items],
            'branchMappings': {k: v.to_dict() for k, v in self.branch_mappings.items()}
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'WorkItemIndex':
        items = [WorkItem.from_dict(item) for item in data.get('items', [])]
        branch_mappings = {
            k: BranchMapping.from_dict(v)
            for k, v in data.get('branchMappings', {}).items()
        }
        return cls(
            last_sync=data.get('lastSync'),
            synced_by=data.get('syncedBy'),
            organization=data.get('organization'),
            project=data.get('project'),
            items=items,
            branch_mappings=branch_mappings
        )


class WorkItemIndexManager:
    """Manages the local work item index."""

    DEFAULT_INDEX_PATH = ".ado/work-items.json"

    def __init__(self, repo_root: Optional[Path] = None):
        """
        Initialize the index manager.

        Args:
            repo_root: Root of the git repository. If None, searches upward from cwd.
        """
        self.repo_root = repo_root or self._find_repo_root()
        self.index_path = self.repo_root / self.DEFAULT_INDEX_PATH
        self._index: Optional[WorkItemIndex] = None

    def _find_repo_root(self) -> Path:
        """Find the git repository root."""
        current = Path.cwd()
        while current != current.parent:
            if (current / '.git').exists():
                return current
            current = current.parent
        return Path.cwd()  # Fallback to cwd

    def _ensure_ado_dir(self) -> None:
        """Ensure .ado directory exists."""
        ado_dir = self.repo_root / '.ado'
        ado_dir.mkdir(parents=True, exist_ok=True)

        # Add to .gitignore if not already there
        gitignore = self.repo_root / '.gitignore'
        if gitignore.exists():
            content = gitignore.read_text()
            if '.ado/work-items.json' not in content:
                with open(gitignore, 'a') as f:
                    f.write('\n# Azure DevOps work item cache\n.ado/work-items.json\n')

    def load(self) -> WorkItemIndex:
        """Load the index from disk."""
        if self._index is not None:
            return self._index

        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text())
                self._index = WorkItemIndex.from_dict(data)
            except (json.JSONDecodeError, KeyError) as e:
                print(f"Warning: Could not parse index, creating new: {e}")
                self._index = WorkItemIndex()
        else:
            self._index = WorkItemIndex()

        return self._index

    def save(self) -> None:
        """Save the index to disk."""
        if self._index is None:
            return

        self._ensure_ado_dir()
        self.index_path.write_text(
            json.dumps(self._index.to_dict(), indent=2, default=str)
        )

    def get_staleness(self) -> IndexStaleness:
        """Check how stale the index is."""
        index = self.load()

        if not index.last_sync:
            return IndexStaleness.NEVER_SYNCED

        try:
            last_sync = datetime.fromisoformat(index.last_sync.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age = now - last_sync

            if age < timedelta(hours=1):
                return IndexStaleness.FRESH
            elif age < timedelta(hours=24):
                return IndexStaleness.RECENT
            elif age < timedelta(days=7):
                return IndexStaleness.STALE
            else:
                return IndexStaleness.VERY_STALE
        except ValueError:
            return IndexStaleness.NEVER_SYNCED

    def get_staleness_message(self) -> str:
        """Get a human-readable staleness message."""
        index = self.load()
        staleness = self.get_staleness()

        if staleness == IndexStaleness.NEVER_SYNCED:
            return "Index never synced. Run sync to populate."

        try:
            last_sync = datetime.fromisoformat(index.last_sync.replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            age = now - last_sync

            if age < timedelta(minutes=1):
                age_str = "just now"
            elif age < timedelta(hours=1):
                age_str = f"{int(age.total_seconds() / 60)} minutes ago"
            elif age < timedelta(hours=24):
                age_str = f"{int(age.total_seconds() / 3600)} hours ago"
            else:
                age_str = f"{age.days} days ago"

            messages = {
                IndexStaleness.FRESH: f"Index synced {age_str}",
                IndexStaleness.RECENT: f"Index synced {age_str}",
                IndexStaleness.STALE: f"⚠️ Index synced {age_str} - consider refreshing",
                IndexStaleness.VERY_STALE: f"⚠️ Index very stale ({age_str}) - run sync",
            }
            return messages.get(staleness, f"Synced {age_str}")
        except ValueError:
            return "Unknown sync status"

    # -------------------------------------------------------------------------
    # Work Item Operations
    # -------------------------------------------------------------------------

    def get_item(self, item_id: int) -> Optional[WorkItem]:
        """Get a work item by ID from the index."""
        index = self.load()
        for item in index.items:
            if item.id == item_id:
                return item
        return None

    def get_items_by_state(self, states: List[str]) -> List[WorkItem]:
        """Get work items in specific states."""
        index = self.load()
        states_lower = [s.lower() for s in states]
        return [item for item in index.items if item.state.lower() in states_lower]

    def get_active_items(self) -> List[WorkItem]:
        """Get all active/in-progress work items."""
        return self.get_items_by_state(['Active', 'In Progress', 'New', 'Committed'])

    def get_items_by_type(self, item_type: str) -> List[WorkItem]:
        """Get work items of a specific type."""
        index = self.load()
        return [item for item in index.items if item.type.lower() == item_type.lower()]

    def search_items(self, query: str, limit: int = 10) -> List[WorkItem]:
        """
        Search work items by title, tags, or ID.

        Supports:
        - Text search in title
        - Tag matching (#tag or tag:value)
        - ID lookup (AB#123 or #123 or just 123)
        """
        index = self.load()
        query_lower = query.lower().strip()

        # Check for ID pattern
        id_match = re.search(r'(?:AB)?#?(\d+)', query, re.IGNORECASE)
        if id_match:
            item_id = int(id_match.group(1))
            item = self.get_item(item_id)
            if item:
                return [item]

        # Score-based search
        scored_items: List[tuple[float, WorkItem]] = []

        for item in index.items:
            score = 0.0

            # Title match
            title_lower = item.title.lower()
            if query_lower in title_lower:
                score += 10.0
                # Bonus for word boundary match
                if re.search(rf'\b{re.escape(query_lower)}\b', title_lower):
                    score += 5.0

            # Tag match
            for tag in item.tags:
                if query_lower in tag.lower():
                    score += 3.0

            # Type match
            if query_lower in item.type.lower():
                score += 2.0

            # State match
            if query_lower in item.state.lower():
                score += 1.0

            if score > 0:
                scored_items.append((score, item))

        # Sort by score descending
        scored_items.sort(key=lambda x: x[0], reverse=True)

        return [item for _, item in scored_items[:limit]]

    def upsert_item(self, item: WorkItem) -> None:
        """Add or update a work item in the index."""
        index = self.load()

        # Find and replace or append
        for i, existing in enumerate(index.items):
            if existing.id == item.id:
                # Preserve local tracking data
                item.local_branch = existing.local_branch or item.local_branch
                item.local_commits = list(set(existing.local_commits + item.local_commits))
                index.items[i] = item
                return

        index.items.append(item)

    def upsert_items(self, items: List[WorkItem]) -> None:
        """Add or update multiple work items."""
        for item in items:
            self.upsert_item(item)

    def remove_item(self, item_id: int) -> bool:
        """Remove a work item from the index."""
        index = self.load()
        original_len = len(index.items)
        index.items = [item for item in index.items if item.id != item_id]
        return len(index.items) < original_len

    def clear_items(self) -> None:
        """Clear all items from the index."""
        index = self.load()
        index.items = []

    # -------------------------------------------------------------------------
    # Branch Mapping Operations
    # -------------------------------------------------------------------------

    def link_branch(self, branch_name: str, work_item_id: int) -> None:
        """Link a branch to a work item."""
        index = self.load()

        mapping = BranchMapping(
            branch_name=branch_name,
            work_item_id=work_item_id,
            linked_at=datetime.now(timezone.utc).isoformat(),
            commits=[]
        )

        index.branch_mappings[branch_name] = mapping

        # Update work item's local branch reference
        item = self.get_item(work_item_id)
        if item:
            item.local_branch = branch_name

    def unlink_branch(self, branch_name: str) -> bool:
        """Unlink a branch from its work item."""
        index = self.load()
        if branch_name in index.branch_mappings:
            del index.branch_mappings[branch_name]
            return True
        return False

    def get_branch_mapping(self, branch_name: str) -> Optional[BranchMapping]:
        """Get the mapping for a branch."""
        index = self.load()
        return index.branch_mappings.get(branch_name)

    def get_work_item_for_branch(self, branch_name: str) -> Optional[WorkItem]:
        """Get the work item linked to a branch."""
        mapping = self.get_branch_mapping(branch_name)
        if mapping:
            return self.get_item(mapping.work_item_id)
        return None

    def add_commit_to_branch(self, branch_name: str, commit_sha: str) -> None:
        """Record a commit against a branch's linked work item."""
        index = self.load()
        mapping = index.branch_mappings.get(branch_name)

        if mapping and commit_sha not in mapping.commits:
            mapping.commits.append(commit_sha)

            # Also update the work item
            item = self.get_item(mapping.work_item_id)
            if item and commit_sha not in item.local_commits:
                item.local_commits.append(commit_sha)

    # -------------------------------------------------------------------------
    # Sync Operations
    # -------------------------------------------------------------------------

    def mark_synced(self, synced_by: str, organization: str, project: str) -> None:
        """Mark the index as synced."""
        index = self.load()
        index.last_sync = datetime.now(timezone.utc).isoformat()
        index.synced_by = synced_by
        index.organization = organization
        index.project = project

    def get_sync_info(self) -> Dict[str, Any]:
        """Get information about the last sync."""
        index = self.load()
        return {
            'lastSync': index.last_sync,
            'syncedBy': index.synced_by,
            'organization': index.organization,
            'project': index.project,
            'itemCount': len(index.items),
            'branchMappings': len(index.branch_mappings),
            'staleness': self.get_staleness().value,
            'stalenessMessage': self.get_staleness_message()
        }

    # -------------------------------------------------------------------------
    # Summary and Display
    # -------------------------------------------------------------------------

    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the index."""
        index = self.load()

        # Count by type
        by_type: Dict[str, int] = {}
        for item in index.items:
            by_type[item.type] = by_type.get(item.type, 0) + 1

        # Count by state
        by_state: Dict[str, int] = {}
        for item in index.items:
            by_state[item.state] = by_state.get(item.state, 0) + 1

        # Active items
        active = self.get_active_items()

        return {
            'total': len(index.items),
            'byType': by_type,
            'byState': by_state,
            'active': len(active),
            'branchMappings': len(index.branch_mappings),
            **self.get_sync_info()
        }

    def format_item(self, item: WorkItem, verbose: bool = False) -> str:
        """Format a work item for display."""
        type_icons = {
            'Bug': '🐛',
            'User Story': '📖',
            'Task': '✅',
            'Feature': '⭐',
            'Epic': '🏔️',
        }
        icon = type_icons.get(item.type, '📋')

        line = f"{icon} AB#{item.id}: {item.title}"

        if verbose:
            line += f"\n   State: {item.state}"
            if item.assigned_to:
                line += f" | Assigned: {item.assigned_to}"
            if item.tags:
                line += f"\n   Tags: {', '.join(item.tags)}"
            if item.local_branch:
                line += f"\n   Branch: {item.local_branch}"
            if item.local_commits:
                line += f"\n   Commits: {len(item.local_commits)}"
        else:
            line += f" [{item.state}]"

        return line


# -----------------------------------------------------------------------------
# CLI Interface
# -----------------------------------------------------------------------------

def main():
    """CLI for work item index management."""
    import argparse

    parser = argparse.ArgumentParser(description='Work Item Index Manager')
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Status command
    status_parser = subparsers.add_parser('status', help='Show index status')
    status_parser.add_argument('--verbose', '-v', action='store_true')

    # List command
    list_parser = subparsers.add_parser('list', help='List indexed items')
    list_parser.add_argument('--type', help='Filter by type (Bug, Task, etc.)')
    list_parser.add_argument('--state', help='Filter by state')
    list_parser.add_argument('--active', action='store_true', help='Show only active items')
    list_parser.add_argument('--verbose', '-v', action='store_true')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search indexed items')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--limit', type=int, default=10)
    search_parser.add_argument('--verbose', '-v', action='store_true')

    # Get command
    get_parser = subparsers.add_parser('get', help='Get a specific item')
    get_parser.add_argument('id', type=int, help='Work item ID')

    args = parser.parse_args()

    manager = WorkItemIndexManager()

    if args.command == 'status':
        summary = manager.get_summary()
        print(f"Work Item Index Status")
        print(f"=" * 40)
        print(f"Last Sync: {summary['stalenessMessage']}")
        print(f"Organization: {summary.get('organization', 'Not set')}")
        print(f"Project: {summary.get('project', 'Not set')}")
        print(f"Total Items: {summary['total']}")
        print(f"Active Items: {summary['active']}")
        print(f"Branch Mappings: {summary['branchMappings']}")

        if args.verbose and summary['byType']:
            print(f"\nBy Type:")
            for t, count in sorted(summary['byType'].items()):
                print(f"  {t}: {count}")

        if args.verbose and summary['byState']:
            print(f"\nBy State:")
            for s, count in sorted(summary['byState'].items()):
                print(f"  {s}: {count}")

    elif args.command == 'list':
        if args.active:
            items = manager.get_active_items()
        elif args.type:
            items = manager.get_items_by_type(args.type)
        elif args.state:
            items = manager.get_items_by_state([args.state])
        else:
            items = manager.load().items

        if not items:
            print("No items found. Run sync to populate the index.")
            return

        for item in items:
            print(manager.format_item(item, args.verbose))
            if args.verbose:
                print()

    elif args.command == 'search':
        items = manager.search_items(args.query, args.limit)

        if not items:
            print(f"No items found matching '{args.query}'")
            print(f"({manager.get_staleness_message()})")
            return

        print(f"Found {len(items)} items matching '{args.query}':")
        print()
        for item in items:
            print(manager.format_item(item, args.verbose))
            if args.verbose:
                print()

    elif args.command == 'get':
        item = manager.get_item(args.id)
        if item:
            print(manager.format_item(item, verbose=True))
        else:
            print(f"Item AB#{args.id} not found in index")
            print(f"({manager.get_staleness_message()})")

    else:
        parser.print_help()


if __name__ == '__main__':
    main()

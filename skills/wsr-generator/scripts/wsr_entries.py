#!/usr/bin/env python3
"""
wsr_entries.py - Manage WSR entries for weekly status reports.

This script manages the data file for WSR entries. Data gathering is handled
by Claude using the azure-devops skill and git commands, then imported here.

Commands:
    add      Add a single entry manually
    import   Bulk import entries from JSON (stdin or file)
    list     List entries for a week
    remove   Remove an entry by ID
    export   Export current week's entries as JSON
    clear    Clear all entries for a week

Usage:
    python wsr_entries.py add --title "Feature X" --status Completed
    python wsr_entries.py import --file entries.json
    cat entries.json | python wsr_entries.py import
    python wsr_entries.py list
    python wsr_entries.py remove --id abc123
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any
import uuid

from wsr_config import WSRConfig, get_week_id, get_week_date_range


@dataclass
class WorkItemRef:
    """Reference to an Azure DevOps work item."""
    id: int
    title: Optional[str] = None
    type: Optional[str] = None  # Bug, Task, User Story, Feature, Epic
    state: Optional[str] = None
    url: Optional[str] = None


@dataclass
class CommitRef:
    """Reference to a git commit."""
    sha: str
    short_sha: str
    subject: str
    author: Optional[str] = None
    date: Optional[str] = None
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    url: Optional[str] = None
    repository: Optional[str] = None


@dataclass
class WSREntry:
    """A single WSR entry representing a feature, fix, or task."""
    id: str                                    # Unique ID for this entry
    title: str                                 # Max 80 chars, action-oriented
    status: str                                # Completed, In Progress, Blocked, On Hold
    domain: str                                # Development, Infrastructure, Security, etc.
    priority: str                              # High, Medium, Low
    timeline_start: str                        # ISO date
    timeline_end: str                          # ISO date

    # Content sections
    objective: str = ""                        # Why this work was undertaken
    solution: str = ""                         # Technical approach
    business_impact: str = ""                  # Value delivered
    technical_impact: str = ""                 # Code quality, performance
    risks: str = ""                            # Risk assessment
    next_steps: str = ""                       # Follow-up actions

    # References
    work_items: List[Dict] = field(default_factory=list)   # WorkItemRef as dicts
    commits: List[Dict] = field(default_factory=list)      # CommitRef as dicts
    parent_id: Optional[int] = None            # Parent Feature/Epic ID

    # Metadata
    created_at: str = ""
    updated_at: str = ""
    repository: Optional[str] = None
    tags: List[str] = field(default_factory=list)

    # Stats
    total_insertions: int = 0
    total_deletions: int = 0
    total_files_changed: int = 0

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        self.updated_at = datetime.utcnow().isoformat() + "Z"

    def add_work_item(self, work_item: WorkItemRef):
        """Add a work item reference."""
        if not any(wi.get("id") == work_item.id for wi in self.work_items):
            self.work_items.append(asdict(work_item))

    def add_commit(self, commit: CommitRef):
        """Add a commit reference."""
        if not any(c.get("sha") == commit.sha for c in self.commits):
            self.commits.append(asdict(commit))
            self.total_insertions += commit.insertions
            self.total_deletions += commit.deletions
            self.total_files_changed += commit.files_changed

    @property
    def work_item_ids(self) -> List[int]:
        """Get list of work item IDs."""
        return [wi["id"] for wi in self.work_items]

    @property
    def commit_shas(self) -> List[str]:
        """Get list of commit SHAs."""
        return [c["sha"] for c in self.commits]


@dataclass
class WeeklyData:
    """Container for a week's worth of WSR entries."""
    week_id: str                               # YYYY-WNN
    period_start: str                          # ISO date
    period_end: str                            # ISO date
    entries: List[Dict] = field(default_factory=list)  # WSREntry as dicts
    notes: str = ""                            # Free-form notes
    created_at: str = ""
    updated_at: str = ""

    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.utcnow().isoformat() + "Z"
        self.updated_at = datetime.utcnow().isoformat() + "Z"

    def add_entry(self, entry: WSREntry):
        """Add or update an entry."""
        for i, existing in enumerate(self.entries):
            if existing.get("id") == entry.id:
                self.entries[i] = asdict(entry)
                self.updated_at = datetime.utcnow().isoformat() + "Z"
                return

        self.entries.append(asdict(entry))
        self.updated_at = datetime.utcnow().isoformat() + "Z"

    def get_entry(self, entry_id: str) -> Optional[WSREntry]:
        """Get entry by ID."""
        for entry_dict in self.entries:
            if entry_dict.get("id") == entry_id:
                return WSREntry(**entry_dict)
        return None

    def remove_entry(self, entry_id: str) -> bool:
        """Remove entry by ID."""
        for i, entry in enumerate(self.entries):
            if entry.get("id") == entry_id:
                self.entries.pop(i)
                self.updated_at = datetime.utcnow().isoformat() + "Z"
                return True
        return False

    def clear_entries(self):
        """Clear all entries."""
        self.entries = []
        self.updated_at = datetime.utcnow().isoformat() + "Z"

    @classmethod
    def load(cls, data_dir: str, week_id: str) -> "WeeklyData":
        """Load weekly data from file."""
        path = Path(data_dir) / f"{week_id}-entries.json"
        if path.exists():
            data = json.loads(path.read_text())
            return cls(**data)

        # Create new weekly data
        start, end = get_week_date_range(week_id)
        return cls(
            week_id=week_id,
            period_start=start.strftime("%Y-%m-%d"),
            period_end=end.strftime("%Y-%m-%d")
        )

    def save(self, data_dir: str):
        """Save weekly data to file."""
        path = Path(data_dir) / f"{self.week_id}-entries.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2, default=str))


def import_entries_from_json(json_data: Dict, config: WSRConfig, weekly_data: WeeklyData) -> int:
    """
    Import entries from JSON data structure.

    Expected format:
    {
        "entries": [
            {
                "title": "Feature title",
                "status": "Completed",
                "priority": "High",
                "domain": "Development",
                "objective": "Why this was done",
                "business_impact": "Value delivered",
                "next_steps": "What's next",
                "work_items": [
                    {"id": 1234, "title": "Task title", "type": "Task", "state": "Done"}
                ],
                "commits": [
                    {"sha": "abc123", "subject": "Commit message"}
                ]
            }
        ]
    }
    """
    entries_data = json_data.get("entries", [])
    if not entries_data and isinstance(json_data, list):
        # Allow passing array directly
        entries_data = json_data

    count = 0
    for entry_data in entries_data:
        entry_id = entry_data.get("id") or str(uuid.uuid4())[:8]

        entry = WSREntry(
            id=entry_id,
            title=entry_data.get("title", "Untitled")[:80],
            status=entry_data.get("status", "In Progress"),
            domain=entry_data.get("domain", "Development"),
            priority=entry_data.get("priority", "Medium"),
            timeline_start=entry_data.get("timeline_start", weekly_data.period_start),
            timeline_end=entry_data.get("timeline_end", weekly_data.period_end),
            objective=entry_data.get("objective", ""),
            solution=entry_data.get("solution", ""),
            business_impact=entry_data.get("business_impact", ""),
            technical_impact=entry_data.get("technical_impact", ""),
            risks=entry_data.get("risks", ""),
            next_steps=entry_data.get("next_steps", ""),
            repository=entry_data.get("repository"),
            tags=entry_data.get("tags", []),
            parent_id=entry_data.get("parent_id"),
        )

        # Add work items
        for wi_data in entry_data.get("work_items", []):
            wi_id = wi_data.get("id")
            if wi_id:
                entry.add_work_item(WorkItemRef(
                    id=wi_id,
                    title=wi_data.get("title"),
                    type=wi_data.get("type"),
                    state=wi_data.get("state"),
                    url=wi_data.get("url") or config.get_work_item_url(wi_id)
                ))

        # Add commits
        for commit_data in entry_data.get("commits", []):
            sha = commit_data.get("sha", "")
            if sha:
                entry.add_commit(CommitRef(
                    sha=sha,
                    short_sha=commit_data.get("short_sha", sha[:7]),
                    subject=commit_data.get("subject", ""),
                    author=commit_data.get("author"),
                    date=commit_data.get("date"),
                    files_changed=commit_data.get("files_changed", 0),
                    insertions=commit_data.get("insertions", 0),
                    deletions=commit_data.get("deletions", 0),
                    repository=commit_data.get("repository"),
                    url=commit_data.get("url") or config.get_commit_url(sha)
                ))

        weekly_data.add_entry(entry)
        count += 1

    return count


def main():
    parser = argparse.ArgumentParser(
        description="Manage WSR entries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Add entry manually
  python wsr_entries.py add --title "Implemented login feature" --status Completed --priority High

  # Import entries from file
  python wsr_entries.py import --file entries.json

  # Import entries from stdin (Claude can pipe JSON)
  echo '{"entries": [...]}' | python wsr_entries.py import

  # List entries
  python wsr_entries.py list

  # Remove an entry
  python wsr_entries.py remove --id abc123

  # Export for debugging
  python wsr_entries.py export
"""
    )
    parser.add_argument("--config", "-c", default=".wsr/config.json", help="Config file path")
    parser.add_argument("--week", "-w", help="Week ID (YYYY-WNN), default: current week")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # add command
    add_parser = subparsers.add_parser("add", help="Add a new entry")
    add_parser.add_argument("--title", "-t", required=True, help="Entry title (max 80 chars)")
    add_parser.add_argument("--status", "-s", default="In Progress",
                            choices=["Completed", "In Progress", "Blocked", "On Hold"])
    add_parser.add_argument("--domain", "-d", default="Development",
                            choices=["Development", "Architecture", "Infrastructure",
                                     "Security", "Documentation", "Support"])
    add_parser.add_argument("--priority", "-p", default="Medium",
                            choices=["High", "Medium", "Low"])
    add_parser.add_argument("--work-items", nargs="+", type=int, help="Work item IDs")
    add_parser.add_argument("--objective", help="Why this work was undertaken")
    add_parser.add_argument("--business-impact", help="Business value delivered")
    add_parser.add_argument("--next-steps", help="Follow-up actions")

    # import command
    import_parser = subparsers.add_parser("import", help="Import entries from JSON")
    import_parser.add_argument("--file", "-f", help="JSON file path (default: stdin)")

    # list command
    subparsers.add_parser("list", help="List entries for a week")

    # remove command
    remove_parser = subparsers.add_parser("remove", help="Remove an entry by ID")
    remove_parser.add_argument("--id", required=True, help="Entry ID to remove")

    # export command
    export_parser = subparsers.add_parser("export", help="Export entries as JSON")
    export_parser.add_argument("--output", "-o", help="Output file (default: stdout)")

    # clear command
    clear_parser = subparsers.add_parser("clear", help="Clear all entries for a week")
    clear_parser.add_argument("--confirm", action="store_true", help="Confirm clearing")

    args = parser.parse_args()

    # Load config
    try:
        config = WSRConfig.load(args.config)
    except FileNotFoundError:
        print("WSR not configured. Run: python wsr_config.py init", file=sys.stderr)
        return 1

    week_id = args.week or get_week_id()
    weekly_data = WeeklyData.load(config.data_dir, week_id)

    if args.command == "add":
        entry = WSREntry(
            id=str(uuid.uuid4())[:8],
            title=args.title[:80],
            status=args.status,
            domain=args.domain,
            priority=args.priority,
            timeline_start=weekly_data.period_start,
            timeline_end=weekly_data.period_end,
            objective=args.objective or "",
            business_impact=getattr(args, 'business_impact', "") or "",
            next_steps=getattr(args, 'next_steps', "") or "",
        )

        if args.work_items:
            for wi_id in args.work_items:
                entry.add_work_item(WorkItemRef(
                    id=wi_id,
                    url=config.get_work_item_url(wi_id)
                ))

        weekly_data.add_entry(entry)
        weekly_data.save(config.data_dir)
        print(f"Added entry: {entry.id} - {entry.title}")

    elif args.command == "import":
        # Read JSON from file or stdin
        if args.file:
            json_text = Path(args.file).read_text()
        else:
            if sys.stdin.isatty():
                print("Reading JSON from stdin (Ctrl+D to finish)...", file=sys.stderr)
            json_text = sys.stdin.read()

        try:
            json_data = json.loads(json_text)
        except json.JSONDecodeError as e:
            print(f"Invalid JSON: {e}", file=sys.stderr)
            return 1

        count = import_entries_from_json(json_data, config, weekly_data)
        weekly_data.save(config.data_dir)
        print(f"Imported {count} entries for week {week_id}")

    elif args.command == "list":
        if not weekly_data.entries:
            print(f"No entries for week {week_id}")
            return 0

        print(f"\nWeek {week_id} ({weekly_data.period_start} to {weekly_data.period_end})")
        print("=" * 60)
        for entry_dict in weekly_data.entries:
            status_sym = {"Completed": "●", "In Progress": "◐", "Blocked": "■", "On Hold": "○"}.get(
                entry_dict.get("status", ""), "○"
            )
            priority_sym = {"High": "▲", "Medium": "●", "Low": "▽"}.get(
                entry_dict.get("priority", ""), "●"
            )
            print(f"\n[{entry_dict['id']}] {status_sym} {entry_dict['title']}")
            print(f"    {entry_dict['status']} | {entry_dict['domain']} | {priority_sym} {entry_dict['priority']}")
            if entry_dict.get('work_items'):
                wi_ids = [wi['id'] for wi in entry_dict['work_items']]
                print(f"    Work Items: {', '.join(f'AB#{id}' for id in wi_ids)}")
            if entry_dict.get('commits'):
                print(f"    Commits: {len(entry_dict['commits'])}")

    elif args.command == "remove":
        if weekly_data.remove_entry(args.id):
            weekly_data.save(config.data_dir)
            print(f"Removed entry: {args.id}")
        else:
            print(f"Entry not found: {args.id}", file=sys.stderr)
            return 1

    elif args.command == "export":
        output = json.dumps(asdict(weekly_data), indent=2, default=str)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Exported to {args.output}", file=sys.stderr)
        else:
            print(output)

    elif args.command == "clear":
        if not args.confirm:
            print(f"This will clear all {len(weekly_data.entries)} entries for week {week_id}.")
            print("Use --confirm to proceed.", file=sys.stderr)
            return 1
        weekly_data.clear_entries()
        weekly_data.save(config.data_dir)
        print(f"Cleared all entries for week {week_id}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

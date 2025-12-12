#!/usr/bin/env python3
"""
query-issues.py - Query GitHub issues across repositories.

Features:
- Preset queries for common use cases
- Multi-repo support
- Table and JSON output formats
- Filter by state, labels, assignee

Usage:
    python3 query-issues.py --preset my-open
    python3 query-issues.py --repo owner/repo --state open
    python3 query-issues.py --preset bugs --format table
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any


# Query presets
PRESETS = {
    "my-open": {
        "description": "Open issues assigned to me",
        "args": ["--assignee", "@me", "--state", "open"],
    },
    "my-all": {
        "description": "All issues assigned to me",
        "args": ["--assignee", "@me", "--state", "all"],
    },
    "created-by-me": {
        "description": "Issues I created",
        "args": ["--author", "@me", "--state", "all"],
    },
    "mentioned": {
        "description": "Issues where I'm mentioned",
        "args": ["--mention", "@me", "--state", "all"],
    },
    "recent": {
        "description": "Recently updated issues (last 7 days)",
        "args": ["--state", "all"],
        "filter_days": 7,
    },
    "high-priority": {
        "description": "Issues labeled priority:high or urgent",
        "args": ["--label", "priority:high,urgent", "--state", "open"],
    },
    "bugs": {
        "description": "Issues labeled bug",
        "args": ["--label", "bug", "--state", "open"],
    },
    "features": {
        "description": "Issues labeled enhancement or feature",
        "args": ["--label", "enhancement,feature", "--state", "open"],
    },
}

# Fields to fetch from GitHub API (for gh issue list - single repo)
ISSUE_FIELDS_REPO = [
    "number",
    "title",
    "state",
    "author",
    "assignees",
    "labels",
    "createdAt",
    "updatedAt",
    "closedAt",
    "url",
    "milestone",
]

# Fields for gh search issues (cross-repo)
ISSUE_FIELDS_SEARCH = [
    "number",
    "title",
    "state",
    "author",
    "assignees",
    "labels",
    "createdAt",
    "updatedAt",
    "closedAt",
    "url",
    "repository",
]


def run_gh_command(args: List[str]) -> tuple[int, str, str]:
    """Run a gh command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(["gh"] + args, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", "GitHub CLI (gh) not found"


def get_username() -> Optional[str]:
    """Get the authenticated user's username."""
    code, stdout, _ = run_gh_command(["api", "user", "--jq", ".login"])
    if code == 0:
        return stdout.strip()
    return None


def query_issues(
    repo: Optional[str] = None,
    preset: Optional[str] = None,
    state: str = "open",
    assignee: Optional[str] = None,
    author: Optional[str] = None,
    labels: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Query issues using gh CLI."""

    args = ["issue", "list"]

    # Add repo if specified
    if repo:
        args.extend(["--repo", repo])

    # Apply preset if specified
    filter_days = None
    if preset and preset in PRESETS:
        preset_config = PRESETS[preset]
        args.extend(preset_config["args"])
        filter_days = preset_config.get("filter_days")
    else:
        # Manual filters
        args.extend(["--state", state])
        if assignee:
            args.extend(["--assignee", assignee])
        if author:
            args.extend(["--author", author])
        if labels:
            args.extend(["--label", labels])

    args.extend(["--limit", str(limit)])

    # Request JSON output with specific fields
    args.extend(["--json", ",".join(ISSUE_FIELDS_REPO)])

    code, stdout, stderr = run_gh_command(args)

    if code != 0:
        print(f"Error querying issues: {stderr}", file=sys.stderr)
        return []

    try:
        issues = json.loads(stdout) if stdout else []
    except json.JSONDecodeError:
        print(f"Error parsing response: {stdout}", file=sys.stderr)
        return []

    # Apply date filter if needed
    if filter_days:
        cutoff = datetime.now() - timedelta(days=filter_days)
        cutoff_str = cutoff.isoformat()
        issues = [i for i in issues if i.get("updatedAt", "") >= cutoff_str]

    return issues


def query_issues_all_repos(
    preset: Optional[str] = None,
    state: str = "open",
    assignee: Optional[str] = None,
    limit: int = 50,
) -> List[Dict[str, Any]]:
    """Query issues across all repos using GitHub search."""

    # Build search query
    query_parts = ["is:issue"]

    filter_days = None
    if preset and preset in PRESETS:
        preset_config = PRESETS[preset]
        preset_args = preset_config["args"]
        filter_days = preset_config.get("filter_days")

        # Convert preset args to search query
        i = 0
        while i < len(preset_args):
            arg = preset_args[i]
            if arg == "--assignee":
                query_parts.append(f"assignee:{preset_args[i+1]}")
                i += 2
            elif arg == "--author":
                query_parts.append(f"author:{preset_args[i+1]}")
                i += 2
            elif arg == "--mention":
                query_parts.append(f"mentions:{preset_args[i+1]}")
                i += 2
            elif arg == "--state":
                state_val = preset_args[i+1]
                if state_val != "all":
                    query_parts.append(f"is:{state_val}")
                i += 2
            elif arg == "--label":
                for label in preset_args[i+1].split(","):
                    query_parts.append(f"label:{label}")
                i += 2
            else:
                i += 1
    else:
        if state != "all":
            query_parts.append(f"is:{state}")
        if assignee:
            query_parts.append(f"assignee:{assignee}")

    if filter_days:
        cutoff = datetime.now() - timedelta(days=filter_days)
        query_parts.append(f"updated:>={cutoff.strftime('%Y-%m-%d')}")

    search_query = " ".join(query_parts)

    args = [
        "search", "issues",
        "--json", ",".join(ISSUE_FIELDS_SEARCH),
        "--limit", str(limit),
        search_query
    ]

    code, stdout, stderr = run_gh_command(args)

    if code != 0:
        print(f"Error searching issues: {stderr}", file=sys.stderr)
        return []

    try:
        return json.loads(stdout) if stdout else []
    except json.JSONDecodeError:
        print(f"Error parsing response: {stdout}", file=sys.stderr)
        return []


def format_table(issues: List[Dict[str, Any]], repo_context: Optional[str] = None) -> str:
    """Format issues as a table."""
    if not issues:
        return "No issues found"

    lines = []

    # Only show repo column if we're searching across repos
    if repo_context:
        lines.append(f"{'#':<8} {'State':<8} {'Title':<60} {'Labels':<30}")
        lines.append("-" * 110)
    else:
        lines.append(f"{'#':<8} {'State':<8} {'Repo':<30} {'Title':<50} {'Labels':<20}")
        lines.append("-" * 120)

    for issue in issues:
        number = f"#{issue.get('number', '?')}"
        state = issue.get("state", "?")[:7]

        title = issue.get("title", "")

        labels = issue.get("labels", [])
        if isinstance(labels, list):
            label_names = [l.get("name", str(l)) if isinstance(l, dict) else str(l) for l in labels[:3]]
            labels_str = ", ".join(label_names)
        else:
            labels_str = ""

        if repo_context:
            title = title[:59]
            labels_str = labels_str[:29]
            lines.append(f"{number:<8} {state:<8} {title:<60} {labels_str:<30}")
        else:
            # Get repo name for cross-repo search
            repo_info = issue.get("repository", {})
            if isinstance(repo_info, dict):
                repo = repo_info.get("nameWithOwner", repo_info.get("name", ""))
            else:
                repo = str(repo_info) if repo_info else ""
            repo = repo[:29]
            title = title[:49]
            labels_str = labels_str[:19]
            lines.append(f"{number:<8} {state:<8} {repo:<30} {title:<50} {labels_str:<20}")

    return "\n".join(lines)


def format_json(issues: List[Dict[str, Any]]) -> str:
    """Format issues as JSON."""
    return json.dumps(issues, indent=2)


def format_simple(issues: List[Dict[str, Any]]) -> str:
    """Format issues in simple text format."""
    if not issues:
        return "No issues found"

    lines = []
    for issue in issues:
        number = issue.get("number", "?")
        state = issue.get("state", "?")
        title = issue.get("title", "")
        url = issue.get("url", "")

        repo_info = issue.get("repository", {})
        if isinstance(repo_info, dict):
            repo = repo_info.get("nameWithOwner", "")
        else:
            repo = ""

        state_sym = "●" if state == "OPEN" else "○"

        lines.append(f"{state_sym} {repo}#{number}: {title}")
        if url:
            lines.append(f"  {url}")
        lines.append("")

    return "\n".join(lines)


def list_presets():
    """Print available presets."""
    print("Available presets:")
    print("-" * 50)
    for name, config in PRESETS.items():
        print(f"  {name:<20} {config['description']}")


def main():
    parser = argparse.ArgumentParser(
        description="Query GitHub issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Query open issues assigned to me
  python3 query-issues.py --preset my-open

  # Query bugs in a specific repo
  python3 query-issues.py --repo owner/repo --label bug

  # Query all my issues in table format
  python3 query-issues.py --preset my-all --format table

  # List available presets
  python3 query-issues.py --list-presets
"""
    )

    parser.add_argument("--repo", "-r", help="Repository (owner/repo). If not specified, searches all repos")
    parser.add_argument("--preset", "-p", choices=list(PRESETS.keys()), help="Use a preset query")
    parser.add_argument("--state", "-s", choices=["open", "closed", "all"], default="open", help="Issue state")
    parser.add_argument("--assignee", "-a", help="Filter by assignee (use @me for yourself)")
    parser.add_argument("--author", help="Filter by author")
    parser.add_argument("--label", "-l", help="Filter by labels (comma-separated)")
    parser.add_argument("--limit", "-n", type=int, default=50, help="Maximum issues to return")
    parser.add_argument("--format", "-f", choices=["table", "json", "simple"], default="simple", help="Output format")
    parser.add_argument("--list-presets", action="store_true", help="List available presets")

    args = parser.parse_args()

    if args.list_presets:
        list_presets()
        return 0

    # Query issues
    if args.repo:
        issues = query_issues(
            repo=args.repo,
            preset=args.preset,
            state=args.state,
            assignee=args.assignee,
            author=args.author,
            labels=args.label,
            limit=args.limit,
        )
    else:
        # Search across all repos
        issues = query_issues_all_repos(
            preset=args.preset,
            state=args.state,
            assignee=args.assignee,
            limit=args.limit,
        )

    # Format output
    if args.format == "table":
        print(format_table(issues, repo_context=args.repo))
    elif args.format == "json":
        print(format_json(issues))
    else:
        print(format_simple(issues))

    return 0


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
gather-git-activity.py - Extract git commit history with work item correlation.

Gathers commits from git log and extracts Azure DevOps work item references.

Usage:
    python gather-git-activity.py --since "7 days ago"
    python gather-git-activity.py --since "2024-01-01" --until "2024-01-15"
    python gather-git-activity.py --since "7 days ago" --author "user@email.com"
"""

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class Commit:
    """A git commit with extracted metadata."""
    hash: str
    short_hash: str
    author_name: str
    author_email: str
    date: str
    subject: str
    body: str
    files_changed: int = 0
    insertions: int = 0
    deletions: int = 0
    work_item_refs: list = field(default_factory=list)


@dataclass
class GitActivity:
    """Summary of git activity."""
    repository: str
    branch: str
    period_start: str
    period_end: str
    author_filter: Optional[str]
    total_commits: int
    total_files_changed: int
    total_insertions: int
    total_deletions: int
    work_items_referenced: list = field(default_factory=list)
    commits: list = field(default_factory=list)
    commits_by_work_item: dict = field(default_factory=dict)
    orphan_commits: list = field(default_factory=list)


# Patterns for work item references
WORK_ITEM_PATTERNS = [
    r'AB#(\d+)',           # Azure Boards: AB#1234
    r'#(\d+)',             # Simple: #1234
    r'Fixes #(\d+)',       # Fixes #1234
    r'Closes #(\d+)',      # Closes #1234
    r'Related to #(\d+)',  # Related to #1234
    r'Resolves #(\d+)',    # Resolves #1234
    r'\[(\d+)\]',          # [1234]
]


def run_git_command(args: list, cwd: Optional[str] = None) -> Optional[str]:
    """Run a git command and return output."""
    cmd = ["git"] + args
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=cwd,
            timeout=30
        )
        
        if result.returncode != 0:
            print(f"Warning: git command failed: {' '.join(args)}", file=sys.stderr)
            print(f"  Error: {result.stderr}", file=sys.stderr)
            return None
        
        return result.stdout.strip()
        
    except subprocess.TimeoutExpired:
        print(f"Warning: git command timed out", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: git error: {e}", file=sys.stderr)
        return None


def get_repo_info(repo_path: Optional[str] = None) -> tuple[str, str]:
    """Get repository name and current branch."""
    # Get repo root
    root = run_git_command(["rev-parse", "--show-toplevel"], cwd=repo_path)
    repo_name = Path(root).name if root else "unknown"
    
    # Get current branch
    branch = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path)
    branch = branch or "unknown"
    
    return repo_name, branch


def extract_work_item_refs(text: str) -> list[int]:
    """Extract work item IDs from commit message."""
    refs = set()
    
    for pattern in WORK_ITEM_PATTERNS:
        matches = re.findall(pattern, text, re.IGNORECASE)
        for match in matches:
            try:
                refs.add(int(match))
            except ValueError:
                pass
    
    return sorted(list(refs))


def parse_commit_stats(stats_line: str) -> tuple[int, int, int]:
    """Parse git stat summary line."""
    files_changed = 0
    insertions = 0
    deletions = 0
    
    # Pattern: "3 files changed, 45 insertions(+), 12 deletions(-)"
    files_match = re.search(r'(\d+) files? changed', stats_line)
    if files_match:
        files_changed = int(files_match.group(1))
    
    ins_match = re.search(r'(\d+) insertions?\(\+\)', stats_line)
    if ins_match:
        insertions = int(ins_match.group(1))
    
    del_match = re.search(r'(\d+) deletions?\(-\)', stats_line)
    if del_match:
        deletions = int(del_match.group(1))
    
    return files_changed, insertions, deletions


def get_commits(
    since: str,
    until: Optional[str] = None,
    author: Optional[str] = None,
    repo_path: Optional[str] = None
) -> list[Commit]:
    """Get commits in the specified range."""
    
    # Build git log command
    # Use a delimiter that won't appear in commit messages
    delimiter = "---COMMIT_DELIMITER---"
    field_sep = "---FIELD_SEP---"
    
    format_str = f"%H{field_sep}%h{field_sep}%an{field_sep}%ae{field_sep}%ai{field_sep}%s{field_sep}%b{delimiter}"
    
    args = [
        "log",
        f"--since={since}",
        f"--pretty=format:{format_str}",
        "--shortstat",
        "--no-merges"
    ]
    
    if until:
        args.append(f"--until={until}")
    
    if author:
        args.append(f"--author={author}")
    
    output = run_git_command(args, cwd=repo_path)
    
    if not output:
        return []
    
    commits = []
    
    # Split by delimiter
    commit_blocks = output.split(delimiter)
    
    for block in commit_blocks:
        block = block.strip()
        if not block:
            continue
        
        # Split the block into commit info and stats
        lines = block.split('\n')
        
        # First line contains the formatted commit info
        if not lines:
            continue
        
        commit_line = lines[0]
        
        # Parse stats from remaining lines
        stats_line = ""
        for line in lines[1:]:
            if "files changed" in line or "file changed" in line:
                stats_line = line
                break
        
        # Parse commit fields
        fields = commit_line.split(field_sep)
        
        if len(fields) < 6:
            continue
        
        full_hash = fields[0]
        short_hash = fields[1]
        author_name = fields[2]
        author_email = fields[3]
        date = fields[4]
        subject = fields[5]
        body = fields[6] if len(fields) > 6 else ""
        
        # Parse stats
        files_changed, insertions, deletions = parse_commit_stats(stats_line)
        
        # Extract work item references
        full_message = f"{subject} {body}"
        work_item_refs = extract_work_item_refs(full_message)
        
        commit = Commit(
            hash=full_hash,
            short_hash=short_hash,
            author_name=author_name,
            author_email=author_email,
            date=date,
            subject=subject.strip(),
            body=body.strip(),
            files_changed=files_changed,
            insertions=insertions,
            deletions=deletions,
            work_item_refs=work_item_refs
        )
        
        commits.append(commit)
    
    return commits


def gather_git_activity(
    since: str,
    until: Optional[str] = None,
    author: Optional[str] = None,
    repo_path: Optional[str] = None
) -> GitActivity:
    """Gather all git activity for the specified period."""
    
    repo_name, branch = get_repo_info(repo_path)
    
    # Get author email if not specified
    if not author:
        author = run_git_command(["config", "user.email"], cwd=repo_path)
    
    # Get commits
    commits = get_commits(since, until, author, repo_path)
    
    # Aggregate stats
    total_files = sum(c.files_changed for c in commits)
    total_insertions = sum(c.insertions for c in commits)
    total_deletions = sum(c.deletions for c in commits)
    
    # Collect all work item references
    all_work_items = set()
    commits_by_work_item = {}
    orphan_commits = []
    
    for commit in commits:
        if commit.work_item_refs:
            for wi in commit.work_item_refs:
                all_work_items.add(wi)
                if wi not in commits_by_work_item:
                    commits_by_work_item[wi] = []
                commits_by_work_item[wi].append(commit.short_hash)
        else:
            orphan_commits.append(commit.short_hash)
    
    # Determine period boundaries
    if commits:
        dates = [c.date for c in commits]
        period_start = min(dates)[:10]  # Just date part
        period_end = max(dates)[:10]
    else:
        period_start = since
        period_end = until or datetime.now().strftime("%Y-%m-%d")
    
    return GitActivity(
        repository=repo_name,
        branch=branch,
        period_start=period_start,
        period_end=period_end,
        author_filter=author,
        total_commits=len(commits),
        total_files_changed=total_files,
        total_insertions=total_insertions,
        total_deletions=total_deletions,
        work_items_referenced=sorted(list(all_work_items)),
        commits=[asdict(c) for c in commits],
        commits_by_work_item=commits_by_work_item,
        orphan_commits=orphan_commits
    )


def main():
    parser = argparse.ArgumentParser(
        description="Gather git activity with work item correlation."
    )
    parser.add_argument(
        "--since", "-s",
        required=True,
        help="Start of time range (e.g., '7 days ago', '2024-01-01')"
    )
    parser.add_argument(
        "--until", "-u",
        help="End of time range (default: now)"
    )
    parser.add_argument(
        "--author", "-a",
        help="Filter by author email (default: current user)"
    )
    parser.add_argument(
        "--repo", "-r",
        help="Repository path (default: current directory)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file (default: stdout)"
    )
    
    args = parser.parse_args()
    
    # Check we're in a git repo
    if not run_git_command(["rev-parse", "--git-dir"], cwd=args.repo):
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)
    
    print(f"Gathering git activity since {args.since}...", file=sys.stderr)
    
    activity = gather_git_activity(
        since=args.since,
        until=args.until,
        author=args.author,
        repo_path=args.repo
    )
    
    # Convert to JSON
    result = asdict(activity)
    json_output = json.dumps(result, indent=2, default=str)
    
    if args.output:
        Path(args.output).write_text(json_output)
        print(f"Activity written to {args.output}", file=sys.stderr)
    else:
        print(json_output)
    
    # Summary
    print(f"\nSummary:", file=sys.stderr)
    print(f"  Repository: {activity.repository} ({activity.branch})", file=sys.stderr)
    print(f"  Period: {activity.period_start} to {activity.period_end}", file=sys.stderr)
    print(f"  Commits: {activity.total_commits}", file=sys.stderr)
    print(f"  Files changed: {activity.total_files_changed}", file=sys.stderr)
    print(f"  Lines: +{activity.total_insertions} -{activity.total_deletions}", file=sys.stderr)
    print(f"  Work items referenced: {len(activity.work_items_referenced)}", file=sys.stderr)
    print(f"  Orphan commits: {len(activity.orphan_commits)}", file=sys.stderr)


if __name__ == "__main__":
    main()

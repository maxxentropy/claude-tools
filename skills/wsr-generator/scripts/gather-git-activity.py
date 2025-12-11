#!/usr/bin/env python3
"""
gather-git-activity.py - Extract git commit history with work item correlation.

Usage:
    python gather-git-activity.py --since "7 days ago"
    python gather-git-activity.py --since "2024-01-01" --until "2024-01-15"
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class GitActivity:
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


WORK_ITEM_PATTERNS = [r'AB#(\d+)', r'#(\d+)', r'Fixes #(\d+)', r'Closes #(\d+)', r'Resolves #(\d+)']


def run_git_command(args: list, cwd: Optional[str] = None) -> Optional[str]:
    try:
        result = subprocess.run(["git"] + args, capture_output=True, text=True, cwd=cwd, timeout=30)
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def get_repo_info(repo_path: Optional[str] = None) -> tuple[str, str]:
    root = run_git_command(["rev-parse", "--show-toplevel"], cwd=repo_path)
    repo_name = Path(root).name if root else "unknown"
    branch = run_git_command(["rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_path) or "unknown"
    return repo_name, branch


def extract_work_item_refs(text: str) -> list[int]:
    refs = set()
    for pattern in WORK_ITEM_PATTERNS:
        for match in re.findall(pattern, text, re.IGNORECASE):
            try:
                refs.add(int(match))
            except ValueError:
                pass
    return sorted(list(refs))


def get_commits(since: str, until: Optional[str] = None, author: Optional[str] = None, repo_path: Optional[str] = None) -> list[dict]:
    delimiter, field_sep = "---COMMIT_DELIMITER---", "---FIELD_SEP---"
    format_str = f"%H{field_sep}%h{field_sep}%an{field_sep}%ae{field_sep}%ai{field_sep}%s{field_sep}%b{delimiter}"
    
    args = ["log", f"--since={since}", f"--pretty=format:{format_str}", "--shortstat", "--no-merges"]
    if until:
        args.append(f"--until={until}")
    if author:
        args.append(f"--author={author}")
    
    output = run_git_command(args, cwd=repo_path)
    if not output:
        return []
    
    commits = []
    for block in output.split(delimiter):
        block = block.strip()
        if not block:
            continue
        
        lines = block.split('\n')
        fields = lines[0].split(field_sep)
        if len(fields) < 6:
            continue
        
        # Parse stats
        files_changed = insertions = deletions = 0
        for line in lines[1:]:
            if "file" in line and "changed" in line:
                m = re.search(r'(\d+) files? changed', line)
                files_changed = int(m.group(1)) if m else 0
                m = re.search(r'(\d+) insertions?\(\+\)', line)
                insertions = int(m.group(1)) if m else 0
                m = re.search(r'(\d+) deletions?\(-\)', line)
                deletions = int(m.group(1)) if m else 0
                break
        
        full_message = f"{fields[5]} {fields[6] if len(fields) > 6 else ''}"
        commits.append({
            "hash": fields[0], "short_hash": fields[1], "author_name": fields[2], "author_email": fields[3],
            "date": fields[4], "subject": fields[5].strip(), "body": (fields[6] if len(fields) > 6 else "").strip(),
            "files_changed": files_changed, "insertions": insertions, "deletions": deletions,
            "work_item_refs": extract_work_item_refs(full_message)
        })
    
    return commits


def gather_git_activity(since: str, until: Optional[str] = None, author: Optional[str] = None, repo_path: Optional[str] = None) -> GitActivity:
    repo_name, branch = get_repo_info(repo_path)
    if not author:
        author = run_git_command(["config", "user.email"], cwd=repo_path)
    
    commits = get_commits(since, until, author, repo_path)
    
    all_work_items = set()
    commits_by_work_item = {}
    orphan_commits = []
    
    for commit in commits:
        if commit["work_item_refs"]:
            for wi in commit["work_item_refs"]:
                all_work_items.add(wi)
                commits_by_work_item.setdefault(wi, []).append(commit["short_hash"])
        else:
            orphan_commits.append(commit["short_hash"])
    
    period_start = min(c["date"] for c in commits)[:10] if commits else since
    period_end = max(c["date"] for c in commits)[:10] if commits else (until or datetime.now().strftime("%Y-%m-%d"))
    
    return GitActivity(
        repository=repo_name, branch=branch, period_start=period_start, period_end=period_end,
        author_filter=author, total_commits=len(commits),
        total_files_changed=sum(c["files_changed"] for c in commits),
        total_insertions=sum(c["insertions"] for c in commits),
        total_deletions=sum(c["deletions"] for c in commits),
        work_items_referenced=sorted(list(all_work_items)), commits=commits,
        commits_by_work_item=commits_by_work_item, orphan_commits=orphan_commits
    )


def main():
    parser = argparse.ArgumentParser(description="Gather git activity with work item correlation.")
    parser.add_argument("--since", "-s", required=True, help="Start of time range")
    parser.add_argument("--until", "-u", help="End of time range")
    parser.add_argument("--author", "-a", help="Filter by author email")
    parser.add_argument("--repo", "-r", help="Repository path")
    parser.add_argument("--output", "-o", help="Output file")
    args = parser.parse_args()
    
    if not run_git_command(["rev-parse", "--git-dir"], cwd=args.repo):
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)
    
    activity = gather_git_activity(args.since, args.until, args.author, args.repo)
    output = json.dumps(asdict(activity), indent=2, default=str)
    
    if args.output:
        Path(args.output).write_text(output)
        print(f"Activity written to {args.output}", file=sys.stderr)
    else:
        print(output)
    
    print(f"\nSummary: {activity.total_commits} commits, {len(activity.work_items_referenced)} work items, {len(activity.orphan_commits)} orphans", file=sys.stderr)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Commit message hook for Azure DevOps work item linking.

This hook ensures commits are linked to work items (AB#1234) by:
1. Checking if message already contains a work item reference
2. Auto-appending reference from branch context if detectable
3. Warning (but not blocking) if no reference can be determined

Usage:
    As a git hook: python3 commit_msg_hook.py .git/COMMIT_EDITMSG
    With pre-commit: configured in .pre-commit-config.yaml

Exit codes:
    0 - Success (reference found, added, or not required)
    1 - Error (only for actual failures, not missing references)
"""

import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple

# Configuration
WORK_ITEM_PATTERN = re.compile(r'AB#(\d+)', re.IGNORECASE)
EXEMPT_BRANCHES = {'main', 'master', 'develop', 'release', 'hotfix'}
EXEMPT_PREFIXES = ('release/', 'hotfix/', 'dependabot/', 'renovate/')


def get_current_branch() -> Optional[str]:
    """Get the current git branch name."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            cwd=os.getcwd()
        )
        if result.returncode == 0:
            branch = result.stdout.strip()
            return branch if branch != "HEAD" else None
        return None
    except Exception:
        return None


def parse_work_item_from_branch(branch_name: str) -> Tuple[Optional[int], Optional[str]]:
    """
    Extract work item ID from branch name.

    Supported formats:
    - feature/AB#1234-description
    - fix/AB#1234-short-desc
    - bugfix/1234-description
    - user/name/AB#1234/feature
    - AB#1234

    Returns:
        Tuple of (work_item_id, raw_match)
    """
    if not branch_name:
        return None, None

    # Try AB# format first (highest confidence)
    match = re.search(r'AB#(\d+)', branch_name, re.IGNORECASE)
    if match:
        return int(match.group(1)), match.group(0)

    # Try bare number with common prefixes
    patterns = [
        r'(?:feature|fix|bugfix|hotfix)/(\d{4,6})[-/]',
        r'user/[^/]+/(\d{4,6})',
        r'^(\d{4,6})[-/]',
    ]

    for pattern in patterns:
        match = re.search(pattern, branch_name, re.IGNORECASE)
        if match:
            work_item_id = int(match.group(1))
            if 1 <= work_item_id <= 9999999:
                return work_item_id, f"AB#{work_item_id}"

    return None, None


def is_exempt_branch(branch_name: Optional[str]) -> bool:
    """Check if branch is exempt from work item requirement."""
    if not branch_name:
        return True

    # Direct match
    if branch_name.lower() in EXEMPT_BRANCHES:
        return True

    # Prefix match
    branch_lower = branch_name.lower()
    for prefix in EXEMPT_PREFIXES:
        if branch_lower.startswith(prefix):
            return True

    return False


def has_work_item_reference(message: str) -> bool:
    """Check if commit message already contains a work item reference."""
    return bool(WORK_ITEM_PATTERN.search(message))


def format_reference(work_item_id: int) -> str:
    """Format a work item reference for commit messages."""
    return f"AB#{work_item_id}"


def append_reference_to_message(message: str, reference: str) -> str:
    """
    Append work item reference to commit message.

    Adds reference on a new line, preserving any existing trailing content
    like Signed-off-by lines.
    """
    lines = message.rstrip('\n').split('\n')

    # Find where to insert (before any trailer lines like Signed-off-by)
    trailer_patterns = [
        r'^Signed-off-by:',
        r'^Co-authored-by:',
        r'^Reviewed-by:',
        r'^Acked-by:',
    ]

    insert_index = len(lines)
    for i, line in enumerate(lines):
        for pattern in trailer_patterns:
            if re.match(pattern, line, re.IGNORECASE):
                insert_index = i
                break
        if insert_index != len(lines):
            break

    # Insert the reference
    if insert_index == len(lines):
        # No trailers, just append
        lines.append('')
        lines.append(reference)
    else:
        # Insert before trailers with blank line
        lines.insert(insert_index, '')
        lines.insert(insert_index + 1, reference)

    return '\n'.join(lines) + '\n'


def main() -> int:
    """Main entry point for the commit-msg hook."""
    if len(sys.argv) < 2:
        print("Usage: commit_msg_hook.py <commit-msg-file>", file=sys.stderr)
        return 1

    commit_msg_file = Path(sys.argv[1])

    if not commit_msg_file.exists():
        print(f"Error: Commit message file not found: {commit_msg_file}", file=sys.stderr)
        return 1

    try:
        message = commit_msg_file.read_text()
    except Exception as e:
        print(f"Error reading commit message: {e}", file=sys.stderr)
        return 1

    # Skip if message is empty (will be caught by git)
    stripped = message.strip()
    if not stripped or stripped.startswith('#'):
        return 0

    # Check if already has work item reference
    if has_work_item_reference(message):
        # Already linked, nothing to do
        return 0

    # Get current branch
    branch = get_current_branch()

    # Check if branch is exempt
    if is_exempt_branch(branch):
        # Exempt branch, don't require work item
        return 0

    # Try to detect work item from branch name
    work_item_id, raw_match = parse_work_item_from_branch(branch)

    if work_item_id:
        # Found work item in branch name - auto-append
        reference = format_reference(work_item_id)
        new_message = append_reference_to_message(message, reference)

        try:
            commit_msg_file.write_text(new_message)
            print(f"✓ Auto-linked to {reference} (from branch: {branch})")
            return 0
        except Exception as e:
            print(f"Error updating commit message: {e}", file=sys.stderr)
            return 1

    # No work item found - warn but don't block
    # This allows commits on branches without work item references
    print(f"⚠ No work item reference (AB#1234) found")
    print(f"  Branch: {branch}")
    print(f"  Tip: Include 'AB#1234' in branch name for auto-linking")
    print(f"  Or add 'AB#1234' to your commit message manually")

    # Return 0 to not block the commit
    # Change to return 1 if you want to enforce work item references
    return 0


if __name__ == "__main__":
    sys.exit(main())

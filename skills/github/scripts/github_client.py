#!/usr/bin/env python3
"""
github_client.py - GitHub API client with rate limiting and error handling.

Features:
- Wraps gh CLI for API calls
- Rate limit monitoring
- Error classification
- Batch operations

Usage:
    from github_client import GitHubClient, GitHubConfig

    config = GitHubConfig()
    client = GitHubClient(config)

    # Get issues
    issues = client.get_issues("owner/repo", state="open")

    # Create issue
    issue = client.create_issue("owner/repo", "Title", "Body", labels=["bug"])
"""

import json
import subprocess
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional, List, Dict, Any


class GitHubErrorType(Enum):
    """Types of GitHub API errors."""
    TRANSIENT = "transient"          # Temporary failure, retry
    RATE_LIMITED = "rate_limited"    # Hit rate limit
    AUTH_FAILED = "auth_failed"      # Authentication issue
    NOT_FOUND = "not_found"          # Resource doesn't exist
    VALIDATION = "validation"        # Bad request
    PERMISSION = "permission"        # Access denied


@dataclass
class GitHubError(Exception):
    """Structured GitHub API error."""
    error_type: GitHubErrorType
    message: str
    status_code: Optional[int] = None
    retry_after: Optional[int] = None

    def __str__(self):
        return f"[{self.error_type.value}] {self.message}"


@dataclass
class GitHubConfig:
    """GitHub client configuration."""
    default_repo: Optional[str] = None
    max_retries: int = 3
    retry_delay: float = 1.0
    verbose: bool = False

    @classmethod
    def from_file(cls, path: str) -> "GitHubConfig":
        """Load config from JSON file."""
        config_path = Path(path)
        if config_path.exists():
            data = json.loads(config_path.read_text())
            return cls(**data)
        return cls()


class GitHubClient:
    """GitHub API client using gh CLI."""

    def __init__(self, config: Optional[GitHubConfig] = None, verbose: bool = False):
        self.config = config or GitHubConfig()
        self.verbose = verbose or self.config.verbose
        self._username: Optional[str] = None

    def _log(self, message: str):
        """Log message if verbose mode is on."""
        if self.verbose:
            print(f"[GitHub] {message}", file=sys.stderr)

    def _run_gh(self, args: List[str], retries: int = 0) -> Dict[str, Any]:
        """Run gh command and return parsed JSON response."""
        self._log(f"Running: gh {' '.join(args)}")

        try:
            result = subprocess.run(
                ["gh"] + args,
                capture_output=True,
                text=True
            )
        except FileNotFoundError:
            raise GitHubError(
                GitHubErrorType.AUTH_FAILED,
                "GitHub CLI (gh) not found. Install from https://cli.github.com/"
            )

        if result.returncode != 0:
            error = self._classify_error(result.stderr, result.returncode)

            # Retry on transient errors
            if error.error_type == GitHubErrorType.TRANSIENT and retries < self.config.max_retries:
                delay = self.config.retry_delay * (2 ** retries)
                self._log(f"Transient error, retrying in {delay}s...")
                time.sleep(delay)
                return self._run_gh(args, retries + 1)

            # Retry on rate limit with backoff
            if error.error_type == GitHubErrorType.RATE_LIMITED:
                retry_after = error.retry_after or 60
                if retries < self.config.max_retries:
                    self._log(f"Rate limited, waiting {retry_after}s...")
                    time.sleep(retry_after)
                    return self._run_gh(args, retries + 1)

            raise error

        # Parse JSON response if present
        if result.stdout:
            try:
                return json.loads(result.stdout)
            except json.JSONDecodeError:
                return {"raw": result.stdout}

        return {}

    def _classify_error(self, stderr: str, code: int) -> GitHubError:
        """Classify error based on stderr output."""
        stderr_lower = stderr.lower()

        if "rate limit" in stderr_lower or "403" in stderr:
            return GitHubError(
                GitHubErrorType.RATE_LIMITED,
                "API rate limit exceeded",
                status_code=403
            )

        if "401" in stderr or "authentication" in stderr_lower or "not logged in" in stderr_lower:
            return GitHubError(
                GitHubErrorType.AUTH_FAILED,
                "Authentication failed. Run 'gh auth login'",
                status_code=401
            )

        if "404" in stderr or "not found" in stderr_lower:
            return GitHubError(
                GitHubErrorType.NOT_FOUND,
                f"Resource not found: {stderr}",
                status_code=404
            )

        if "403" in stderr or "permission" in stderr_lower or "forbidden" in stderr_lower:
            return GitHubError(
                GitHubErrorType.PERMISSION,
                f"Permission denied: {stderr}",
                status_code=403
            )

        if "422" in stderr or "validation" in stderr_lower:
            return GitHubError(
                GitHubErrorType.VALIDATION,
                f"Validation error: {stderr}",
                status_code=422
            )

        if "500" in stderr or "502" in stderr or "503" in stderr:
            return GitHubError(
                GitHubErrorType.TRANSIENT,
                f"Server error: {stderr}",
                status_code=500
            )

        return GitHubError(
            GitHubErrorType.VALIDATION,
            stderr or "Unknown error",
            status_code=code
        )

    @property
    def username(self) -> str:
        """Get authenticated username."""
        if self._username is None:
            result = self._run_gh(["api", "user", "--jq", ".login"])
            self._username = result.get("raw", "").strip()
        return self._username

    def get_rate_limit(self) -> Dict[str, Any]:
        """Get current rate limit status."""
        return self._run_gh(["api", "rate_limit", "--jq", ".rate"])

    # =========================================================================
    # Issues
    # =========================================================================

    def get_issues(
        self,
        repo: str,
        state: str = "open",
        assignee: Optional[str] = None,
        labels: Optional[List[str]] = None,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get issues from a repository."""
        args = ["issue", "list", "--repo", repo, "--state", state, "--limit", str(limit)]

        if assignee:
            args.extend(["--assignee", assignee])
        if labels:
            args.extend(["--label", ",".join(labels)])

        args.extend(["--json", "number,title,state,author,assignees,labels,createdAt,updatedAt,url"])

        result = self._run_gh(args)
        return result if isinstance(result, list) else []

    def get_issue(self, repo: str, number: int) -> Dict[str, Any]:
        """Get a specific issue."""
        args = [
            "issue", "view", str(number),
            "--repo", repo,
            "--json", "number,title,state,body,author,assignees,labels,comments,createdAt,updatedAt,closedAt,url"
        ]
        return self._run_gh(args)

    def create_issue(
        self,
        repo: str,
        title: str,
        body: str = "",
        labels: Optional[List[str]] = None,
        assignees: Optional[List[str]] = None,
        milestone: Optional[str] = None
    ) -> Dict[str, Any]:
        """Create a new issue."""
        args = ["issue", "create", "--repo", repo, "--title", title]

        if body:
            args.extend(["--body", body])
        if labels:
            args.extend(["--label", ",".join(labels)])
        if assignees:
            args.extend(["--assignee", ",".join(assignees)])
        if milestone:
            args.extend(["--milestone", milestone])

        # Return JSON
        args.append("--json")
        args.append("number,title,url")

        return self._run_gh(args)

    def update_issue(
        self,
        repo: str,
        number: int,
        title: Optional[str] = None,
        body: Optional[str] = None,
        state: Optional[str] = None,
        add_labels: Optional[List[str]] = None,
        remove_labels: Optional[List[str]] = None,
        add_assignees: Optional[List[str]] = None,
        remove_assignees: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Update an issue."""
        args = ["issue", "edit", str(number), "--repo", repo]

        if title:
            args.extend(["--title", title])
        if body:
            args.extend(["--body", body])
        if add_labels:
            args.extend(["--add-label", ",".join(add_labels)])
        if remove_labels:
            args.extend(["--remove-label", ",".join(remove_labels)])
        if add_assignees:
            args.extend(["--add-assignee", ",".join(add_assignees)])
        if remove_assignees:
            args.extend(["--remove-assignee", ",".join(remove_assignees)])

        # gh issue edit doesn't return JSON by default
        result = subprocess.run(["gh"] + args, capture_output=True, text=True)
        if result.returncode != 0:
            raise self._classify_error(result.stderr, result.returncode)

        return {"success": True, "number": number}

    def close_issue(self, repo: str, number: int, reason: str = "completed") -> Dict[str, Any]:
        """Close an issue."""
        args = ["issue", "close", str(number), "--repo", repo]
        if reason == "not_planned":
            args.append("--reason")
            args.append("not planned")

        result = subprocess.run(["gh"] + args, capture_output=True, text=True)
        if result.returncode != 0:
            raise self._classify_error(result.stderr, result.returncode)

        return {"success": True, "number": number, "state": "closed"}

    def reopen_issue(self, repo: str, number: int) -> Dict[str, Any]:
        """Reopen a closed issue."""
        args = ["issue", "reopen", str(number), "--repo", repo]

        result = subprocess.run(["gh"] + args, capture_output=True, text=True)
        if result.returncode != 0:
            raise self._classify_error(result.stderr, result.returncode)

        return {"success": True, "number": number, "state": "open"}

    def add_comment(self, repo: str, number: int, body: str) -> Dict[str, Any]:
        """Add a comment to an issue."""
        args = ["issue", "comment", str(number), "--repo", repo, "--body", body]

        result = subprocess.run(["gh"] + args, capture_output=True, text=True)
        if result.returncode != 0:
            raise self._classify_error(result.stderr, result.returncode)

        return {"success": True, "number": number}

    # =========================================================================
    # Pull Requests
    # =========================================================================

    def get_prs(
        self,
        repo: str,
        state: str = "open",
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Get pull requests from a repository."""
        args = [
            "pr", "list",
            "--repo", repo,
            "--state", state,
            "--limit", str(limit),
            "--json", "number,title,state,author,headRefName,baseRefName,createdAt,updatedAt,url"
        ]
        result = self._run_gh(args)
        return result if isinstance(result, list) else []

    def get_pr(self, repo: str, number: int) -> Dict[str, Any]:
        """Get a specific pull request."""
        args = [
            "pr", "view", str(number),
            "--repo", repo,
            "--json", "number,title,state,body,author,headRefName,baseRefName,commits,files,reviews,comments,createdAt,updatedAt,mergedAt,url"
        ]
        return self._run_gh(args)

    # =========================================================================
    # Repositories
    # =========================================================================

    def list_repos(self, limit: int = 50, visibility: str = "all") -> List[Dict[str, Any]]:
        """List repositories for authenticated user."""
        args = [
            "repo", "list",
            "--limit", str(limit),
            "--json", "name,nameWithOwner,description,isPrivate,updatedAt,url"
        ]

        if visibility != "all":
            args.extend(["--visibility", visibility])

        result = self._run_gh(args)
        return result if isinstance(result, list) else []

    def get_repo(self, repo: str) -> Dict[str, Any]:
        """Get repository details."""
        args = [
            "repo", "view", repo,
            "--json", "name,nameWithOwner,description,isPrivate,defaultBranchRef,stargazerCount,forkCount,createdAt,updatedAt,url"
        ]
        return self._run_gh(args)

    # =========================================================================
    # Search
    # =========================================================================

    def search_issues(
        self,
        query: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search issues across repositories."""
        args = [
            "search", "issues",
            "--limit", str(limit),
            "--json", "number,title,state,author,repository,labels,createdAt,updatedAt,url",
            query
        ]
        result = self._run_gh(args)
        return result if isinstance(result, list) else []

    def search_prs(
        self,
        query: str,
        limit: int = 50
    ) -> List[Dict[str, Any]]:
        """Search pull requests across repositories."""
        args = [
            "search", "prs",
            "--limit", str(limit),
            "--json", "number,title,state,author,repository,createdAt,updatedAt,url",
            query
        ]
        result = self._run_gh(args)
        return result if isinstance(result, list) else []


# =============================================================================
# CLI for testing
# =============================================================================

def main():
    """Test the client."""
    import argparse

    parser = argparse.ArgumentParser(description="GitHub client test")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    args = parser.parse_args()

    client = GitHubClient(verbose=args.verbose)

    print(f"Authenticated as: {client.username}")
    print()

    rate = client.get_rate_limit()
    print(f"Rate limit: {rate}")
    print()

    repos = client.list_repos(limit=5)
    print(f"Your repos ({len(repos)}):")
    for repo in repos[:5]:
        print(f"  - {repo.get('nameWithOwner')}")


if __name__ == "__main__":
    main()

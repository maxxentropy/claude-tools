#!/usr/bin/env python3
"""
detect-platform.py - Detect which work item platform to use for the current repo.

Logic:
1. If .ado/config.json exists -> Azure DevOps (always wins)
2. Else if GitHub remote exists -> GitHub
3. Else -> Unknown (ask user)

Usage:
    python3 skills/detect-platform.py
    python3 skills/detect-platform.py --path /path/to/repo
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


def check_ado_config(repo_path: Path) -> Optional[dict]:
    """Check for Azure DevOps configuration."""
    config_path = repo_path / ".ado" / "config.json"
    if config_path.exists():
        try:
            return json.loads(config_path.read_text())
        except json.JSONDecodeError:
            return {}
    return None


def get_git_remotes(repo_path: Path) -> dict:
    """Get git remotes for the repo."""
    try:
        result = subprocess.run(
            ["git", "-C", str(repo_path), "remote", "-v"],
            capture_output=True,
            text=True
        )
        if result.returncode != 0:
            return {}

        remotes = {}
        for line in result.stdout.strip().split("\n"):
            if not line:
                continue
            parts = line.split()
            if len(parts) >= 2:
                name, url = parts[0], parts[1]
                if "(fetch)" in line or name not in remotes:
                    remotes[name] = url
        return remotes
    except FileNotFoundError:
        return {}


def classify_remote(url: str) -> Optional[str]:
    """Classify a remote URL as github or azure."""
    url_lower = url.lower()
    if "github.com" in url_lower:
        return "github"
    if "dev.azure.com" in url_lower or "visualstudio.com" in url_lower:
        return "azure-devops"
    return None


def detect_platform(repo_path: Path) -> Tuple[str, dict]:
    """
    Detect the work item platform for a repo.

    Returns:
        Tuple of (platform_name, details)
        platform_name: "azure-devops", "github", or "unknown"
    """
    # Rule 1: ADO config always wins
    ado_config = check_ado_config(repo_path)
    if ado_config is not None:
        return "azure-devops", {
            "reason": "Azure DevOps configured (.ado/config.json exists)",
            "organization": ado_config.get("organization"),
            "project": ado_config.get("project"),
        }

    # Rule 2: Check git remotes
    remotes = get_git_remotes(repo_path)

    github_remote = None
    azure_remote = None

    for name, url in remotes.items():
        platform = classify_remote(url)
        if platform == "github" and not github_remote:
            github_remote = {"name": name, "url": url}
        elif platform == "azure-devops" and not azure_remote:
            azure_remote = {"name": name, "url": url}

    # If we have an Azure remote (even without config), prefer it
    # This handles repos that haven't run ADO setup yet
    if azure_remote:
        return "azure-devops", {
            "reason": "Azure DevOps remote found",
            "remote": azure_remote,
            "note": "Run 'python3 skills/azure-devops/scripts/check-prerequisites.py' to configure",
        }

    # GitHub remote
    if github_remote:
        return "github", {
            "reason": "GitHub remote found",
            "remote": github_remote,
        }

    # No remotes or unrecognized
    return "unknown", {
        "reason": "No Azure DevOps or GitHub remote found",
        "remotes": remotes,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Detect work item platform for current repo"
    )
    parser.add_argument(
        "--path", "-p",
        default=".",
        help="Path to repo (default: current directory)"
    )
    parser.add_argument(
        "--json", "-j",
        action="store_true",
        help="Output as JSON"
    )
    args = parser.parse_args()

    repo_path = Path(args.path).resolve()
    platform, details = detect_platform(repo_path)

    if args.json:
        print(json.dumps({
            "platform": platform,
            "details": details,
            "repo_path": str(repo_path),
        }, indent=2))
    else:
        print(f"Platform: {platform}")
        print(f"Reason: {details.get('reason', 'Unknown')}")

        if platform == "azure-devops":
            if details.get("organization"):
                print(f"Organization: {details['organization']}")
                print(f"Project: {details['project']}")
            elif details.get("remote"):
                print(f"Remote: {details['remote']['url']}")
                if details.get("note"):
                    print(f"Note: {details['note']}")
        elif platform == "github":
            if details.get("remote"):
                print(f"Remote: {details['remote']['url']}")
        elif platform == "unknown":
            print("Suggestion: Configure Azure DevOps or push to GitHub")

    # Exit code: 0 for known platform, 1 for unknown
    return 0 if platform != "unknown" else 1


if __name__ == "__main__":
    sys.exit(main())

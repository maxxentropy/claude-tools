#!/usr/bin/env python3
"""
wsr_config.py - WSR skill configuration management.

Handles:
- Configuration file management (.wsr/config.json)
- URL generation for work items and commits
- Directory structure setup
- Audience level definitions

Usage:
    python wsr_config.py init                    # Initialize configuration
    python wsr_config.py show                    # Show current configuration
    python wsr_config.py set output_dir ~/reports  # Set a config value
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, List


# Default configuration
DEFAULT_CONFIG = {
    "version": "2.0",
    "organization": None,           # Azure DevOps organization URL
    "project": None,                # Azure DevOps project name
    "output_dir": ".wsr/reports",   # Where to save reports
    "data_dir": ".wsr/data",        # Where to store incremental data
    "git_remote_type": "azure",     # "azure" or "github"
    "git_remote_url": None,         # Base URL for commit links
    "default_audience": "standard", # "executive", "standard", "technical"
    "author_email": None,           # Git author filter
    "include_orphan_commits": True, # Include commits without work items
    "max_entries_per_report": 10,   # Limit entries in executive summary
}


# Audience level definitions
AUDIENCE_LEVELS = {
    "executive": {
        "description": "High-level summary for leadership",
        "include_sections": ["objective", "business_impact", "next_steps"],
        "max_bullet_points": 3,
        "include_code_stats": False,
        "include_commit_details": False,
        "include_work_item_list": True,
        "summary_only": True,
    },
    "standard": {
        "description": "Balanced report for stakeholders",
        "include_sections": ["objective", "solution", "business_impact", "technical_impact", "next_steps"],
        "max_bullet_points": 5,
        "include_code_stats": True,
        "include_commit_details": False,
        "include_work_item_list": True,
        "summary_only": False,
    },
    "technical": {
        "description": "Detailed report for engineering team",
        "include_sections": ["objective", "solution", "business_impact", "technical_impact", "risks", "next_steps"],
        "max_bullet_points": None,  # No limit
        "include_code_stats": True,
        "include_commit_details": True,
        "include_work_item_list": True,
        "summary_only": False,
    }
}


@dataclass
class WSRConfig:
    """WSR skill configuration."""
    version: str = "2.0"
    organization: Optional[str] = None
    project: Optional[str] = None
    output_dir: str = ".wsr/reports"
    data_dir: str = ".wsr/data"
    git_remote_type: str = "azure"  # azure or github
    git_remote_url: Optional[str] = None
    default_audience: str = "standard"
    author_email: Optional[str] = None
    include_orphan_commits: bool = True
    max_entries_per_report: int = 10

    @classmethod
    def load(cls, config_path: str = ".wsr/config.json") -> "WSRConfig":
        """Load configuration from file."""
        path = Path(config_path)
        if not path.exists():
            raise FileNotFoundError(f"Config not found: {config_path}. Run 'wsr_config.py init' first.")

        data = json.loads(path.read_text())
        return cls(**{k: v for k, v in data.items() if k in cls.__dataclass_fields__})

    @classmethod
    def load_or_default(cls, config_path: str = ".wsr/config.json") -> "WSRConfig":
        """Load configuration or return defaults."""
        try:
            return cls.load(config_path)
        except FileNotFoundError:
            return cls()

    def save(self, config_path: str = ".wsr/config.json"):
        """Save configuration to file."""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))

    def ensure_directories(self):
        """Create necessary directories."""
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        Path(self.data_dir).mkdir(parents=True, exist_ok=True)

    def get_work_item_url(self, work_item_id: int) -> str:
        """Generate URL for a work item."""
        if not self.organization or not self.project:
            return f"AB#{work_item_id}"

        org = self.organization.rstrip("/")
        return f"{org}/{self.project}/_workitems/edit/{work_item_id}"

    def get_commit_url(self, commit_sha: str, repo_name: Optional[str] = None) -> str:
        """Generate URL for a commit."""
        if not self.git_remote_url:
            return commit_sha[:7]

        base_url = self.git_remote_url.rstrip("/")

        if self.git_remote_type == "github":
            # GitHub: https://github.com/owner/repo/commit/sha
            return f"{base_url}/commit/{commit_sha}"
        else:
            # Azure Repos: https://dev.azure.com/org/project/_git/repo/commit/sha
            if repo_name:
                return f"{base_url}/_git/{repo_name}/commit/{commit_sha}"
            else:
                # Try to extract repo from URL or use project name
                return f"{base_url}/commit/{commit_sha}"

    def format_work_item_link(self, work_item_id: int, title: Optional[str] = None) -> str:
        """Format work item as markdown link."""
        url = self.get_work_item_url(work_item_id)
        label = f"AB#{work_item_id}"
        if title:
            label = f"{label}: {title[:50]}..."

        if url.startswith("http"):
            return f"[{label}]({url})"
        return label

    def format_commit_link(self, commit_sha: str, subject: Optional[str] = None, repo_name: Optional[str] = None) -> str:
        """Format commit as markdown link."""
        url = self.get_commit_url(commit_sha, repo_name)
        short_sha = commit_sha[:7]

        if url.startswith("http"):
            if subject:
                return f"[`{short_sha}`]({url}) - {subject[:60]}"
            return f"[`{short_sha}`]({url})"

        if subject:
            return f"`{short_sha}` - {subject[:60]}"
        return f"`{short_sha}`"

    def get_audience_settings(self, audience: Optional[str] = None) -> dict:
        """Get settings for specified audience level."""
        level = audience or self.default_audience
        return AUDIENCE_LEVELS.get(level, AUDIENCE_LEVELS["standard"])


def detect_git_remote() -> tuple[str, Optional[str]]:
    """Detect git remote type and URL."""
    try:
        result = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            return "azure", None

        url = result.stdout.strip()

        # GitHub patterns
        if "github.com" in url:
            # Convert git@github.com:owner/repo.git to https://github.com/owner/repo
            if url.startswith("git@"):
                match = re.match(r'git@github\.com:(.+?)(?:\.git)?$', url)
                if match:
                    return "github", f"https://github.com/{match.group(1)}"
            elif url.startswith("https://github.com"):
                return "github", url.replace(".git", "")

        # Azure DevOps patterns
        if "dev.azure.com" in url or "visualstudio.com" in url:
            return "azure", url.replace(".git", "")

        return "azure", url

    except Exception:
        return "azure", None


def detect_ado_config() -> tuple[Optional[str], Optional[str]]:
    """Detect Azure DevOps configuration from .ado/config.json."""
    try:
        ado_config = json.loads(Path(".ado/config.json").read_text())
        return ado_config.get("organization"), ado_config.get("project")
    except Exception:
        return None, None


def detect_git_email() -> Optional[str]:
    """Detect git user email."""
    try:
        result = subprocess.run(
            ["git", "config", "user.email"],
            capture_output=True, text=True, timeout=10
        )
        return result.stdout.strip() if result.returncode == 0 else None
    except Exception:
        return None


def init_config(config_path: str = ".wsr/config.json", interactive: bool = True) -> WSRConfig:
    """Initialize WSR configuration."""
    print("Initializing WSR configuration...\n")

    # Start with defaults
    config = WSRConfig()

    # Detect Azure DevOps settings
    org, project = detect_ado_config()
    if org:
        print(f"  Detected ADO organization: {org}")
        config.organization = org
    if project:
        print(f"  Detected ADO project: {project}")
        config.project = project

    # Detect git remote
    remote_type, remote_url = detect_git_remote()
    print(f"  Detected git remote type: {remote_type}")
    if remote_url:
        print(f"  Detected git remote URL: {remote_url}")
        config.git_remote_type = remote_type
        config.git_remote_url = remote_url

    # Detect git email
    email = detect_git_email()
    if email:
        print(f"  Detected git author: {email}")
        config.author_email = email

    # Save configuration
    config.save(config_path)
    config.ensure_directories()

    # Add to .gitignore if not present
    gitignore = Path(".gitignore")
    if gitignore.exists():
        content = gitignore.read_text()
        if ".wsr/" not in content:
            gitignore.write_text(content.rstrip() + "\n.wsr/\n")
            print("  Added .wsr/ to .gitignore")

    print(f"\nConfiguration saved to {config_path}")
    print(f"Reports will be saved to: {config.output_dir}")
    print(f"Data will be stored in: {config.data_dir}")

    return config


def get_week_id(date: Optional[datetime] = None) -> str:
    """Get ISO week identifier (YYYY-WNN)."""
    d = date or datetime.now()
    return f"{d.isocalendar()[0]}-W{d.isocalendar()[1]:02d}"


def get_week_date_range(week_id: str) -> tuple[datetime, datetime]:
    """Get start and end dates for a week ID."""
    year, week = int(week_id[:4]), int(week_id[6:])
    # ISO week starts on Monday
    from datetime import timedelta
    jan_4 = datetime(year, 1, 4)
    start_of_year = jan_4 - timedelta(days=jan_4.weekday())
    week_start = start_of_year + timedelta(weeks=week - 1)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def main():
    parser = argparse.ArgumentParser(description="WSR configuration management")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize configuration")
    init_parser.add_argument("--config", "-c", default=".wsr/config.json")

    # show command
    show_parser = subparsers.add_parser("show", help="Show current configuration")
    show_parser.add_argument("--config", "-c", default=".wsr/config.json")

    # set command
    set_parser = subparsers.add_parser("set", help="Set a configuration value")
    set_parser.add_argument("key", help="Configuration key")
    set_parser.add_argument("value", help="Configuration value")
    set_parser.add_argument("--config", "-c", default=".wsr/config.json")

    # audiences command
    audiences_parser = subparsers.add_parser("audiences", help="Show audience level definitions")

    args = parser.parse_args()

    if args.command == "init":
        init_config(args.config)

    elif args.command == "show":
        try:
            config = WSRConfig.load(args.config)
            print(json.dumps(asdict(config), indent=2))
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    elif args.command == "set":
        try:
            config = WSRConfig.load(args.config)
            if hasattr(config, args.key):
                # Convert value type
                current = getattr(config, args.key)
                if isinstance(current, bool):
                    value = args.value.lower() in ("true", "1", "yes")
                elif isinstance(current, int):
                    value = int(args.value)
                else:
                    value = args.value
                setattr(config, args.key, value)
                config.save(args.config)
                print(f"Set {args.key} = {value}")
            else:
                print(f"Unknown key: {args.key}", file=sys.stderr)
                return 1
        except FileNotFoundError as e:
            print(f"Error: {e}", file=sys.stderr)
            return 1

    elif args.command == "audiences":
        for name, settings in AUDIENCE_LEVELS.items():
            print(f"\n{name.upper()}")
            print(f"  {settings['description']}")
            print(f"  Sections: {', '.join(settings['include_sections'])}")
            print(f"  Code stats: {settings['include_code_stats']}")
            print(f"  Commit details: {settings['include_commit_details']}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

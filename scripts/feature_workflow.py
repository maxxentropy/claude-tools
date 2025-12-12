#!/usr/bin/env python3
"""
Feature workflow helper - integrates with Azure DevOps for work item lookups.

Used by feature.sh to fetch work item titles and other metadata.
"""

import json
import subprocess
import sys
from pathlib import Path


def run_az_command(args: list[str]) -> dict | list | None:
    """Run an Azure CLI command and return parsed JSON output."""
    try:
        result = subprocess.run(
            ["az"] + args + ["-o", "json"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode == 0 and result.stdout.strip():
            return json.loads(result.stdout)
        return None
    except (subprocess.TimeoutExpired, json.JSONDecodeError, FileNotFoundError):
        return None


def get_ado_config() -> dict | None:
    """Get Azure DevOps configuration from .ado/config.json or az defaults."""
    # Check for .ado/config.json
    config_path = Path(".ado/config.json")
    if config_path.exists():
        try:
            with open(config_path) as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError):
            pass

    # Try az devops configure --list
    try:
        result = subprocess.run(
            ["az", "devops", "configure", "--list"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            config = {}
            for line in result.stdout.splitlines():
                if "=" in line:
                    key, value = line.split("=", 1)
                    config[key.strip()] = value.strip()
            if config.get("organization") and config.get("project"):
                return {
                    "organization": config["organization"],
                    "project": config["project"],
                }
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    return None


def get_work_item_title(work_item_id: str) -> str | None:
    """Fetch work item title from Azure DevOps."""
    config = get_ado_config()
    if not config:
        return None

    org = config.get("organization", "")
    project = config.get("project", "")

    if not org or not project:
        return None

    # Query work item
    result = run_az_command([
        "boards", "work-item", "show",
        "--id", str(work_item_id),
        "--org", org,
    ])

    if result and "fields" in result:
        return result["fields"].get("System.Title")

    return None


def get_work_item_type(work_item_id: str) -> str | None:
    """Fetch work item type (Bug, User Story, Task, etc.)."""
    config = get_ado_config()
    if not config:
        return None

    org = config.get("organization", "")

    result = run_az_command([
        "boards", "work-item", "show",
        "--id", str(work_item_id),
        "--org", org,
    ])

    if result and "fields" in result:
        return result["fields"].get("System.WorkItemType")

    return None


def suggest_branch_prefix(work_item_id: str) -> str:
    """Suggest branch prefix based on work item type."""
    work_item_type = get_work_item_type(work_item_id)

    if work_item_type:
        type_lower = work_item_type.lower()
        if "bug" in type_lower:
            return "fix"
        elif "task" in type_lower:
            return "task"
        elif "feature" in type_lower or "story" in type_lower:
            return "feature"

    return "feature"


def main():
    if len(sys.argv) < 2:
        print("Usage: feature_workflow.py <command> [args]", file=sys.stderr)
        print("Commands:", file=sys.stderr)
        print("  get-title <work-item-id>   Get work item title", file=sys.stderr)
        print("  get-type <work-item-id>    Get work item type", file=sys.stderr)
        print("  suggest-prefix <work-item-id>  Suggest branch prefix", file=sys.stderr)
        sys.exit(1)

    command = sys.argv[1]

    if command == "get-title":
        if len(sys.argv) < 3:
            print("Usage: feature_workflow.py get-title <work-item-id>", file=sys.stderr)
            sys.exit(1)
        title = get_work_item_title(sys.argv[2])
        if title:
            print(title)
        else:
            sys.exit(1)

    elif command == "get-type":
        if len(sys.argv) < 3:
            print("Usage: feature_workflow.py get-type <work-item-id>", file=sys.stderr)
            sys.exit(1)
        work_type = get_work_item_type(sys.argv[2])
        if work_type:
            print(work_type)
        else:
            sys.exit(1)

    elif command == "suggest-prefix":
        if len(sys.argv) < 3:
            print("Usage: feature_workflow.py suggest-prefix <work-item-id>", file=sys.stderr)
            sys.exit(1)
        prefix = suggest_branch_prefix(sys.argv[2])
        print(prefix)

    else:
        print(f"Unknown command: {command}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

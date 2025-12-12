#!/usr/bin/env python3
"""
discover-project.py - Discover Azure DevOps project structure and work item schemas.

Discovers:
- Area paths and iteration paths
- Teams
- Work item types with FULL FIELD DEFINITIONS (required fields, allowed values, defaults)
- Pipelines and repositories

The field definitions are critical for creating/updating work items correctly.

Usage:
    python discover-project.py --config .ado/config.json --output .ado/project-metadata.json
    python discover-project.py --config .ado/config.json --output .ado/project-metadata.json --verbose
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


def run_az_command(args: list, timeout: int = 60, verbose: bool = False) -> Optional[Any]:
    """Run Azure CLI command and return JSON result."""
    cmd = ["az"] + args + ["--output", "json"]
    if verbose:
        print(f"  Running: {' '.join(cmd[:6])}...", file=sys.stderr)
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            if verbose:
                print(f"  Warning: {result.stderr[:200]}", file=sys.stderr)
            return None
        return json.loads(result.stdout) if result.stdout.strip() else None
    except subprocess.TimeoutExpired:
        print(f"  Warning: Command timed out after {timeout}s", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        if verbose:
            print(f"  Warning: Invalid JSON: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"  Warning: {e}", file=sys.stderr)
        return None


def run_rest_api(org: str, endpoint: str, timeout: int = 60, verbose: bool = False) -> Optional[Any]:
    """
    Call Azure DevOps REST API using az rest command.
    This uses the same authentication as az login.
    """
    # Normalize org URL
    if not org.startswith("http"):
        org = f"https://dev.azure.com/{org}"
    org = org.rstrip("/")

    url = f"{org}/{endpoint}"
    if "api-version" not in url:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}api-version=7.1"

    cmd = [
        "az", "rest",
        "--method", "get",
        "--url", url,
        "--resource", "499b84ac-1321-427f-aa17-267ca6975798"  # Azure DevOps resource ID
    ]

    if verbose:
        print(f"  REST: {endpoint[:60]}...", file=sys.stderr)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            if verbose:
                print(f"  Warning: REST API failed: {result.stderr[:200]}", file=sys.stderr)
            return None
        return json.loads(result.stdout) if result.stdout.strip() else None
    except Exception as e:
        if verbose:
            print(f"  Warning: {e}", file=sys.stderr)
        return None


def discover_areas(org: str, project: str, verbose: bool = False) -> list:
    """Discover area paths hierarchy."""
    print("Discovering area paths...", file=sys.stderr)
    data = run_az_command(
        ["boards", "area", "project", "list", "--organization", org, "--project", project, "--depth", "10"],
        verbose=verbose
    )
    if not data:
        return []

    def parse_area(node):
        if not isinstance(node, dict):
            return None
        area = {
            "id": node.get("id", 0),
            "name": node.get("name", ""),
            "path": node.get("path", ""),
            "children": []
        }
        if "children" in node:
            area["children"] = [a for a in (parse_area(child) for child in node["children"]) if a is not None]
        return area

    if isinstance(data, dict):
        result = parse_area(data)
        return [result] if result else []
    return [a for a in (parse_area(item) for item in data) if a is not None]


def discover_iterations(org: str, project: str, verbose: bool = False) -> list:
    """Discover iterations with dates."""
    print("Discovering iterations...", file=sys.stderr)
    data = run_az_command(
        ["boards", "iteration", "project", "list", "--organization", org, "--project", project, "--depth", "10"],
        verbose=verbose
    )
    if not data:
        return []

    iterations = []
    def parse_iteration(node):
        attrs = node.get("attributes", {})
        iterations.append({
            "id": node.get("id", 0),
            "name": node.get("name", ""),
            "path": node.get("path", ""),
            "start_date": attrs.get("startDate"),
            "finish_date": attrs.get("finishDate"),
            "time_frame": attrs.get("timeFrame")  # past, current, future
        })
        for child in node.get("children", []):
            parse_iteration(child)

    for item in (data if isinstance(data, list) else [data]):
        parse_iteration(item)
    return iterations


def discover_teams(org: str, project: str, verbose: bool = False) -> list:
    """Discover teams."""
    print("Discovering teams...", file=sys.stderr)
    data = run_az_command(
        ["devops", "team", "list", "--organization", org, "--project", project],
        verbose=verbose
    )
    return [
        {"id": t.get("id", ""), "name": t.get("name", ""), "description": t.get("description", "")}
        for t in (data or [])
    ]


def discover_work_item_type_fields(org: str, project: str, wit_name: str, verbose: bool = False) -> list:
    """
    Discover fields for a specific work item type with full schema.

    Uses REST API: GET {org}/{project}/_apis/wit/workitemtypes/{type}/fields?$expand=all

    Returns fields with:
    - referenceName: The API field name (e.g., "System.Title")
    - name: Display name (e.g., "Title")
    - alwaysRequired: Whether field is required
    - defaultValue: Default value if any
    - allowedValues: List of valid values for picklists
    - type: Field type (string, integer, dateTime, etc.)
    """
    endpoint = f"{project}/_apis/wit/workitemtypes/{wit_name}/fields?$expand=all"
    data = run_rest_api(org, endpoint, verbose=verbose)

    if not data or "value" not in data:
        # Fallback to CLI if REST fails
        if verbose:
            print(f"  Falling back to CLI for {wit_name} fields", file=sys.stderr)
        return []

    fields = []
    for field in data.get("value", []):
        field_info = {
            "referenceName": field.get("referenceName", ""),
            "name": field.get("name", ""),
            "type": field.get("type", "string"),
            "alwaysRequired": field.get("alwaysRequired", False),
            "defaultValue": field.get("defaultValue"),
            "helpText": field.get("helpText", ""),
        }

        # Include allowed values if present (for picklists)
        allowed = field.get("allowedValues")
        if allowed:
            field_info["allowedValues"] = allowed

        # Include dependent fields if present
        dependent = field.get("dependentFields")
        if dependent:
            field_info["dependentFields"] = [
                {"referenceName": d.get("referenceName"), "name": d.get("name")}
                for d in dependent
            ]

        fields.append(field_info)

    return fields


def discover_work_item_types(org: str, project: str, verbose: bool = False) -> list:
    """
    Discover work item types with FULL FIELD DEFINITIONS.

    This is critical for creating work items correctly - it tells us:
    - What fields are required
    - What values are allowed for each field
    - What the default values are
    """
    print("Discovering work item types...", file=sys.stderr)

    # Get list of work item types
    data = run_az_command(
        ["boards", "work-item", "type", "list", "--organization", org, "--project", project],
        verbose=verbose
    )

    if not data:
        return []

    work_item_types = []
    for wit in data:
        wit_name = wit.get("name", "")
        if not wit_name:
            continue

        print(f"  Fetching fields for: {wit_name}...", file=sys.stderr)

        # Get full field definitions for this work item type
        fields = discover_work_item_type_fields(org, project, wit_name, verbose=verbose)

        # Separate required vs optional fields
        required_fields = [f for f in fields if f.get("alwaysRequired")]
        optional_fields = [f for f in fields if not f.get("alwaysRequired")]

        # Identify key field categories
        picklist_fields = [f for f in fields if f.get("allowedValues")]

        work_item_types.append({
            "name": wit_name,
            "description": wit.get("description", ""),
            "icon": wit.get("icon", {}).get("url", ""),
            "color": wit.get("color", ""),
            "fields": fields,
            "requiredFields": [f["referenceName"] for f in required_fields],
            "picklistFields": {f["referenceName"]: f.get("allowedValues", []) for f in picklist_fields},
            "fieldCount": len(fields),
            "requiredCount": len(required_fields)
        })

    return work_item_types


def discover_pipelines(org: str, project: str, verbose: bool = False) -> list:
    """Discover pipelines."""
    print("Discovering pipelines...", file=sys.stderr)
    data = run_az_command(
        ["pipelines", "list", "--organization", org, "--project", project],
        verbose=verbose
    )
    return [
        {"id": p.get("id", 0), "name": p.get("name", ""), "folder": p.get("folder", "")}
        for p in (data or [])
    ]


def discover_repositories(org: str, project: str, verbose: bool = False) -> list:
    """Discover repositories."""
    print("Discovering repositories...", file=sys.stderr)
    data = run_az_command(
        ["repos", "list", "--organization", org, "--project", project],
        verbose=verbose
    )
    return [
        {
            "id": r.get("id", ""),
            "name": r.get("name", ""),
            "default_branch": r.get("defaultBranch", "").replace("refs/heads/", "")
        }
        for r in (data or [])
    ]


def generate_field_summary(work_item_types: list) -> dict:
    """
    Generate a quick-reference summary of fields across all work item types.
    Useful for Claude to quickly look up valid values.
    """
    summary = {
        "commonRequiredFields": [],
        "statesByType": {},
        "priorityValues": [],
        "severityValues": [],
    }

    # Find common required fields
    if work_item_types:
        first_required = set(work_item_types[0].get("requiredFields", []))
        for wit in work_item_types[1:]:
            first_required &= set(wit.get("requiredFields", []))
        summary["commonRequiredFields"] = sorted(list(first_required))

    # Extract states and other picklist values per type
    for wit in work_item_types:
        wit_name = wit["name"]
        picklists = wit.get("picklistFields", {})

        if "System.State" in picklists:
            summary["statesByType"][wit_name] = picklists["System.State"]

        if "Microsoft.VSTS.Common.Priority" in picklists and not summary["priorityValues"]:
            summary["priorityValues"] = picklists["Microsoft.VSTS.Common.Priority"]

        if "Microsoft.VSTS.Common.Severity" in picklists and not summary["severityValues"]:
            summary["severityValues"] = picklists["Microsoft.VSTS.Common.Severity"]

    return summary


def main():
    parser = argparse.ArgumentParser(
        description="Discover Azure DevOps project structure and work item schemas.",
        epilog="""
This script discovers your project's complete schema including:
- Work item types with ALL field definitions
- Required fields and allowed values for each type
- Area paths, iterations, teams, pipelines, and repos

The output is cached to .ado/project-metadata.json so Claude can
create/update work items correctly without guessing field values.
        """
    )
    parser.add_argument("--config", "-c", required=True, help="Path to .ado/config.json")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed progress")
    parser.add_argument("--skip-fields", action="store_true",
                        help="Skip detailed field discovery (faster but less complete)")
    args = parser.parse_args()

    # Load config
    try:
        config = json.loads(Path(args.config).read_text())
        org = config["organization"]
        project = config["project"]
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1
    except (json.JSONDecodeError, KeyError) as e:
        print(f"Error: Invalid config file: {e}", file=sys.stderr)
        return 1

    print(f"Discovering project: {project} at {org}", file=sys.stderr)
    print("=" * 50, file=sys.stderr)

    # Discover all metadata
    metadata = {
        "organization": org,
        "project": project,
        "discovered_at": datetime.utcnow().isoformat() + "Z",
        "schema_version": "2.0",  # New version with full field definitions
        "areas": discover_areas(org, project, args.verbose),
        "iterations": discover_iterations(org, project, args.verbose),
        "teams": discover_teams(org, project, args.verbose),
        "work_item_types": discover_work_item_types(org, project, args.verbose) if not args.skip_fields else [],
        "pipelines": discover_pipelines(org, project, args.verbose),
        "repositories": discover_repositories(org, project, args.verbose),
    }

    # Generate field summary for quick reference
    if metadata["work_item_types"]:
        metadata["fieldSummary"] = generate_field_summary(metadata["work_item_types"])

    # Output
    output = json.dumps(metadata, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output)
        print(f"\nMetadata written to {args.output}", file=sys.stderr)
    else:
        print(output)

    # Summary
    print("=" * 50, file=sys.stderr)
    print("Discovery complete:", file=sys.stderr)
    print(f"  Areas: {len(metadata['areas'])}", file=sys.stderr)
    print(f"  Iterations: {len(metadata['iterations'])}", file=sys.stderr)
    print(f"  Teams: {len(metadata['teams'])}", file=sys.stderr)
    print(f"  Work Item Types: {len(metadata['work_item_types'])}", file=sys.stderr)
    if metadata["work_item_types"]:
        total_fields = sum(wit.get("fieldCount", 0) for wit in metadata["work_item_types"])
        print(f"  Total Fields Discovered: {total_fields}", file=sys.stderr)
    print(f"  Pipelines: {len(metadata['pipelines'])}", file=sys.stderr)
    print(f"  Repositories: {len(metadata['repositories'])}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())

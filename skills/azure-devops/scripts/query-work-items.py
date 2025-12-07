#!/usr/bin/env python3
"""
query-work-items.py - Query Azure DevOps work items with common presets.

Provides convenient presets for common queries and outputs clean JSON.

Usage:
    python query-work-items.py --config .ado/config.json --preset my-active
    python query-work-items.py --config .ado/config.json --preset changed-this-week
    python query-work-items.py --config .ado/config.json --wiql "SELECT ... FROM workitems WHERE ..."
    python query-work-items.py --config .ado/config.json --id 1234  # Get single item
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


# Preset WIQL queries
QUERY_PRESETS = {
    "my-active": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AssignedTo], [System.AreaPath], [System.IterationPath],
               [System.ChangedDate], [System.CreatedDate]
        FROM workitems
        WHERE [System.AssignedTo] = @Me
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [System.ChangedDate] DESC
    """,
    
    "my-all": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AssignedTo], [System.AreaPath], [System.IterationPath],
               [System.ChangedDate], [System.CreatedDate]
        FROM workitems
        WHERE [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """,
    
    "changed-today": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AssignedTo], [System.AreaPath], [System.ChangedDate],
               [System.Reason], [System.ChangedBy]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today
          AND [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """,
    
    "changed-this-week": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AssignedTo], [System.AreaPath], [System.ChangedDate],
               [System.Reason], [System.ChangedBy]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today - 7
          AND [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """,
    
    "completed-this-week": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AssignedTo], [System.AreaPath], [System.ChangedDate],
               [Microsoft.VSTS.Common.ClosedDate]
        FROM workitems
        WHERE [System.State] IN ('Closed', 'Done')
          AND [System.ChangedDate] >= @Today - 7
          AND [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """,
    
    "recent-bugs": """
        SELECT [System.Id], [System.Title], [System.State], [System.AssignedTo],
               [System.AreaPath], [System.ChangedDate], [Microsoft.VSTS.Common.Priority],
               [Microsoft.VSTS.Common.Severity]
        FROM workitems
        WHERE [System.WorkItemType] = 'Bug'
          AND [System.ChangedDate] >= @Today - 14
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
    """,
    
    "sprint-items": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AssignedTo], [System.AreaPath], [Microsoft.VSTS.Scheduling.RemainingWork]
        FROM workitems
        WHERE [System.IterationPath] = @CurrentIteration
          AND [System.State] NOT IN ('Removed')
        ORDER BY [System.WorkItemType], [System.State]
    """,
    
    "blocked": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AssignedTo], [System.AreaPath], [System.Tags]
        FROM workitems
        WHERE ([System.Tags] CONTAINS 'Blocked' OR [System.State] = 'Blocked')
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [System.ChangedDate] DESC
    """
}


def run_az_command(args: list, timeout: int = 60) -> dict | list | None:
    """Run an Azure CLI command and return parsed JSON output."""
    cmd = ["az"] + args + ["--output", "json"]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout
        )
        
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return None
        
        if result.stdout.strip():
            return json.loads(result.stdout)
        return None
        
    except subprocess.TimeoutExpired:
        print(f"Error: Command timed out", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Failed to parse JSON: {e}", file=sys.stderr)
        return None


def load_config(config_path: str) -> tuple[str, str]:
    """Load organization and project from config file."""
    config = json.loads(Path(config_path).read_text())
    return config["organization"], config["project"]


def query_work_items(org: str, project: str, wiql: str) -> list[dict]:
    """Query work items using WIQL."""
    # Clean up WIQL (remove extra whitespace)
    wiql_clean = " ".join(wiql.split())
    
    result = run_az_command([
        "boards", "query",
        "--organization", org,
        "--project", project,
        "--wiql", wiql_clean
    ])
    
    if not result:
        return []
    
    # The query returns a list of work item references, we need to get full details
    work_items = []
    
    for item in result:
        if "id" in item:
            # Get full work item details
            details = run_az_command([
                "boards", "work-item", "show",
                "--organization", org,
                "--id", str(item["id"])
            ], timeout=30)
            
            if details:
                # Flatten the fields for easier access
                flat_item = {
                    "id": details.get("id"),
                    "url": details.get("url"),
                    "rev": details.get("rev")
                }
                
                # Extract common fields
                fields = details.get("fields", {})
                flat_item.update({
                    "title": fields.get("System.Title"),
                    "state": fields.get("System.State"),
                    "workItemType": fields.get("System.WorkItemType"),
                    "assignedTo": fields.get("System.AssignedTo", {}).get("displayName") if isinstance(fields.get("System.AssignedTo"), dict) else fields.get("System.AssignedTo"),
                    "areaPath": fields.get("System.AreaPath"),
                    "iterationPath": fields.get("System.IterationPath"),
                    "createdDate": fields.get("System.CreatedDate"),
                    "changedDate": fields.get("System.ChangedDate"),
                    "reason": fields.get("System.Reason"),
                    "priority": fields.get("Microsoft.VSTS.Common.Priority"),
                    "tags": fields.get("System.Tags"),
                    "description": fields.get("System.Description"),
                    "parent": fields.get("System.Parent")
                })
                
                work_items.append(flat_item)
    
    return work_items


def get_work_item(org: str, item_id: int) -> Optional[dict]:
    """Get a single work item by ID."""
    details = run_az_command([
        "boards", "work-item", "show",
        "--organization", org,
        "--id", str(item_id)
    ])
    
    if not details:
        return None
    
    # Flatten for easier access
    fields = details.get("fields", {})
    
    return {
        "id": details.get("id"),
        "url": details.get("url"),
        "rev": details.get("rev"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "workItemType": fields.get("System.WorkItemType"),
        "assignedTo": fields.get("System.AssignedTo", {}).get("displayName") if isinstance(fields.get("System.AssignedTo"), dict) else None,
        "areaPath": fields.get("System.AreaPath"),
        "iterationPath": fields.get("System.IterationPath"),
        "createdDate": fields.get("System.CreatedDate"),
        "changedDate": fields.get("System.ChangedDate"),
        "reason": fields.get("System.Reason"),
        "priority": fields.get("Microsoft.VSTS.Common.Priority"),
        "tags": fields.get("System.Tags"),
        "description": fields.get("System.Description"),
        "acceptanceCriteria": fields.get("Microsoft.VSTS.Common.AcceptanceCriteria"),
        "parent": fields.get("System.Parent"),
        "allFields": fields  # Include all fields for advanced use
    }


def main():
    parser = argparse.ArgumentParser(
        description="Query Azure DevOps work items."
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to .ado/config.json file",
        default=".ado/config.json"
    )
    parser.add_argument(
        "--preset", "-p",
        help="Use a preset query",
        choices=list(QUERY_PRESETS.keys())
    )
    parser.add_argument(
        "--wiql", "-w",
        help="Custom WIQL query"
    )
    parser.add_argument(
        "--id", "-i",
        type=int,
        help="Get a specific work item by ID"
    )
    parser.add_argument(
        "--list-presets",
        action="store_true",
        help="List available presets"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file (default: stdout)"
    )
    
    args = parser.parse_args()
    
    # List presets
    if args.list_presets:
        print("Available presets:")
        for name, query in QUERY_PRESETS.items():
            # Get first line of description
            desc = query.strip().split('\n')[0]
            print(f"  {name}")
        return 0
    
    # Load config
    try:
        org, project = load_config(args.config)
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        print("Run configuration wizard first.", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"Error loading config: {e}", file=sys.stderr)
        return 1
    
    # Execute query
    if args.id:
        result = get_work_item(org, args.id)
        if not result:
            print(f"Work item {args.id} not found", file=sys.stderr)
            return 1
        results = [result]
    elif args.preset:
        wiql = QUERY_PRESETS[args.preset]
        results = query_work_items(org, project, wiql)
    elif args.wiql:
        results = query_work_items(org, project, args.wiql)
    else:
        print("Error: Specify --preset, --wiql, or --id", file=sys.stderr)
        return 1
    
    # Output
    output = {
        "organization": org,
        "project": project,
        "queryTime": datetime.utcnow().isoformat() + "Z",
        "count": len(results) if isinstance(results, list) else 1,
        "items": results if isinstance(results, list) else [results]
    }
    
    json_output = json.dumps(output, indent=2, default=str)
    
    if args.output:
        Path(args.output).write_text(json_output)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(json_output)
    
    print(f"\nFound {output['count']} work items", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

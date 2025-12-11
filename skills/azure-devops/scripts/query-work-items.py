#!/usr/bin/env python3
"""
query-work-items.py - Query Azure DevOps work items with presets.

Usage:
    python query-work-items.py --config .ado/config.json --preset my-active
    python query-work-items.py --config .ado/config.json --wiql "SELECT ... FROM workitems WHERE ..."
    python query-work-items.py --config .ado/config.json --id 1234
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional


QUERY_PRESETS = {
    "my-active": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems WHERE [System.AssignedTo] = @Me AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [System.ChangedDate] DESC
    """,
    "my-all": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems WHERE [System.AssignedTo] = @Me ORDER BY [System.ChangedDate] DESC
    """,
    "changed-today": """
        SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
        FROM workitems WHERE [System.ChangedDate] >= @Today AND [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """,
    "changed-this-week": """
        SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
        FROM workitems WHERE [System.ChangedDate] >= @Today - 7 AND [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """,
    "completed-this-week": """
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.ClosedDate]
        FROM workitems WHERE [System.State] IN ('Closed', 'Done') AND [System.ChangedDate] >= @Today - 7 AND [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """,
    "recent-bugs": """
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Priority]
        FROM workitems WHERE [System.WorkItemType] = 'Bug' AND [System.ChangedDate] >= @Today - 14
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC
    """,
    "sprint-items": """
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems WHERE [System.IterationPath] = @CurrentIteration AND [System.State] NOT IN ('Removed')
        ORDER BY [System.WorkItemType], [System.State]
    """,
    "blocked": """
        SELECT [System.Id], [System.Title], [System.State], [System.Tags]
        FROM workitems WHERE ([System.Tags] CONTAINS 'Blocked' OR [System.State] = 'Blocked')
        AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
    """
}


def run_az_command(args: list, timeout: int = 60):
    cmd = ["az"] + args + ["--output", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return None
        return json.loads(result.stdout) if result.stdout.strip() else None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def query_work_items(org: str, project: str, wiql: str) -> list[dict]:
    wiql_clean = " ".join(wiql.split())
    result = run_az_command(["boards", "query", "--organization", org, "--project", project, "--wiql", wiql_clean])
    if not result:
        return []
    
    work_items = []
    for item in result:
        if "id" in item:
            details = run_az_command(["boards", "work-item", "show", "--organization", org, "--id", str(item["id"])], timeout=30)
            if details:
                fields = details.get("fields", {})
                assigned = fields.get("System.AssignedTo")
                work_items.append({
                    "id": details.get("id"), "url": details.get("url"),
                    "title": fields.get("System.Title"), "state": fields.get("System.State"),
                    "workItemType": fields.get("System.WorkItemType"),
                    "assignedTo": assigned.get("displayName") if isinstance(assigned, dict) else assigned,
                    "areaPath": fields.get("System.AreaPath"), "iterationPath": fields.get("System.IterationPath"),
                    "changedDate": fields.get("System.ChangedDate"), "priority": fields.get("Microsoft.VSTS.Common.Priority"),
                    "tags": fields.get("System.Tags"), "parent": fields.get("System.Parent")
                })
    return work_items


def get_work_item(org: str, item_id: int) -> Optional[dict]:
    details = run_az_command(["boards", "work-item", "show", "--organization", org, "--id", str(item_id)])
    if not details:
        return None
    fields = details.get("fields", {})
    assigned = fields.get("System.AssignedTo")
    return {
        "id": details.get("id"), "title": fields.get("System.Title"), "state": fields.get("System.State"),
        "workItemType": fields.get("System.WorkItemType"),
        "assignedTo": assigned.get("displayName") if isinstance(assigned, dict) else None,
        "description": fields.get("System.Description"), "allFields": fields
    }


def main():
    parser = argparse.ArgumentParser(description="Query Azure DevOps work items.")
    parser.add_argument("--config", "-c", default=".ado/config.json", help="Path to config file")
    parser.add_argument("--preset", "-p", choices=list(QUERY_PRESETS.keys()), help="Use preset query")
    parser.add_argument("--wiql", "-w", help="Custom WIQL query")
    parser.add_argument("--id", "-i", type=int, help="Get specific work item by ID")
    parser.add_argument("--list-presets", action="store_true", help="List available presets")
    parser.add_argument("--output", "-o", help="Output file (default: stdout)")
    args = parser.parse_args()
    
    if args.list_presets:
        print("Available presets:", *QUERY_PRESETS.keys(), sep="\n  ")
        return 0
    
    try:
        config = json.loads(Path(args.config).read_text())
        org, project = config["organization"], config["project"]
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        return 1
    
    if args.id:
        results = [get_work_item(org, args.id)]
    elif args.preset:
        results = query_work_items(org, project, QUERY_PRESETS[args.preset])
    elif args.wiql:
        results = query_work_items(org, project, args.wiql)
    else:
        print("Error: Specify --preset, --wiql, or --id", file=sys.stderr)
        return 1
    
    output = {"organization": org, "project": project, "queryTime": datetime.utcnow().isoformat() + "Z", "count": len(results), "items": results}
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

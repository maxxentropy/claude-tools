#!/usr/bin/env python3
"""
query-work-items.py - Query Azure DevOps work items with presets.

Uses batch API for efficient work item retrieval (up to 200 per request).
Includes rate limiting support and proper error handling.

Usage:
    python query-work-items.py --config .ado/config.json --preset my-active
    python query-work-items.py --config .ado/config.json --wiql "SELECT ... FROM workitems WHERE ..."
    python query-work-items.py --config .ado/config.json --id 1234 1235 1236
    python query-work-items.py --config .ado/config.json --preset my-active --format table

Best Practices:
    - Presets use optimized queries with date/range limiting
    - Batch API fetches work item details (no N+1 queries)
    - Rate limiting handled automatically with exponential backoff
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, Union, List, Dict, Any

# Import the ADO client module
try:
    from ado_client import (
        ADOClient, ADOConfig, ADOError, ErrorType,
        load_client, format_work_item
    )
    HAS_CLIENT = True
except ImportError:
    HAS_CLIENT = False


# Optimized query presets following Microsoft best practices:
# - Date/range limiting clauses near the top
# - Avoid Contains operator (use Contains Words when available)
# - Minimize Or operators
# - Specify fields explicitly to reduce payload
QUERY_PRESETS = {
    "my-active": {
        "description": "Active work items assigned to me",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
                   [System.AreaPath], [System.IterationPath], [Microsoft.VSTS.Common.Priority]
            FROM workitems
            WHERE [System.AssignedTo] = @Me
              AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
            ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "System.WorkItemType",
                   "System.AreaPath", "System.IterationPath", "Microsoft.VSTS.Common.Priority",
                   "System.AssignedTo", "System.ChangedDate"]
    },
    "my-all": {
        "description": "All work items assigned to me",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
            FROM workitems
            WHERE [System.AssignedTo] = @Me
            ORDER BY [System.ChangedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "System.WorkItemType",
                   "System.AssignedTo", "System.ChangedDate"]
    },
    "changed-today": {
        "description": "Items I changed today",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
            FROM workitems
            WHERE [System.ChangedDate] >= @Today
              AND [System.AssignedTo] = @Me
            ORDER BY [System.ChangedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "System.ChangedDate",
                   "System.WorkItemType", "System.AssignedTo"]
    },
    "changed-this-week": {
        "description": "Items I changed in the past 7 days",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
            FROM workitems
            WHERE [System.ChangedDate] >= @Today - 7
              AND [System.AssignedTo] = @Me
            ORDER BY [System.ChangedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "System.ChangedDate",
                   "System.WorkItemType", "System.AssignedTo"]
    },
    "completed-this-week": {
        "description": "Items completed in the past 7 days",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.ClosedDate]
            FROM workitems
            WHERE [System.ChangedDate] >= @Today - 7
              AND [System.AssignedTo] = @Me
              AND [System.State] IN ('Closed', 'Done')
            ORDER BY [System.ChangedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "System.ChangedDate",
                   "Microsoft.VSTS.Common.ClosedDate", "System.WorkItemType", "System.AssignedTo"]
    },
    "recent-bugs": {
        "description": "Bugs changed in the past 14 days",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Priority]
            FROM workitems
            WHERE [System.ChangedDate] >= @Today - 14
              AND [System.WorkItemType] = 'Bug'
            ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "Microsoft.VSTS.Common.Priority",
                   "System.WorkItemType", "System.AssignedTo", "System.ChangedDate"]
    },
    "sprint-items": {
        "description": "Items in current sprint/iteration",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
            FROM workitems
            WHERE [System.IterationPath] = @CurrentIteration
              AND [System.State] NOT IN ('Removed')
            ORDER BY [System.WorkItemType], [Microsoft.VSTS.Common.Priority] ASC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "System.WorkItemType",
                   "System.AssignedTo", "System.IterationPath", "Microsoft.VSTS.Common.Priority"]
    },
    "blocked": {
        "description": "Blocked work items",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [System.Tags]
            FROM workitems
            WHERE [System.State] NOT IN ('Closed', 'Done', 'Removed')
              AND ([System.Tags] CONTAINS 'Blocked' OR [System.State] = 'Blocked')
            ORDER BY [System.ChangedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "System.Tags",
                   "System.WorkItemType", "System.AssignedTo", "System.ChangedDate"]
    },
    "created-by-me": {
        "description": "Items I created in the past 30 days",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [System.CreatedDate]
            FROM workitems
            WHERE [System.CreatedDate] >= @Today - 30
              AND [System.CreatedBy] = @Me
            ORDER BY [System.CreatedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "System.CreatedDate",
                   "System.WorkItemType", "System.AssignedTo"]
    },
    "high-priority": {
        "description": "High priority (P1/P2) active items",
        "wiql": """
            SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Priority]
            FROM workitems
            WHERE [Microsoft.VSTS.Common.Priority] <= 2
              AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
            ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
        """,
        "fields": ["System.Id", "System.Title", "System.State", "Microsoft.VSTS.Common.Priority",
                   "System.WorkItemType", "System.AssignedTo", "System.ChangedDate"]
    }
}


def run_az_command(args: list, timeout: int = 60) -> Optional[dict | list]:
    """Run Azure CLI command and return JSON result (fallback method)."""
    cmd = ["az"] + args + ["--output", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            print(f"Error: {result.stderr}", file=sys.stderr)
            return None
        return json.loads(result.stdout) if result.stdout.strip() else None
    except subprocess.TimeoutExpired:
        print(f"Error: Command timed out after {timeout}s", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON response: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        return None


def query_with_cli_fallback(
    org: str,
    project: str,
    wiql: str,
    fields: Optional[list[str]] = None
) -> list[dict]:
    """
    Query work items using CLI (fallback when ado_client not available).
    Still uses batch approach but via CLI commands.
    """
    wiql_clean = " ".join(wiql.split())

    # Run WIQL query to get IDs
    result = run_az_command([
        "boards", "query",
        "--organization", org,
        "--project", project,
        "--wiql", wiql_clean
    ])

    if not result:
        return []

    # Extract IDs
    ids = [item["id"] for item in result if "id" in item]

    if not ids:
        return []

    # Fetch details in batches of 200 (Azure DevOps limit)
    BATCH_SIZE = 200
    all_items = []

    for i in range(0, len(ids), BATCH_SIZE):
        batch_ids = ids[i:i + BATCH_SIZE]
        id_str = ",".join(str(id) for id in batch_ids)

        # Use az boards work-item show with multiple IDs
        # Unfortunately, CLI doesn't support batch, so we use individual calls
        # but this is the fallback - prefer ado_client for production
        for item_id in batch_ids:
            details = run_az_command([
                "boards", "work-item", "show",
                "--organization", org,
                "--id", str(item_id)
            ], timeout=30)

            if details:
                item_fields = details.get("fields", {})
                assigned = item_fields.get("System.AssignedTo")
                all_items.append({
                    "id": details.get("id"),
                    "url": details.get("url"),
                    "title": item_fields.get("System.Title"),
                    "state": item_fields.get("System.State"),
                    "workItemType": item_fields.get("System.WorkItemType"),
                    "assignedTo": assigned.get("displayName") if isinstance(assigned, dict) else assigned,
                    "areaPath": item_fields.get("System.AreaPath"),
                    "iterationPath": item_fields.get("System.IterationPath"),
                    "changedDate": item_fields.get("System.ChangedDate"),
                    "priority": item_fields.get("Microsoft.VSTS.Common.Priority"),
                    "tags": item_fields.get("System.Tags"),
                    "parent": item_fields.get("System.Parent")
                })

    return all_items


def query_work_items(
    config: dict,
    wiql: str,
    fields: Optional[list[str]] = None,
    verbose: bool = False
) -> list[dict]:
    """
    Query work items using the best available method.

    Prefers ado_client (REST API with batch support) over CLI fallback.
    """
    org = config["organization"]
    project = config["project"]

    if HAS_CLIENT:
        try:
            client = ADOClient(ADOConfig(org, project), verbose=verbose)
            items = client.query_work_items(wiql, fields=fields)
            return [format_work_item(item) for item in items]
        except ADOError as e:
            if e.error_type == ErrorType.AUTH_FAILED:
                print(f"Authentication failed. Falling back to CLI.", file=sys.stderr)
            else:
                print(f"API error: {e}. Falling back to CLI.", file=sys.stderr)

    # Fallback to CLI-based query
    return query_with_cli_fallback(org, project, wiql, fields)


def get_work_item_by_id(
    config: dict,
    item_id: int,
    verbose: bool = False
) -> Optional[dict]:
    """Get a single work item by ID."""
    org = config["organization"]
    project = config["project"]

    if HAS_CLIENT:
        try:
            client = ADOClient(ADOConfig(org, project), verbose=verbose)
            item = client.get_work_item(item_id)
            if item:
                return format_work_item(item)
            return None
        except ADOError as e:
            print(f"API error: {e}. Falling back to CLI.", file=sys.stderr)

    # Fallback
    details = run_az_command([
        "boards", "work-item", "show",
        "--organization", org,
        "--id", str(item_id)
    ])

    if not details:
        return None

    fields = details.get("fields", {})
    assigned = fields.get("System.AssignedTo")
    return {
        "id": details.get("id"),
        "title": fields.get("System.Title"),
        "state": fields.get("System.State"),
        "workItemType": fields.get("System.WorkItemType"),
        "assignedTo": assigned.get("displayName") if isinstance(assigned, dict) else None,
        "description": fields.get("System.Description"),
        "allFields": fields
    }


def get_work_items_batch(
    config: dict,
    ids: list[int],
    verbose: bool = False
) -> list[dict]:
    """Get multiple work items by IDs (batch operation)."""
    org = config["organization"]
    project = config["project"]

    if HAS_CLIENT:
        try:
            client = ADOClient(ADOConfig(org, project), verbose=verbose)
            items = client.get_work_items_batch(ids)
            return [format_work_item(item) for item in items]
        except ADOError as e:
            print(f"API error: {e}. Falling back to CLI.", file=sys.stderr)

    # Fallback: fetch one at a time
    results = []
    for item_id in ids:
        item = get_work_item_by_id(config, item_id, verbose)
        if item:
            results.append(item)
    return results


def format_as_table(items: list[dict], columns: Optional[list[str]] = None) -> str:
    """Format work items as a table for terminal output."""
    if not items:
        return "No work items found."

    default_columns = ["id", "workItemType", "state", "title"]
    columns = columns or default_columns

    # Calculate column widths
    widths = {}
    for col in columns:
        values = [str(item.get(col, ""))[:50] for item in items]
        widths[col] = max(len(col), max(len(v) for v in values) if values else len(col))

    # Build header
    header = " | ".join(col.ljust(widths[col]) for col in columns)
    separator = "-+-".join("-" * widths[col] for col in columns)

    # Build rows
    rows = []
    for item in items:
        row = " | ".join(str(item.get(col, ""))[:widths[col]].ljust(widths[col]) for col in columns)
        rows.append(row)

    return f"{header}\n{separator}\n" + "\n".join(rows)


def main():
    parser = argparse.ArgumentParser(
        description="Query Azure DevOps work items with presets or custom WIQL.",
        epilog="""
Examples:
  %(prog)s --preset my-active                  # Active items assigned to me
  %(prog)s --preset changed-this-week          # Items changed in past 7 days
  %(prog)s --id 1234 1235 1236                 # Get specific work items
  %(prog)s --wiql "SELECT ... FROM workitems"  # Custom WIQL query
  %(prog)s --preset my-active --format table   # Display as table
        """
    )
    parser.add_argument("--config", "-c", default=".ado/config.json",
                        help="Path to config file (default: .ado/config.json)")
    parser.add_argument("--preset", "-p", choices=list(QUERY_PRESETS.keys()),
                        help="Use preset query")
    parser.add_argument("--wiql", "-w",
                        help="Custom WIQL query")
    parser.add_argument("--id", "-i", type=int, nargs="+",
                        help="Get specific work item(s) by ID")
    parser.add_argument("--list-presets", action="store_true",
                        help="List available presets with descriptions")
    parser.add_argument("--output", "-o",
                        help="Output file (default: stdout)")
    parser.add_argument("--format", "-f", choices=["json", "table"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose output")
    parser.add_argument("--max-results", "-n", type=int, default=200,
                        help="Maximum results to return (default: 200)")

    args = parser.parse_args()

    # List presets
    if args.list_presets:
        print("Available presets:\n")
        for name, preset in QUERY_PRESETS.items():
            print(f"  {name:20} - {preset['description']}")
        return 0

    # Load config
    try:
        config = json.loads(Path(args.config).read_text())
    except FileNotFoundError:
        print(f"Error: Config file not found: {args.config}", file=sys.stderr)
        print("Run the configuration wizard first or create .ado/config.json", file=sys.stderr)
        return 1
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in config file: {e}", file=sys.stderr)
        return 1

    # Execute query
    results: list[dict] = []

    if args.id:
        results = get_work_items_batch(config, args.id, verbose=args.verbose)
    elif args.preset:
        preset = QUERY_PRESETS[args.preset]
        results = query_work_items(
            config, preset["wiql"],
            fields=preset.get("fields"),
            verbose=args.verbose
        )
        # Limit results
        if len(results) > args.max_results:
            results = results[:args.max_results]
            print(f"Note: Results limited to {args.max_results} items", file=sys.stderr)
    elif args.wiql:
        results = query_work_items(config, args.wiql, verbose=args.verbose)
        if len(results) > args.max_results:
            results = results[:args.max_results]
    else:
        parser.print_help()
        print("\nError: Specify --preset, --wiql, or --id", file=sys.stderr)
        return 1

    # Format output
    if args.format == "table":
        output_str = format_as_table(results)
    else:
        output = {
            "organization": config["organization"],
            "project": config["project"],
            "queryTime": datetime.utcnow().isoformat() + "Z",
            "count": len(results),
            "items": results
        }
        output_str = json.dumps(output, indent=2, default=str)

    # Write output
    if args.output:
        Path(args.output).write_text(output_str)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output_str)

    print(f"\nFound {len(results)} work item(s)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

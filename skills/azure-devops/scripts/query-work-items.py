#!/usr/bin/env python3
"""
query-work-items.py - Query Azure DevOps work items with presets.

Uses batch API for efficient work item retrieval (up to 200 per request).
Includes rate limiting support and proper error handling.
Integrates with local work item index for faster lookups.

Usage:
    python query-work-items.py --config .ado/config.json --preset my-active
    python query-work-items.py --config .ado/config.json --wiql "SELECT ... FROM workitems WHERE ..."
    python query-work-items.py --config .ado/config.json --id 1234 1235 1236
    python query-work-items.py --config .ado/config.json --preset my-active --format table
    python query-work-items.py --id 1234 --cache-only                        # Use cached data only
    python query-work-items.py --context                                      # Show current work item context

Best Practices:
    - Presets use optimized queries with date/range limiting
    - Batch API fetches work item details (no N+1 queries)
    - Rate limiting handled automatically with exponential backoff
    - Use --cache-only for quick lookups without network calls
    - Run sync_work_items.py periodically to keep cache fresh
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

# Import work item index modules
try:
    from work_item_index import WorkItemIndexManager, WorkItem, IndexStaleness
    from work_item_context import (
        WorkItemContextDetector, GitContext, BranchParser,
        format_context_summary
    )
    HAS_INDEX = True
except ImportError:
    HAS_INDEX = False

# Import query presets
try:
    from query_presets import QUERY_PRESETS, list_presets, get_categories
    HAS_PRESETS_MODULE = True
except ImportError:
    HAS_PRESETS_MODULE = False
    # Fallback: minimal presets for backwards compatibility
    QUERY_PRESETS = {
        "my-active": {
            "description": "Active work items assigned to me",
            "wiql": """
                SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
                FROM workitems
                WHERE [System.AssignedTo] = @Me
                  AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
                ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
            """,
            "fields": ["System.Id", "System.Title", "System.State", "System.WorkItemType",
                       "System.AssignedTo", "System.ChangedDate"]
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


# ============================================================================
# Cache/Index Functions
# ============================================================================

def work_item_to_dict(item: "WorkItem") -> dict:
    """Convert WorkItem dataclass to dictionary for output."""
    return {
        "id": item.id,
        "title": item.title,
        "state": item.state,
        "workItemType": item.work_item_type,
        "assignedTo": item.assigned_to,
        "areaPath": item.area_path,
        "iterationPath": item.iteration_path,
        "priority": item.priority,
        "tags": ";".join(item.tags) if item.tags else None,
        "parent": item.parent_id,
        "url": item.url,
        "changedDate": item.changed_date.isoformat() if item.changed_date else None,
        "cached": True,
        "lastFetched": item.last_fetched.isoformat() if item.last_fetched else None
    }


def get_cached_work_items(
    index_manager: "WorkItemIndexManager",
    ids: list[int]
) -> tuple[list[dict], list[int]]:
    """
    Get work items from cache.

    Returns:
        Tuple of (found_items, missing_ids)
    """
    found = []
    missing = []

    for item_id in ids:
        item = index_manager.get_work_item(item_id)
        if item:
            found.append(work_item_to_dict(item))
        else:
            missing.append(item_id)

    return found, missing


def search_cached_work_items(
    index_manager: "WorkItemIndexManager",
    query: str,
    limit: int = 50
) -> list[dict]:
    """Search work items in cache."""
    items = index_manager.search_items(query, limit=limit)
    return [work_item_to_dict(item) for item in items]


def show_context(index_path: str = ".ado/work-items.json", config_path: str = ".ado/config.json") -> int:
    """Show current work item context and return exit code."""
    if not HAS_INDEX:
        print("Error: Work item index module not available", file=sys.stderr)
        return 1

    index_manager = WorkItemIndexManager(index_path)
    detector = WorkItemContextDetector(index_manager)

    # Use existence check to provide more helpful output
    try:
        from work_item_context import format_existence_check_summary
        check_result = detector.detect_with_existence_check(config_path)
        context = check_result["context"]
        print(format_existence_check_summary(check_result))
    except (ImportError, AttributeError):
        # Fallback to basic context detection
        context = detector.detect()
        print(format_context_summary(context))

    # Show staleness info
    staleness = index_manager.get_staleness()
    if staleness != IndexStaleness.FRESH:
        print(f"\nNote: Index is {staleness.value}. Run sync_work_items.py to refresh.")

    return 0 if context.has_context else 1


def update_index_from_results(
    index_manager: "WorkItemIndexManager",
    items: list[dict]
) -> int:
    """
    Update local index with query results.

    Returns:
        Number of items updated
    """
    count = 0
    for item in items:
        # Parse tags
        tags = []
        if item.get("tags"):
            tags = [t.strip() for t in item["tags"].split(";") if t.strip()]

        # Parse dates
        changed_date = None
        if item.get("changedDate"):
            try:
                changed_date = datetime.fromisoformat(item["changedDate"].replace("Z", "+00:00"))
            except (ValueError, AttributeError):
                pass

        work_item = WorkItem(
            id=item.get("id", 0),
            title=item.get("title", ""),
            state=item.get("state", ""),
            work_item_type=item.get("workItemType", ""),
            assigned_to=item.get("assignedTo"),
            area_path=item.get("areaPath"),
            iteration_path=item.get("iterationPath"),
            priority=item.get("priority"),
            tags=tags,
            parent_id=item.get("parent"),
            url=item.get("url"),
            last_fetched=datetime.utcnow(),
            changed_date=changed_date
        )
        index_manager.upsert_work_item(work_item)
        count += 1

    return count


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
  %(prog)s --id 1234 --cache-only              # Get from cache only (no network)
  %(prog)s --search "auth bug"                 # Search cached work items
  %(prog)s --context                           # Show current work item context
        """
    )
    parser.add_argument("--config", "-c", default=".ado/config.json",
                        help="Path to config file (default: .ado/config.json)")
    parser.add_argument("--preset", "-p", metavar="NAME",
                        help="Use preset query (see --list-presets)")
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

    # Cache/Index options
    cache_group = parser.add_argument_group("Cache options")
    cache_group.add_argument("--index", default=".ado/work-items.json",
                             help="Path to work item index (default: .ado/work-items.json)")
    cache_group.add_argument("--cache-only", action="store_true",
                             help="Use cached data only, don't query ADO")
    cache_group.add_argument("--update-index", action="store_true",
                             help="Update local index with query results")
    cache_group.add_argument("--search", "-s", metavar="QUERY",
                             help="Search cached work items by title/tags")
    cache_group.add_argument("--context", action="store_true",
                             help="Show current work item context (from branch/commits)")

    args = parser.parse_args()

    # List presets
    if args.list_presets:
        if HAS_PRESETS_MODULE:
            print("Azure DevOps Query Presets")
            print("=" * 60)
            print(list_presets(verbose=args.verbose))
            print(f"\nTotal: {len(QUERY_PRESETS)} presets in {len(get_categories())} categories")
            print("\nUsage: python query-work-items.py --preset <name>")
        else:
            print("Available presets:\n")
            for name, preset in QUERY_PRESETS.items():
                print(f"  {name:20} - {preset['description']}")
        return 0

    # Show context (checks ADO if work item not in cache)
    if args.context:
        return show_context(args.index, args.config)

    # Initialize index manager if available
    index_manager = None
    if HAS_INDEX:
        index_manager = WorkItemIndexManager(args.index)

    # Handle cache-only operations that don't need ADO config
    if args.search:
        if not index_manager:
            print("Error: Work item index module not available", file=sys.stderr)
            return 1
        results = search_cached_work_items(index_manager, args.search, limit=args.max_results)
        if not results:
            print(f"No cached items matching '{args.search}'", file=sys.stderr)
            staleness = index_manager.get_staleness()
            if staleness in (IndexStaleness.NEVER_SYNCED, IndexStaleness.VERY_STALE):
                print("Tip: Run sync_work_items.py to populate the cache", file=sys.stderr)
            return 0

        # Format and output
        if args.format == "table":
            output_str = format_as_table(results)
        else:
            output = {
                "source": "cache",
                "query": args.search,
                "queryTime": datetime.utcnow().isoformat() + "Z",
                "count": len(results),
                "items": results
            }
            output_str = json.dumps(output, indent=2, default=str)

        if args.output:
            Path(args.output).write_text(output_str)
            print(f"Results written to {args.output}", file=sys.stderr)
        else:
            print(output_str)

        print(f"\nFound {len(results)} cached work item(s)", file=sys.stderr)
        return 0

    # Handle cache-only ID lookup
    if args.cache_only and args.id:
        if not index_manager:
            print("Error: Work item index module not available", file=sys.stderr)
            return 1

        results, missing = get_cached_work_items(index_manager, args.id)

        if missing:
            print(f"Warning: {len(missing)} item(s) not in cache: {missing}", file=sys.stderr)

        if args.format == "table":
            output_str = format_as_table(results)
        else:
            output = {
                "source": "cache",
                "queryTime": datetime.utcnow().isoformat() + "Z",
                "count": len(results),
                "missing": missing,
                "items": results
            }
            output_str = json.dumps(output, indent=2, default=str)

        if args.output:
            Path(args.output).write_text(output_str)
        else:
            print(output_str)

        print(f"\nFound {len(results)} cached work item(s)", file=sys.stderr)
        return 0

    # For other operations, we need config
    config = None
    if not args.cache_only:
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
    from_cache = False

    if args.id:
        # Try cache first for ID lookups
        if index_manager and not args.cache_only:
            cached, missing = get_cached_work_items(index_manager, args.id)
            if not missing:
                # All items found in cache
                results = cached
                from_cache = True
                if args.verbose:
                    print("All items found in cache", file=sys.stderr)
            elif cached and missing:
                # Partial cache hit - fetch only missing from ADO
                if args.verbose:
                    print(f"Cache hit: {len(cached)}, fetching {len(missing)} from ADO", file=sys.stderr)
                remote_results = get_work_items_batch(config, missing, verbose=args.verbose)
                results = cached + remote_results
            else:
                # Cache miss - fetch all from ADO
                results = get_work_items_batch(config, args.id, verbose=args.verbose)
        else:
            results = get_work_items_batch(config, args.id, verbose=args.verbose)

    elif args.preset:
        if args.preset not in QUERY_PRESETS:
            print(f"Error: Unknown preset '{args.preset}'", file=sys.stderr)
            print(f"Use --list-presets to see available presets", file=sys.stderr)
            return 1
        preset = QUERY_PRESETS[args.preset]
        if args.verbose:
            print(f"Running preset: {args.preset}", file=sys.stderr)
            if preset.get("use_case"):
                print(f"  Use case: {preset['use_case']}", file=sys.stderr)
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
        print("\nError: Specify --preset, --wiql, --id, --search, or --context", file=sys.stderr)
        return 1

    # Update index with results if requested
    if args.update_index and index_manager and results and not from_cache:
        updated = update_index_from_results(index_manager, results)
        index_manager.save()
        if args.verbose:
            print(f"Updated {updated} items in local index", file=sys.stderr)

    # Format output
    if args.format == "table":
        output_str = format_as_table(results)
    else:
        output = {
            "source": "cache" if from_cache else "ado",
            "queryTime": datetime.utcnow().isoformat() + "Z",
            "count": len(results),
            "items": results
        }
        if config:
            output["organization"] = config.get("organization")
            output["project"] = config.get("project")
        output_str = json.dumps(output, indent=2, default=str)

    # Write output
    if args.output:
        Path(args.output).write_text(output_str)
        print(f"Results written to {args.output}", file=sys.stderr)
    else:
        print(output_str)

    source_note = " (from cache)" if from_cache else ""
    print(f"\nFound {len(results)} work item(s){source_note}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

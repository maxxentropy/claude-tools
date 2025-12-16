#!/usr/bin/env python3
"""
Sync Work Items - Populate local index from Azure DevOps.

Syncs work items from ADO to the local index for faster queries and context detection.
Uses batch API for efficient retrieval and incremental sync when possible.

Usage:
    python sync_work_items.py                      # Sync with defaults
    python sync_work_items.py --full               # Full sync (ignore incremental)
    python sync_work_items.py --preset my-active   # Sync specific preset
    python sync_work_items.py --status             # Show sync status only
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

from work_item_index import WorkItemIndexManager, WorkItem, IndexStaleness

# Import ADO client if available
try:
    from ado_client import ADOClient, ADOConfig, ADOError, format_work_item
    HAS_CLIENT = True
except ImportError:
    HAS_CLIENT = False

# Import query presets
try:
    from importlib import import_module
    query_module = import_module("query-work-items")
    QUERY_PRESETS = getattr(query_module, "QUERY_PRESETS", {})
    query_work_items = getattr(query_module, "query_work_items", None)
except (ImportError, AttributeError):
    # Fallback presets
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
                       "System.AssignedTo", "System.ChangedDate", "System.Tags", "System.Parent"]
        }
    }
    query_work_items = None


# Default presets to sync
DEFAULT_SYNC_PRESETS = ["my-active", "changed-this-week", "sprint-items"]


def load_config(config_path: str = ".ado/config.json") -> Optional[Dict[str, Any]]:
    """Load ADO configuration."""
    try:
        return json.loads(Path(config_path).read_text())
    except FileNotFoundError:
        return None
    except json.JSONDecodeError:
        return None


def query_ado(config: Dict, wiql: str, fields: Optional[List[str]] = None,
              verbose: bool = False) -> List[Dict]:
    """
    Query ADO for work items.

    Uses ado_client if available, otherwise falls back to query-work-items module.
    """
    if query_work_items:
        return query_work_items(config, wiql, fields=fields, verbose=verbose)

    if not HAS_CLIENT:
        print("Error: Neither ado_client nor query-work-items module available", file=sys.stderr)
        return []

    try:
        client = ADOClient(ADOConfig(config["organization"], config["project"]), verbose=verbose)
        items = client.query_work_items(wiql, fields=fields)
        return [format_work_item(item) for item in items]
    except ADOError as e:
        print(f"Error querying ADO: {e}", file=sys.stderr)
        return []


def convert_ado_item_to_work_item(ado_item: Dict) -> WorkItem:
    """Convert ADO query result to WorkItem for index."""
    # Parse dates
    changed_date = None
    if ado_item.get("changedDate"):
        try:
            changed_date = datetime.fromisoformat(ado_item["changedDate"].replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            pass

    # Extract tags
    tags = []
    if ado_item.get("tags"):
        tags = [t.strip() for t in ado_item["tags"].split(";") if t.strip()]

    return WorkItem(
        id=ado_item.get("id", 0),
        title=ado_item.get("title", ""),
        state=ado_item.get("state", ""),
        work_item_type=ado_item.get("workItemType", ""),
        assigned_to=ado_item.get("assignedTo"),
        area_path=ado_item.get("areaPath"),
        iteration_path=ado_item.get("iterationPath"),
        priority=ado_item.get("priority"),
        tags=tags,
        parent_id=ado_item.get("parent"),
        url=ado_item.get("url"),
        last_fetched=datetime.now(timezone.utc),
        changed_date=changed_date
    )


def sync_preset(
    config: Dict,
    index_manager: WorkItemIndexManager,
    preset_name: str,
    verbose: bool = False
) -> int:
    """
    Sync a specific preset to the index.

    Returns:
        Number of items synced
    """
    preset = QUERY_PRESETS.get(preset_name)
    if not preset:
        print(f"Warning: Unknown preset '{preset_name}', skipping", file=sys.stderr)
        return 0

    if verbose:
        print(f"Syncing preset: {preset_name} - {preset['description']}")

    items = query_ado(config, preset["wiql"], fields=preset.get("fields"), verbose=verbose)

    synced = 0
    for ado_item in items:
        work_item = convert_ado_item_to_work_item(ado_item)
        index_manager.upsert_work_item(work_item)
        synced += 1

    if verbose:
        print(f"  Synced {synced} items from {preset_name}")

    return synced


def sync_incremental(
    config: Dict,
    index_manager: WorkItemIndexManager,
    verbose: bool = False
) -> int:
    """
    Perform incremental sync based on last sync time.

    Queries only items changed since last sync.

    Returns:
        Number of items synced
    """
    last_sync = index_manager.index.last_sync
    if not last_sync:
        if verbose:
            print("No previous sync found, performing full sync")
        return sync_full(config, index_manager, verbose=verbose)

    # Query items changed since last sync
    # Add 1 hour buffer to account for any timing issues
    since = last_sync - timedelta(hours=1)
    since_str = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    wiql = f"""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AreaPath], [System.IterationPath], [Microsoft.VSTS.Common.Priority],
               [System.AssignedTo], [System.ChangedDate], [System.Tags], [System.Parent]
        FROM workitems
        WHERE [System.ChangedDate] >= '{since_str}'
          AND [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """

    if verbose:
        print(f"Incremental sync: items changed since {since.isoformat()}")

    items = query_ado(config, wiql, verbose=verbose)

    synced = 0
    for ado_item in items:
        work_item = convert_ado_item_to_work_item(ado_item)
        index_manager.upsert_work_item(work_item)
        synced += 1

    if verbose:
        print(f"Incremental sync completed: {synced} items updated")

    return synced


def sync_full(
    config: Dict,
    index_manager: WorkItemIndexManager,
    presets: Optional[List[str]] = None,
    verbose: bool = False
) -> int:
    """
    Perform full sync of specified presets.

    Returns:
        Total number of items synced
    """
    presets = presets or DEFAULT_SYNC_PRESETS

    total_synced = 0
    for preset_name in presets:
        if preset_name in QUERY_PRESETS:
            synced = sync_preset(config, index_manager, preset_name, verbose=verbose)
            total_synced += synced

    return total_synced


def show_status(index_manager: WorkItemIndexManager) -> None:
    """Display current sync status."""
    index = index_manager.index
    staleness = index_manager.get_staleness()

    print("Work Item Index Status")
    print("=" * 50)

    if index.last_sync:
        age = datetime.now(timezone.utc) - index.last_sync
        print(f"Last sync: {index.last_sync.isoformat()}")
        print(f"Age: {age.total_seconds() / 3600:.1f} hours")
    else:
        print("Last sync: Never")

    print(f"Staleness: {staleness.value}")
    print(f"Total items: {len(index.work_items)}")
    print(f"Branch mappings: {len(index.branch_mappings)}")

    if index.work_items:
        # Count by state
        states: Dict[str, int] = {}
        for item in index.work_items.values():
            state = item.state or "Unknown"
            states[state] = states.get(state, 0) + 1

        print("\nBy state:")
        for state, count in sorted(states.items(), key=lambda x: -x[1]):
            print(f"  {state}: {count}")

        # Count by type
        types: Dict[str, int] = {}
        for item in index.work_items.values():
            wit = item.work_item_type or "Unknown"
            types[wit] = types.get(wit, 0) + 1

        print("\nBy type:")
        for wit, count in sorted(types.items(), key=lambda x: -x[1]):
            print(f"  {wit}: {count}")


def main():
    parser = argparse.ArgumentParser(
        description="Sync Azure DevOps work items to local index.",
        epilog="""
Examples:
  %(prog)s                        # Smart sync (incremental if recent, full if stale)
  %(prog)s --full                 # Force full sync
  %(prog)s --preset my-active     # Sync specific preset only
  %(prog)s --status               # Show sync status
  %(prog)s --presets              # List available presets
        """
    )
    parser.add_argument("--config", "-c", default=".ado/config.json",
                        help="Path to ADO config file (default: .ado/config.json)")
    parser.add_argument("--index", "-i", default=".ado/work-items.json",
                        help="Path to index file (default: .ado/work-items.json)")
    parser.add_argument("--full", "-f", action="store_true",
                        help="Force full sync (ignore incremental)")
    parser.add_argument("--preset", "-p", choices=list(QUERY_PRESETS.keys()),
                        help="Sync specific preset only")
    parser.add_argument("--status", "-s", action="store_true",
                        help="Show sync status only (no sync)")
    parser.add_argument("--presets", action="store_true",
                        help="List available presets")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Enable verbose output")
    parser.add_argument("--force-stale-threshold", type=int, default=4,
                        help="Hours before index is considered stale (default: 4)")

    args = parser.parse_args()

    # List presets
    if args.presets:
        print("Available sync presets:\n")
        for name, preset in QUERY_PRESETS.items():
            default_marker = " (default)" if name in DEFAULT_SYNC_PRESETS else ""
            print(f"  {name:20} - {preset['description']}{default_marker}")
        return 0

    # Initialize index manager
    index_manager = WorkItemIndexManager(args.index)

    # Status only
    if args.status:
        show_status(index_manager)
        return 0

    # Load config
    config = load_config(args.config)
    if not config:
        print(f"Error: Could not load config from {args.config}", file=sys.stderr)
        print("Run the configuration wizard or create .ado/config.json", file=sys.stderr)
        return 1

    # Determine sync strategy
    staleness = index_manager.get_staleness()

    if args.preset:
        # Sync specific preset
        synced = sync_preset(config, index_manager, args.preset, verbose=args.verbose)
        index_manager.save()
        print(f"Synced {synced} items from preset '{args.preset}'")

    elif args.full or staleness in (IndexStaleness.VERY_STALE, IndexStaleness.NEVER_SYNCED):
        # Full sync
        if args.verbose and not args.full:
            print(f"Index is {staleness.value}, performing full sync")
        synced = sync_full(config, index_manager, verbose=args.verbose)
        index_manager.save()
        print(f"Full sync completed: {synced} items")

    elif staleness in (IndexStaleness.STALE, IndexStaleness.RECENT):
        # Incremental sync
        if args.verbose:
            print(f"Index is {staleness.value}, performing incremental sync")
        synced = sync_incremental(config, index_manager, verbose=args.verbose)
        index_manager.save()
        print(f"Incremental sync completed: {synced} items updated")

    else:
        # Fresh - skip sync
        if args.verbose:
            print("Index is fresh, skipping sync")
        print("Index is up to date (use --full to force sync)")

    return 0


if __name__ == "__main__":
    sys.exit(main())

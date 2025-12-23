#!/usr/bin/env python3
"""
Sync Findings CLI - Sync between local and global findings stores.

This script manages synchronization between per-repo findings (.findings/)
and the global aggregation store (~/.claude/findings/).

Usage:
    # Push local findings to global store
    python3 sync_findings.py --push

    # Push specific finding to global
    python3 sync_findings.py --push --id f-abc123

    # List all repositories with findings
    python3 sync_findings.py --repos

    # Show sync status
    python3 sync_findings.py --status

    # Search across all repos
    python3 sync_findings.py --search "N+1 query"

    # Find similar findings across repos
    python3 sync_findings.py --similar "N+1 query in OrderService"
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from findings_store import FindingsStore, Finding
from global_store import GlobalStore, GlobalFinding, get_repo_name_from_path


class Colors:
    """ANSI color codes."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def color(text: str, *codes: str) -> str:
    """Apply color codes to text."""
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + text + Colors.RESET


def format_global_finding(finding: GlobalFinding, verbose: bool = False) -> str:
    """Format a global finding for display."""
    lines = []

    # Header with global ID and source repo
    lines.append(
        f"{color(finding.global_id, Colors.CYAN, Colors.BOLD)} "
        f"[{color(finding.source_repo, Colors.MAGENTA)}] "
        f"[{color(finding.severity, Colors.YELLOW)}]"
    )

    # Title
    lines.append(f"  {color(finding.title, Colors.WHITE, Colors.BOLD)}")

    # Local ID reference
    lines.append(f"  {color('Local ID:', Colors.DIM)} {finding.id}")

    if verbose:
        # Location
        if finding.file_path:
            loc = finding.file_path
            if finding.line_number:
                loc += f":{finding.line_number}"
            lines.append(f"  {color('Location:', Colors.DIM)} {loc}")

        # Description
        if finding.description:
            lines.append(f"  {color('Description:', Colors.DIM)}")
            for line in finding.description.split("\n")[:3]:
                lines.append(f"    {line[:80]}")

        # Tags
        if finding.tags:
            lines.append(f"  {color('Tags:', Colors.DIM)} {', '.join(finding.tags)}")

        # Timestamps
        lines.append(f"  {color('Discovered:', Colors.DIM)} {finding.discovered_at}")
        lines.append(f"  {color('Synced:', Colors.DIM)} {finding.synced_at}")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Sync findings between local and global stores",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Push all local findings to global
  %(prog)s --push

  # Push a specific finding
  %(prog)s --push --id f-abc123

  # List repositories
  %(prog)s --repos

  # Show sync status
  %(prog)s --status

  # Search across all repos
  %(prog)s --search "performance issue"

  # Find similar findings
  %(prog)s --similar "N+1 query in OrderService"

  # Query global findings
  %(prog)s --global --open
"""
    )

    # Sync operations
    sync_group = parser.add_argument_group("Sync Operations")
    sync_group.add_argument(
        "--push", action="store_true",
        help="Push local findings to global store"
    )
    sync_group.add_argument(
        "--id", type=str,
        help="Specific finding ID to push (use with --push)"
    )
    sync_group.add_argument(
        "--all-open", action="store_true",
        help="Push all open findings (use with --push)"
    )

    # Repository management
    repo_group = parser.add_argument_group("Repository Management")
    repo_group.add_argument(
        "--repos", action="store_true",
        help="List all repositories with findings"
    )
    repo_group.add_argument(
        "--register", type=str, metavar="NAME",
        help="Register current repo with given name"
    )
    repo_group.add_argument(
        "--unregister", type=str, metavar="NAME",
        help="Unregister a repository"
    )

    # Query operations
    query_group = parser.add_argument_group("Query Global Store")
    query_group.add_argument(
        "--global", dest="query_global", action="store_true",
        help="Query the global store"
    )
    query_group.add_argument(
        "--search", type=str,
        help="Search across all repos"
    )
    query_group.add_argument(
        "--similar", type=str,
        help="Find similar findings to given text"
    )
    query_group.add_argument(
        "--repo", type=str,
        help="Filter by repository name"
    )
    query_group.add_argument(
        "--open", action="store_true",
        help="Show open findings only"
    )

    # Status
    status_group = parser.add_argument_group("Status")
    status_group.add_argument(
        "--status", action="store_true",
        help="Show sync status for current repo"
    )
    status_group.add_argument(
        "--stats", action="store_true",
        help="Show global statistics"
    )

    # Maintenance
    maint_group = parser.add_argument_group("Maintenance")
    maint_group.add_argument(
        "--compact", action="store_true",
        help="Compact global store JSONL"
    )
    maint_group.add_argument(
        "--compact-apply", action="store_true",
        help="Apply compaction (dry run without this)"
    )
    maint_group.add_argument(
        "--rebuild-index", action="store_true",
        help="Rebuild global index"
    )

    # Output format
    format_group = parser.add_argument_group("Format")
    format_group.add_argument(
        "--json", action="store_true",
        help="Output as JSON"
    )
    format_group.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose output"
    )
    format_group.add_argument(
        "--limit", type=int, default=20,
        help="Maximum results (default: 20)"
    )

    args = parser.parse_args()

    # Initialize stores
    global_store = GlobalStore()

    # Try to initialize local store (may not exist in current dir)
    local_store = None
    repo_name = None
    repo_path = None
    try:
        local_store = FindingsStore()
        repo_path = str(local_store.root_dir)
        repo_name = get_repo_name_from_path(local_store.root_dir)
    except Exception:
        pass

    # Handle --repos
    if args.repos:
        repos = global_store.list_repositories()
        if args.json:
            print(json.dumps([r.to_dict() for r in repos], indent=2))
        else:
            if not repos:
                print(color("No repositories registered.", Colors.DIM))
            else:
                print(color(f"Registered repositories ({len(repos)}):", Colors.BOLD))
                print()
                for repo in repos:
                    print(f"  {color(repo.name, Colors.CYAN, Colors.BOLD)}")
                    print(f"    Path: {repo.path}")
                    if repo.remote_url:
                        print(f"    Remote: {repo.remote_url}")
                    print(f"    Findings: {repo.finding_count}")
                    if repo.last_synced:
                        print(f"    Last synced: {repo.last_synced}")
                    print()
        sys.exit(0)

    # Handle --register
    if args.register:
        if not repo_path:
            print(color("Error: Not in a git repository", Colors.RED))
            sys.exit(1)

        repo_info = global_store.register_repository(
            name=args.register,
            path=repo_path
        )
        if args.json:
            print(json.dumps(repo_info.to_dict(), indent=2))
        else:
            print(color(f"Registered repository: {args.register}", Colors.GREEN))
            print(f"  Path: {repo_path}")
        sys.exit(0)

    # Handle --unregister
    if args.unregister:
        success = global_store.unregister_repository(args.unregister)
        if args.json:
            print(json.dumps({"unregistered": success, "name": args.unregister}))
        elif success:
            print(color(f"Unregistered: {args.unregister}", Colors.GREEN))
        else:
            print(color(f"Repository not found: {args.unregister}", Colors.RED))
        sys.exit(0 if success else 1)

    # Handle --push
    if args.push:
        if not local_store:
            print(color("Error: Not in a repository with findings", Colors.RED))
            sys.exit(1)

        findings_to_push = []

        if args.id:
            # Push specific finding
            finding = local_store.get_finding(args.id)
            if not finding:
                print(color(f"Finding not found: {args.id}", Colors.RED))
                sys.exit(1)
            findings_to_push = [finding]
        elif args.all_open:
            # Push all open findings
            findings_to_push = local_store.get_open_findings()
        else:
            # Push all findings
            findings_to_push = local_store.query_findings(limit=1000)

        if not findings_to_push:
            print(color("No findings to push.", Colors.DIM))
            sys.exit(0)

        synced = 0
        skipped = 0
        for finding in findings_to_push:
            # Skip private findings
            if "private" in finding.tags:
                skipped += 1
                continue

            global_id = global_store.sync_finding(
                finding_data=finding.to_dict(),
                source_repo=repo_name,
                source_repo_path=repo_path
            )

            if global_id:
                synced += 1
                # Update local finding with global_id
                if not finding.global_id:
                    local_store.update_finding(finding.id, global_id=global_id)

        if args.json:
            print(json.dumps({
                "synced": synced,
                "skipped": skipped,
                "repo": repo_name
            }))
        else:
            print(color(f"Synced {synced} findings to global store", Colors.GREEN))
            if skipped:
                print(color(f"  Skipped {skipped} private findings", Colors.DIM))
        sys.exit(0)

    # Handle --status
    if args.status:
        if not local_store:
            print(color("Error: Not in a repository with findings", Colors.RED))
            sys.exit(1)

        local_stats = local_store.get_statistics()
        global_stats = global_store.get_statistics()
        repo_info = global_store.get_repository(repo_name)

        if args.json:
            print(json.dumps({
                "repo": repo_name,
                "path": repo_path,
                "local": local_stats,
                "global": {
                    "total": global_stats["total"],
                    "from_this_repo": global_stats["by_repo"].get(repo_name, 0)
                },
                "last_synced": repo_info.last_synced if repo_info else None
            }, indent=2))
        else:
            print(color(f"Sync Status: {repo_name}", Colors.BOLD))
            print()
            print(f"  Local findings: {local_stats['total']}")
            print(f"    Open: {local_stats.get('open', 0)}")
            print(f"    Resolved: {local_stats.get('resolved', 0)}")
            print()
            print(f"  Global store:")
            print(f"    Total findings: {global_stats['total']}")
            print(f"    From this repo: {global_stats['by_repo'].get(repo_name, 0)}")
            print(f"    Repositories: {global_stats['repositories']}")
            if repo_info and repo_info.last_synced:
                print(f"    Last synced: {repo_info.last_synced}")
            else:
                print(color("    Not synced yet", Colors.YELLOW))
        sys.exit(0)

    # Handle --stats
    if args.stats:
        stats = global_store.get_statistics()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(color("Global Findings Statistics", Colors.BOLD))
            print()
            print(f"  Total findings: {stats['total']}")
            print(f"  Repositories: {stats['repositories']}")
            print(f"  Open: {stats['open']}")
            print()
            print("  By Repository:")
            for repo, count in sorted(stats["by_repo"].items(), key=lambda x: -x[1]):
                print(f"    {repo}: {count}")
            print()
            print("  By Severity:")
            for sev, count in stats["by_severity"].items():
                print(f"    {sev}: {count}")
        sys.exit(0)

    # Handle --search
    if args.search:
        results = global_store.search(args.search, limit=args.limit)

        if args.json:
            print(json.dumps([f.to_dict() for f in results], indent=2))
        else:
            if not results:
                print(color("No findings found.", Colors.DIM))
            else:
                print(color(f"Found {len(results)} finding(s) matching '{args.search}':", Colors.BOLD))
                print()
                for finding in results:
                    print(format_global_finding(finding, verbose=args.verbose))
                    print()
        sys.exit(0)

    # Handle --similar
    if args.similar:
        results = global_store.find_similar(args.similar)

        if args.json:
            print(json.dumps([
                {"finding": f.to_dict(), "similarity": s}
                for f, s in results[:args.limit]
            ], indent=2))
        else:
            if not results:
                print(color("No similar findings found.", Colors.DIM))
            else:
                print(color(f"Found {len(results)} similar finding(s):", Colors.BOLD))
                print()
                for finding, score in results[:args.limit]:
                    print(f"{color(f'{score:.0%}', Colors.GREEN)} match:")
                    print(format_global_finding(finding, verbose=args.verbose))
                    print()
        sys.exit(0)

    # Handle --global (query global store)
    if args.query_global:
        status_filter = "open" if args.open else None
        results = global_store.query_findings(
            source_repo=args.repo,
            status=status_filter,
            limit=args.limit
        )

        if args.json:
            print(json.dumps([f.to_dict() for f in results], indent=2))
        else:
            if not results:
                print(color("No findings found.", Colors.DIM))
            else:
                print(color(f"Found {len(results)} global finding(s):", Colors.BOLD))
                print()
                for finding in results:
                    print(format_global_finding(finding, verbose=args.verbose))
                    print()
        sys.exit(0)

    # Handle --compact
    if args.compact:
        result = global_store.compact(dry_run=not args.compact_apply)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(color("Global Store Compact Analysis", Colors.BOLD))
            print(f"  Original lines: {result['original_lines']}")
            print(f"  Unique findings: {result['unique_findings']}")
            print(f"  Lines to remove: {result['lines_removed']}")
            if result['dry_run']:
                print(color("\n  (Dry run - use --compact-apply to apply)", Colors.DIM))
            else:
                print(color("\n  Compaction applied.", Colors.GREEN))
        sys.exit(0)

    # Handle --rebuild-index
    if args.rebuild_index:
        index = global_store._rebuild_index()
        if args.json:
            print(json.dumps({
                "rebuilt": True,
                "findings_count": len(index["findings"]),
                "repos_count": len(index["by_repo"])
            }))
        else:
            print(color("Global index rebuilt.", Colors.GREEN))
            print(f"  Findings indexed: {len(index['findings'])}")
            print(f"  Repositories: {len(index['by_repo'])}")
        sys.exit(0)

    # Default: show help
    parser.print_help()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Query Findings CLI - Main interface for the findings system.

Usage:
    # Capture a new finding
    python3 query_findings.py --capture --title "N+1 query" --severity medium

    # Query findings
    python3 query_findings.py --open                    # Open findings
    python3 query_findings.py --ready                   # Ready to work on
    python3 query_findings.py --search "N+1"           # Search
    python3 query_findings.py --branch                  # Current branch

    # Update findings
    python3 query_findings.py --resolve f-abc123       # Mark resolved
    python3 query_findings.py --promote f-abc123       # Promote to ADO

    # Statistics
    python3 query_findings.py --stats
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from findings_store import (
    FindingsStore, Finding,
    FINDING_TYPES, SEVERITIES, CATEGORIES
)


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


def severity_color(severity: str) -> str:
    """Get color for severity level."""
    colors = {
        "critical": Colors.RED + Colors.BOLD,
        "high": Colors.RED,
        "medium": Colors.YELLOW,
        "low": Colors.GREEN,
        "info": Colors.CYAN
    }
    return colors.get(severity, "")


def format_finding(finding: Finding, verbose: bool = False) -> str:
    """Format a finding for display."""
    lines = []

    # Header with ID and status
    status_colors = {
        "open": Colors.YELLOW,
        "in_progress": Colors.BLUE,
        "resolved": Colors.GREEN,
        "wont_fix": Colors.DIM,
        "promoted": Colors.MAGENTA
    }
    status_color = status_colors.get(finding.status, "")

    sev_color = severity_color(finding.severity)
    lines.append(
        f"{color(finding.id, Colors.CYAN, Colors.BOLD)} "
        f"[{color(finding.severity, sev_color)}] "
        f"[{color(finding.status, status_color)}]"
    )

    # Title
    lines.append(f"  {color(finding.title, Colors.WHITE, Colors.BOLD)}")

    # Location
    if finding.evidence and finding.evidence.file:
        loc = finding.evidence.file
        if finding.evidence.line:
            loc += f":{finding.evidence.line}"
        if finding.evidence.function:
            loc += f" ({finding.evidence.function})"
        lines.append(f"  {color('Location:', Colors.DIM)} {loc}")

    # Category and type
    lines.append(
        f"  {color('Type:', Colors.DIM)} {finding.finding_type} | "
        f"{color('Category:', Colors.DIM)} {finding.category}"
    )

    if verbose:
        # Description
        if finding.description:
            lines.append(f"  {color('Description:', Colors.DIM)}")
            for line in finding.description.split("\n")[:3]:
                lines.append(f"    {line}")

        # Tags
        if finding.tags:
            lines.append(f"  {color('Tags:', Colors.DIM)} {', '.join(finding.tags)}")

        # Links
        if finding.ado_work_item:
            lines.append(f"  {color('ADO:', Colors.DIM)} {finding.ado_work_item}")
        if finding.eval_result:
            lines.append(f"  {color('Eval:', Colors.DIM)} {finding.eval_result}")

        # Context
        if finding.branch:
            lines.append(f"  {color('Branch:', Colors.DIM)} {finding.branch}")
        if finding.discovered_during:
            lines.append(f"  {color('Source:', Colors.DIM)} {finding.discovered_during}")

        # Timestamps
        lines.append(f"  {color('Created:', Colors.DIM)} {finding.created_at}")
        if finding.resolved_at:
            lines.append(f"  {color('Resolved:', Colors.DIM)} {finding.resolved_at}")

    return "\n".join(lines)


def format_table(findings: List[Finding]) -> str:
    """Format findings as a table."""
    if not findings:
        return "No findings found."

    lines = []

    # Header
    lines.append(
        f"{'ID':<12} {'Sev':<8} {'Status':<10} {'Type':<12} {'Title':<40}"
    )
    lines.append("-" * 90)

    for f in findings:
        title = f.title[:38] + ".." if len(f.title) > 40 else f.title
        lines.append(
            f"{f.id:<12} {f.severity:<8} {f.status:<10} {f.finding_type:<12} {title:<40}"
        )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(
        description="Query and manage findings",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Capture a finding
  %(prog)s --capture --title "N+1 query in OrderService" --severity medium --file src/Services/OrderService.cs --line 145

  # Query open findings
  %(prog)s --open

  # Search findings
  %(prog)s --search "performance"

  # Show finding details
  %(prog)s --show f-abc123

  # Mark as resolved
  %(prog)s --resolve f-abc123 --resolution "Fixed in commit abc123"
"""
    )

    # Query modes
    query_group = parser.add_argument_group("Query")
    query_group.add_argument(
        "--open", action="store_true",
        help="Show open findings"
    )
    query_group.add_argument(
        "--ready", action="store_true",
        help="Show ready findings (open, not blocked)"
    )
    query_group.add_argument(
        "--blocked", action="store_true",
        help="Show blocked findings"
    )
    query_group.add_argument(
        "--branch", action="store_true",
        help="Show findings for current branch"
    )
    query_group.add_argument(
        "--all", action="store_true",
        help="Show all findings"
    )
    query_group.add_argument(
        "--search", type=str, metavar="TERM",
        help="Search in title and description"
    )
    query_group.add_argument(
        "--show", type=str, metavar="ID",
        help="Show details for a specific finding"
    )

    # Capture
    capture_group = parser.add_argument_group("Capture")
    capture_group.add_argument(
        "--capture", action="store_true",
        help="Capture a new finding"
    )
    capture_group.add_argument(
        "--title", type=str,
        help="Finding title"
    )
    capture_group.add_argument(
        "--description", "-d", type=str, default="",
        help="Finding description"
    )
    capture_group.add_argument(
        "--type", "-t", type=str, choices=FINDING_TYPES, default="discovery",
        help="Finding type (default: discovery)"
    )
    capture_group.add_argument(
        "--severity", "-s", type=str, choices=SEVERITIES, default="medium",
        help="Severity level (default: medium)"
    )
    capture_group.add_argument(
        "--category", "-c", type=str, choices=CATEGORIES, default="other",
        help="Category (default: other)"
    )
    capture_group.add_argument(
        "--file", type=str,
        help="File path for the finding"
    )
    capture_group.add_argument(
        "--line", type=int,
        help="Line number"
    )
    capture_group.add_argument(
        "--snippet", type=str,
        help="Code snippet"
    )
    capture_group.add_argument(
        "--function", type=str,
        help="Function name"
    )
    capture_group.add_argument(
        "--tags", type=str, nargs="*",
        help="Tags for the finding"
    )
    capture_group.add_argument(
        "--priority", "-p", type=int, choices=[1, 2, 3, 4], default=3,
        help="Priority 1-4 (default: 3)"
    )
    capture_group.add_argument(
        "--during", type=str,
        help="What activity discovered this (e.g., architecture-review)"
    )
    capture_group.add_argument(
        "--eval", type=str,
        help="Link to eval-framework result"
    )
    capture_group.add_argument(
        "--ado", type=str,
        help="Link to ADO work item (AB#1234)"
    )

    # Update
    update_group = parser.add_argument_group("Update")
    update_group.add_argument(
        "--resolve", type=str, metavar="ID",
        help="Mark finding as resolved"
    )
    update_group.add_argument(
        "--resolution", type=str, default="fixed",
        help="Resolution description (use with --resolve)"
    )
    update_group.add_argument(
        "--promote", type=str, metavar="ID",
        help="Link finding to ADO work item (does NOT create the item - create it first)"
    )
    update_group.add_argument(
        "--promote-to", type=str, metavar="AB#1234",
        help="ADO work item ID to link (use with --promote)"
    )

    # Dependencies
    dep_group = parser.add_argument_group("Dependencies")
    dep_group.add_argument(
        "--block", type=str, nargs=2, metavar=("BLOCKER", "BLOCKED"),
        help="Mark BLOCKER as blocking BLOCKED (e.g., --block f-abc f-def)"
    )
    dep_group.add_argument(
        "--unblock", type=str, nargs=2, metavar=("BLOCKER", "BLOCKED"),
        help="Remove blocking relationship"
    )
    dep_group.add_argument(
        "--relate", type=str, nargs=2, metavar=("ID1", "ID2"),
        help="Mark two findings as related"
    )
    dep_group.add_argument(
        "--unrelate", type=str, nargs=2, metavar=("ID1", "ID2"),
        help="Remove related relationship"
    )
    dep_group.add_argument(
        "--show-deps", type=str, metavar="ID",
        help="Show dependencies for a finding"
    )

    # Other
    other_group = parser.add_argument_group("Other")
    other_group.add_argument(
        "--stats", action="store_true",
        help="Show statistics"
    )
    other_group.add_argument(
        "--rebuild-index", action="store_true",
        help="Rebuild the index from JSONL (use if index is corrupted)"
    )
    other_group.add_argument(
        "--compact", action="store_true",
        help="Compact the JSONL file (remove old versions)"
    )
    other_group.add_argument(
        "--compact-apply", action="store_true",
        help="Apply compaction (without this, only shows what would be compacted)"
    )

    # Output format
    format_group = parser.add_argument_group("Format")
    format_group.add_argument(
        "--json", action="store_true",
        help="Output as JSON"
    )
    format_group.add_argument(
        "--table", action="store_true",
        help="Output as table"
    )
    format_group.add_argument(
        "--verbose", "-v", action="store_true",
        help="Verbose output"
    )
    format_group.add_argument(
        "--limit", type=int, default=20,
        help="Maximum results (default: 20)"
    )

    # Filter options
    filter_group = parser.add_argument_group("Filters")
    filter_group.add_argument(
        "--status", type=str,
        help="Filter by status"
    )
    filter_group.add_argument(
        "--filter-type", type=str,
        help="Filter by finding type"
    )
    filter_group.add_argument(
        "--filter-severity", type=str,
        help="Filter by severity"
    )
    filter_group.add_argument(
        "--filter-category", type=str,
        help="Filter by category"
    )
    filter_group.add_argument(
        "--tag", type=str,
        help="Filter by tag"
    )

    args = parser.parse_args()
    store = FindingsStore()

    # Handle capture
    if args.capture:
        if not args.title:
            print(color("Error: --title is required for --capture", Colors.RED))
            sys.exit(1)

        finding_id = store.create_finding(
            title=args.title,
            description=args.description,
            finding_type=args.type,
            severity=args.severity,
            category=args.category,
            file_path=args.file,
            line=args.line,
            snippet=args.snippet,
            function=args.function,
            tags=args.tags,
            priority=args.priority,
            discovered_during=args.during,
            eval_result=args.eval,
            ado_work_item=args.ado,
        )

        if args.json:
            print(json.dumps({"id": finding_id, "status": "created"}))
        else:
            print(color("Finding captured!", Colors.GREEN, Colors.BOLD))
            print(f"  ID: {color(finding_id, Colors.CYAN)}")
            print()
            finding = store.get_finding(finding_id)
            if finding:
                print(format_finding(finding, verbose=True))

        sys.exit(0)

    # Handle resolve
    if args.resolve:
        success = store.resolve_finding(
            args.resolve,
            resolution=args.resolution,
            resolved_by="claude"
        )
        if args.json:
            print(json.dumps({"id": args.resolve, "resolved": success}))
        elif success:
            print(color(f"Finding {args.resolve} marked as resolved.", Colors.GREEN))
        else:
            print(color(f"Finding {args.resolve} not found.", Colors.RED))
        sys.exit(0 if success else 1)

    # Handle promote
    if args.promote:
        if not args.promote_to:
            print(color("Error: --promote-to is required with --promote", Colors.RED))
            sys.exit(1)

        success = store.promote_to_ado(args.promote, args.promote_to)
        if args.json:
            print(json.dumps({
                "id": args.promote,
                "promoted": success,
                "work_item": args.promote_to
            }))
        elif success:
            print(color(
                f"Finding {args.promote} promoted to {args.promote_to}.",
                Colors.GREEN
            ))
        else:
            print(color(f"Finding {args.promote} not found.", Colors.RED))
        sys.exit(0 if success else 1)

    # Handle block
    if args.block:
        blocker_id, blocked_id = args.block

        blocker = store.get_finding(blocker_id)
        blocked = store.get_finding(blocked_id)

        if not blocker:
            print(color(f"Error: Finding {blocker_id} not found", Colors.RED))
            sys.exit(1)
        if not blocked:
            print(color(f"Error: Finding {blocked_id} not found", Colors.RED))
            sys.exit(1)

        # Update blocker's "blocks" list
        blocks = blocker.blocks.copy()
        if blocked_id not in blocks:
            blocks.append(blocked_id)
        store.update_finding(blocker_id, blocks=blocks)

        # Update blocked's "blocked_by" list
        blocked_by = blocked.blocked_by.copy()
        if blocker_id not in blocked_by:
            blocked_by.append(blocker_id)
        store.update_finding(blocked_id, blocked_by=blocked_by)

        if args.json:
            print(json.dumps({"blocker": blocker_id, "blocked": blocked_id, "action": "block"}))
        else:
            print(color(f"{blocker_id} now blocks {blocked_id}", Colors.GREEN))
        sys.exit(0)

    # Handle unblock
    if args.unblock:
        blocker_id, blocked_id = args.unblock

        blocker = store.get_finding(blocker_id)
        blocked = store.get_finding(blocked_id)

        if not blocker:
            print(color(f"Error: Finding {blocker_id} not found", Colors.RED))
            sys.exit(1)
        if not blocked:
            print(color(f"Error: Finding {blocked_id} not found", Colors.RED))
            sys.exit(1)

        # Remove from blocker's "blocks" list
        blocks = [b for b in blocker.blocks if b != blocked_id]
        store.update_finding(blocker_id, blocks=blocks)

        # Remove from blocked's "blocked_by" list
        blocked_by = [b for b in blocked.blocked_by if b != blocker_id]
        store.update_finding(blocked_id, blocked_by=blocked_by)

        if args.json:
            print(json.dumps({"blocker": blocker_id, "blocked": blocked_id, "action": "unblock"}))
        else:
            print(color(f"{blocker_id} no longer blocks {blocked_id}", Colors.GREEN))
        sys.exit(0)

    # Handle relate
    if args.relate:
        id1, id2 = args.relate

        f1 = store.get_finding(id1)
        f2 = store.get_finding(id2)

        if not f1:
            print(color(f"Error: Finding {id1} not found", Colors.RED))
            sys.exit(1)
        if not f2:
            print(color(f"Error: Finding {id2} not found", Colors.RED))
            sys.exit(1)

        # Add bidirectional relationship
        related1 = f1.related_to.copy()
        if id2 not in related1:
            related1.append(id2)
        store.update_finding(id1, related_to=related1)

        related2 = f2.related_to.copy()
        if id1 not in related2:
            related2.append(id1)
        store.update_finding(id2, related_to=related2)

        if args.json:
            print(json.dumps({"id1": id1, "id2": id2, "action": "relate"}))
        else:
            print(color(f"{id1} and {id2} are now related", Colors.GREEN))
        sys.exit(0)

    # Handle unrelate
    if args.unrelate:
        id1, id2 = args.unrelate

        f1 = store.get_finding(id1)
        f2 = store.get_finding(id2)

        if not f1:
            print(color(f"Error: Finding {id1} not found", Colors.RED))
            sys.exit(1)
        if not f2:
            print(color(f"Error: Finding {id2} not found", Colors.RED))
            sys.exit(1)

        # Remove bidirectional relationship
        related1 = [r for r in f1.related_to if r != id2]
        store.update_finding(id1, related_to=related1)

        related2 = [r for r in f2.related_to if r != id1]
        store.update_finding(id2, related_to=related2)

        if args.json:
            print(json.dumps({"id1": id1, "id2": id2, "action": "unrelate"}))
        else:
            print(color(f"{id1} and {id2} are no longer related", Colors.GREEN))
        sys.exit(0)

    # Handle show-deps
    if args.show_deps:
        finding = store.get_finding(args.show_deps)
        if not finding:
            print(color(f"Error: Finding {args.show_deps} not found", Colors.RED))
            sys.exit(1)

        if args.json:
            print(json.dumps({
                "id": args.show_deps,
                "blocks": finding.blocks,
                "blocked_by": finding.blocked_by,
                "related_to": finding.related_to,
                "parent": finding.parent
            }, indent=2))
        else:
            print(color(f"Dependencies for {args.show_deps}:", Colors.CYAN, Colors.BOLD))
            print(f"  Title: {finding.title}")
            print()

            if finding.blocked_by:
                print(color("  Blocked by:", Colors.RED))
                for bid in finding.blocked_by:
                    bf = store.get_finding(bid)
                    title = bf.title[:40] if bf else "(not found)"
                    print(f"    - {bid}: {title}")
            else:
                print(color("  Blocked by: (none)", Colors.DIM))

            if finding.blocks:
                print(color("  Blocks:", Colors.YELLOW))
                for bid in finding.blocks:
                    bf = store.get_finding(bid)
                    title = bf.title[:40] if bf else "(not found)"
                    print(f"    - {bid}: {title}")
            else:
                print(color("  Blocks: (none)", Colors.DIM))

            if finding.related_to:
                print(color("  Related to:", Colors.BLUE))
                for rid in finding.related_to:
                    rf = store.get_finding(rid)
                    title = rf.title[:40] if rf else "(not found)"
                    print(f"    - {rid}: {title}")
            else:
                print(color("  Related to: (none)", Colors.DIM))

            if finding.parent:
                pf = store.get_finding(finding.parent)
                title = pf.title[:40] if pf else "(not found)"
                print(color(f"  Parent: {finding.parent}: {title}", Colors.MAGENTA))

        sys.exit(0)

    # Handle show
    if args.show:
        finding = store.get_finding(args.show)
        if not finding:
            print(color(f"Finding {args.show} not found.", Colors.RED))
            sys.exit(1)

        if args.json:
            print(json.dumps(finding.to_dict(), indent=2))
        else:
            print(format_finding(finding, verbose=True))
        sys.exit(0)

    # Handle stats
    if args.stats:
        stats = store.get_statistics()
        if args.json:
            print(json.dumps(stats, indent=2))
        else:
            print(color("Findings Statistics", Colors.BOLD))
            print(f"  Total: {stats['total']}")
            print()
            print("  By Status:")
            for status, count in stats.get("by_status", {}).items():
                print(f"    {status}: {count}")
            print()
            print("  By Severity:")
            for sev, count in stats.get("by_severity", {}).items():
                print(f"    {sev}: {count}")
            print()
            print("  By Type:")
            for t, count in stats.get("by_type", {}).items():
                print(f"    {t}: {count}")
        sys.exit(0)

    # Handle rebuild-index
    if args.rebuild_index:
        index = store._rebuild_index()
        if args.json:
            print(json.dumps({"rebuilt": True, "findings_count": len(index["findings"])}))
        else:
            print(color("Index rebuilt.", Colors.GREEN))
            print(f"  Findings indexed: {len(index['findings'])}")
        sys.exit(0)

    # Handle compact
    if args.compact:
        result = store.compact(dry_run=not args.compact_apply)
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(color("Compact Analysis", Colors.BOLD))
            print(f"  Original lines: {result['original_lines']}")
            print(f"  Unique findings: {result['unique_findings']}")
            print(f"  Lines to remove: {result['lines_removed']}")
            if result['dry_run']:
                print(color("\n  (Dry run - use --compact-apply to apply)", Colors.DIM))
            else:
                print(color("\n  Compaction applied.", Colors.GREEN))
        sys.exit(0)

    # Handle queries
    findings: List[Finding] = []

    if args.open:
        findings = store.get_open_findings()
    elif args.ready:
        findings = store.get_ready_findings()
    elif args.blocked:
        findings = store.get_blocked_findings()
    elif args.branch:
        findings = store.get_findings_by_branch()
    elif args.all:
        findings = store.query_findings(limit=args.limit)
    elif args.search:
        findings = store.query_findings(search=args.search, limit=args.limit)
    else:
        # Default: show open findings
        findings = store.get_open_findings()

    # Apply additional filters
    if args.status:
        findings = [f for f in findings if f.status == args.status]
    if args.filter_type:
        findings = [f for f in findings if f.finding_type == args.filter_type]
    if args.filter_severity:
        findings = [f for f in findings if f.severity == args.filter_severity]
    if args.filter_category:
        findings = [f for f in findings if f.category == args.filter_category]
    if args.tag:
        findings = [f for f in findings if args.tag in f.tags]

    # Limit results
    findings = findings[:args.limit]

    # Output
    if args.json:
        print(json.dumps([f.to_dict() for f in findings], indent=2))
    elif args.table:
        print(format_table(findings))
    else:
        if not findings:
            print(color("No findings found.", Colors.DIM))
        else:
            print(color(f"Found {len(findings)} finding(s):", Colors.BOLD))
            print()
            for finding in findings:
                print(format_finding(finding, verbose=args.verbose))
                print()


if __name__ == "__main__":
    main()

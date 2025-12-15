#!/usr/bin/env python3
"""
Link Findings to Eval Results - Manage bidirectional links between findings and evaluations.

This script helps maintain the connection between:
- Findings discovered during evaluations
- Eval-framework result files

Usage:
    # Link a finding to an eval result
    python3 link_eval_results.py --finding f-abc123 --eval arch-review-2025-12-15-eval-xyz

    # Show findings linked to an eval
    python3 link_eval_results.py --show-eval arch-review-2025-12-15-eval-xyz

    # Show what eval a finding is linked to
    python3 link_eval_results.py --show-finding f-abc123

    # Unlink a finding from its eval
    python3 link_eval_results.py --unlink f-abc123
"""

import argparse
import json
import sys
from pathlib import Path
from typing import Optional, List

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from findings_store import FindingsStore, Finding


class Colors:
    """ANSI color codes."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def color(text: str, *codes: str) -> str:
    """Apply color codes to text."""
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + text + Colors.RESET


def find_eval_file(eval_id: str) -> Optional[Path]:
    """Try to find an eval result file by ID."""
    # Common locations
    search_paths = [
        Path(".eval-results"),
        Path("eval-results"),
        Path("."),
    ]

    for search_path in search_paths:
        if not search_path.exists():
            continue

        # Look for files matching the ID
        for f in search_path.glob("*.yaml"):
            if eval_id in f.stem:
                return f
        for f in search_path.glob("*.yml"):
            if eval_id in f.stem:
                return f

    return None


def get_findings_for_eval(store: FindingsStore, eval_id: str) -> List[Finding]:
    """Get all findings linked to an eval result."""
    all_findings = store.query_findings(limit=1000)
    return [f for f in all_findings if f.eval_result == eval_id]


def main():
    parser = argparse.ArgumentParser(
        description="Link findings to eval-framework results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --finding f-abc123 --eval arch-review-2025-12-15-eval-xyz
  %(prog)s --show-eval arch-review-2025-12-15-eval-xyz
  %(prog)s --show-finding f-abc123
  %(prog)s --unlink f-abc123
"""
    )

    # Actions
    action_group = parser.add_argument_group("Actions")
    action_group.add_argument(
        "--finding", "-f",
        metavar="ID",
        help="Finding ID to link"
    )
    action_group.add_argument(
        "--eval", "-e",
        metavar="EVAL_ID",
        help="Eval result ID to link to"
    )
    action_group.add_argument(
        "--unlink", "-u",
        metavar="FINDING_ID",
        help="Unlink a finding from its eval"
    )

    # Queries
    query_group = parser.add_argument_group("Queries")
    query_group.add_argument(
        "--show-eval",
        metavar="EVAL_ID",
        help="Show all findings linked to an eval"
    )
    query_group.add_argument(
        "--show-finding",
        metavar="FINDING_ID",
        help="Show what eval a finding is linked to"
    )
    query_group.add_argument(
        "--list-evals",
        action="store_true",
        help="List all eval IDs that have linked findings"
    )

    # Output
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()
    store = FindingsStore()

    # Handle linking
    if args.finding and args.eval:
        finding = store.get_finding(args.finding)
        if not finding:
            print(color(f"Error: Finding {args.finding} not found", Colors.RED))
            sys.exit(1)

        # Update the finding
        store.update_finding(args.finding, eval_result=args.eval)

        if args.json:
            print(json.dumps({
                "finding_id": args.finding,
                "eval_result": args.eval,
                "linked": True
            }))
        else:
            print(color(f"Linked {args.finding} to {args.eval}", Colors.GREEN))

            # Check if eval file exists
            eval_file = find_eval_file(args.eval)
            if eval_file:
                print(f"  Eval file: {eval_file}")
            else:
                print(color(f"  Note: Eval file for {args.eval} not found locally", Colors.DIM))

        sys.exit(0)

    # Handle unlinking
    if args.unlink:
        finding = store.get_finding(args.unlink)
        if not finding:
            print(color(f"Error: Finding {args.unlink} not found", Colors.RED))
            sys.exit(1)

        if not finding.eval_result:
            print(color(f"Finding {args.unlink} is not linked to any eval", Colors.YELLOW))
            sys.exit(0)

        old_eval = finding.eval_result
        store.update_finding(args.unlink, eval_result=None)

        if args.json:
            print(json.dumps({
                "finding_id": args.unlink,
                "previous_eval": old_eval,
                "unlinked": True
            }))
        else:
            print(color(f"Unlinked {args.unlink} from {old_eval}", Colors.GREEN))

        sys.exit(0)

    # Handle show-eval
    if args.show_eval:
        findings = get_findings_for_eval(store, args.show_eval)

        if args.json:
            print(json.dumps({
                "eval_id": args.show_eval,
                "findings": [
                    {
                        "id": f.id,
                        "title": f.title,
                        "severity": f.severity,
                        "status": f.status
                    }
                    for f in findings
                ]
            }, indent=2))
        else:
            print(color(f"Findings linked to {args.show_eval}:", Colors.CYAN))
            if not findings:
                print(color("  (none)", Colors.DIM))
            else:
                for f in findings:
                    status_color = {
                        "open": Colors.YELLOW,
                        "resolved": Colors.GREEN,
                        "promoted": Colors.CYAN
                    }.get(f.status, "")
                    print(f"  {f.id} [{color(f.status, status_color)}] {f.title[:50]}")

            # Check for eval file
            eval_file = find_eval_file(args.show_eval)
            if eval_file:
                print(f"\n  Eval file: {eval_file}")

        sys.exit(0)

    # Handle show-finding
    if args.show_finding:
        finding = store.get_finding(args.show_finding)
        if not finding:
            print(color(f"Error: Finding {args.show_finding} not found", Colors.RED))
            sys.exit(1)

        if args.json:
            print(json.dumps({
                "finding_id": args.show_finding,
                "eval_result": finding.eval_result,
                "discovered_during": finding.discovered_during
            }))
        else:
            print(color(f"Finding {args.show_finding}:", Colors.CYAN))
            print(f"  Title: {finding.title}")
            if finding.eval_result:
                print(f"  Eval result: {color(finding.eval_result, Colors.GREEN)}")
                eval_file = find_eval_file(finding.eval_result)
                if eval_file:
                    print(f"  Eval file: {eval_file}")
            else:
                print(color("  Not linked to any eval", Colors.DIM))

            if finding.discovered_during:
                print(f"  Discovered during: {finding.discovered_during}")

        sys.exit(0)

    # Handle list-evals
    if args.list_evals:
        all_findings = store.query_findings(limit=1000)
        eval_ids = set()
        for f in all_findings:
            if f.eval_result:
                eval_ids.add(f.eval_result)

        if args.json:
            print(json.dumps({
                "eval_ids": sorted(eval_ids),
                "count": len(eval_ids)
            }, indent=2))
        else:
            print(color("Eval IDs with linked findings:", Colors.CYAN))
            if not eval_ids:
                print(color("  (none)", Colors.DIM))
            else:
                for eval_id in sorted(eval_ids):
                    count = len([f for f in all_findings if f.eval_result == eval_id])
                    print(f"  {eval_id} ({count} findings)")

        sys.exit(0)

    # No action specified
    parser.print_help()
    sys.exit(1)


if __name__ == "__main__":
    main()

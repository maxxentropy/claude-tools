#!/usr/bin/env python3
"""
Promote Finding to ADO - Create Azure DevOps work item from a finding.

This script bridges the findings system with Azure DevOps by:
1. Reading a finding from the local store
2. Creating an ADO work item with the finding's details
3. Linking the finding back to the created work item

Usage:
    # Promote a finding (creates Task by default)
    python3 promote_to_ado.py f-abc123

    # Promote as a specific type
    python3 promote_to_ado.py f-abc123 --type Bug

    # Dry run (show what would be created)
    python3 promote_to_ado.py f-abc123 --dry-run

    # With custom area path
    python3 promote_to_ado.py f-abc123 --area "Project\\Backend"
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Dict, Any

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from findings_store import FindingsStore, Finding


# Map finding severity to ADO priority (1=highest, 4=lowest)
SEVERITY_TO_PRIORITY = {
    "critical": 1,
    "high": 2,
    "medium": 3,
    "low": 4,
    "info": 4
}

# Map finding type to ADO work item type
FINDING_TYPE_TO_ADO_TYPE = {
    "bug": "Bug",
    "discovery": "Task",
    "todo": "Task",
    "question": "Task",
    "note": "Task",
    "tech-debt": "Task"
}


class Colors:
    """ANSI color codes."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def color(text: str, *codes: str) -> str:
    """Apply color codes to text."""
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + text + Colors.RESET


def load_ado_config(config_path: str = ".ado/config.json") -> Optional[Dict[str, Any]]:
    """Load ADO configuration."""
    path = Path(config_path)
    if not path.exists():
        # Try to find it relative to git root
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--show-toplevel"],
                capture_output=True, text=True
            )
            if result.returncode == 0:
                root = Path(result.stdout.strip())
                path = root / ".ado" / "config.json"
        except Exception:
            pass

    if not path.exists():
        return None

    try:
        return json.loads(path.read_text())
    except Exception:
        return None


def format_description(finding: Finding) -> str:
    """Format finding as ADO work item description (HTML)."""
    lines = []

    lines.append(f"<h3>Finding: {finding.id}</h3>")

    if finding.description:
        lines.append(f"<p>{finding.description}</p>")

    # Evidence/Location
    if finding.evidence:
        lines.append("<h4>Location</h4>")
        lines.append("<ul>")
        if finding.evidence.file:
            loc = finding.evidence.file
            if finding.evidence.line:
                loc += f":{finding.evidence.line}"
            lines.append(f"<li><strong>File:</strong> <code>{loc}</code></li>")
        if finding.evidence.function:
            lines.append(f"<li><strong>Function:</strong> <code>{finding.evidence.function}</code></li>")
        if finding.evidence.snippet:
            lines.append(f"<li><strong>Code:</strong><pre>{finding.evidence.snippet}</pre></li>")
        lines.append("</ul>")

    # Metadata
    lines.append("<h4>Metadata</h4>")
    lines.append("<ul>")
    lines.append(f"<li><strong>Severity:</strong> {finding.severity}</li>")
    lines.append(f"<li><strong>Category:</strong> {finding.category}</li>")
    lines.append(f"<li><strong>Type:</strong> {finding.finding_type}</li>")
    if finding.discovered_during:
        lines.append(f"<li><strong>Discovered during:</strong> {finding.discovered_during}</li>")
    if finding.branch:
        lines.append(f"<li><strong>Branch:</strong> {finding.branch}</li>")
    if finding.tags:
        lines.append(f"<li><strong>Tags:</strong> {', '.join(finding.tags)}</li>")
    lines.append("</ul>")

    # Source link
    lines.append(f"<p><em>Promoted from finding {finding.id} on {finding.created_at}</em></p>")

    return "\n".join(lines)


def create_ado_work_item(
    config: Dict[str, Any],
    work_item_type: str,
    title: str,
    description: str,
    priority: int = 3,
    area_path: Optional[str] = None,
    tags: Optional[str] = None,
    dry_run: bool = False
) -> Optional[Dict[str, Any]]:
    """Create an ADO work item using the az CLI."""

    cmd = [
        "az", "boards", "work-item", "create",
        "--organization", config["organization"],
        "--project", config["project"],
        "--type", work_item_type,
        "--title", title,
        "--description", description,
        "--output", "json"
    ]

    # Add priority
    cmd.extend(["--fields", f"Microsoft.VSTS.Common.Priority={priority}"])

    if area_path:
        cmd.extend(["--area", area_path])

    if tags:
        # Tags need to be added via --fields
        existing_fields_idx = None
        for i, arg in enumerate(cmd):
            if arg == "--fields":
                existing_fields_idx = i + 1
                break

        if existing_fields_idx:
            cmd[existing_fields_idx] += f" System.Tags={tags}"
        else:
            cmd.extend(["--fields", f"System.Tags={tags}"])

    if dry_run:
        print(color("Dry run - would execute:", Colors.YELLOW))
        # Redact description for readability
        display_cmd = cmd.copy()
        desc_idx = display_cmd.index("--description") + 1
        display_cmd[desc_idx] = "[HTML description...]"
        print(f"  {' '.join(display_cmd)}")
        return {"id": 0, "fields": {"System.Title": title}}

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)

        if result.returncode == 0:
            return json.loads(result.stdout)
        else:
            print(color(f"Error creating work item: {result.stderr}", Colors.RED))
            return None
    except subprocess.TimeoutExpired:
        print(color("Error: az command timed out", Colors.RED))
        return None
    except Exception as e:
        print(color(f"Error: {e}", Colors.RED))
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Promote a finding to an Azure DevOps work item",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s f-abc123                    # Promote finding (creates Task)
  %(prog)s f-abc123 --type Bug         # Promote as Bug
  %(prog)s f-abc123 --dry-run          # Show what would be created
  %(prog)s f-abc123 --area "Proj\\API" # Set area path
"""
    )

    parser.add_argument(
        "finding_id",
        help="Finding ID to promote (e.g., f-abc123)"
    )
    parser.add_argument(
        "--type", "-t",
        dest="work_item_type",
        help="ADO work item type (default: auto from finding type)"
    )
    parser.add_argument(
        "--area", "-a",
        help="Area path for the work item"
    )
    parser.add_argument(
        "--config", "-c",
        default=".ado/config.json",
        help="Path to ADO config file"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be created without creating"
    )
    parser.add_argument(
        "--no-update",
        action="store_true",
        help="Don't update the finding with the work item link"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()

    # Load ADO config
    config = load_ado_config(args.config)
    if not config:
        print(color("Error: ADO config not found. Create .ado/config.json first.", Colors.RED))
        print(color("  See: skills/azure-devops/SKILL.md for setup instructions", Colors.DIM))
        sys.exit(1)

    # Load finding
    store = FindingsStore()
    finding = store.get_finding(args.finding_id)

    if not finding:
        print(color(f"Error: Finding {args.finding_id} not found", Colors.RED))
        sys.exit(1)

    # Check if already promoted
    if finding.ado_work_item and not args.dry_run:
        print(color(f"Warning: Finding already linked to {finding.ado_work_item}", Colors.YELLOW))
        response = input("Create another work item anyway? [y/N] ")
        if response.lower() != 'y':
            sys.exit(0)

    # Determine work item type
    work_item_type = args.work_item_type
    if not work_item_type:
        work_item_type = FINDING_TYPE_TO_ADO_TYPE.get(finding.finding_type, "Task")

    # Build work item details
    title = finding.title
    description = format_description(finding)
    priority = SEVERITY_TO_PRIORITY.get(finding.severity, 3)
    tags = ",".join(finding.tags) if finding.tags else None

    # Show what we're doing
    if not args.json:
        print(color(f"Promoting finding {finding.id} to ADO...", Colors.CYAN))
        print(f"  Title: {title}")
        print(f"  Type: {work_item_type}")
        print(f"  Priority: {priority}")
        if args.area:
            print(f"  Area: {args.area}")
        print()

    # Create work item
    result = create_ado_work_item(
        config=config,
        work_item_type=work_item_type,
        title=title,
        description=description,
        priority=priority,
        area_path=args.area,
        tags=tags,
        dry_run=args.dry_run
    )

    if not result:
        sys.exit(1)

    work_item_id = result.get("id")
    work_item_ref = f"AB#{work_item_id}"

    # Update finding with link
    if not args.no_update and not args.dry_run:
        store.promote_to_ado(args.finding_id, work_item_ref)

    # Output
    if args.json:
        output = {
            "finding_id": args.finding_id,
            "work_item_id": work_item_id,
            "work_item_ref": work_item_ref,
            "work_item_type": work_item_type,
            "dry_run": args.dry_run
        }
        print(json.dumps(output, indent=2))
    else:
        if args.dry_run:
            print(color("\nDry run complete. No work item created.", Colors.YELLOW))
        else:
            print(color(f"Created work item: {work_item_ref}", Colors.GREEN, Colors.BOLD))
            print(f"  URL: {config['organization']}/{config['project']}/_workitems/edit/{work_item_id}")
            if not args.no_update:
                print(f"  Finding {args.finding_id} marked as promoted")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Extract Findings from Eval Results - Import findings from eval-framework output.

This script parses eval-framework YAML output and creates findings in the
local store, enabling persistence of evaluation discoveries.

Usage:
    # Extract findings from an eval result file
    python3 findings_from_eval.py --eval-file .eval-results/arch-review-2025-12-15.yaml

    # Dry run (show what would be created)
    python3 findings_from_eval.py --eval-file .eval-results/arch-review-2025-12-15.yaml --dry-run

    # Only import high+ severity
    python3 findings_from_eval.py --eval-file .eval-results/arch-review-2025-12-15.yaml --min-severity high

    # Skip already-fixed findings
    python3 findings_from_eval.py --eval-file .eval-results/arch-review-2025-12-15.yaml --skip-fixed
"""

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Optional, Dict, Any, List

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from findings_store import FindingsStore, SEVERITIES, CATEGORIES


# Try to import PyYAML
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


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


# Severity ordering for filtering
SEVERITY_ORDER = {sev: i for i, sev in enumerate(SEVERITIES)}


def parse_yaml_file(file_path: Path) -> Optional[Dict[str, Any]]:
    """Parse a YAML file, handling frontmatter."""
    if not HAS_YAML:
        print(color("Error: PyYAML not installed. Run: pip install pyyaml", Colors.RED))
        return None

    content = file_path.read_text()

    # Handle YAML frontmatter (--- delimited)
    if content.startswith("---"):
        parts = content.split("---", 2)
        if len(parts) >= 3:
            # First part is empty, second is frontmatter, third is rest
            try:
                # Try to parse as multiple documents
                docs = list(yaml.safe_load_all(content))
                # Merge all documents
                result = {}
                for doc in docs:
                    if doc:
                        result.update(doc)
                return result
            except yaml.YAMLError:
                pass

    # Simple parse
    try:
        return yaml.safe_load(content)
    except yaml.YAMLError as e:
        print(color(f"Error parsing YAML: {e}", Colors.RED))
        return None


def normalize_category(category: str) -> str:
    """Normalize eval category to findings category."""
    category = category.lower().replace(" ", "-").replace("_", "-")

    # Direct mappings
    if category in CATEGORIES:
        return category

    # Fuzzy mappings
    mappings = {
        "concurrency": "thread-safety",
        "race-condition": "thread-safety",
        "deadlock": "thread-safety",
        "memory-leak": "resource-management",
        "resource-leak": "resource-management",
        "connection-leak": "resource-management",
        "exception": "error-handling",
        "exception-handling": "error-handling",
        "recovery": "error-handling",
        "state-machine": "state-management",
        "persistence": "state-management",
        "timeout": "external-operations",
        "retry": "external-operations",
        "external-call": "external-operations",
        "api": "api-web-layer",
        "validation": "api-web-layer",
        "input": "api-web-layer",
        "web": "api-web-layer",
        "config": "configuration",
        "secrets": "configuration",
        "credentials": "configuration",
        "pattern": "code-consistency",
        "naming": "code-consistency",
        "dead-code": "code-consistency",
        "auth": "security",
        "injection": "security",
        "xss": "security",
        "optimization": "performance",
        "n+1": "performance",
        "query": "performance",
    }

    for pattern, normalized in mappings.items():
        if pattern in category:
            return normalized

    return "other"


def extract_eval_id(file_path: Path) -> Optional[str]:
    """Extract evaluation ID from filename."""
    # Pattern: arch-review-2025-12-15-eval-abc123.yaml
    match = re.search(r'eval-([a-f0-9]+)', file_path.stem)
    if match:
        return f"eval-{match.group(1)}"

    # Fallback to filename stem
    return file_path.stem


def convert_eval_finding(
    eval_finding: Dict[str, Any],
    eval_id: str,
    eval_type: str
) -> Dict[str, Any]:
    """Convert an eval-framework finding to our finding schema."""
    location = eval_finding.get("location", {})

    # Build evidence
    evidence_dict = {}
    if location.get("file"):
        evidence_dict["file"] = location["file"]
    if location.get("line"):
        evidence_dict["line"] = location["line"]
    if location.get("function"):
        evidence_dict["function"] = location["function"]
    if eval_finding.get("evidence"):
        evidence_dict["snippet"] = eval_finding["evidence"][:500]  # Truncate

    # Build description from multiple fields
    desc_parts = []
    if eval_finding.get("evidence"):
        desc_parts.append(f"**Evidence:**\n{eval_finding['evidence']}")
    if eval_finding.get("reasoning"):
        desc_parts.append(f"**Reasoning:**\n{eval_finding['reasoning']}")
    if eval_finding.get("impact"):
        desc_parts.append(f"**Impact:** {eval_finding['impact']}")
    if eval_finding.get("recommendation"):
        desc_parts.append(f"**Recommendation:**\n{eval_finding['recommendation']}")

    description = "\n\n".join(desc_parts)

    # Normalize severity
    severity = eval_finding.get("severity", "medium").lower()
    if severity not in SEVERITIES:
        severity = "medium"

    # Normalize category
    category = normalize_category(eval_finding.get("category", "other"))

    # Determine finding type
    finding_type = "discovery"
    if eval_finding.get("fix_applied"):
        finding_type = "note"  # Already fixed, just for reference

    return {
        "title": eval_finding.get("title", "Untitled finding"),
        "finding_type": finding_type,
        "severity": severity,
        "category": category,
        "description": description,
        "file_path": evidence_dict.get("file"),
        "line": evidence_dict.get("line"),
        "snippet": evidence_dict.get("snippet"),
        "function": evidence_dict.get("function"),
        "discovered_during": eval_type,
        "eval_result": eval_id,
        "tags": [eval_type, category],
        "priority": {"critical": 1, "high": 2, "medium": 3, "low": 4, "info": 4}.get(severity, 3),
        # Extra metadata from eval
        "_eval_id": eval_finding.get("id"),
        "_fix_applied": eval_finding.get("fix_applied", False),
        "_work_item": eval_finding.get("work_item"),
    }


def main():
    parser = argparse.ArgumentParser(
        description="Extract findings from eval-framework results",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --eval-file .eval-results/arch-review-2025-12-15.yaml
  %(prog)s --eval-file .eval-results/*.yaml --min-severity high
  %(prog)s --eval-file review.yaml --dry-run --skip-fixed
"""
    )

    parser.add_argument(
        "--eval-file", "-e",
        required=True,
        help="Path to eval-framework YAML file"
    )
    parser.add_argument(
        "--dry-run", "-n",
        action="store_true",
        help="Show what would be created without creating"
    )
    parser.add_argument(
        "--min-severity",
        choices=SEVERITIES,
        default="info",
        help="Minimum severity to import (default: info = all)"
    )
    parser.add_argument(
        "--skip-fixed",
        action="store_true",
        help="Skip findings marked as fix_applied=true"
    )
    parser.add_argument(
        "--skip-linked",
        action="store_true",
        help="Skip findings that already have a work_item"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Verbose output"
    )

    args = parser.parse_args()

    if not HAS_YAML:
        print(color("Error: PyYAML required. Install with: pip install pyyaml", Colors.RED))
        sys.exit(1)

    # Load eval file
    eval_path = Path(args.eval_file)
    if not eval_path.exists():
        print(color(f"Error: File not found: {eval_path}", Colors.RED))
        sys.exit(1)

    data = parse_yaml_file(eval_path)
    if not data:
        sys.exit(1)

    # Extract evaluation metadata
    eval_meta = data.get("evaluation", {})
    eval_id = eval_meta.get("id") or extract_eval_id(eval_path)
    eval_type = eval_meta.get("type", "evaluation")

    # Get findings array
    findings_data = data.get("findings", [])
    if not findings_data:
        print(color("No findings found in eval file", Colors.YELLOW))
        sys.exit(0)

    # Filter and convert findings
    min_severity_order = SEVERITY_ORDER.get(args.min_severity, 99)
    store = FindingsStore()
    created = []
    skipped = []

    for eval_finding in findings_data:
        # Apply filters
        severity = eval_finding.get("severity", "medium").lower()
        severity_order = SEVERITY_ORDER.get(severity, 99)

        if severity_order > min_severity_order:
            skipped.append({"reason": "severity", "finding": eval_finding})
            continue

        if args.skip_fixed and eval_finding.get("fix_applied"):
            skipped.append({"reason": "fixed", "finding": eval_finding})
            continue

        if args.skip_linked and eval_finding.get("work_item"):
            skipped.append({"reason": "linked", "finding": eval_finding})
            continue

        # Convert to our format
        converted = convert_eval_finding(eval_finding, eval_id, eval_type)

        if args.dry_run:
            created.append({
                "title": converted["title"],
                "severity": converted["severity"],
                "category": converted["category"],
                "eval_id": converted.get("_eval_id"),
                "would_create": True
            })
        else:
            # Create the finding
            finding_id = store.create_finding(
                title=converted["title"],
                finding_type=converted["finding_type"],
                severity=converted["severity"],
                category=converted["category"],
                description=converted["description"],
                file_path=converted.get("file_path"),
                line=converted.get("line"),
                snippet=converted.get("snippet"),
                function=converted.get("function"),
                discovered_during=converted["discovered_during"],
                eval_result=converted["eval_result"],
                tags=converted["tags"],
                priority=converted["priority"],
                ado_work_item=converted.get("_work_item"),
            )

            # If the eval finding was already fixed, mark as resolved
            if converted.get("_fix_applied"):
                store.resolve_finding(finding_id, resolution="Fixed during evaluation")

            created.append({
                "id": finding_id,
                "title": converted["title"],
                "severity": converted["severity"],
                "category": converted["category"],
                "eval_id": converted.get("_eval_id"),
            })

    # Output results
    if args.json:
        output = {
            "eval_file": str(eval_path),
            "eval_id": eval_id,
            "eval_type": eval_type,
            "total_in_file": len(findings_data),
            "created": len(created),
            "skipped": len(skipped),
            "findings": created,
            "dry_run": args.dry_run
        }
        print(json.dumps(output, indent=2))
    else:
        print(color(f"Eval file: {eval_path}", Colors.CYAN))
        print(f"  ID: {eval_id}")
        print(f"  Type: {eval_type}")
        print(f"  Findings in file: {len(findings_data)}")
        print()

        if args.dry_run:
            print(color("Dry run - would create:", Colors.YELLOW))
        else:
            print(color("Created findings:", Colors.GREEN))

        for f in created:
            sev_color = {
                "critical": Colors.RED,
                "high": Colors.RED,
                "medium": Colors.YELLOW,
                "low": Colors.GREEN,
                "info": Colors.DIM
            }.get(f["severity"], "")

            id_str = f.get("id", "[dry-run]")
            print(f"  {color(id_str, Colors.CYAN)} [{color(f['severity'], sev_color)}] {f['title'][:50]}")

        if skipped and args.verbose:
            print()
            print(color(f"Skipped {len(skipped)} findings:", Colors.DIM))
            for s in skipped[:5]:
                print(f"  - {s['reason']}: {s['finding'].get('title', 'untitled')[:40]}")
            if len(skipped) > 5:
                print(f"  ... and {len(skipped) - 5} more")

        print()
        print(f"Created: {len(created)}, Skipped: {len(skipped)}")


if __name__ == "__main__":
    main()

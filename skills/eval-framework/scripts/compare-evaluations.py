#!/usr/bin/env python3
"""
Evaluation Comparison Tool

Compares two evaluation YAML files and generates consistency metrics.

Usage:
    python compare-evaluations.py eval-a.yaml eval-b.yaml [--output report.md]
"""

import argparse
import hashlib
import sys
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Dict, List, Optional, Tuple

try:
    import yaml
except ImportError:
    print("Error: PyYAML required. Install with: pip install pyyaml")
    sys.exit(1)


def load_evaluation(path: Path) -> dict:
    """Load evaluation YAML file."""
    with open(path) as f:
        return yaml.safe_load(f)


def similarity(a: str, b: str) -> float:
    """Calculate string similarity (0-1)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def location_match(loc_a: dict, loc_b: dict, line_tolerance: int = 10) -> bool:
    """Check if two locations match."""
    if loc_a.get("file") != loc_b.get("file"):
        return False

    # Same file - check function or line proximity
    if loc_a.get("function") and loc_b.get("function"):
        return loc_a["function"] == loc_b["function"]

    line_a = loc_a.get("line", 0)
    line_b = loc_b.get("line", 0)
    return abs(line_a - line_b) <= line_tolerance


def finding_match(find_a: dict, find_b: dict) -> Tuple[bool, str]:
    """
    Check if two findings match.

    Returns:
        Tuple of (matches, match_reason)
    """
    # Check location match
    if location_match(find_a.get("location", {}), find_b.get("location", {})):
        return True, "location"

    # Check title similarity
    title_sim = similarity(find_a.get("title", ""), find_b.get("title", ""))
    if title_sim > 0.7:
        return True, f"title ({title_sim:.0%})"

    # Check evidence similarity (key phrases)
    evidence_sim = similarity(
        find_a.get("evidence", "")[:200],
        find_b.get("evidence", "")[:200]
    )
    if evidence_sim > 0.6:
        return True, f"evidence ({evidence_sim:.0%})"

    return False, ""


def match_findings(
    findings_a: List[dict],
    findings_b: List[dict]
) -> Tuple[List[Tuple[dict, dict, str]], List[dict], List[dict]]:
    """
    Match findings between two evaluations.

    Returns:
        Tuple of (matched_pairs, only_in_a, only_in_b)
    """
    matched = []
    used_b = set()

    for fa in findings_a:
        best_match = None
        best_reason = ""

        for i, fb in enumerate(findings_b):
            if i in used_b:
                continue

            matches, reason = finding_match(fa, fb)
            if matches:
                best_match = (i, fb, reason)
                break  # Take first match

        if best_match:
            used_b.add(best_match[0])
            matched.append((fa, best_match[1], best_match[2]))

    only_a = [f for f in findings_a if not any(m[0] == f for m in matched)]
    only_b = [f for i, f in enumerate(findings_b) if i not in used_b]

    return matched, only_a, only_b


def calculate_metrics(
    matched: List[Tuple[dict, dict, str]],
    only_a: List[dict],
    only_b: List[dict]
) -> Dict[str, float]:
    """Calculate comparison metrics."""
    total_a = len(matched) + len(only_a)
    total_b = len(matched) + len(only_b)
    total_union = total_a + len(only_b)  # |A| + |B - A|

    if total_union == 0:
        return {
            "overlap": 1.0,
            "precision": 1.0,
            "recall": 1.0,
            "severity_agreement": 1.0,
            "category_agreement": 1.0,
        }

    # Jaccard similarity (overlap)
    overlap = len(matched) / total_union if total_union > 0 else 0

    # Precision: of A's findings, how many in B?
    precision = len(matched) / total_a if total_a > 0 else 0

    # Recall: of B's findings, how many in A?
    recall = len(matched) / total_b if total_b > 0 else 0

    # Severity agreement among matched
    severity_matches = sum(
        1 for fa, fb, _ in matched
        if fa.get("severity") == fb.get("severity")
    )
    severity_agreement = severity_matches / len(matched) if matched else 1.0

    # Category agreement among matched
    category_matches = sum(
        1 for fa, fb, _ in matched
        if fa.get("category") == fb.get("category")
    )
    category_agreement = category_matches / len(matched) if matched else 1.0

    return {
        "overlap": overlap,
        "precision": precision,
        "recall": recall,
        "severity_agreement": severity_agreement,
        "category_agreement": category_agreement,
    }


def generate_report(
    eval_a: dict,
    eval_b: dict,
    matched: List[Tuple[dict, dict, str]],
    only_a: List[dict],
    only_b: List[dict],
    metrics: Dict[str, float]
) -> str:
    """Generate markdown comparison report."""
    meta_a = eval_a.get("evaluation", {})
    meta_b = eval_b.get("evaluation", {})

    consistency_score = (
        metrics["overlap"] * 0.3 +
        metrics["severity_agreement"] * 0.3 +
        metrics["category_agreement"] * 0.2 +
        (metrics["precision"] + metrics["recall"]) / 2 * 0.2
    )

    report = f"""# Evaluation Comparison Report

Generated: {datetime.utcnow().isoformat()}Z

## Evaluations Compared

| Property | Evaluation A | Evaluation B |
|----------|--------------|--------------|
| ID | {meta_a.get('id', 'N/A')} | {meta_b.get('id', 'N/A')} |
| Date | {meta_a.get('date', 'N/A')} | {meta_b.get('date', 'N/A')} |
| Model | {meta_a.get('model', 'N/A')} | {meta_b.get('model', 'N/A')} |
| Target | {meta_a.get('target', {}).get('path', 'N/A')} | {meta_b.get('target', {}).get('path', 'N/A')} |
| Total Findings | {len(eval_a.get('findings', []))} | {len(eval_b.get('findings', []))} |

## Metrics

| Metric | Value | Interpretation |
|--------|-------|----------------|
| Overlap (Jaccard) | {metrics['overlap']:.1%} | % of findings in both |
| Precision (A→B) | {metrics['precision']:.1%} | Of A's findings, % in B |
| Recall (A→B) | {metrics['recall']:.1%} | Of B's findings, % in A |
| Severity Agreement | {metrics['severity_agreement']:.1%} | Matched findings with same severity |
| Category Agreement | {metrics['category_agreement']:.1%} | Matched findings with same category |

## Consistency Score: {consistency_score:.0%}

{"✅ HIGH CONSISTENCY" if consistency_score >= 0.8 else "⚠️ MODERATE CONSISTENCY" if consistency_score >= 0.6 else "❌ LOW CONSISTENCY"}

---

## Finding Comparison

### Matched Findings ({len(matched)})

| A Finding | B Finding | Match Type | Severity | Category |
|-----------|-----------|------------|----------|----------|
"""

    for fa, fb, reason in matched:
        sev_match = "✅" if fa.get("severity") == fb.get("severity") else f"❌ {fa.get('severity')}→{fb.get('severity')}"
        cat_match = "✅" if fa.get("category") == fb.get("category") else f"❌ {fa.get('category')}→{fb.get('category')}"
        report += f"| {fa.get('id')} | {fb.get('id')} | {reason} | {sev_match} | {cat_match} |\n"

    if only_a:
        report += f"\n### Only in A ({len(only_a)}) - Potentially missed by B\n\n"
        for f in only_a:
            report += f"- **{f.get('id')}**: {f.get('title')} ({f.get('location', {}).get('file', 'N/A')})\n"

    if only_b:
        report += f"\n### Only in B ({len(only_b)}) - Potentially missed by A\n\n"
        for f in only_b:
            report += f"- **{f.get('id')}**: {f.get('title')} ({f.get('location', {}).get('file', 'N/A')})\n"

    # Score comparison
    scores_a = eval_a.get("scores", {})
    scores_b = eval_b.get("scores", {})

    report += f"""
---

## Score Comparison

| Category | A | B | Diff |
|----------|---|---|------|
"""
    cats_a = scores_a.get("categories", {})
    cats_b = scores_b.get("categories", {})
    all_cats = set(cats_a.keys()) | set(cats_b.keys())

    for cat in sorted(all_cats):
        sa = cats_a.get(cat, "-")
        sb = cats_b.get(cat, "-")
        diff = ""
        if isinstance(sa, (int, float)) and isinstance(sb, (int, float)):
            d = sb - sa
            diff = f"+{d}" if d > 0 else str(d)
        report += f"| {cat} | {sa} | {sb} | {diff} |\n"

    report += f"| **Overall** | {scores_a.get('overall', '-')} | {scores_b.get('overall', '-')} | |\n"

    return report


def main():
    parser = argparse.ArgumentParser(description="Compare two evaluation files")
    parser.add_argument("eval_a", type=Path, help="First evaluation YAML file")
    parser.add_argument("eval_b", type=Path, help="Second evaluation YAML file")
    parser.add_argument("-o", "--output", type=Path, help="Output report file")
    parser.add_argument("--json", action="store_true", help="Output metrics as JSON")

    args = parser.parse_args()

    # Load evaluations
    eval_a = load_evaluation(args.eval_a)
    eval_b = load_evaluation(args.eval_b)

    # Match findings
    matched, only_a, only_b = match_findings(
        eval_a.get("findings", []),
        eval_b.get("findings", [])
    )

    # Calculate metrics
    metrics = calculate_metrics(matched, only_a, only_b)

    if args.json:
        import json
        print(json.dumps(metrics, indent=2))
        return

    # Generate report
    report = generate_report(eval_a, eval_b, matched, only_a, only_b, metrics)

    if args.output:
        args.output.write_text(report)
        print(f"Report written to {args.output}")
    else:
        print(report)


if __name__ == "__main__":
    main()

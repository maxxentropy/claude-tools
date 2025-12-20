#!/usr/bin/env python3
"""
TLA+ Code-Spec Drift Checker - Detect synchronization issues between code and specs.

This module checks for drift between TLA+ specifications and their mapped code:
- File existence validation
- Method/function existence validation
- Line number accuracy checking
- Spec file existence validation

Severity levels:
- critical: Mapped file deleted or renamed
- high: Mapped method/function not found
- medium: Line numbers significantly off (>20 lines)
- low: Minor line number drift (5-20 lines)
- info: Slight drift (<5 lines) or informational
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from tla_store import TLAStore, ModelMapping, ActionMapping


class Severity(str, Enum):
    """Drift issue severity levels."""

    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    INFO = "info"


class OutputFormat(str, Enum):
    """Output format options."""

    TABLE = "table"
    JSON = "json"
    MARKDOWN = "markdown"


@dataclass
class DriftIssue:
    """A single drift issue between code and spec."""

    model: str
    mapping_type: str  # action, variable, constant, spec
    mapping_name: str
    severity: Severity
    description: str
    spec_location: str
    code_location: str
    suggestion: str

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "mappingType": self.mapping_type,
            "mappingName": self.mapping_name,
            "severity": self.severity.value,
            "description": self.description,
            "specLocation": self.spec_location,
            "codeLocation": self.code_location,
            "suggestion": self.suggestion,
        }


@dataclass
class DriftReport:
    """Complete drift report for one or more models."""

    issues: list[DriftIssue] = field(default_factory=list)
    models_checked: list[str] = field(default_factory=list)
    files_checked: int = 0
    mappings_checked: int = 0

    @property
    def has_issues(self) -> bool:
        return len(self.issues) > 0

    @property
    def critical_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.CRITICAL)

    @property
    def high_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.HIGH)

    @property
    def medium_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.MEDIUM)

    @property
    def low_count(self) -> int:
        return sum(1 for i in self.issues if i.severity == Severity.LOW)

    def to_dict(self) -> dict:
        return {
            "issues": [i.to_dict() for i in self.issues],
            "modelsChecked": self.models_checked,
            "filesChecked": self.files_checked,
            "mappingsChecked": self.mappings_checked,
            "summary": {
                "total": len(self.issues),
                "critical": self.critical_count,
                "high": self.high_count,
                "medium": self.medium_count,
                "low": self.low_count,
            },
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        lines = ["# TLA+ Code-Spec Drift Report", ""]

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(f"- Models checked: {len(self.models_checked)}")
        lines.append(f"- Files checked: {self.files_checked}")
        lines.append(f"- Mappings checked: {self.mappings_checked}")
        lines.append(f"- Issues found: {len(self.issues)}")
        lines.append("")

        if not self.issues:
            lines.append("✅ **No drift detected** - all mappings are in sync.")
            return "\n".join(lines)

        # Severity breakdown
        lines.append("### By Severity")
        lines.append("")
        if self.critical_count:
            lines.append(f"- 🔴 Critical: {self.critical_count}")
        if self.high_count:
            lines.append(f"- 🟠 High: {self.high_count}")
        if self.medium_count:
            lines.append(f"- 🟡 Medium: {self.medium_count}")
        if self.low_count:
            lines.append(f"- 🔵 Low: {self.low_count}")
        lines.append("")

        # Issues by model
        lines.append("## Issues")
        lines.append("")

        current_model = None
        for issue in sorted(self.issues, key=lambda x: (x.model, x.severity.value)):
            if issue.model != current_model:
                current_model = issue.model
                lines.append(f"### {current_model}")
                lines.append("")

            severity_icon = {
                Severity.CRITICAL: "🔴",
                Severity.HIGH: "🟠",
                Severity.MEDIUM: "🟡",
                Severity.LOW: "🔵",
                Severity.INFO: "ℹ️",
            }[issue.severity]

            lines.append(f"**{severity_icon} {issue.mapping_type}: `{issue.mapping_name}`**")
            lines.append(f"- {issue.description}")
            lines.append(f"- Spec: `{issue.spec_location}`")
            lines.append(f"- Code: `{issue.code_location}`")
            lines.append(f"- Suggestion: {issue.suggestion}")
            lines.append("")

        return "\n".join(lines)

    def to_table(self) -> str:
        if not self.issues:
            return "✅ No drift detected - all mappings are in sync."

        lines = []

        # Header
        lines.append(
            f"{'Severity':<10} {'Model':<20} {'Type':<10} {'Name':<25} {'Description':<40}"
        )
        lines.append("-" * 105)

        for issue in sorted(self.issues, key=lambda x: (x.severity.value, x.model)):
            severity = issue.severity.value.upper()
            model = issue.model[:18] + ".." if len(issue.model) > 20 else issue.model
            mtype = issue.mapping_type[:8] + ".." if len(issue.mapping_type) > 10 else issue.mapping_type
            name = issue.mapping_name[:23] + ".." if len(issue.mapping_name) > 25 else issue.mapping_name
            desc = issue.description[:38] + ".." if len(issue.description) > 40 else issue.description

            lines.append(f"{severity:<10} {model:<20} {mtype:<10} {name:<25} {desc:<40}")

        # Summary
        lines.append("")
        lines.append(f"Total: {len(self.issues)} issues")
        lines.append(
            f"  Critical: {self.critical_count}, High: {self.high_count}, "
            f"Medium: {self.medium_count}, Low: {self.low_count}"
        )

        return "\n".join(lines)


class DriftChecker:
    """Checks for drift between TLA+ specs and mapped code."""

    # Line number drift thresholds
    DRIFT_THRESHOLD_LOW = 5
    DRIFT_THRESHOLD_MEDIUM = 20

    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)
        self.store = TLAStore(self.project_root)

    def check(
        self,
        model: Optional[str] = None,
        include_info: bool = False,
    ) -> DriftReport:
        """
        Check for drift between code and specifications.

        Args:
            model: Specific model to check (None for all)
            include_info: Include INFO-level issues

        Returns:
            DriftReport with all issues found
        """
        report = DriftReport()

        if not self.store.is_initialized():
            # No TLA+ project initialized - check if specs exist anyway
            specs_dir = self.project_root / "specs" / "tla+"
            if not specs_dir.exists():
                return report
            # Can't check mappings without store
            return report

        # Get models to check
        mappings = self.store.get_mappings()
        models_data = mappings.get("models", {})

        if model:
            if model not in models_data:
                report.issues.append(DriftIssue(
                    model=model,
                    mapping_type="model",
                    mapping_name=model,
                    severity=Severity.CRITICAL,
                    description=f"Model '{model}' not found in mappings",
                    spec_location="N/A",
                    code_location="N/A",
                    suggestion="Add model to .tla-plus/mappings.json or check model name",
                ))
                return report
            models_to_check = {model: models_data[model]}
        else:
            models_to_check = models_data

        report.models_checked = list(models_to_check.keys())

        # Check each model
        for model_name, model_data in models_to_check.items():
            self._check_model(model_name, model_data, report, include_info)

        return report

    def _check_model(
        self,
        model_name: str,
        model_data: dict,
        report: DriftReport,
        include_info: bool,
    ) -> None:
        """Check a single model for drift."""
        # Check spec file exists
        specs_dir = self.store.get_specs_dir()
        model_dir = specs_dir / model_name

        if not model_dir.exists():
            report.issues.append(DriftIssue(
                model=model_name,
                mapping_type="spec",
                mapping_name=model_name,
                severity=Severity.CRITICAL,
                description=f"Spec directory not found: {model_dir}",
                spec_location=str(model_dir),
                code_location="N/A",
                suggestion="Create spec directory or remove model from mappings",
            ))
            return

        tla_files = list(model_dir.glob("*.tla"))
        if not tla_files:
            report.issues.append(DriftIssue(
                model=model_name,
                mapping_type="spec",
                mapping_name=model_name,
                severity=Severity.CRITICAL,
                description=f"No .tla files found in {model_dir}",
                spec_location=str(model_dir),
                code_location="N/A",
                suggestion="Add TLA+ specification file",
            ))
            return

        # Check action mappings
        actions = model_data.get("actions", {})
        for action_name, action_data in actions.items():
            report.mappings_checked += 1
            self._check_action_mapping(
                model_name, action_name, action_data, report, include_info
            )

        # Check variable mappings
        variables = model_data.get("variables", {})
        for var_name, var_data in variables.items():
            report.mappings_checked += 1
            # Variable mappings are usually to database tables, less strict checking
            if include_info and var_data.get("table"):
                # Could add database schema checking here in the future
                pass

    def _check_action_mapping(
        self,
        model_name: str,
        action_name: str,
        action_data: dict,
        report: DriftReport,
        include_info: bool,
    ) -> None:
        """Check a single action mapping for drift."""
        code_file = action_data.get("codeFile")
        method = action_data.get("method")
        expected_line = action_data.get("line", 0)

        if not code_file:
            return

        file_path = self.project_root / code_file
        report.files_checked += 1

        # Check 1: File exists
        if not file_path.exists():
            report.issues.append(DriftIssue(
                model=model_name,
                mapping_type="action",
                mapping_name=action_name,
                severity=Severity.CRITICAL,
                description=f"Mapped file not found: {code_file}",
                spec_location=f"{model_name}/{action_name}",
                code_location=code_file,
                suggestion="Update mapping or restore file",
            ))
            return

        # Read file content
        try:
            content = file_path.read_text()
            lines = content.split("\n")
        except Exception as e:
            report.issues.append(DriftIssue(
                model=model_name,
                mapping_type="action",
                mapping_name=action_name,
                severity=Severity.HIGH,
                description=f"Cannot read file: {e}",
                spec_location=f"{model_name}/{action_name}",
                code_location=code_file,
                suggestion="Check file permissions and encoding",
            ))
            return

        # Check 2: Method/function exists
        if method:
            method_info = self._find_method(content, method, file_path.suffix)

            if not method_info:
                report.issues.append(DriftIssue(
                    model=model_name,
                    mapping_type="action",
                    mapping_name=action_name,
                    severity=Severity.HIGH,
                    description=f"Method '{method}' not found in file",
                    spec_location=f"{model_name}/{action_name}",
                    code_location=f"{code_file}:{expected_line}",
                    suggestion=f"Update mapping - method may have been renamed or moved",
                ))
                return

            actual_line = method_info["line"]

            # Check 3: Line number accuracy
            if expected_line > 0:
                drift = abs(actual_line - expected_line)

                if drift > self.DRIFT_THRESHOLD_MEDIUM:
                    report.issues.append(DriftIssue(
                        model=model_name,
                        mapping_type="action",
                        mapping_name=action_name,
                        severity=Severity.MEDIUM,
                        description=f"Line number drift: expected {expected_line}, found {actual_line} (drift: {drift})",
                        spec_location=f"{model_name}/{action_name}",
                        code_location=f"{code_file}:{actual_line}",
                        suggestion=f"Update mapping line number to {actual_line}",
                    ))
                elif drift > self.DRIFT_THRESHOLD_LOW:
                    report.issues.append(DriftIssue(
                        model=model_name,
                        mapping_type="action",
                        mapping_name=action_name,
                        severity=Severity.LOW,
                        description=f"Minor line drift: expected {expected_line}, found {actual_line} (drift: {drift})",
                        spec_location=f"{model_name}/{action_name}",
                        code_location=f"{code_file}:{actual_line}",
                        suggestion=f"Consider updating mapping line number to {actual_line}",
                    ))
                elif drift > 0 and include_info:
                    report.issues.append(DriftIssue(
                        model=model_name,
                        mapping_type="action",
                        mapping_name=action_name,
                        severity=Severity.INFO,
                        description=f"Slight line drift: {drift} lines",
                        spec_location=f"{model_name}/{action_name}",
                        code_location=f"{code_file}:{actual_line}",
                        suggestion="No action needed",
                    ))

    def _find_method(
        self,
        content: str,
        method_name: str,
        file_ext: str,
    ) -> Optional[dict]:
        """
        Find a method/function in source code.

        Returns dict with 'line' and 'signature' if found, None otherwise.
        """
        lines = content.split("\n")

        # Language-specific patterns
        if file_ext in [".cs", ".java"]:
            # C# / Java method pattern
            # Matches: public async Task<T> MethodName(params)
            # Matches: private void MethodName()
            pattern = rf"\b{re.escape(method_name)}\s*[<\(]"
        elif file_ext == ".py":
            # Python function/method pattern
            pattern = rf"def\s+{re.escape(method_name)}\s*\("
        elif file_ext in [".ts", ".js"]:
            # TypeScript/JavaScript
            pattern = rf"(?:function\s+{re.escape(method_name)}|{re.escape(method_name)}\s*[=:]\s*(?:async\s*)?\(|{re.escape(method_name)}\s*\()"
        elif file_ext == ".go":
            # Go function pattern
            pattern = rf"func\s+(?:\([^)]+\)\s+)?{re.escape(method_name)}\s*\("
        else:
            # Generic pattern - just look for the name followed by (
            pattern = rf"\b{re.escape(method_name)}\s*\("

        for i, line in enumerate(lines, 1):
            if re.search(pattern, line):
                return {"line": i, "signature": line.strip()}

        # Try case-insensitive if no match
        for i, line in enumerate(lines, 1):
            if re.search(pattern, line, re.IGNORECASE):
                return {"line": i, "signature": line.strip()}

        return None

    def fix_drift(
        self,
        model: Optional[str] = None,
        dry_run: bool = True,
    ) -> list[str]:
        """
        Attempt to automatically fix drift issues.

        Args:
            model: Specific model to fix
            dry_run: If True, only report what would be changed

        Returns:
            List of fixes applied (or that would be applied)
        """
        report = self.check(model)
        fixes = []

        mappings = self.store.get_mappings()

        for issue in report.issues:
            if issue.severity in [Severity.LOW, Severity.MEDIUM]:
                # Try to fix line number drift
                if "Line" in issue.description and "drift" in issue.description:
                    # Extract actual line from code_location
                    match = re.search(r":(\d+)$", issue.code_location)
                    if match:
                        actual_line = int(match.group(1))
                        action_name = issue.mapping_name

                        if issue.model in mappings.get("models", {}):
                            actions = mappings["models"][issue.model].get("actions", {})
                            if action_name in actions:
                                old_line = actions[action_name].get("line", 0)
                                fix_msg = (
                                    f"Update {issue.model}/{action_name} "
                                    f"line {old_line} -> {actual_line}"
                                )
                                fixes.append(fix_msg)

                                if not dry_run:
                                    actions[action_name]["line"] = actual_line

        if not dry_run and fixes:
            self.store._write_json(self.store.mappings_file, mappings)

        return fixes


def main():
    """CLI for TLA+ drift checking."""
    parser = argparse.ArgumentParser(
        description="Check for drift between TLA+ specs and mapped code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Check all models
  %(prog)s

  # Check specific model
  %(prog)s --model node-registration

  # Output as markdown
  %(prog)s --format markdown

  # Include informational issues
  %(prog)s --include-info

  # Auto-fix line number drift
  %(prog)s --fix

  # Preview fixes without applying
  %(prog)s --fix --dry-run
        """,
    )

    parser.add_argument(
        "--project", "-p",
        default=".",
        help="Project root directory",
    )
    parser.add_argument(
        "--model", "-m",
        help="Specific model to check",
    )
    parser.add_argument(
        "--format", "-f",
        choices=["table", "json", "markdown"],
        default="table",
        help="Output format (default: table)",
    )
    parser.add_argument(
        "--include-info",
        action="store_true",
        help="Include INFO-level issues",
    )
    parser.add_argument(
        "--fix",
        action="store_true",
        help="Attempt to auto-fix line number drift",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --fix, show what would be changed without applying",
    )
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Exit with error if any issues found",
    )

    args = parser.parse_args()

    checker = DriftChecker(args.project)

    # Handle fix mode
    if args.fix:
        fixes = checker.fix_drift(args.model, dry_run=args.dry_run)

        if not fixes:
            print("No fixable issues found.")
            return

        if args.dry_run:
            print("Fixes that would be applied:")
        else:
            print("Applied fixes:")

        for fix in fixes:
            print(f"  - {fix}")

        if args.dry_run:
            print(f"\nRun without --dry-run to apply {len(fixes)} fixes.")
        return

    # Regular check mode
    report = checker.check(args.model, include_info=args.include_info)

    # Output based on format
    output_format = OutputFormat(args.format)

    if output_format == OutputFormat.JSON:
        print(report.to_json())
    elif output_format == OutputFormat.MARKDOWN:
        print(report.to_markdown())
    else:
        print(report.to_table())

    # Summary for non-JSON output
    if output_format != OutputFormat.JSON:
        if report.has_issues:
            print(f"\nChecked {len(report.models_checked)} models, "
                  f"{report.files_checked} files, "
                  f"{report.mappings_checked} mappings")
        else:
            print(f"\n✅ Checked {len(report.models_checked)} models - no drift detected")

    # Exit with error if strict mode and issues found
    if args.strict and report.has_issues:
        sys.exit(1)


if __name__ == "__main__":
    main()

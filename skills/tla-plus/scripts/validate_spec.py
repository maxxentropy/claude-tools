#!/usr/bin/env python3
"""
TLA+ Specification Validator (SANY).

This module validates TLA+ specification syntax using SANY (Syntactic Analyzer):
- Parse and validate TLA+ syntax
- Check module structure
- Verify imports and extends
- Report detailed error locations
- Structured output (text, JSON, markdown)

SANY is part of the tla2tools.jar and is used before TLC for syntax checking.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from tla_store import TLAStore
from run_tlc import TLCRunner  # Reuse TLC jar download


class OutputFormat(str, Enum):
    """Output format options."""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


class ErrorSeverity(str, Enum):
    """Error severity levels."""

    ERROR = "error"
    WARNING = "warning"
    INFO = "info"


@dataclass
class SyntaxError:
    """A syntax error found during validation."""

    severity: ErrorSeverity
    message: str
    file: Optional[str] = None
    line: Optional[int] = None
    column: Optional[int] = None
    context: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v.value if isinstance(v, Enum) else v for k, v in asdict(self).items()}


@dataclass
class ModuleInfo:
    """Information about a validated module."""

    name: str
    file: str
    extends: list[str] = field(default_factory=list)
    constants: list[str] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    operators: list[str] = field(default_factory=list)


@dataclass
class ValidationResult:
    """Result of SANY validation."""

    success: bool
    file: str
    duration_seconds: float = 0.0
    errors: list[SyntaxError] = field(default_factory=list)
    warnings: list[SyntaxError] = field(default_factory=list)
    module_info: Optional[ModuleInfo] = None
    raw_output: str = ""

    def to_dict(self) -> dict:
        result = asdict(self)
        result["errors"] = [e.to_dict() for e in self.errors]
        result["warnings"] = [w.to_dict() for w in self.warnings]
        if self.module_info:
            result["module_info"] = asdict(self.module_info)
        return result

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        lines = [f"## Validation: {Path(self.file).name}"]
        lines.append("")

        status = "VALID" if self.success else "INVALID"
        icon = "[checkmark]" if self.success else "[cross]"
        lines.append(f"**Status:** {icon} **{status}**")
        lines.append(f"**Duration:** {self.duration_seconds:.2f}s")
        lines.append("")

        if self.module_info:
            lines.append("### Module Structure")
            lines.append(f"- **Name:** {self.module_info.name}")
            if self.module_info.extends:
                lines.append(f"- **Extends:** {', '.join(self.module_info.extends)}")
            if self.module_info.constants:
                lines.append(f"- **Constants:** {', '.join(self.module_info.constants)}")
            if self.module_info.variables:
                lines.append(f"- **Variables:** {', '.join(self.module_info.variables)}")
            if self.module_info.operators:
                lines.append(f"- **Operators:** {len(self.module_info.operators)} defined")
            lines.append("")

        if self.errors:
            lines.append("### Errors")
            for err in self.errors:
                location = ""
                if err.line:
                    location = f" (line {err.line}"
                    if err.column:
                        location += f", col {err.column}"
                    location += ")"
                lines.append(f"- **{err.severity.value.upper()}**{location}: {err.message}")
                if err.context:
                    lines.append(f"  ```")
                    lines.append(f"  {err.context}")
                    lines.append(f"  ```")
            lines.append("")

        if self.warnings:
            lines.append("### Warnings")
            for warn in self.warnings:
                lines.append(f"- {warn.message}")
            lines.append("")

        return "\n".join(lines)

    def to_text(self) -> str:
        lines = []
        status = "VALID" if self.success else "INVALID"
        lines.append(f"{Path(self.file).name}: {status}")

        if self.errors:
            for err in self.errors:
                location = f":{err.line}" if err.line else ""
                lines.append(f"  ERROR{location}: {err.message}")

        if self.warnings:
            for warn in self.warnings:
                lines.append(f"  WARNING: {warn.message}")

        return "\n".join(lines)


class SpecValidator:
    """Validates TLA+ specifications using SANY."""

    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)
        self.store = TLAStore(self.project_root)
        self.tlc_runner = TLCRunner(self.project_root)

    def validate(
        self,
        spec_file: Path | str,
        check_structure: bool = True,
        timeout_seconds: int = 60,
    ) -> ValidationResult:
        """
        Validate a TLA+ specification file.

        Args:
            spec_file: Path to .tla file
            check_structure: Also extract module structure info
            timeout_seconds: Timeout for validation

        Returns:
            ValidationResult with validation results
        """
        start_time = time.time()
        spec_path = Path(spec_file)

        if not spec_path.is_absolute():
            spec_path = self.project_root / spec_path

        if not spec_path.exists():
            return ValidationResult(
                success=False,
                file=str(spec_file),
                errors=[SyntaxError(
                    severity=ErrorSeverity.ERROR,
                    message=f"File not found: {spec_file}",
                )],
            )

        try:
            # Get TLA+ tools jar
            tlc_jar = self.tlc_runner.get_tlc_jar()

            # Run SANY directly using classpath
            # Must use absolute paths since we run from project root
            cmd = [
                "java",
                "-cp", str(tlc_jar.resolve()),
                "tla2sany.SANY",
                str(spec_path.resolve()),
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_seconds,
                cwd=self.project_root,  # Run from project root for consistent paths
            )

            duration = time.time() - start_time
            output = result.stdout + result.stderr

            # Parse SANY output
            errors, warnings = self._parse_errors(output, spec_path)

            # Determine success
            success = result.returncode == 0 and not errors

            # Extract module info if requested
            module_info = None
            if check_structure and success:
                module_info = self._extract_module_info(spec_path)

            return ValidationResult(
                success=success,
                file=str(spec_file),
                duration_seconds=duration,
                errors=errors,
                warnings=warnings,
                module_info=module_info,
                raw_output=output,
            )

        except subprocess.TimeoutExpired:
            return ValidationResult(
                success=False,
                file=str(spec_file),
                duration_seconds=timeout_seconds,
                errors=[SyntaxError(
                    severity=ErrorSeverity.ERROR,
                    message=f"Timeout after {timeout_seconds} seconds",
                )],
            )

        except Exception as e:
            return ValidationResult(
                success=False,
                file=str(spec_file),
                duration_seconds=time.time() - start_time,
                errors=[SyntaxError(
                    severity=ErrorSeverity.ERROR,
                    message=str(e),
                )],
            )

    def _parse_errors(
        self,
        output: str,
        spec_path: Path,
    ) -> tuple[list[SyntaxError], list[SyntaxError]]:
        """Parse SANY output for errors and warnings."""
        errors = []
        warnings = []

        # Error patterns
        error_patterns = [
            # Line-specific errors
            r"(?:Error|Aborting).*?line\s+(\d+),?\s*(?:col(?:umn)?\s*(\d+))?[:\s]*(.+)",
            # Parse errors
            r"Parse\s+Error.*?line\s+(\d+).*?:\s*(.+)",
            # Syntax errors
            r"Syntax\s+error.*?at\s+line\s+(\d+).*?:\s*(.+)",
            # General errors
            r"^\s*Error:\s*(.+)",
            # Semantic errors
            r"Semantic\s+error.*?line\s+(\d+).*?:\s*(.+)",
        ]

        # Warning patterns
        warning_patterns = [
            r"Warning.*?:\s*(.+)",
            r".*?is\s+never\s+used",
        ]

        lines = output.split("\n")
        current_context = None

        for i, line in enumerate(lines):
            # Check for errors
            for pattern in error_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    groups = match.groups()

                    # Parse based on pattern type
                    if len(groups) == 3:
                        line_num = int(groups[0]) if groups[0] else None
                        col_num = int(groups[1]) if groups[1] else None
                        message = groups[2].strip()
                    elif len(groups) == 2:
                        line_num = int(groups[0]) if groups[0] and groups[0].isdigit() else None
                        col_num = None
                        message = groups[1].strip()
                    else:
                        line_num = None
                        col_num = None
                        message = groups[0].strip()

                    # Try to get context from next line
                    context = None
                    if i + 1 < len(lines) and lines[i + 1].strip():
                        next_line = lines[i + 1].strip()
                        if not any(p in next_line.lower() for p in ["error", "warning", "abort"]):
                            context = next_line

                    errors.append(SyntaxError(
                        severity=ErrorSeverity.ERROR,
                        message=message,
                        file=str(spec_path.name),
                        line=line_num,
                        column=col_num,
                        context=context,
                    ))
                    break

            # Check for warnings
            for pattern in warning_patterns:
                match = re.search(pattern, line, re.IGNORECASE)
                if match:
                    warnings.append(SyntaxError(
                        severity=ErrorSeverity.WARNING,
                        message=match.group(1) if match.groups() else line.strip(),
                        file=str(spec_path.name),
                    ))
                    break

        # Check for common issues
        if "module name mismatch" in output.lower():
            errors.append(SyntaxError(
                severity=ErrorSeverity.ERROR,
                message="Module name does not match filename",
                file=str(spec_path.name),
            ))

        if "Could not find module" in output:
            match = re.search(r"Could not find module\s+(\w+)", output)
            if match:
                errors.append(SyntaxError(
                    severity=ErrorSeverity.ERROR,
                    message=f"Missing module: {match.group(1)}",
                    file=str(spec_path.name),
                ))

        return errors, warnings

    def _extract_module_info(self, spec_path: Path) -> ModuleInfo:
        """Extract module structure information."""
        content = spec_path.read_text()

        # Extract module name
        name_match = re.search(r"MODULE\s+(\w+)", content)
        module_name = name_match.group(1) if name_match else spec_path.stem

        # Extract EXTENDS
        extends = []
        extends_match = re.search(r"EXTENDS\s+([^\n]+)", content)
        if extends_match:
            extends = [e.strip() for e in extends_match.group(1).split(",")]

        # Extract CONSTANTS
        constants = []
        const_match = re.search(r"CONSTANTS?\s*\n(.*?)(?=VARIABLES?|\n\n|\\*\s*-----)", content, re.DOTALL)
        if const_match:
            const_text = const_match.group(1)
            constants = [
                c.strip().split()[0].rstrip(",")
                for c in const_text.split("\n")
                if c.strip() and not c.strip().startswith("\\*")
            ]

        # Extract VARIABLES
        variables = []
        var_match = re.search(r"VARIABLES?\s*\n\s*([^\n]+)", content)
        if var_match:
            var_text = var_match.group(1)
            variables = [v.strip().rstrip(",") for v in var_text.split(",") if v.strip()]

        # Extract operator names
        operators = []
        op_pattern = r"^(\w+)(?:\([^)]*\))?\s*==\s*$"
        for line in content.split("\n"):
            match = re.match(op_pattern, line.strip())
            if match:
                op_name = match.group(1)
                if op_name not in ["MODULE", "EXTENDS", "CONSTANTS", "VARIABLES"]:
                    operators.append(op_name)

        return ModuleInfo(
            name=module_name,
            file=str(spec_path),
            extends=extends,
            constants=constants,
            variables=variables,
            operators=operators,
        )

    def validate_model(self, model: str) -> list[ValidationResult]:
        """Validate all spec files for a model."""
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"
        model_dir = specs_dir / model

        if not model_dir.exists():
            return [ValidationResult(
                success=False,
                file=str(model_dir),
                errors=[SyntaxError(
                    severity=ErrorSeverity.ERROR,
                    message=f"Model directory not found: {model}",
                )],
            )]

        results = []
        for tla_file in model_dir.glob("*.tla"):
            result = self.validate(tla_file)
            results.append(result)

        return results

    def validate_all(self) -> list[ValidationResult]:
        """Validate all models in the project."""
        results = []
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"

        if not specs_dir.exists():
            return results

        for model_dir in specs_dir.iterdir():
            if not model_dir.is_dir() or model_dir.name.startswith(".") or model_dir.name == "common":
                continue

            model_results = self.validate_model(model_dir.name)
            results.extend(model_results)

        return results

    def list_models(self) -> list[str]:
        """List available models."""
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"

        if not specs_dir.exists():
            return []

        models = []
        for d in specs_dir.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != "common":
                if list(d.glob("*.tla")):
                    models.append(d.name)

        return sorted(models)


def main():
    """CLI for TLA+ validation."""
    import argparse

    parser = argparse.ArgumentParser(
        description="TLA+ Specification Validator (SANY)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --file specs/tla+/node-registration/NodeRegistration.tla
  %(prog)s --model node-registration
  %(prog)s --all --format markdown
  %(prog)s --file my-spec.tla --no-structure
        """,
    )

    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    parser.add_argument("--file", "-f", help="Specific .tla file to validate")
    parser.add_argument("--model", "-m", help="Model name to validate")
    parser.add_argument("--all", "-a", action="store_true", help="Validate all models")
    parser.add_argument("--no-structure", action="store_true", help="Skip structure extraction")
    parser.add_argument("--timeout", "-t", type=int, default=60, help="Timeout in seconds")
    parser.add_argument(
        "--format",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--list", "-l", action="store_true", help="List available models")
    parser.add_argument("--verbose", "-v", action="store_true", help="Show detailed output")

    args = parser.parse_args()

    validator = SpecValidator(args.project)

    if args.list:
        models = validator.list_models()
        if not models:
            print("No models found.")
        else:
            print("Available models:")
            for m in models:
                print(f"  {m}")
        return

    # Determine what to validate
    results = []

    if args.file:
        results = [validator.validate(
            args.file,
            check_structure=not args.no_structure,
            timeout_seconds=args.timeout,
        )]
    elif args.model:
        results = validator.validate_model(args.model)
    elif args.all:
        results = validator.validate_all()
    else:
        parser.error("One of --file, --model, or --all is required")

    if not results:
        print("No specifications found to validate.")
        return

    # Output results
    output_format = OutputFormat(args.format)
    all_success = all(r.success for r in results)

    if output_format == OutputFormat.JSON:
        output = {
            "results": [r.to_dict() for r in results],
            "success": all_success,
            "total": len(results),
            "passed": sum(1 for r in results if r.success),
        }
        print(json.dumps(output, indent=2))

    elif output_format == OutputFormat.MARKDOWN:
        for r in results:
            print(r.to_markdown())
            print("---")
        passed = sum(1 for r in results if r.success)
        print(f"\n**Summary:** {passed}/{len(results)} specifications valid")

    else:  # text
        for r in results:
            print(r.to_text())
            if args.verbose and r.raw_output:
                print("\n--- Raw Output ---")
                print(r.raw_output)
            print()

        passed = sum(1 for r in results if r.success)
        total = len(results)
        print(f"Summary: {passed}/{total} valid")

    # Exit with error if any failed
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()

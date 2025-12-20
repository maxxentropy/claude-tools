#!/usr/bin/env python3
"""
Apalache Symbolic Model Checker Runner.

This module provides functions to run the Apalache symbolic model checker:
- Bounded model checking with Z3
- Inductive invariant checking
- Type checking
- Structured output (text, JSON, markdown)
- CI integration support
- Automatic tool download

Apalache is complementary to TLC:
- TLC: Explicit state enumeration, fast for small state spaces
- Apalache: Symbolic/SMT-based, handles larger/infinite state spaces
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from tla_store import TLAStore


class CheckMode(str, Enum):
    """Apalache checking modes."""

    CHECK = "check"              # Standard bounded model checking
    TYPECHECK = "typecheck"      # Type checking only
    SIMULATE = "simulate"        # Random simulation
    TEST = "test"                # Test invariants


class OutputFormat(str, Enum):
    """Output format options."""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


@dataclass
class ApalacheResult:
    """Result of an Apalache verification run."""

    success: bool
    model: str
    mode: str
    length: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    error_type: Optional[str] = None
    counterexample_file: Optional[str] = None
    type_errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    apalache_version: Optional[str] = None
    spec_file: Optional[str] = None
    stats: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        return asdict(self)

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = [f"## Apalache Verification: {self.model}"]
        lines.append("")

        status = "PASSED" if self.success else "FAILED"
        lines.append(f"**Status:** {'[checkmark]' if self.success else '[cross]'} **{status}**")
        lines.append(f"**Mode:** {self.mode}")
        lines.append(f"**Bound Length:** {self.length}")
        lines.append(f"**Duration:** {self.duration_seconds:.2f}s")
        lines.append("")

        if self.stats:
            lines.append("### Statistics")
            for key, value in self.stats.items():
                lines.append(f"- {key}: {value}")
            lines.append("")

        if self.error:
            lines.append("### Error")
            lines.append(f"**Type:** {self.error_type or 'Unknown'}")
            lines.append("```")
            lines.append(self.error)
            lines.append("```")
            lines.append("")

        if self.type_errors:
            lines.append("### Type Errors")
            for err in self.type_errors:
                lines.append(f"- {err}")
            lines.append("")

        if self.counterexample_file:
            lines.append("### Counterexample")
            lines.append(f"See: `{self.counterexample_file}`")
            lines.append("")

        if self.warnings:
            lines.append("### Warnings")
            for w in self.warnings:
                lines.append(f"- {w}")
            lines.append("")

        return "\n".join(lines)

    def to_text(self) -> str:
        """Convert to plain text format."""
        lines = []
        status = "PASSED" if self.success else "FAILED"
        lines.append(f"Model: {self.model} [{status}]")
        lines.append(f"Mode: {self.mode}")
        lines.append(f"Bound: {self.length} steps")
        lines.append(f"Duration: {self.duration_seconds:.2f}s")

        if self.error:
            lines.append(f"Error: {self.error}")

        if self.counterexample_file:
            lines.append(f"Counterexample: {self.counterexample_file}")

        return "\n".join(lines)


class ApalacheRunner:
    """Runs Apalache symbolic model checker."""

    APALACHE_VERSION = "0.44.11"
    APALACHE_URL = f"https://github.com/apalache-mc/apalache/releases/download/v{APALACHE_VERSION}/apalache-{APALACHE_VERSION}.tgz"
    APALACHE_DIR = "apalache"

    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)
        self.store = TLAStore(self.project_root)

    def get_tools_dir(self) -> Path:
        """Get the tools directory, creating if needed."""
        if self.store.is_initialized():
            return self.store.get_tools_dir()
        # Default fallback
        tools_dir = self.project_root / "specs" / "tla+" / ".tools"
        tools_dir.mkdir(parents=True, exist_ok=True)
        return tools_dir

    def get_apalache_path(self) -> Path:
        """Get path to Apalache, downloading if needed."""
        tools_dir = self.get_tools_dir()
        apalache_dir = tools_dir / self.APALACHE_DIR

        if not apalache_dir.exists():
            print(f"Downloading Apalache {self.APALACHE_VERSION}...", file=sys.stderr)
            self._download_apalache(apalache_dir)

        # Find the apalache-mc script
        script = apalache_dir / "bin" / "apalache-mc"
        if not script.exists():
            # Try nested directory (apalache-{version}/bin/apalache-mc)
            nested = list(apalache_dir.glob("*/bin/apalache-mc"))
            if nested:
                script = nested[0]

        return script

    def _download_apalache(self, target_dir: Path) -> None:
        """Download and extract Apalache."""
        target_dir.parent.mkdir(parents=True, exist_ok=True)

        # Download tarball
        with tempfile.NamedTemporaryFile(suffix=".tgz", delete=False) as tmp:
            tmp_path = Path(tmp.name)

        try:
            urllib.request.urlretrieve(self.APALACHE_URL, tmp_path)

            # Extract
            target_dir.mkdir(parents=True, exist_ok=True)
            with tarfile.open(tmp_path, "r:gz") as tar:
                tar.extractall(target_dir)

            # Make script executable
            for script in target_dir.rglob("apalache-mc"):
                script.chmod(script.stat().st_mode | 0o111)

        finally:
            tmp_path.unlink(missing_ok=True)

    def find_model_files(self, model: str) -> tuple[Path, Optional[Path]]:
        """Find spec and config files for a model."""
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"
        model_dir = specs_dir / model

        if not model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        # Find main spec file (not Race or Buggy)
        tla_files = list(model_dir.glob("*.tla"))
        main_files = [f for f in tla_files if not any(x in f.stem for x in ["Race", "Buggy", "MC"])]

        if not main_files:
            raise FileNotFoundError(f"No main .tla file found in {model_dir}")

        spec_file = main_files[0]

        # Find config file (optional for Apalache)
        cfg_files = list(model_dir.glob("*.cfg"))
        config_file = None
        for cfg in cfg_files:
            if not any(x in cfg.stem for x in ["Large", "Race", "Buggy"]):
                config_file = cfg
                break

        return spec_file, config_file

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

    def check_installation(self) -> tuple[bool, str]:
        """Check if Apalache is properly installed."""
        try:
            apalache = self.get_apalache_path()
            if not apalache.exists():
                return False, f"Apalache script not found at {apalache}"

            # Try running version check
            result = subprocess.run(
                [str(apalache), "version"],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode == 0:
                return True, result.stdout.strip()
            else:
                return False, result.stderr

        except Exception as e:
            return False, str(e)

    def run(
        self,
        model: str,
        mode: CheckMode = CheckMode.CHECK,
        length: int = 10,
        inv: Optional[str] = None,
        config: Optional[str] = None,
        init: Optional[str] = None,
        next_action: Optional[str] = None,
        cinit: Optional[str] = None,
        timeout_minutes: int = 30,
        workers: int = 1,
        smt_encoding: str = "oopsla19",
        discard_disabled: bool = True,
        no_deadlock: bool = True,
        out_dir: Optional[str] = None,
    ) -> ApalacheResult:
        """
        Run Apalache model checker.

        Args:
            model: Model name (directory under specs/tla+/)
            mode: Checking mode (check, typecheck, simulate, test)
            length: Maximum trace length (bound)
            inv: Specific invariant to check
            config: Specific config file
            init: Init predicate name (overrides config)
            next_action: Next predicate name (overrides config)
            cinit: Constant initialization predicate
            timeout_minutes: Timeout in minutes
            workers: Number of parallel workers
            smt_encoding: SMT encoding (oopsla19, arrays)
            discard_disabled: Discard disabled transitions
            no_deadlock: Check for deadlock-free
            out_dir: Output directory for results

        Returns:
            ApalacheResult with verification results
        """
        start_time = time.time()

        try:
            spec_file, config_file = self.find_model_files(model)

            # Override config
            if config:
                model_dir = spec_file.parent
                explicit_cfg = model_dir / config
                if explicit_cfg.exists():
                    config_file = explicit_cfg

            apalache = self.get_apalache_path()

            # Determine output directory
            if out_dir:
                output_path = Path(out_dir)
            else:
                output_path = spec_file.parent / "_apalache-out"
            output_path.mkdir(parents=True, exist_ok=True)

            # Build command
            cmd = [str(apalache)]

            if mode == CheckMode.CHECK:
                cmd.append("check")
                cmd.extend(["--length", str(length)])

                if inv:
                    cmd.extend(["--inv", inv])

                if init:
                    cmd.extend(["--init", init])
                elif config_file:
                    init_from_cfg = self._extract_from_cfg(config_file, "INIT")
                    if init_from_cfg:
                        cmd.extend(["--init", init_from_cfg])

                if next_action:
                    cmd.extend(["--next", next_action])
                elif config_file:
                    next_from_cfg = self._extract_from_cfg(config_file, "NEXT")
                    if next_from_cfg:
                        cmd.extend(["--next", next_from_cfg])

                if cinit:
                    cmd.extend(["--cinit", cinit])

                cmd.extend(["--smt-encoding", smt_encoding])

                if discard_disabled:
                    cmd.append("--discard-disabled")

                if no_deadlock:
                    cmd.append("--no-deadlock")

            elif mode == CheckMode.TYPECHECK:
                cmd.append("typecheck")

            elif mode == CheckMode.SIMULATE:
                cmd.append("simulate")
                cmd.extend(["--length", str(length)])
                cmd.extend(["--max-run", "100"])

            elif mode == CheckMode.TEST:
                cmd.append("test")
                if inv:
                    cmd.extend(["--inv", inv])

            # Common options
            cmd.extend(["--out-dir", str(output_path)])
            cmd.extend(["--write-intermediate", "false"])

            # Add spec file
            cmd.append(str(spec_file))

            # Run Apalache
            env = os.environ.copy()
            # Apalache needs Java
            if "JAVA_HOME" not in env:
                java_path = shutil.which("java")
                if java_path:
                    java_home = Path(java_path).parent.parent
                    env["JAVA_HOME"] = str(java_home)

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_minutes * 60,
                cwd=spec_file.parent,
                env=env,
            )

            duration = time.time() - start_time
            output = result.stdout + result.stderr

            # Parse output
            return self._parse_output(
                output=output,
                exit_code=result.returncode,
                model=model,
                mode=mode.value,
                length=length,
                duration=duration,
                spec_file=str(spec_file),
                out_dir=str(output_path),
            )

        except subprocess.TimeoutExpired:
            return ApalacheResult(
                success=False,
                model=model,
                mode=mode.value,
                length=length,
                duration_seconds=timeout_minutes * 60,
                error=f"Timeout after {timeout_minutes} minutes",
                error_type="Timeout",
            )

        except FileNotFoundError as e:
            return ApalacheResult(
                success=False,
                model=model,
                mode=mode.value,
                length=length,
                duration_seconds=time.time() - start_time,
                error=str(e),
                error_type="FileNotFound",
            )

        except Exception as e:
            return ApalacheResult(
                success=False,
                model=model,
                mode=mode.value,
                length=length,
                duration_seconds=time.time() - start_time,
                error=str(e),
                error_type=type(e).__name__,
            )

    def _extract_from_cfg(self, cfg_file: Path, key: str) -> Optional[str]:
        """Extract value from config file."""
        content = cfg_file.read_text()
        pattern = rf"{key}\s+(\w+)"
        match = re.search(pattern, content)
        return match.group(1) if match else None

    def _parse_output(
        self,
        output: str,
        exit_code: int,
        model: str,
        mode: str,
        length: int,
        duration: float,
        spec_file: str,
        out_dir: str,
    ) -> ApalacheResult:
        """Parse Apalache output into structured result."""
        result = ApalacheResult(
            success=exit_code == 0,
            model=model,
            mode=mode,
            length=length,
            duration_seconds=duration,
            spec_file=spec_file,
        )

        # Extract version
        version_match = re.search(r"Apalache\s+(\S+)", output)
        if version_match:
            result.apalache_version = version_match.group(1)

        # Check for success messages
        if "The outcome is: NoError" in output or "PASS" in output:
            result.success = True

        # Check for errors
        if "The outcome is: Error" in output or "FAIL" in output:
            result.success = False

        # Extract error message
        error_match = re.search(r"Error:\s*(.+?)(?:\n|$)", output)
        if error_match:
            result.error = error_match.group(1).strip()

        # Determine error type
        if "Counterexample" in output or "counterexample" in output:
            result.error_type = "Counterexample"
            # Look for counterexample file
            ce_match = re.search(r"counterexample\d*\.tla", output)
            if ce_match:
                result.counterexample_file = str(Path(out_dir) / ce_match.group(0))

        elif "type error" in output.lower() or "Type error" in output:
            result.error_type = "TypeError"
            # Extract type errors
            for line in output.split("\n"):
                if "type error" in line.lower() or "Type error" in line:
                    result.type_errors.append(line.strip())

        elif "Deadlock" in output:
            result.error_type = "Deadlock"

        elif "Invariant" in output and "violated" in output:
            result.error_type = "InvariantViolation"
            inv_match = re.search(r"Invariant\s+(\w+)", output)
            if inv_match:
                result.error = f"Invariant {inv_match.group(1)} violated"

        # Extract statistics
        stats_patterns = {
            "states_explored": r"Explored\s+(\d+)\s+state",
            "transitions": r"(\d+)\s+transition",
            "smt_calls": r"(\d+)\s+SMT.*call",
            "z3_time": r"Z3.*?(\d+\.?\d*)\s*s",
        }

        for stat_name, pattern in stats_patterns.items():
            match = re.search(pattern, output, re.IGNORECASE)
            if match:
                result.stats[stat_name] = match.group(1)

        # Extract warnings
        for line in output.split("\n"):
            if line.startswith("Warning:") or line.startswith("WARN"):
                result.warnings.append(line.strip())

        return result

    def typecheck(self, model: str) -> ApalacheResult:
        """Run type checking only."""
        return self.run(model, mode=CheckMode.TYPECHECK)

    def check_inductive(
        self,
        model: str,
        inv: str,
        length: int = 1,
    ) -> ApalacheResult:
        r"""
        Check if an invariant is inductive.

        An invariant Inv is inductive if:
        1. Init => Inv
        2. Inv /\ Next => Inv'

        This checks step 2 with a length-1 execution.
        """
        return self.run(
            model=model,
            mode=CheckMode.CHECK,
            inv=inv,
            length=length,
        )

    def run_all(
        self,
        mode: CheckMode = CheckMode.CHECK,
        length: int = 10,
        timeout_minutes: int = 30,
    ) -> list[ApalacheResult]:
        """Run Apalache on all models."""
        models = self.list_models()
        results = []

        for model in models:
            result = self.run(
                model=model,
                mode=mode,
                length=length,
                timeout_minutes=timeout_minutes,
            )
            results.append(result)

        return results


def main():
    """CLI for Apalache runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Apalache Symbolic Model Checker Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --model node-registration --length 10
  %(prog)s --model token-refresh --check-inductive --inv SafetyInvariant
  %(prog)s --model order-locking --typecheck
  %(prog)s --all --length 5 --format json
  %(prog)s --check-install
        """,
    )

    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    parser.add_argument("--model", "-m", help="Model name to verify")
    parser.add_argument("--all", "-a", action="store_true", help="Verify all models")
    parser.add_argument(
        "--mode",
        choices=["check", "typecheck", "simulate", "test"],
        default="check",
        help="Checking mode (default: check)",
    )
    parser.add_argument("--length", "-l", type=int, default=10, help="Maximum trace length (default: 10)")
    parser.add_argument("--inv", help="Specific invariant to check")
    parser.add_argument("--config", "-c", help="Specific config file")
    parser.add_argument("--init", help="Init predicate name")
    parser.add_argument("--next", dest="next_action", help="Next predicate name")
    parser.add_argument("--check-inductive", action="store_true", help="Check if invariant is inductive")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Timeout in minutes")
    parser.add_argument("--out-dir", "-o", help="Output directory for results")
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--list", action="store_true", help="List available models")
    parser.add_argument("--check-install", action="store_true", help="Check Apalache installation")

    args = parser.parse_args()

    runner = ApalacheRunner(args.project)

    if args.check_install:
        ok, msg = runner.check_installation()
        if ok:
            print(f"Apalache is installed: {msg}")
        else:
            print(f"Apalache not found or error: {msg}")
            print(f"\nTrying to download Apalache {runner.APALACHE_VERSION}...")
            try:
                runner.get_apalache_path()
                print("Apalache downloaded successfully!")
            except Exception as e:
                print(f"Failed to download: {e}")
                sys.exit(1)
        return

    if args.list:
        models = runner.list_models()
        if not models:
            print("No models found.")
        else:
            print("Available models:")
            for m in models:
                print(f"  {m}")
        return

    if not args.model and not args.all:
        parser.error("Either --model or --all is required")

    mode = CheckMode(args.mode)
    output_format = OutputFormat(args.format)

    if args.all:
        results = runner.run_all(
            mode=mode,
            length=args.length,
            timeout_minutes=args.timeout,
        )
    elif args.check_inductive:
        if not args.inv:
            parser.error("--inv required for --check-inductive")
        results = [runner.check_inductive(
            model=args.model,
            inv=args.inv,
            length=args.length,
        )]
    else:
        results = [runner.run(
            model=args.model,
            mode=mode,
            length=args.length,
            inv=args.inv,
            config=args.config,
            init=args.init,
            next_action=args.next_action,
            timeout_minutes=args.timeout,
            out_dir=args.out_dir,
        )]

    # Output results
    all_success = all(r.success for r in results)

    if output_format == OutputFormat.JSON:
        output = {"results": [r.to_dict() for r in results], "success": all_success}
        print(json.dumps(output, indent=2))
    elif output_format == OutputFormat.MARKDOWN:
        for r in results:
            print(r.to_markdown())
            print("---")
        summary = "All models passed!" if all_success else "Some models failed."
        print(f"\n**Summary:** {summary}")
    else:
        for r in results:
            print(r.to_text())
            print()
        passed = sum(1 for r in results if r.success)
        total = len(results)
        print(f"Summary: {passed}/{total} models passed")

    # Exit with error if any failed
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()

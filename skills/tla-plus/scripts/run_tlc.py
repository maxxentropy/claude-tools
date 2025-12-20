#!/usr/bin/env python3
"""
TLC Model Checker Runner - Run TLA+ verification with structured output.

This module provides functions to run TLC model checker with:
- Multiple verification modes (quick/simulation, standard, thorough)
- Structured output (text, JSON, markdown)
- CI integration support
- Automatic tool download
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.request
from dataclasses import dataclass, field, asdict
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from tla_store import TLAStore


class VerificationMode(str, Enum):
    """TLC verification modes."""

    QUICK = "quick"  # Simulation mode, fast feedback
    STANDARD = "standard"  # Full BFS with default config
    THOROUGH = "thorough"  # Full BFS with large config


class OutputFormat(str, Enum):
    """Output format options."""

    TEXT = "text"
    JSON = "json"
    MARKDOWN = "markdown"


@dataclass
class CounterexampleState:
    """A single state in a counterexample trace."""

    state_num: int
    action: Optional[str]
    variables: dict[str, str]


@dataclass
class TLCResult:
    """Result of a TLC verification run."""

    success: bool
    model: str
    mode: str
    states_generated: int = 0
    distinct_states: int = 0
    depth: int = 0
    duration_seconds: float = 0.0
    error: Optional[str] = None
    error_type: Optional[str] = None
    counterexample: list[CounterexampleState] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    tlc_version: Optional[str] = None
    spec_file: Optional[str] = None
    config_file: Optional[str] = None

    def to_dict(self) -> dict:
        """Convert to dictionary for JSON serialization."""
        result = asdict(self)
        result["counterexample"] = [asdict(s) for s in self.counterexample]
        return result

    def to_json(self, indent: int = 2) -> str:
        """Convert to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        """Convert to markdown format."""
        lines = [f"## TLC Verification: {self.model}"]
        lines.append("")

        status = "✅ **PASSED**" if self.success else "❌ **FAILED**"
        lines.append(f"**Status:** {status}")
        lines.append(f"**Mode:** {self.mode}")
        lines.append(f"**Duration:** {self.duration_seconds:.2f}s")
        lines.append("")

        if self.states_generated > 0:
            lines.append("### Statistics")
            lines.append(f"- States generated: {self.states_generated:,}")
            lines.append(f"- Distinct states: {self.distinct_states:,}")
            lines.append(f"- Depth: {self.depth}")
            lines.append("")

        if self.error:
            lines.append("### Error")
            lines.append(f"**Type:** {self.error_type or 'Unknown'}")
            lines.append("```")
            lines.append(self.error)
            lines.append("```")
            lines.append("")

        if self.counterexample:
            lines.append("### Counterexample Trace")
            for state in self.counterexample:
                action_str = f" (Action: {state.action})" if state.action else ""
                lines.append(f"**State {state.state_num}**{action_str}")
                for var, val in state.variables.items():
                    lines.append(f"  - {var} = {val}")
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
        lines.append(f"Duration: {self.duration_seconds:.2f}s")

        if self.states_generated > 0:
            lines.append(f"States: {self.states_generated:,} generated, {self.distinct_states:,} distinct")
            lines.append(f"Depth: {self.depth}")

        if self.error:
            lines.append(f"Error: {self.error}")

        return "\n".join(lines)


class TLCRunner:
    """Runs TLC model checker with various configurations."""

    TLC_VERSION = "1.8.0"
    TLC_URL = f"https://github.com/tlaplus/tlaplus/releases/download/v{TLC_VERSION}/tla2tools.jar"
    TLC_JAR = "tla2tools.jar"

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

    def get_tlc_jar(self) -> Path:
        """Get path to TLC jar, downloading if needed."""
        tools_dir = self.get_tools_dir()
        tlc_jar = tools_dir / self.TLC_JAR

        if not tlc_jar.exists():
            print(f"Downloading TLC {self.TLC_VERSION}...", file=sys.stderr)
            self._download_tlc(tlc_jar)

        return tlc_jar

    def _download_tlc(self, target: Path) -> None:
        """Download TLC jar file."""
        target.parent.mkdir(parents=True, exist_ok=True)
        urllib.request.urlretrieve(self.TLC_URL, target)

    def find_model_files(self, model: str) -> tuple[Path, Path]:
        """Find spec and config files for a model."""
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"
        model_dir = specs_dir / model

        if not model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        # Find main spec file (not Race or Buggy)
        tla_files = list(model_dir.glob("*.tla"))
        main_files = [f for f in tla_files if not any(x in f.stem for x in ["Race", "Buggy"])]

        if not main_files:
            raise FileNotFoundError(f"No main .tla file found in {model_dir}")

        spec_file = main_files[0]

        # Find config file - exclude Race, Buggy, and Large variants
        cfg_files = list(model_dir.glob("*.cfg"))
        if not cfg_files:
            raise FileNotFoundError(f"No .cfg file found in {model_dir}")

        # Prefer standard config (not Large, Race, or Buggy)
        config_file = None
        for cfg in cfg_files:
            if not any(x in cfg.stem for x in ["Large", "Race", "Buggy"]):
                config_file = cfg
                break

        # Fallback to first non-Large config
        if config_file is None:
            for cfg in cfg_files:
                if "Large" not in cfg.stem:
                    config_file = cfg
                    break

        # Last resort: use first config
        if config_file is None:
            config_file = cfg_files[0]

        return spec_file, config_file

    def find_large_config(self, model: str) -> Optional[Path]:
        """Find large config file for thorough verification."""
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"
        model_dir = specs_dir / model

        for cfg in model_dir.glob("*_Large.cfg"):
            return cfg
        return None

    def list_models(self) -> list[str]:
        """List available models."""
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"

        if not specs_dir.exists():
            return []

        models = []
        for d in specs_dir.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != "common":
                # Check if it has TLA files
                if list(d.glob("*.tla")):
                    models.append(d.name)

        return sorted(models)

    def run(
        self,
        model: str,
        mode: VerificationMode = VerificationMode.QUICK,
        config: Optional[str] = None,
        workers: int = -1,
        simulation_depth: int = 100000,
        timeout_minutes: int = 30,
    ) -> TLCResult:
        """
        Run TLC model checker.

        Args:
            model: Model name (directory under specs/tla+/)
            mode: Verification mode (quick, standard, thorough)
            config: Specific config file (optional)
            workers: Number of workers (-1 for auto)
            simulation_depth: Number of traces for simulation mode
            timeout_minutes: Timeout in minutes

        Returns:
            TLCResult with verification results
        """
        start_time = time.time()

        try:
            spec_file, config_file = self.find_model_files(model)

            # Override config for thorough mode
            if mode == VerificationMode.THOROUGH:
                large_cfg = self.find_large_config(model)
                if large_cfg:
                    config_file = large_cfg

            # Override with explicit config
            if config:
                model_dir = spec_file.parent
                explicit_cfg = model_dir / config
                if explicit_cfg.exists():
                    config_file = explicit_cfg

            tlc_jar = self.get_tlc_jar()

            # Build command - use absolute paths
            cmd = [
                "java",
                "-XX:+UseParallelGC",
                "-jar", str(tlc_jar.resolve()),
                "-config", str(config_file.resolve()),
                "-workers", "auto" if workers == -1 else str(workers),
                "-deadlock",
            ]

            # Add simulation mode for quick verification
            if mode == VerificationMode.QUICK:
                cmd.extend(["-simulate", f"num={simulation_depth}"])

            cmd.append(str(spec_file.resolve()))

            # Run TLC
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_minutes * 60,
                cwd=spec_file.parent,
            )

            duration = time.time() - start_time
            output = result.stdout + result.stderr

            # Parse output
            return self._parse_output(
                output=output,
                exit_code=result.returncode,
                model=model,
                mode=mode.value,
                duration=duration,
                spec_file=str(spec_file),
                config_file=str(config_file),
            )

        except subprocess.TimeoutExpired:
            return TLCResult(
                success=False,
                model=model,
                mode=mode.value,
                duration_seconds=timeout_minutes * 60,
                error=f"Timeout after {timeout_minutes} minutes",
                error_type="Timeout",
            )

        except FileNotFoundError as e:
            return TLCResult(
                success=False,
                model=model,
                mode=mode.value,
                duration_seconds=time.time() - start_time,
                error=str(e),
                error_type="FileNotFound",
            )

        except Exception as e:
            return TLCResult(
                success=False,
                model=model,
                mode=mode.value,
                duration_seconds=time.time() - start_time,
                error=str(e),
                error_type=type(e).__name__,
            )

    def _parse_output(
        self,
        output: str,
        exit_code: int,
        model: str,
        mode: str,
        duration: float,
        spec_file: str,
        config_file: str,
    ) -> TLCResult:
        """Parse TLC output into structured result."""
        result = TLCResult(
            success=exit_code == 0,
            model=model,
            mode=mode,
            duration_seconds=duration,
            spec_file=spec_file,
            config_file=config_file,
        )

        # Extract TLC version
        version_match = re.search(r"TLC2 Version (\S+)", output)
        if version_match:
            result.tlc_version = version_match.group(1)

        # Extract states
        states_match = re.search(
            r"(\d+) states generated.*?(\d+) distinct states",
            output.replace(",", ""),
        )
        if states_match:
            result.states_generated = int(states_match.group(1))
            result.distinct_states = int(states_match.group(2))

        # Extract depth
        depth_match = re.search(r"depth.*?(\d+)", output, re.IGNORECASE)
        if depth_match:
            result.depth = int(depth_match.group(1))

        # Extract warnings
        for line in output.split("\n"):
            if line.startswith("Warning:"):
                result.warnings.append(line[8:].strip())

        # Check for errors
        if "Error:" in output or "Invariant" in output and "violated" in output:
            result.success = False

            # Extract error message
            error_match = re.search(r"Error: (.+?)(?:\n|$)", output)
            if error_match:
                result.error = error_match.group(1)

            # Determine error type
            if "Invariant" in output and "violated" in output:
                result.error_type = "InvariantViolation"
                inv_match = re.search(r"Invariant (\w+) is violated", output)
                if inv_match:
                    result.error = f"Invariant {inv_match.group(1)} is violated"

            elif "Deadlock" in output:
                result.error_type = "Deadlock"

            elif "assertion failed" in output.lower():
                result.error_type = "AssertionFailed"

            # Extract counterexample (simplified)
            result.counterexample = self._parse_counterexample(output)

        # Check for successful completion
        if "Model checking completed. No error has been found." in output:
            result.success = True
        elif "Finished in" in output and not result.error:
            result.success = True

        return result

    def _parse_counterexample(self, output: str) -> list[CounterexampleState]:
        """Parse counterexample trace from TLC output."""
        states = []
        current_state = None
        current_vars = {}

        for line in output.split("\n"):
            # State header
            state_match = re.match(r"State (\d+):", line)
            if state_match:
                if current_state is not None:
                    states.append(CounterexampleState(
                        state_num=current_state,
                        action=None,
                        variables=current_vars,
                    ))
                current_state = int(state_match.group(1))
                current_vars = {}
                continue

            # Variable assignment
            if current_state is not None and "=" in line:
                var_match = re.match(r"/\\ (\w+) = (.+)", line.strip())
                if var_match:
                    current_vars[var_match.group(1)] = var_match.group(2)

        # Add last state
        if current_state is not None:
            states.append(CounterexampleState(
                state_num=current_state,
                action=None,
                variables=current_vars,
            ))

        return states

    def run_all(
        self,
        mode: VerificationMode = VerificationMode.QUICK,
        workers: int = -1,
        simulation_depth: int = 100000,
        timeout_minutes: int = 30,
    ) -> list[TLCResult]:
        """Run TLC on all models."""
        models = self.list_models()
        results = []

        for model in models:
            result = self.run(
                model=model,
                mode=mode,
                workers=workers,
                simulation_depth=simulation_depth,
                timeout_minutes=timeout_minutes,
            )
            results.append(result)

        return results


def main():
    """CLI for TLC runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="TLC Model Checker Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --model node-registration --mode quick
  %(prog)s --all --mode standard --format json
  %(prog)s --model token-refresh --mode thorough
        """,
    )

    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    parser.add_argument("--model", "-m", help="Model name to verify")
    parser.add_argument("--all", "-a", action="store_true", help="Verify all models")
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "thorough"],
        default="quick",
        help="Verification mode (default: quick)",
    )
    parser.add_argument("--config", "-c", help="Specific config file")
    parser.add_argument("--workers", "-w", type=int, default=-1, help="Number of workers (-1 for auto)")
    parser.add_argument("--depth", "-d", type=int, default=100000, help="Simulation depth for quick mode")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Timeout in minutes")
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--list", "-l", action="store_true", help="List available models")

    args = parser.parse_args()

    runner = TLCRunner(args.project)

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

    mode = VerificationMode(args.mode)
    output_format = OutputFormat(args.format)

    if args.all:
        results = runner.run_all(
            mode=mode,
            workers=args.workers,
            simulation_depth=args.depth,
            timeout_minutes=args.timeout,
        )
    else:
        results = [runner.run(
            model=args.model,
            mode=mode,
            config=args.config,
            workers=args.workers,
            simulation_depth=args.depth,
            timeout_minutes=args.timeout,
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

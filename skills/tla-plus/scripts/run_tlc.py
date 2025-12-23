#!/usr/bin/env python3
"""
TLC Model Checker Runner - Run TLA+ verification with structured output.

This module provides functions to run TLC model checker with:
- Multiple verification modes (quick/simulation, standard, thorough)
- Structured output (text, JSON, markdown, JUnit XML)
- CI integration support
- Automatic tool download
- Negative testing (buggy variant verification)
- Parallel execution support

Unified runner for XTConnect TLA+ verification ecosystem.
See: docs/TLA_PLUS_BEST_PRACTICES.md
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
import xml.etree.ElementTree as ET
from concurrent.futures import ProcessPoolExecutor, as_completed
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

    def to_junit_testcase(self) -> ET.Element:
        """Convert to JUnit XML testcase element."""
        testcase = ET.Element("testcase")
        testcase.set("name", self.model)
        testcase.set("classname", f"TLA.{self.mode}")
        testcase.set("time", f"{self.duration_seconds:.3f}")

        if not self.success:
            if self.error_type == "InvariantViolation":
                failure = ET.SubElement(testcase, "failure")
                failure.set("type", "InvariantViolation")
                failure.set("message", self.error or "Invariant violated")
                if self.counterexample:
                    trace = "\n".join(
                        f"State {s.state_num}: {s.variables}"
                        for s in self.counterexample
                    )
                    failure.text = trace
            else:
                error_elem = ET.SubElement(testcase, "error")
                error_elem.set("type", self.error_type or "Error")
                error_elem.set("message", self.error or "Unknown error")

        return testcase


def results_to_junit(results: list[TLCResult], suite_name: str = "TLA+ Verification") -> str:
    """Convert list of results to JUnit XML format."""
    testsuite = ET.Element("testsuite")
    testsuite.set("name", suite_name)
    testsuite.set("tests", str(len(results)))
    testsuite.set("failures", str(sum(1 for r in results if not r.success and r.error_type == "InvariantViolation")))
    testsuite.set("errors", str(sum(1 for r in results if not r.success and r.error_type != "InvariantViolation")))
    testsuite.set("time", f"{sum(r.duration_seconds for r in results):.3f}")

    for result in results:
        testsuite.append(result.to_junit_testcase())

    # Pretty print
    ET.indent(testsuite)
    return ET.tostring(testsuite, encoding="unicode", xml_declaration=True)


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

    def list_buggy_models(self) -> list[str]:
        """List models that have buggy variants."""
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"

        if not specs_dir.exists():
            return []

        buggy = []
        for d in specs_dir.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != "common":
                if list(d.glob("*Buggy.tla")):
                    buggy.append(d.name)

        return sorted(buggy)

    def find_buggy_model_files(self, model: str) -> tuple[Path, Path]:
        """Find buggy spec and config files for a model."""
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"
        model_dir = specs_dir / model

        if not model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        # Find buggy spec file
        buggy_files = list(model_dir.glob("*Buggy.tla"))
        if not buggy_files:
            raise FileNotFoundError(f"No buggy .tla file found in {model_dir}")

        spec_file = buggy_files[0]

        # Find buggy config file
        buggy_cfgs = list(model_dir.glob("*Buggy.cfg"))
        if not buggy_cfgs:
            raise FileNotFoundError(f"No buggy .cfg file found in {model_dir}")

        config_file = buggy_cfgs[0]

        return spec_file, config_file

    def filter_models(self, models: list[str], spec_filter: Optional[str]) -> list[str]:
        """Filter models by spec name pattern."""
        if not spec_filter:
            return models

        # Support comma-separated list or single spec
        if "," in spec_filter:
            filters = [f.strip() for f in spec_filter.split(",")]
        else:
            filters = [spec_filter]

        filtered = []
        for model in models:
            for f in filters:
                if f in model or model.startswith(f):
                    filtered.append(model)
                    break

        return filtered

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
        spec_filter: Optional[str] = None,
    ) -> list[TLCResult]:
        """Run TLC on all models."""
        models = self.filter_models(self.list_models(), spec_filter)
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

    def run_buggy(
        self,
        model: str,
        mode: VerificationMode = VerificationMode.QUICK,
        workers: int = -1,
        simulation_depth: int = 100000,
        timeout_minutes: int = 30,
    ) -> TLCResult:
        """Run TLC on a buggy model variant (expects failure)."""
        start_time = time.time()

        try:
            spec_file, config_file = self.find_buggy_model_files(model)
            tlc_jar = self.get_tlc_jar()

            cmd = [
                "java",
                "-XX:+UseParallelGC",
                "-jar", str(tlc_jar.resolve()),
                "-config", str(config_file.resolve()),
                "-workers", "auto" if workers == -1 else str(workers),
                "-deadlock",
            ]

            if mode == VerificationMode.QUICK:
                cmd.extend(["-simulate", f"num={simulation_depth}"])

            cmd.append(str(spec_file.resolve()))

            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout_minutes * 60,
                cwd=spec_file.parent,
            )

            duration = time.time() - start_time
            output = result.stdout + result.stderr

            tlc_result = self._parse_output(
                output=output,
                exit_code=result.returncode,
                model=f"{model}Buggy",
                mode=mode.value,
                duration=duration,
                spec_file=str(spec_file),
                config_file=str(config_file),
            )

            return tlc_result

        except FileNotFoundError as e:
            return TLCResult(
                success=True,  # No buggy variant = skip
                model=f"{model}Buggy",
                mode=mode.value,
                duration_seconds=time.time() - start_time,
                error=f"No buggy variant: {e}",
                error_type="NoBuggyVariant",
            )

        except Exception as e:
            return TLCResult(
                success=False,
                model=f"{model}Buggy",
                mode=mode.value,
                duration_seconds=time.time() - start_time,
                error=str(e),
                error_type=type(e).__name__,
            )

    def run_negative(
        self,
        mode: VerificationMode = VerificationMode.QUICK,
        workers: int = -1,
        simulation_depth: int = 100000,
        timeout_minutes: int = 30,
        spec_filter: Optional[str] = None,
    ) -> list[TLCResult]:
        """
        Run negative tests on all buggy model variants.

        For negative tests, we EXPECT TLC to find errors. A passing negative test
        means TLC correctly detected the bug in the buggy variant.

        Returns list of results where:
        - success=True means the buggy model correctly FAILED (TLC caught the bug)
        - success=False means the buggy model incorrectly PASSED (TLC missed the bug)
        """
        models = self.filter_models(self.list_buggy_models(), spec_filter)
        results = []

        for model in models:
            tlc_result = self.run_buggy(
                model=model,
                mode=mode,
                workers=workers,
                simulation_depth=simulation_depth,
                timeout_minutes=timeout_minutes,
            )

            # Invert success: for negative tests, TLC failure = test pass
            if tlc_result.error_type == "NoBuggyVariant":
                # Skip models without buggy variants
                continue

            negative_result = TLCResult(
                success=not tlc_result.success,  # Inverted!
                model=tlc_result.model,
                mode=f"{tlc_result.mode}-negative",
                states_generated=tlc_result.states_generated,
                distinct_states=tlc_result.distinct_states,
                depth=tlc_result.depth,
                duration_seconds=tlc_result.duration_seconds,
                error=tlc_result.error if not tlc_result.success else None,
                error_type="BugNotDetected" if tlc_result.success else None,
                counterexample=tlc_result.counterexample,
                warnings=tlc_result.warnings,
                tlc_version=tlc_result.tlc_version,
                spec_file=tlc_result.spec_file,
                config_file=tlc_result.config_file,
            )

            if tlc_result.success:
                negative_result.error = "Buggy model passed when it should have failed"

            results.append(negative_result)

        return results

    def run_all_parallel(
        self,
        mode: VerificationMode = VerificationMode.QUICK,
        workers: int = -1,
        simulation_depth: int = 100000,
        timeout_minutes: int = 30,
        max_parallel: int = 4,
        spec_filter: Optional[str] = None,
    ) -> list[TLCResult]:
        """Run TLC on all models in parallel."""
        models = self.filter_models(self.list_models(), spec_filter)

        if not models:
            return []

        results = []

        # Use a simpler approach: run sequentially but with individual timeouts
        # True parallelism requires picklable runner which is complex
        with ProcessPoolExecutor(max_workers=min(max_parallel, len(models))) as executor:
            futures = {}
            for model in models:
                future = executor.submit(
                    _run_model_standalone,
                    str(self.project_root),
                    model,
                    mode.value,
                    workers,
                    simulation_depth,
                    timeout_minutes,
                )
                futures[future] = model

            for future in as_completed(futures):
                model = futures[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception as e:
                    results.append(TLCResult(
                        success=False,
                        model=model,
                        mode=mode.value,
                        error=str(e),
                        error_type=type(e).__name__,
                    ))

        return results


def _run_model_standalone(
    project_root: str,
    model: str,
    mode: str,
    workers: int,
    simulation_depth: int,
    timeout_minutes: int,
) -> TLCResult:
    """Standalone function for parallel execution (must be picklable)."""
    runner = TLCRunner(project_root)
    return runner.run(
        model=model,
        mode=VerificationMode(mode),
        workers=workers,
        simulation_depth=simulation_depth,
        timeout_minutes=timeout_minutes,
    )


def main():
    """CLI for TLC runner."""
    import argparse

    parser = argparse.ArgumentParser(
        description="TLC Model Checker Runner - Unified XTConnect TLA+ Verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --model node-registration --mode quick
  %(prog)s --all --mode standard --format json
  %(prog)s --model token-refresh --mode thorough
  %(prog)s --all --negative                        # Run negative tests
  %(prog)s --all --parallel --mode quick           # Run in parallel
  %(prog)s --spec boot-manager --all --mode quick  # Filter by spec
  %(prog)s --all --junit results.xml              # Output JUnit XML
        """,
    )

    # Basic options
    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    parser.add_argument("--model", "-m", help="Model name to verify")
    parser.add_argument("--all", "-a", action="store_true", help="Verify all models")
    parser.add_argument("--spec", "-s", help="Filter by spec name (comma-separated)")
    parser.add_argument(
        "--mode",
        choices=["quick", "standard", "thorough"],
        default="quick",
        help="Verification mode (default: quick)",
    )
    parser.add_argument("--config", "-c", help="Specific config file")

    # Execution options
    parser.add_argument("--workers", "-w", type=int, default=-1, help="Number of workers (-1 for auto)")
    parser.add_argument("--depth", "-d", type=int, default=100000, help="Simulation depth for quick mode")
    parser.add_argument("--timeout", "-t", type=int, default=30, help="Timeout in minutes per spec")

    # New unified features
    parser.add_argument("--negative", action="store_true",
                        help="Run negative tests (verify buggy variants fail)")
    parser.add_argument("--parallel", action="store_true",
                        help="Run specs in parallel")
    parser.add_argument("--max-parallel", type=int, default=4,
                        help="Maximum parallel specs (default: 4)")

    # Output options
    parser.add_argument(
        "--format", "-f",
        choices=["text", "json", "markdown"],
        default="text",
        help="Output format (default: text)",
    )
    parser.add_argument("--junit", help="Output JUnit XML to file")
    parser.add_argument("--ci", action="store_true",
                        help="CI mode: structured output, non-zero exit on failure")

    # Info options
    parser.add_argument("--list", "-l", action="store_true", help="List available models")
    parser.add_argument("--list-buggy", action="store_true", help="List models with buggy variants")

    args = parser.parse_args()

    runner = TLCRunner(args.project)

    # Handle list commands
    if args.list:
        models = runner.list_models()
        if not models:
            print("No models found.")
        else:
            print("Available models:")
            for m in models:
                print(f"  {m}")
        return

    if args.list_buggy:
        models = runner.list_buggy_models()
        if not models:
            print("No models with buggy variants found.")
        else:
            print("Models with buggy variants:")
            for m in models:
                print(f"  {m}")
        return

    # Validate arguments
    if not args.model and not args.all and not args.negative:
        parser.error("Either --model, --all, or --negative is required")

    mode = VerificationMode(args.mode)
    output_format = OutputFormat(args.format)

    # Run verification
    results = []

    if args.negative:
        # Run negative tests (buggy variants)
        if args.ci:
            print("[INFO] Running negative tests (buggy variants)...", file=sys.stderr)
        results = runner.run_negative(
            mode=mode,
            workers=args.workers,
            simulation_depth=args.depth,
            timeout_minutes=args.timeout,
            spec_filter=args.spec,
        )
    elif args.all:
        if args.parallel:
            if args.ci:
                print(f"[INFO] Running {len(runner.list_models())} specs in parallel...", file=sys.stderr)
            results = runner.run_all_parallel(
                mode=mode,
                workers=args.workers,
                simulation_depth=args.depth,
                timeout_minutes=args.timeout,
                max_parallel=args.max_parallel,
                spec_filter=args.spec,
            )
        else:
            if args.ci:
                print(f"[INFO] Running {len(runner.list_models())} specs sequentially...", file=sys.stderr)
            results = runner.run_all(
                mode=mode,
                workers=args.workers,
                simulation_depth=args.depth,
                timeout_minutes=args.timeout,
                spec_filter=args.spec,
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

    # Calculate summary
    all_success = all(r.success for r in results)
    passed = sum(1 for r in results if r.success)
    total = len(results)

    # Output JUnit XML if requested
    if args.junit:
        suite_name = "TLA+ Negative Tests" if args.negative else "TLA+ Verification"
        junit_xml = results_to_junit(results, suite_name)
        Path(args.junit).write_text(junit_xml)
        if args.ci:
            print(f"[INFO] JUnit XML written to {args.junit}", file=sys.stderr)

    # Output results in requested format
    if output_format == OutputFormat.JSON:
        output = {
            "results": [r.to_dict() for r in results],
            "success": all_success,
            "passed": passed,
            "failed": total - passed,
            "total": total,
            "mode": args.mode,
            "negative": args.negative,
        }
        print(json.dumps(output, indent=2))
    elif output_format == OutputFormat.MARKDOWN:
        test_type = "Negative Tests" if args.negative else "Verification"
        print(f"# TLA+ {test_type} Results\n")
        for r in results:
            print(r.to_markdown())
            print("---")
        status = "✅ All passed!" if all_success else "❌ Some failed."
        print(f"\n**Summary:** {passed}/{total} passed. {status}")
    else:
        # Text format
        test_type = "NEGATIVE TESTS" if args.negative else "VERIFICATION"
        if args.ci:
            print(f"\n{'='*60}")
            print(f"TLA+ {test_type} RESULTS")
            print(f"{'='*60}\n")

        for r in results:
            status = "PASS" if r.success else "FAIL"
            prefix = "[PASS]" if r.success else "[FAIL]"
            if args.negative and r.success:
                prefix = "[PASS]"  # Buggy model correctly failed
                detail = f"CORRECTLY FAILED: {r.error}" if hasattr(r, '_original_error') else "Bug detected"
            elif args.negative and not r.success:
                prefix = "[FAIL]"
                detail = "Bug NOT detected - buggy model passed!"
            else:
                detail = r.error if r.error else ""

            print(f"{prefix} {r.model}: {r.duration_seconds:.1f}s, {r.states_generated} states", end="")
            if detail and not r.success:
                print(f" - {detail}")
            elif args.negative and r.success and r.error:
                print(f" - CORRECTLY FAILED: {r.error}")
            else:
                print()

        print(f"\n{'='*60}")
        print(f"Summary: {passed}/{total} passed")
        print(f"{'='*60}")

    # Exit with error if any failed
    sys.exit(0 if all_success else 1)


if __name__ == "__main__":
    main()

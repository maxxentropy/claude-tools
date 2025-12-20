#!/usr/bin/env python3
"""
TLA+ Counterexample Explainer - Human-readable explanations of TLC counterexamples.

This module parses TLC output and generates clear explanations:
- Step-by-step trace in plain English
- Code locations for each step (from mappings)
- Root cause analysis
- Suggested fix patterns

Supports:
- Reading from TLC output files
- Reading from run_tlc.py JSON output
- Running TLC on buggy variants to generate counterexamples
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tla_store import TLAStore


@dataclass
class TraceState:
    """A single state in a counterexample trace."""

    state_num: int
    action: Optional[str] = None
    action_params: dict = field(default_factory=dict)
    variables: dict[str, str] = field(default_factory=dict)
    is_initial: bool = False
    is_violating: bool = False

    def to_dict(self) -> dict:
        return {
            "stateNum": self.state_num,
            "action": self.action,
            "actionParams": self.action_params,
            "variables": self.variables,
            "isInitial": self.is_initial,
            "isViolating": self.is_violating,
        }


@dataclass
class Counterexample:
    """A parsed TLC counterexample."""

    model: str
    violated_invariant: Optional[str] = None
    error_type: str = "InvariantViolation"
    trace: list[TraceState] = field(default_factory=list)
    raw_error: str = ""

    def to_dict(self) -> dict:
        return {
            "model": self.model,
            "violatedInvariant": self.violated_invariant,
            "errorType": self.error_type,
            "trace": [s.to_dict() for s in self.trace],
            "rawError": self.raw_error,
        }


@dataclass
class CodeLocation:
    """A mapped code location for an action."""

    file: str
    method: str
    line: int

    def __str__(self) -> str:
        return f"{self.file}:{self.line} ({self.method})"


@dataclass
class Explanation:
    """Human-readable explanation of a counterexample."""

    counterexample: Counterexample
    summary: str
    step_explanations: list[str] = field(default_factory=list)
    root_cause: str = ""
    suggested_fix: str = ""
    code_locations: dict[str, CodeLocation] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "counterexample": self.counterexample.to_dict(),
            "summary": self.summary,
            "stepExplanations": self.step_explanations,
            "rootCause": self.root_cause,
            "suggestedFix": self.suggested_fix,
            "codeLocations": {k: str(v) for k, v in self.code_locations.items()},
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def to_markdown(self) -> str:
        lines = ["# Counterexample Explanation", ""]

        # Summary
        lines.append("## Summary")
        lines.append("")
        lines.append(self.summary)
        lines.append("")

        # Violated invariant
        if self.counterexample.violated_invariant:
            lines.append(f"**Violated Invariant:** `{self.counterexample.violated_invariant}`")
            lines.append("")

        # Step-by-step trace
        lines.append("## Step-by-Step Trace")
        lines.append("")

        for i, (state, explanation) in enumerate(zip(
            self.counterexample.trace, self.step_explanations
        )):
            icon = "🔴" if state.is_violating else "➡️" if state.action else "🏁"
            action_str = f" `{state.action}`" if state.action else " (Initial State)"

            lines.append(f"### Step {state.state_num}{action_str} {icon}")
            lines.append("")
            lines.append(explanation)
            lines.append("")

            # Show code location if available
            if state.action and state.action in self.code_locations:
                loc = self.code_locations[state.action]
                lines.append(f"📍 **Code:** `{loc}`")
                lines.append("")

            # Show key variable changes
            if state.variables:
                lines.append("<details>")
                lines.append("<summary>Variable values</summary>")
                lines.append("")
                lines.append("```")
                for var, val in sorted(state.variables.items()):
                    # Truncate long values
                    if len(val) > 60:
                        val = val[:57] + "..."
                    lines.append(f"{var} = {val}")
                lines.append("```")
                lines.append("</details>")
                lines.append("")

        # Root cause
        lines.append("## Root Cause Analysis")
        lines.append("")
        lines.append(self.root_cause)
        lines.append("")

        # Suggested fix
        lines.append("## Suggested Fix")
        lines.append("")
        lines.append(self.suggested_fix)
        lines.append("")

        return "\n".join(lines)

    def to_text(self) -> str:
        lines = ["=" * 60]
        lines.append("COUNTEREXAMPLE EXPLANATION")
        lines.append("=" * 60)
        lines.append("")
        lines.append(f"Model: {self.counterexample.model}")
        if self.counterexample.violated_invariant:
            lines.append(f"Violated: {self.counterexample.violated_invariant}")
        lines.append("")
        lines.append("SUMMARY")
        lines.append("-" * 40)
        lines.append(self.summary)
        lines.append("")
        lines.append("TRACE")
        lines.append("-" * 40)

        for i, (state, explanation) in enumerate(zip(
            self.counterexample.trace, self.step_explanations
        )):
            marker = "[VIOLATION]" if state.is_violating else ""
            action_str = state.action or "Init"
            lines.append(f"Step {state.state_num}: {action_str} {marker}")
            lines.append(f"  {explanation}")

            if state.action and state.action in self.code_locations:
                lines.append(f"  Code: {self.code_locations[state.action]}")
            lines.append("")

        lines.append("ROOT CAUSE")
        lines.append("-" * 40)
        lines.append(self.root_cause)
        lines.append("")
        lines.append("SUGGESTED FIX")
        lines.append("-" * 40)
        lines.append(self.suggested_fix)

        return "\n".join(lines)


class CounterexampleExplainer:
    """Explains TLC counterexamples in human-readable form."""

    # Common bug patterns and their explanations
    BUG_PATTERNS = {
        "TOCTOU": {
            "description": "Time-of-Check to Time-of-Use vulnerability",
            "symptoms": ["read", "check", "write without recheck"],
            "fix": "Re-check the condition immediately before the write operation, "
                   "ideally using an atomic compare-and-swap or optimistic locking pattern.",
        },
        "RACE": {
            "description": "Race condition between concurrent operations",
            "symptoms": ["concurrent", "both succeed", "overwrite"],
            "fix": "Use proper synchronization: mutex locks, database transactions "
                   "with appropriate isolation level, or optimistic concurrency control.",
        },
        "LOST_UPDATE": {
            "description": "Lost update - concurrent modification overwrites previous change",
            "symptoms": ["multiple", "claim", "succeed"],
            "fix": "Implement version checking: add a version column and verify "
                   "it matches before updating. Fail the operation if versions differ.",
        },
        "DEADLOCK": {
            "description": "Deadlock - circular wait between resources",
            "symptoms": ["deadlock", "stuck", "waiting"],
            "fix": "Establish a consistent lock ordering across all code paths, "
                   "or use timeout-based lock acquisition with retry logic.",
        },
    }

    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)
        self.store = TLAStore(self.project_root)

    def parse_tlc_output(self, output: str, model: str = "unknown") -> Counterexample:
        """Parse TLC output into a Counterexample object."""
        counterexample = Counterexample(model=model)

        # Extract violated invariant
        inv_match = re.search(r"Invariant (\w+) is violated", output)
        if inv_match:
            counterexample.violated_invariant = inv_match.group(1)
            counterexample.error_type = "InvariantViolation"

        # Check for other error types
        if "Deadlock" in output:
            counterexample.error_type = "Deadlock"
        elif "assertion failed" in output.lower():
            counterexample.error_type = "AssertionFailed"

        # Extract error message
        error_match = re.search(r"Error: (.+?)(?:\n|$)", output)
        if error_match:
            counterexample.raw_error = error_match.group(1)

        # Parse state trace
        counterexample.trace = self._parse_trace(output)

        # Mark initial and violating states
        if counterexample.trace:
            counterexample.trace[0].is_initial = True
            counterexample.trace[-1].is_violating = True

        return counterexample

    def _parse_trace(self, output: str) -> list[TraceState]:
        """Parse the state trace from TLC output."""
        states = []
        current_state = None
        current_vars = {}
        current_action = None

        lines = output.split("\n")
        in_state = False

        for i, line in enumerate(lines):
            # State header: "State 1: <Initial predicate>"
            state_match = re.match(r"State (\d+):\s*<?(.+?)>?$", line.strip())
            if state_match:
                # Save previous state
                if current_state is not None:
                    states.append(TraceState(
                        state_num=current_state,
                        action=current_action,
                        action_params=self._parse_action_params(current_action),
                        variables=current_vars,
                    ))

                current_state = int(state_match.group(1))
                action_text = state_match.group(2).strip()
                current_action = self._extract_action_name(action_text)
                current_vars = {}
                in_state = True
                continue

            # Variable assignment: "/\ varName = value"
            if in_state and line.strip().startswith("/\\"):
                var_match = re.match(r"/\\\s+(\w+)\s*=\s*(.+)", line.strip())
                if var_match:
                    current_vars[var_match.group(1)] = var_match.group(2).strip()

            # End of state (empty line or new section)
            if in_state and (line.strip() == "" or line.startswith("Error")):
                in_state = False

        # Add final state
        if current_state is not None:
            states.append(TraceState(
                state_num=current_state,
                action=current_action,
                action_params=self._parse_action_params(current_action),
                variables=current_vars,
            ))

        return states

    def _extract_action_name(self, action_text: str) -> Optional[str]:
        """Extract action name from TLC action string."""
        if not action_text or action_text == "Initial predicate":
            return None

        # Remove parameters: "ClaimStart(U1, N1)" -> "ClaimStart"
        match = re.match(r"(\w+)", action_text)
        if match:
            return match.group(1)
        return action_text

    def _parse_action_params(self, action: Optional[str]) -> dict:
        """Parse action parameters if present."""
        if not action:
            return {}

        # Match "Action(param1, param2)"
        match = re.match(r"\w+\(([^)]+)\)", action)
        if match:
            params = match.group(1).split(",")
            return {f"param{i}": p.strip() for i, p in enumerate(params)}
        return {}

    def explain(self, counterexample: Counterexample) -> Explanation:
        """Generate a human-readable explanation of the counterexample."""
        # Get code mappings if available
        code_locations = self._get_code_locations(counterexample.model)

        # Generate step explanations
        step_explanations = []
        for state in counterexample.trace:
            explanation = self._explain_step(state, counterexample)
            step_explanations.append(explanation)

        # Analyze root cause
        root_cause = self._analyze_root_cause(counterexample)

        # Suggest fix
        suggested_fix = self._suggest_fix(counterexample)

        # Generate summary
        summary = self._generate_summary(counterexample)

        return Explanation(
            counterexample=counterexample,
            summary=summary,
            step_explanations=step_explanations,
            root_cause=root_cause,
            suggested_fix=suggested_fix,
            code_locations=code_locations,
        )

    def _get_code_locations(self, model: str) -> dict[str, CodeLocation]:
        """Get code locations for actions from TLAStore."""
        locations = {}

        if not self.store.is_initialized():
            return locations

        mapping = self.store.get_model_mapping(model)
        if not mapping:
            return locations

        for action_name, action_data in mapping.actions.items():
            locations[action_name] = CodeLocation(
                file=action_data.code_file,
                method=action_data.method,
                line=action_data.line,
            )

        return locations

    def _explain_step(self, state: TraceState, counterexample: Counterexample) -> str:
        """Generate explanation for a single step."""
        if state.is_initial:
            return self._explain_initial_state(state)

        if state.is_violating:
            return self._explain_violating_state(state, counterexample)

        return self._explain_action(state)

    def _explain_initial_state(self, state: TraceState) -> str:
        """Explain the initial state."""
        explanations = ["System starts in initial state."]

        # Look for interesting initial values
        for var, val in state.variables.items():
            if "State" in var or "Owner" in var:
                explanations.append(f"  - {var} initialized")

        return " ".join(explanations) if len(explanations) == 1 else explanations[0] + "\n" + "\n".join(explanations[1:])

    def _explain_action(self, state: TraceState) -> str:
        """Explain a normal action step."""
        action = state.action or "Unknown action"

        # Common action patterns
        if "Register" in action:
            return f"Entity registers itself in the system via `{action}`."
        elif "Start" in action or "Begin" in action:
            return f"An operation begins: `{action}`. State is read and stored for later validation."
        elif "Complete" in action or "Finish" in action:
            return f"Operation completes: `{action}`. Changes are written to the database."
        elif "Claim" in action:
            return f"Claim operation: `{action}`. Attempting to take ownership."
        elif "Read" in action:
            return f"Read operation: `{action}`. Current state is captured."
        elif "Write" in action or "Update" in action:
            return f"Write operation: `{action}`. State is modified."
        elif "Fail" in action:
            return f"Operation fails: `{action}`. Conflict or precondition not met."
        else:
            return f"Action `{action}` executes."

    def _explain_violating_state(
        self, state: TraceState, counterexample: Counterexample
    ) -> str:
        """Explain the state where the invariant is violated."""
        invariant = counterexample.violated_invariant or "safety property"
        action = state.action or "the last action"

        base = f"**INVARIANT VIOLATED** after `{action}`. The `{invariant}` property no longer holds."

        # Try to identify what went wrong
        if "Multiple" in invariant or "Single" in invariant:
            base += " Multiple actors have achieved mutually exclusive states."
        elif "Owner" in invariant:
            base += " Ownership constraints have been violated."

        return base

    def _analyze_root_cause(self, counterexample: Counterexample) -> str:
        """Analyze the root cause of the counterexample."""
        trace = counterexample.trace

        # Look for patterns in the trace
        actions = [s.action for s in trace if s.action]

        # Check for TOCTOU pattern
        read_actions = [a for a in actions if any(kw in a for kw in ["Start", "Read", "Check"])]
        write_actions = [a for a in actions if any(kw in a for kw in ["Complete", "Write", "Update"])]

        if len(read_actions) >= 2 and len(write_actions) >= 2:
            return (
                "**Time-of-Check to Time-of-Use (TOCTOU) Vulnerability**\n\n"
                "The trace shows multiple concurrent operations that:\n"
                "1. Read the same state (both see a valid/available state)\n"
                "2. Proceed to write without re-checking\n"
                "3. Both succeed, violating mutual exclusion\n\n"
                "This is a classic race condition where the check and use are not atomic."
            )

        # Check for concurrent claim pattern
        claim_actions = [a for a in actions if "Claim" in a]
        if len(claim_actions) >= 2:
            return (
                "**Race Condition in Claim Logic**\n\n"
                "Multiple actors attempted to claim the same resource concurrently. "
                "The system allowed both claims to succeed because:\n"
                "- Both actors read the resource state before either completed\n"
                "- No re-validation occurred before the final write\n"
                "- The second write overwrote the first actor's claim"
            )

        # Generic analysis
        return (
            "The counterexample shows a sequence of operations that leads to "
            "an invalid state. Analyze the variable values at each step to "
            "understand how the invariant was violated."
        )

    def _suggest_fix(self, counterexample: Counterexample) -> str:
        """Suggest fixes based on the counterexample pattern."""
        trace = counterexample.trace
        actions = [s.action for s in trace if s.action]

        # Detect pattern and suggest fix
        if any("Buggy" in (a or "") for a in actions):
            return (
                "**Implement Optimistic Concurrency Control**\n\n"
                "```csharp\n"
                "// Before writing, re-check the current state\n"
                "var current = await db.FindAsync(id);\n"
                "if (current.State != expectedState || current.Version != expectedVersion)\n"
                "{\n"
                "    throw new ConcurrencyException(\"State changed since read\");\n"
                "}\n"
                "current.State = newState;\n"
                "current.Version++;\n"
                "await db.SaveChangesAsync();\n"
                "```\n\n"
                "Or use database-level locking:\n"
                "```sql\n"
                "UPDATE resource SET state = @new, version = version + 1\n"
                "WHERE id = @id AND state = @expected AND version = @expectedVersion\n"
                "```"
            )

        # Generic suggestion based on invariant
        invariant = counterexample.violated_invariant or ""

        if "Single" in invariant or "Multiple" in invariant:
            return (
                "**Ensure Mutual Exclusion**\n\n"
                "Options:\n"
                "1. **Optimistic locking**: Add version check before write\n"
                "2. **Pessimistic locking**: Use database locks (SELECT FOR UPDATE)\n"
                "3. **Atomic operations**: Use compare-and-swap at database level\n"
                "4. **Queue-based**: Serialize conflicting operations through a queue"
            )

        return (
            "Review the trace to understand the interleaving that caused the violation. "
            "Consider adding synchronization, validation checks, or using atomic operations "
            "to prevent the problematic state from being reached."
        )

    def _generate_summary(self, counterexample: Counterexample) -> str:
        """Generate a summary of the counterexample."""
        model = counterexample.model
        invariant = counterexample.violated_invariant or "a safety property"
        num_steps = len(counterexample.trace)

        summary = f"TLC found a counterexample in model `{model}` that violates `{invariant}` "
        summary += f"in {num_steps} steps. "

        # Count actors if we can detect them
        actions = [s.action for s in counterexample.trace if s.action]

        if len(actions) >= 2:
            summary += "The trace shows concurrent operations interleaving in a way that "
            summary += "leads to an invalid state."

        return summary


def main():
    """CLI for counterexample explanation."""
    parser = argparse.ArgumentParser(
        description="Explain TLC counterexamples in human-readable form",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Explain from TLC output file
  %(prog)s --file tlc-output.txt --model node-registration

  # Explain from run_tlc.py JSON output
  %(prog)s --json-file verification-result.json

  # Run buggy model and explain the counterexample
  %(prog)s --run-buggy node-registration

  # Output as JSON for programmatic use
  %(prog)s --file output.txt --format json
        """,
    )

    parser.add_argument(
        "--project", "-p",
        default=".",
        help="Project root directory",
    )
    parser.add_argument(
        "--file", "-f",
        help="TLC output file to parse",
    )
    parser.add_argument(
        "--json-file", "-j",
        help="JSON file from run_tlc.py",
    )
    parser.add_argument(
        "--run-buggy", "-b",
        metavar="MODEL",
        help="Run buggy variant of model and explain counterexample",
    )
    parser.add_argument(
        "--model", "-m",
        help="Model name (for code location mapping)",
    )
    parser.add_argument(
        "--format",
        choices=["text", "markdown", "json"],
        default="markdown",
        help="Output format (default: markdown)",
    )

    args = parser.parse_args()

    explainer = CounterexampleExplainer(args.project)

    # Get counterexample from source
    if args.run_buggy:
        # Run the buggy variant to generate a counterexample
        from run_tlc import TLCRunner, VerificationMode

        runner = TLCRunner(args.project)
        model = args.run_buggy

        print(f"Running buggy variant of {model}...", file=sys.stderr)

        # Find buggy spec
        specs_dir = Path(args.project) / "specs" / "tla+"
        model_dir = specs_dir / model
        buggy_files = list(model_dir.glob("*Buggy.tla"))

        if not buggy_files:
            print(f"Error: No buggy variant found in {model_dir}", file=sys.stderr)
            sys.exit(1)

        # Run TLC on buggy model (should fail)
        import subprocess

        tlc_jar = runner.get_tlc_jar()
        buggy_spec = buggy_files[0]
        buggy_cfg = model_dir / buggy_spec.stem.replace(".tla", ".cfg")

        if not buggy_cfg.exists():
            buggy_cfg = list(model_dir.glob("*Buggy.cfg"))[0] if list(model_dir.glob("*Buggy.cfg")) else None

        if not buggy_cfg:
            # Use default cfg
            cfgs = [c for c in model_dir.glob("*.cfg") if "Buggy" not in c.stem]
            buggy_cfg = cfgs[0] if cfgs else None

        cmd = [
            "java", "-XX:+UseParallelGC",
            "-jar", str(tlc_jar.resolve()),
            "-config", str(buggy_cfg.resolve()) if buggy_cfg else "",
            str(buggy_spec.resolve()),
        ]

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=model_dir,
            timeout=120,
        )

        output = result.stdout + result.stderr
        counterexample = explainer.parse_tlc_output(output, model)

    elif args.json_file:
        # Parse from run_tlc.py JSON output
        with open(args.json_file) as f:
            data = json.load(f)

        # Handle both single result and results array
        if "results" in data:
            result_data = data["results"][0]
        else:
            result_data = data

        model = args.model or result_data.get("model", "unknown")
        counterexample = Counterexample(
            model=model,
            violated_invariant=result_data.get("error", "").replace("Invariant ", "").replace(" is violated", ""),
            error_type=result_data.get("error_type", "InvariantViolation"),
            raw_error=result_data.get("error", ""),
        )

        # Parse trace from JSON
        for state_data in result_data.get("counterexample", []):
            counterexample.trace.append(TraceState(
                state_num=state_data.get("state_num", 0),
                action=state_data.get("action"),
                variables=state_data.get("variables", {}),
            ))

        if counterexample.trace:
            counterexample.trace[0].is_initial = True
            counterexample.trace[-1].is_violating = True

    elif args.file:
        # Parse from raw TLC output
        with open(args.file) as f:
            output = f.read()

        model = args.model or "unknown"
        counterexample = explainer.parse_tlc_output(output, model)

    else:
        parser.error("One of --file, --json-file, or --run-buggy is required")

    # Check if we have a counterexample
    if not counterexample.trace:
        print("No counterexample found in the input.", file=sys.stderr)
        print("The model may have passed verification.", file=sys.stderr)
        sys.exit(0)

    # Generate explanation
    explanation = explainer.explain(counterexample)

    # Output
    if args.format == "json":
        print(explanation.to_json())
    elif args.format == "markdown":
        print(explanation.to_markdown())
    else:
        print(explanation.to_text())


if __name__ == "__main__":
    main()

"""
Session Context - Manages cross-session continuity for Claude Code.

This module handles the "handoff" between Claude sessions:
- Load context at session start (what was I working on?)
- Save context at session end (what should I remember?)
- Track session history for continuity

Usage:
    # At session start
    python3 session_context.py --load

    # At session end
    python3 session_context.py --save --notes "Fixed N+1 but still need to address caching"

    # Show current context
    python3 session_context.py --show
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

# Add current directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from findings_store import FindingsStore, Finding


@dataclass
class SessionInfo:
    """Information about a Claude session."""
    id: str
    started_at: str
    ended_at: Optional[str] = None
    branch: Optional[str] = None
    work_item: Optional[str] = None  # AB#1234

    # What was worked on
    files_modified: List[str] = field(default_factory=list)
    commits: List[str] = field(default_factory=list)

    # Findings activity
    findings_created: List[str] = field(default_factory=list)
    findings_resolved: List[str] = field(default_factory=list)

    # Handoff
    handoff_notes: str = ""
    open_questions: List[str] = field(default_factory=list)


class SessionContext:
    """
    Manages session context for cross-session continuity.

    Context is stored in .findings/session-context.json (git-ignored).
    """

    def __init__(self, root_dir: Optional[Path] = None):
        self.store = FindingsStore(root_dir)
        self.context_path = self.store.context_path
        self._context: Optional[Dict[str, Any]] = None

    def _load_context(self) -> Dict[str, Any]:
        """Load context from disk."""
        if self._context is not None:
            return self._context

        if self.context_path.exists():
            try:
                with open(self.context_path) as f:
                    self._context = json.load(f)
            except (json.JSONDecodeError, IOError):
                self._context = self._default_context()
        else:
            self._context = self._default_context()

        return self._context

    def _save_context(self) -> None:
        """Save context to disk."""
        if self._context is None:
            return
        with open(self.context_path, "w") as f:
            json.dump(self._context, f, indent=2)

    def _default_context(self) -> Dict[str, Any]:
        """Return default context structure."""
        return {
            "last_session": None,
            "active_context": {
                "work_item": None,
                "focus_area": None,
                "open_questions": []
            },
            "statistics": {
                "total_sessions": 0,
                "total_findings": 0,
                "findings_promoted_to_ado": 0,
                "findings_resolved": 0
            },
            "session_history": []
        }

    def _get_current_branch(self) -> Optional[str]:
        """Get current git branch."""
        try:
            result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True, text=True, cwd=self.store.root_dir
            )
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def _get_work_item_from_branch(self, branch: Optional[str]) -> Optional[str]:
        """Extract work item ID from branch name (e.g., feature/AB#1234-desc)."""
        if not branch:
            return None

        import re
        match = re.search(r'AB#(\d+)', branch, re.IGNORECASE)
        if match:
            return f"AB#{match.group(1)}"

        # Try just a number pattern
        match = re.search(r'[/-](\d{4,})[/-]', branch)
        if match:
            return f"AB#{match.group(1)}"

        return None

    def _generate_session_id(self) -> str:
        """Generate a unique session ID."""
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
        return f"sess-{timestamp}"

    def start_session(self) -> Dict[str, Any]:
        """
        Start a new session and return context for Claude.

        Returns context including:
        - Last session summary
        - Open findings for current branch
        - Active work item context
        """
        context = self._load_context()

        # Create new session
        branch = self._get_current_branch()
        work_item = self._get_work_item_from_branch(branch)

        session = SessionInfo(
            id=self._generate_session_id(),
            started_at=datetime.now(timezone.utc).isoformat() + "Z",
            branch=branch,
            work_item=work_item
        )

        # Store as current session
        context["current_session"] = asdict(session)
        context["active_context"]["work_item"] = work_item
        self._save_context()

        # Get relevant findings
        open_findings = self.store.get_open_findings()
        branch_findings = self.store.get_findings_by_branch(branch) if branch else []
        ready_findings = self.store.get_ready_findings()

        return {
            "session_id": session.id,
            "last_session": context.get("last_session"),
            "active_context": context.get("active_context"),
            "open_findings_count": len(open_findings),
            "ready_findings_count": len(ready_findings),
            "branch_findings": [f.to_dict() for f in branch_findings[:5]],
            "statistics": context.get("statistics", {})
        }

    def end_session(
        self,
        handoff_notes: str = "",
        open_questions: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        End the current session and save handoff context.

        Args:
            handoff_notes: Notes for the next session
            open_questions: Questions that remain unanswered

        Returns:
            Summary of the session
        """
        context = self._load_context()
        current = context.get("current_session")

        if not current:
            return {"error": "No active session to end"}

        # Update session info
        current["ended_at"] = datetime.now(timezone.utc).isoformat() + "Z"
        current["handoff_notes"] = handoff_notes
        current["open_questions"] = open_questions or []

        # Get findings created/resolved during this session
        # (In a real implementation, we'd track this during the session)
        stats = self.store.get_statistics()

        # Move to last_session
        context["last_session"] = current
        context["current_session"] = None

        # Update active context
        context["active_context"]["open_questions"] = open_questions or []

        # Update statistics
        context["statistics"]["total_sessions"] += 1
        context["statistics"]["total_findings"] = stats["total"]
        context["statistics"]["findings_resolved"] = stats.get("resolved", 0)
        context["statistics"]["findings_promoted_to_ado"] = stats.get("promoted", 0)

        # Add to history (keep last 10)
        history = context.get("session_history", [])
        history.insert(0, {
            "id": current["id"],
            "started_at": current["started_at"],
            "ended_at": current["ended_at"],
            "branch": current.get("branch"),
            "work_item": current.get("work_item"),
            "handoff_notes": handoff_notes[:200] if handoff_notes else ""
        })
        context["session_history"] = history[:10]

        self._save_context()

        return {
            "session_id": current["id"],
            "duration_seconds": self._calculate_duration(
                current["started_at"], current["ended_at"]
            ),
            "handoff_notes": handoff_notes,
            "open_questions": open_questions or [],
            "findings_stats": stats
        }

    def _calculate_duration(self, start: str, end: str) -> int:
        """Calculate duration in seconds between two ISO timestamps."""
        try:
            start_dt = datetime.fromisoformat(start.replace("Z", "+00:00"))
            end_dt = datetime.fromisoformat(end.replace("Z", "+00:00"))
            return int((end_dt - start_dt).total_seconds())
        except Exception:
            return 0

    def get_context_summary(self) -> str:
        """
        Get a human-readable context summary for Claude.

        This is the key method for session continuity - it produces
        text that can be injected into Claude's context at session start.
        """
        context = self._load_context()
        last = context.get("last_session")
        active = context.get("active_context", {})
        stats = context.get("statistics", {})

        lines = []
        lines.append("# Session Context")
        lines.append("")

        # Last session info
        if last:
            lines.append("## Last Session")
            if last.get("branch"):
                lines.append(f"- **Branch**: `{last['branch']}`")
            if last.get("work_item"):
                lines.append(f"- **Work Item**: {last['work_item']}")
            if last.get("ended_at"):
                lines.append(f"- **Ended**: {last['ended_at']}")
            if last.get("handoff_notes"):
                lines.append(f"- **Notes**: {last['handoff_notes']}")
            lines.append("")

        # Open questions
        questions = active.get("open_questions", [])
        if questions:
            lines.append("## Open Questions")
            for q in questions:
                lines.append(f"- {q}")
            lines.append("")

        # Findings summary
        open_findings = self.store.get_open_findings()
        ready_findings = self.store.get_ready_findings()

        lines.append("## Findings Summary")
        lines.append(f"- **Open**: {len(open_findings)}")
        lines.append(f"- **Ready to work on**: {len(ready_findings)}")
        lines.append(f"- **Total ever**: {stats.get('total_findings', 0)}")
        lines.append(f"- **Promoted to ADO**: {stats.get('findings_promoted_to_ado', 0)}")
        lines.append("")

        # Ready findings
        if ready_findings:
            lines.append("## Ready Findings")
            for f in ready_findings[:5]:
                severity_emoji = {
                    "critical": "🔴",
                    "high": "🟠",
                    "medium": "🟡",
                    "low": "🟢",
                    "info": "ℹ️"
                }.get(f.severity, "")
                lines.append(f"- {severity_emoji} **{f.id}**: {f.title}")
                if f.evidence and f.evidence.file:
                    lines.append(f"  - `{f.evidence.file}:{f.evidence.line or '?'}`")
            if len(ready_findings) > 5:
                lines.append(f"  - ... and {len(ready_findings) - 5} more")
            lines.append("")

        return "\n".join(lines)

    def get_onboard_prompt(self) -> str:
        """
        Get an onboarding prompt for a new session.

        This is designed to be injected into Claude's system prompt
        or provided at the start of a conversation.
        """
        context_summary = self.get_context_summary()

        prompt = f"""
{context_summary}

## Instructions

You have access to a persistent findings system for tracking discoveries between sessions.

**To capture a finding:**
```bash
python3 skills/findings/scripts/query_findings.py --capture \\
  --title "Description of finding" \\
  --severity medium \\
  --type discovery
```

**To see open findings:**
```bash
python3 skills/findings/scripts/query_findings.py --open
```

**To mark a finding resolved:**
```bash
python3 skills/findings/scripts/query_findings.py --resolve f-abc123
```

**At session end, save context:**
```bash
python3 skills/findings/scripts/session_context.py --save --notes "Your handoff notes"
```

Review the ready findings above and continue any unfinished work.
"""
        return prompt


class Colors:
    """ANSI color codes."""
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    BLUE = "\033[94m"
    MAGENTA = "\033[95m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def color(text: str, *codes: str) -> str:
    """Apply color codes to text."""
    if not sys.stdout.isatty():
        return text
    return "".join(codes) + text + Colors.RESET


def main():
    parser = argparse.ArgumentParser(
        description="Manage session context for cross-session continuity"
    )
    parser.add_argument(
        "--load", action="store_true",
        help="Load context and start a new session"
    )
    parser.add_argument(
        "--save", action="store_true",
        help="Save context and end current session"
    )
    parser.add_argument(
        "--show", action="store_true",
        help="Show current context summary"
    )
    parser.add_argument(
        "--onboard", action="store_true",
        help="Output onboarding prompt for new session"
    )
    parser.add_argument(
        "--notes", type=str, default="",
        help="Handoff notes for next session (use with --save)"
    )
    parser.add_argument(
        "--questions", type=str, nargs="*",
        help="Open questions to carry forward (use with --save)"
    )
    parser.add_argument(
        "--json", action="store_true",
        help="Output as JSON"
    )

    args = parser.parse_args()
    ctx = SessionContext()

    if args.load:
        result = ctx.start_session()
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            print(color("Session Started", Colors.GREEN, Colors.BOLD))
            print(f"  ID: {result['session_id']}")
            print(f"  Open findings: {result['open_findings_count']}")
            print(f"  Ready to work: {result['ready_findings_count']}")
            print()

            if result.get("last_session"):
                last = result["last_session"]
                print(color("Last Session:", Colors.CYAN, Colors.BOLD))
                if last.get("handoff_notes"):
                    print(f"  Notes: {last['handoff_notes']}")
                if last.get("open_questions"):
                    print("  Open questions:")
                    for q in last["open_questions"]:
                        print(f"    - {q}")
                print()

            if result.get("branch_findings"):
                print(color("Recent findings on this branch:", Colors.YELLOW))
                for f in result["branch_findings"]:
                    print(f"  - {f['id']}: {f['title']}")
                print()

    elif args.save:
        result = ctx.end_session(
            handoff_notes=args.notes,
            open_questions=args.questions
        )
        if args.json:
            print(json.dumps(result, indent=2))
        else:
            if "error" in result:
                print(color(f"Error: {result['error']}", Colors.RED))
            else:
                print(color("Session Ended", Colors.GREEN, Colors.BOLD))
                print(f"  ID: {result['session_id']}")
                print(f"  Duration: {result['duration_seconds']} seconds")
                if result.get("handoff_notes"):
                    print(f"  Handoff notes saved: {result['handoff_notes'][:50]}...")
                print()
                print(color("Context saved for next session.", Colors.DIM))

    elif args.show:
        summary = ctx.get_context_summary()
        print(summary)

    elif args.onboard:
        prompt = ctx.get_onboard_prompt()
        if args.json:
            print(json.dumps({"prompt": prompt}))
        else:
            print(prompt)

    else:
        # Default: show context summary
        summary = ctx.get_context_summary()
        print(summary)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
project_health.py - Generate project health reports with metrics and KPIs.

Metrics included:
- Work item velocity (items completed per week)
- Bug trends (open bugs over time)
- Sprint burndown status
- Pipeline health (success rate, failure trends)
- Code churn metrics
- Technical debt indicators

Usage:
    python project_health.py report                    # Current sprint/iteration
    python project_health.py report --weeks 4          # Last 4 weeks trend
    python project_health.py metrics                   # Raw metrics data
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, List, Dict, Any

from wsr_config import WSRConfig, get_week_id


@dataclass
class VelocityMetric:
    """Work item velocity over time."""
    period: str                    # Week ID or Sprint name
    items_completed: int
    story_points: Optional[int] = None
    by_type: Dict[str, int] = field(default_factory=dict)


@dataclass
class BugMetric:
    """Bug tracking metrics."""
    period: str
    bugs_opened: int
    bugs_closed: int
    bugs_open_total: int
    by_severity: Dict[str, int] = field(default_factory=dict)


@dataclass
class PipelineMetric:
    """CI/CD pipeline health."""
    period: str
    total_runs: int
    successful: int
    failed: int
    success_rate: float
    avg_duration_minutes: Optional[float] = None
    by_pipeline: Dict[str, Dict] = field(default_factory=dict)


@dataclass
class CodeMetric:
    """Code change metrics."""
    period: str
    commits: int
    insertions: int
    deletions: int
    files_changed: int
    churn_rate: float  # deletions / (insertions + deletions)


@dataclass
class ProjectHealthReport:
    """Complete project health report."""
    generated_at: str
    period_start: str
    period_end: str
    organization: str
    project: str

    velocity: List[VelocityMetric] = field(default_factory=list)
    bugs: List[BugMetric] = field(default_factory=list)
    pipelines: List[PipelineMetric] = field(default_factory=list)
    code: List[CodeMetric] = field(default_factory=list)

    # Current status
    sprint_name: Optional[str] = None
    sprint_progress: Optional[float] = None  # 0-100%
    items_remaining: int = 0
    blockers: int = 0

    # Health indicators
    health_score: Optional[float] = None  # 0-100
    alerts: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)


def run_az_command(args: list, timeout: int = 60) -> Optional[Any]:
    """Run Azure CLI command and return JSON result."""
    cmd = ["az"] + args + ["--output", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else None
    except Exception:
        return None


def get_velocity_metrics(org: str, project: str, weeks: int = 4) -> List[VelocityMetric]:
    """Calculate work item velocity over recent weeks."""
    metrics = []

    for w in range(weeks):
        # Calculate week boundaries
        end_date = datetime.now() - timedelta(weeks=w)
        start_date = end_date - timedelta(days=7)

        # Query completed items
        wiql = f"""
            SELECT [System.Id], [System.WorkItemType]
            FROM workitems
            WHERE [Microsoft.VSTS.Common.ClosedDate] >= '{start_date.strftime('%Y-%m-%d')}'
              AND [Microsoft.VSTS.Common.ClosedDate] < '{end_date.strftime('%Y-%m-%d')}'
              AND [System.State] IN ('Closed', 'Done')
        """

        result = run_az_command([
            "boards", "query", "--org", org, "--project", project,
            "--wiql", " ".join(wiql.split())
        ])

        items = result or []
        by_type: Dict[str, int] = {}

        for item in items:
            # Get item details
            details = run_az_command([
                "boards", "work-item", "show", "--org", org,
                "--id", str(item.get("id", 0))
            ])
            if details:
                wi_type = details.get("fields", {}).get("System.WorkItemType", "Unknown")
                by_type[wi_type] = by_type.get(wi_type, 0) + 1

        week_id = f"{end_date.isocalendar()[0]}-W{end_date.isocalendar()[1]:02d}"
        metrics.append(VelocityMetric(
            period=week_id,
            items_completed=len(items),
            by_type=by_type
        ))

    return list(reversed(metrics))  # Oldest first


def get_bug_metrics(org: str, project: str, weeks: int = 4) -> List[BugMetric]:
    """Track bug trends over time."""
    metrics = []

    for w in range(weeks):
        end_date = datetime.now() - timedelta(weeks=w)
        start_date = end_date - timedelta(days=7)

        # Bugs opened this week
        opened_wiql = f"""
            SELECT [System.Id] FROM workitems
            WHERE [System.WorkItemType] = 'Bug'
              AND [System.CreatedDate] >= '{start_date.strftime('%Y-%m-%d')}'
              AND [System.CreatedDate] < '{end_date.strftime('%Y-%m-%d')}'
        """
        opened = run_az_command([
            "boards", "query", "--org", org, "--project", project,
            "--wiql", " ".join(opened_wiql.split())
        ]) or []

        # Bugs closed this week
        closed_wiql = f"""
            SELECT [System.Id] FROM workitems
            WHERE [System.WorkItemType] = 'Bug'
              AND [Microsoft.VSTS.Common.ClosedDate] >= '{start_date.strftime('%Y-%m-%d')}'
              AND [Microsoft.VSTS.Common.ClosedDate] < '{end_date.strftime('%Y-%m-%d')}'
        """
        closed = run_az_command([
            "boards", "query", "--org", org, "--project", project,
            "--wiql", " ".join(closed_wiql.split())
        ]) or []

        # Total open bugs as of end_date
        open_wiql = f"""
            SELECT [System.Id] FROM workitems
            WHERE [System.WorkItemType] = 'Bug'
              AND [System.State] NOT IN ('Closed', 'Done', 'Resolved')
        """
        open_bugs = run_az_command([
            "boards", "query", "--org", org, "--project", project,
            "--wiql", " ".join(open_wiql.split())
        ]) or []

        week_id = f"{end_date.isocalendar()[0]}-W{end_date.isocalendar()[1]:02d}"
        metrics.append(BugMetric(
            period=week_id,
            bugs_opened=len(opened),
            bugs_closed=len(closed),
            bugs_open_total=len(open_bugs)
        ))

    return list(reversed(metrics))


def get_pipeline_metrics(org: str, project: str, weeks: int = 4) -> List[PipelineMetric]:
    """Get CI/CD pipeline health metrics."""
    metrics = []

    # Get all pipelines
    pipelines = run_az_command([
        "pipelines", "list", "--org", org, "--project", project
    ]) or []

    for w in range(weeks):
        end_date = datetime.now() - timedelta(weeks=w)
        start_date = end_date - timedelta(days=7)

        week_runs = []
        by_pipeline: Dict[str, Dict] = {}

        for pipeline in pipelines[:10]:  # Limit to top 10
            pipeline_id = pipeline.get("id")
            pipeline_name = pipeline.get("name", "Unknown")

            runs = run_az_command([
                "pipelines", "runs", "list",
                "--org", org, "--project", project,
                "--pipeline-ids", str(pipeline_id)
            ]) or []

            pipeline_runs = []
            for run in runs:
                try:
                    run_time = datetime.fromisoformat(
                        run.get("createdDate", "").replace("Z", "+00:00")
                    ).replace(tzinfo=None)
                    if start_date.replace(tzinfo=None) <= run_time < end_date.replace(tzinfo=None):
                        pipeline_runs.append(run)
                        week_runs.append(run)
                except:
                    continue

            if pipeline_runs:
                success = sum(1 for r in pipeline_runs if r.get("result") == "succeeded")
                by_pipeline[pipeline_name] = {
                    "total": len(pipeline_runs),
                    "success": success,
                    "success_rate": round(success / len(pipeline_runs) * 100, 1) if pipeline_runs else 0
                }

        total = len(week_runs)
        successful = sum(1 for r in week_runs if r.get("result") == "succeeded")
        failed = sum(1 for r in week_runs if r.get("result") == "failed")

        week_id = f"{end_date.isocalendar()[0]}-W{end_date.isocalendar()[1]:02d}"
        metrics.append(PipelineMetric(
            period=week_id,
            total_runs=total,
            successful=successful,
            failed=failed,
            success_rate=round(successful / total * 100, 1) if total else 0,
            by_pipeline=by_pipeline
        ))

    return list(reversed(metrics))


def get_code_metrics(weeks: int = 4, repo_path: Optional[str] = None) -> List[CodeMetric]:
    """Get code change metrics from git."""
    metrics = []

    for w in range(weeks):
        end_date = datetime.now() - timedelta(weeks=w)
        start_date = end_date - timedelta(days=7)

        # Git log for the week
        result = subprocess.run([
            "git", "log",
            f"--since={start_date.strftime('%Y-%m-%d')}",
            f"--until={end_date.strftime('%Y-%m-%d')}",
            "--shortstat", "--oneline"
        ], capture_output=True, text=True, cwd=repo_path, timeout=30)

        commits = 0
        insertions = 0
        deletions = 0
        files_changed = 0

        if result.returncode == 0:
            for line in result.stdout.split('\n'):
                if 'file' in line and 'changed' in line:
                    import re
                    m = re.search(r'(\d+) files? changed', line)
                    files_changed += int(m.group(1)) if m else 0
                    m = re.search(r'(\d+) insertions?', line)
                    insertions += int(m.group(1)) if m else 0
                    m = re.search(r'(\d+) deletions?', line)
                    deletions += int(m.group(1)) if m else 0
                elif line.strip() and not line.startswith(' '):
                    commits += 1

        total_changes = insertions + deletions
        churn = deletions / total_changes if total_changes > 0 else 0

        week_id = f"{end_date.isocalendar()[0]}-W{end_date.isocalendar()[1]:02d}"
        metrics.append(CodeMetric(
            period=week_id,
            commits=commits,
            insertions=insertions,
            deletions=deletions,
            files_changed=files_changed,
            churn_rate=round(churn, 2)
        ))

    return list(reversed(metrics))


def calculate_health_score(report: ProjectHealthReport) -> float:
    """Calculate overall project health score (0-100)."""
    score = 100.0
    alerts = []
    recommendations = []

    # Velocity trend (negative trend is bad)
    if len(report.velocity) >= 2:
        recent = report.velocity[-1].items_completed
        previous = report.velocity[-2].items_completed
        if recent < previous * 0.7:
            score -= 15
            alerts.append("Velocity dropped significantly from previous week")
            recommendations.append("Review sprint planning and blockers")

    # Bug trend (increasing open bugs is bad)
    if len(report.bugs) >= 2:
        recent_bugs = report.bugs[-1].bugs_open_total
        previous_bugs = report.bugs[-2].bugs_open_total
        if recent_bugs > previous_bugs * 1.2:
            score -= 10
            alerts.append(f"Open bugs increased to {recent_bugs}")
            recommendations.append("Prioritize bug fixing in next sprint")

    # Pipeline health (< 80% success is concerning)
    if report.pipelines:
        recent_pipeline = report.pipelines[-1]
        if recent_pipeline.success_rate < 80:
            score -= 10
            alerts.append(f"Pipeline success rate is {recent_pipeline.success_rate}%")
            recommendations.append("Investigate pipeline failures")

    # Blockers
    if report.blockers > 0:
        score -= min(report.blockers * 5, 20)
        alerts.append(f"{report.blockers} items are blocked")
        recommendations.append("Resolve blockers as priority")

    # Code churn (high churn may indicate instability)
    if report.code:
        avg_churn = sum(c.churn_rate for c in report.code) / len(report.code)
        if avg_churn > 0.4:
            score -= 5
            alerts.append(f"High code churn rate ({avg_churn:.0%})")

    report.health_score = max(0, min(100, score))
    report.alerts = alerts
    report.recommendations = recommendations

    return report.health_score


def generate_health_report_markdown(report: ProjectHealthReport) -> str:
    """Generate markdown health report."""
    lines = []

    lines.append(f"# Project Health Report")
    lines.append(f"")
    lines.append(f"**Generated:** {report.generated_at}")
    lines.append(f"**Period:** {report.period_start} to {report.period_end}")
    lines.append(f"**Project:** {report.project}")
    lines.append("")

    # Health Score
    score = report.health_score or 0
    if score >= 80:
        status = "Healthy"
        emoji = "🟢"
    elif score >= 60:
        status = "Fair"
        emoji = "🟡"
    else:
        status = "Needs Attention"
        emoji = "🔴"

    lines.append(f"## Overall Health: {emoji} {status} ({score:.0f}/100)")
    lines.append("")

    # Alerts
    if report.alerts:
        lines.append("### Alerts")
        for alert in report.alerts:
            lines.append(f"- ⚠️ {alert}")
        lines.append("")

    # Recommendations
    if report.recommendations:
        lines.append("### Recommendations")
        for rec in report.recommendations:
            lines.append(f"- 💡 {rec}")
        lines.append("")

    # Velocity
    if report.velocity:
        lines.append("## Velocity Trend")
        lines.append("")
        lines.append("| Week | Items Completed |")
        lines.append("|------|-----------------|")
        for v in report.velocity:
            lines.append(f"| {v.period} | {v.items_completed} |")
        lines.append("")

    # Bug Trend
    if report.bugs:
        lines.append("## Bug Trend")
        lines.append("")
        lines.append("| Week | Opened | Closed | Total Open |")
        lines.append("|------|--------|--------|------------|")
        for b in report.bugs:
            trend = "↑" if b.bugs_opened > b.bugs_closed else "↓" if b.bugs_closed > b.bugs_opened else "→"
            lines.append(f"| {b.period} | {b.bugs_opened} | {b.bugs_closed} | {b.bugs_open_total} {trend} |")
        lines.append("")

    # Pipeline Health
    if report.pipelines:
        lines.append("## Pipeline Health")
        lines.append("")
        lines.append("| Week | Runs | Success Rate |")
        lines.append("|------|------|--------------|")
        for p in report.pipelines:
            rate_emoji = "✅" if p.success_rate >= 90 else "⚠️" if p.success_rate >= 70 else "❌"
            lines.append(f"| {p.period} | {p.total_runs} | {p.success_rate}% {rate_emoji} |")
        lines.append("")

    # Code Metrics
    if report.code:
        lines.append("## Code Activity")
        lines.append("")
        lines.append("| Week | Commits | Lines Changed | Churn |")
        lines.append("|------|---------|---------------|-------|")
        for c in report.code:
            lines_changed = f"+{c.insertions}/-{c.deletions}"
            lines.append(f"| {c.period} | {c.commits} | {lines_changed} | {c.churn_rate:.0%} |")
        lines.append("")

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Project health reports")
    parser.add_argument("--config", "-c", default=".wsr/config.json")

    subparsers = parser.add_subparsers(dest="command")

    # report command
    report_parser = subparsers.add_parser("report", help="Generate health report")
    report_parser.add_argument("--weeks", "-w", type=int, default=4, help="Weeks of history")
    report_parser.add_argument("--output", "-o", help="Output file")
    report_parser.add_argument("--format", "-f", choices=["markdown", "json"], default="markdown")

    # metrics command
    metrics_parser = subparsers.add_parser("metrics", help="Get raw metrics")
    metrics_parser.add_argument("--weeks", "-w", type=int, default=4)

    args = parser.parse_args()

    # Load config
    try:
        config = WSRConfig.load(args.config)
    except FileNotFoundError:
        print("WSR not configured. Run: python wsr_config.py init", file=sys.stderr)
        return 1

    org = config.organization
    project = config.project

    if not org or not project:
        print("Error: organization and project must be configured", file=sys.stderr)
        return 1

    if args.command == "report":
        print(f"Gathering metrics for {args.weeks} weeks...", file=sys.stderr)

        end_date = datetime.now()
        start_date = end_date - timedelta(weeks=args.weeks)

        report = ProjectHealthReport(
            generated_at=datetime.now().isoformat(),
            period_start=start_date.strftime("%Y-%m-%d"),
            period_end=end_date.strftime("%Y-%m-%d"),
            organization=org,
            project=project
        )

        print("  Gathering velocity metrics...", file=sys.stderr)
        report.velocity = get_velocity_metrics(org, project, args.weeks)

        print("  Gathering bug metrics...", file=sys.stderr)
        report.bugs = get_bug_metrics(org, project, args.weeks)

        print("  Gathering pipeline metrics...", file=sys.stderr)
        report.pipelines = get_pipeline_metrics(org, project, args.weeks)

        print("  Gathering code metrics...", file=sys.stderr)
        report.code = get_code_metrics(args.weeks)

        # Calculate health score
        calculate_health_score(report)

        if args.format == "json":
            output = json.dumps(asdict(report), indent=2, default=str)
        else:
            output = generate_health_report_markdown(report)

        if args.output:
            Path(args.output).write_text(output)
            print(f"Report saved to: {args.output}")
        else:
            print(output)

    elif args.command == "metrics":
        metrics = {
            "velocity": [asdict(v) for v in get_velocity_metrics(org, project, args.weeks)],
            "bugs": [asdict(b) for b in get_bug_metrics(org, project, args.weeks)],
            "pipelines": [asdict(p) for p in get_pipeline_metrics(org, project, args.weeks)],
            "code": [asdict(c) for c in get_code_metrics(args.weeks)]
        }
        print(json.dumps(metrics, indent=2))

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

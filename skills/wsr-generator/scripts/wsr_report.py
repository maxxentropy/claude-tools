#!/usr/bin/env python3
"""
wsr_report.py - Generate WSR reports from accumulated entries.

Supports:
- Multiple audience levels (executive, standard, technical)
- Multiple output formats (markdown, html)
- Live links to work items and commits
- Inverted pyramid structure (TL;DR first)
- Professional status indicators
- Trend indicators vs previous week

Usage:
    python wsr_report.py generate                          # Current week, standard
    python wsr_report.py generate --audience executive     # Executive summary
    python wsr_report.py generate --audience technical     # Full technical detail
    python wsr_report.py generate --format html            # HTML output
    python wsr_report.py generate --final                  # Mark as final
    python wsr_report.py generate --week 2025-W50          # Specific week
"""

from __future__ import annotations

import argparse
import html
import json
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any

from wsr_config import WSRConfig, get_week_id, AUDIENCE_LEVELS
from wsr_entries import WeeklyData, WSREntry


# Professional status indicators (Unicode symbols, no emoji)
STATUS_INDICATORS = {
    "Completed": {"symbol": "●", "label": "DONE", "css_class": "status-completed"},
    "In Progress": {"symbol": "◐", "label": "IN PROGRESS", "css_class": "status-in-progress"},
    "Blocked": {"symbol": "■", "label": "BLOCKED", "css_class": "status-blocked"},
    "On Hold": {"symbol": "○", "label": "ON HOLD", "css_class": "status-on-hold"},
}

PRIORITY_INDICATORS = {
    "High": {"symbol": "▲", "label": "HIGH", "css_class": "priority-high"},
    "Medium": {"symbol": "●", "label": "MED", "css_class": "priority-medium"},
    "Low": {"symbol": "▽", "label": "LOW", "css_class": "priority-low"},
}

TREND_INDICATORS = {
    "up": {"symbol": "↑", "label": "increased"},
    "down": {"symbol": "↓", "label": "decreased"},
    "stable": {"symbol": "→", "label": "stable"},
}

# HTML template for styled reports
HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <style>
        :root {{
            --color-completed: #28a745;
            --color-in-progress: #007bff;
            --color-blocked: #dc3545;
            --color-on-hold: #6c757d;
            --color-high: #dc3545;
            --color-medium: #ffc107;
            --color-low: #28a745;
            --color-bg: #ffffff;
            --color-text: #212529;
            --color-muted: #6c757d;
            --color-border: #dee2e6;
        }}
        body {{
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif;
            line-height: 1.6;
            color: var(--color-text);
            max-width: 900px;
            margin: 0 auto;
            padding: 2rem;
            background: var(--color-bg);
        }}
        h1 {{ border-bottom: 2px solid var(--color-border); padding-bottom: 0.5rem; }}
        h2 {{ margin-top: 2rem; color: var(--color-text); }}
        h3 {{ margin-top: 1.5rem; }}
        .meta {{ color: var(--color-muted); font-size: 0.9rem; margin-bottom: 1.5rem; }}
        .executive-summary {{
            background: #f8f9fa;
            border-left: 4px solid var(--color-in-progress);
            padding: 1rem 1.5rem;
            margin: 1.5rem 0;
        }}
        .executive-summary h2 {{ margin-top: 0; }}
        .status-badge, .priority-badge {{
            display: inline-block;
            padding: 0.2rem 0.6rem;
            border-radius: 3px;
            font-size: 0.75rem;
            font-weight: 600;
            text-transform: uppercase;
            letter-spacing: 0.5px;
        }}
        .status-completed {{ background: #d4edda; color: #155724; }}
        .status-in-progress {{ background: #cce5ff; color: #004085; }}
        .status-blocked {{ background: #f8d7da; color: #721c24; }}
        .status-on-hold {{ background: #e2e3e5; color: #383d41; }}
        .priority-high {{ background: #f8d7da; color: #721c24; }}
        .priority-medium {{ background: #fff3cd; color: #856404; }}
        .priority-low {{ background: #d4edda; color: #155724; }}
        .entry {{
            border: 1px solid var(--color-border);
            border-radius: 6px;
            padding: 1.5rem;
            margin: 1rem 0;
            background: #ffffff;
        }}
        .entry-header {{
            display: flex;
            justify-content: space-between;
            align-items: flex-start;
            flex-wrap: wrap;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }}
        .entry-title {{ margin: 0; font-size: 1.1rem; }}
        .entry-badges {{ display: flex; gap: 0.5rem; }}
        .entry-meta {{ color: var(--color-muted); font-size: 0.85rem; margin-bottom: 1rem; }}
        .section {{ margin: 1rem 0; }}
        .section-title {{ font-weight: 600; color: var(--color-text); margin-bottom: 0.25rem; }}
        .code-stats {{ font-family: monospace; font-size: 0.9rem; color: var(--color-muted); }}
        .references {{ margin-top: 1rem; padding-top: 1rem; border-top: 1px solid var(--color-border); }}
        .references a {{ color: var(--color-in-progress); text-decoration: none; }}
        .references a:hover {{ text-decoration: underline; }}
        table {{ width: 100%; border-collapse: collapse; margin: 1rem 0; }}
        th, td {{ padding: 0.75rem; text-align: left; border-bottom: 1px solid var(--color-border); }}
        th {{ background: #f8f9fa; font-weight: 600; }}
        .trend-up {{ color: var(--color-completed); }}
        .trend-down {{ color: var(--color-blocked); }}
        .trend-stable {{ color: var(--color-muted); }}
        details {{ margin: 1rem 0; }}
        summary {{ cursor: pointer; font-weight: 600; padding: 0.5rem; background: #f8f9fa; border-radius: 4px; }}
        summary:hover {{ background: #e9ecef; }}
        .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 1rem; margin: 1rem 0; }}
        .kpi-card {{ background: #f8f9fa; padding: 1rem; border-radius: 6px; text-align: center; }}
        .kpi-value {{ font-size: 2rem; font-weight: 700; }}
        .kpi-label {{ color: var(--color-muted); font-size: 0.85rem; }}
    </style>
</head>
<body>
{content}
</body>
</html>
"""


class WSRReportGenerator:
    """Generate WSR reports with configurable detail levels and formats."""

    def __init__(self, config: WSRConfig, weekly_data: WeeklyData, prev_week_data: Optional[WeeklyData] = None):
        self.config = config
        self.data = weekly_data
        self.prev_data = prev_week_data
        self.audience_settings = {}
        self.output_format = "markdown"

    def set_audience(self, audience: str):
        """Set the audience level for report generation."""
        self.audience_settings = AUDIENCE_LEVELS.get(audience, AUDIENCE_LEVELS["standard"])

    def set_format(self, output_format: str):
        """Set output format (markdown or html)."""
        self.output_format = output_format

    def format_date_range(self, start: str, end: str) -> str:
        """Format date range for display."""
        try:
            start_dt = datetime.fromisoformat(start)
            end_dt = datetime.fromisoformat(end)

            if start_dt.month == end_dt.month:
                return f"{start_dt.strftime('%B')} {start_dt.day}-{end_dt.day}, {end_dt.year}"
            else:
                return f"{start_dt.strftime('%B %d')} - {end_dt.strftime('%B %d, %Y')}"
        except:
            return f"{start} to {end}"

    def get_status_indicator(self, status: str) -> str:
        """Get professional status indicator."""
        indicator = STATUS_INDICATORS.get(status, STATUS_INDICATORS["In Progress"])
        if self.output_format == "html":
            return f'<span class="status-badge {indicator["css_class"]}">{indicator["label"]}</span>'
        return f'`{indicator["symbol"]} {indicator["label"]}`'

    def get_priority_indicator(self, priority: str) -> str:
        """Get professional priority indicator."""
        indicator = PRIORITY_INDICATORS.get(priority, PRIORITY_INDICATORS["Medium"])
        if self.output_format == "html":
            return f'<span class="priority-badge {indicator["css_class"]}">{indicator["label"]}</span>'
        return f'`{indicator["symbol"]} {indicator["label"]}`'

    def get_trend_indicator(self, current: float, previous: float) -> str:
        """Get trend indicator comparing current to previous value."""
        if previous == 0:
            return ""

        pct_change = ((current - previous) / previous) * 100

        if pct_change > 5:
            trend = TREND_INDICATORS["up"]
            css_class = "trend-up"
        elif pct_change < -5:
            trend = TREND_INDICATORS["down"]
            css_class = "trend-down"
        else:
            trend = TREND_INDICATORS["stable"]
            css_class = "trend-stable"

        if self.output_format == "html":
            return f'<span class="{css_class}">{trend["symbol"]} {abs(pct_change):.0f}%</span>'
        return f'{trend["symbol"]} {abs(pct_change):.0f}%'

    def format_work_item_links(self, work_items: List[Dict]) -> str:
        """Format work items as markdown/html links."""
        if not work_items:
            return ""

        links = []
        for wi in work_items:
            wi_id = wi.get("id")
            url = wi.get("url") or self.config.get_work_item_url(wi_id)
            title = wi.get("title", "")

            if url and url.startswith("http"):
                if self.output_format == "html":
                    links.append(f'<a href="{html.escape(url)}">AB#{wi_id}</a>')
                else:
                    links.append(f"[AB#{wi_id}]({url})")
            else:
                links.append(f"AB#{wi_id}")

        return ", ".join(links)

    def format_commit_links(self, commits: List[Dict], include_details: bool = False) -> str:
        """Format commits as markdown/html links."""
        if not commits:
            return ""

        lines = []
        for commit in commits:
            sha = commit.get("sha", "")
            short_sha = commit.get("short_sha", sha[:7])
            subject = commit.get("subject", "")
            url = commit.get("url") or self.config.get_commit_url(sha)

            if url and url.startswith("http"):
                if self.output_format == "html":
                    link = f'<a href="{html.escape(url)}"><code>{short_sha}</code></a>'
                else:
                    link = f"[`{short_sha}`]({url})"
            else:
                link = f"`{short_sha}`"

            if include_details and subject:
                lines.append(f"{link} - {subject[:60]}")
            else:
                lines.append(link)

        if include_details:
            if self.output_format == "html":
                return "<ul>" + "".join(f"<li>{line}</li>" for line in lines) + "</ul>"
            return "\n".join(f"- {line}" for line in lines)
        return ", ".join(lines)

    def calculate_summary_stats(self, entries: List[Dict]) -> Dict[str, Any]:
        """Calculate summary statistics for entries."""
        stats = {
            "total_entries": len(entries),
            "completed": sum(1 for e in entries if e.get("status") == "Completed"),
            "in_progress": sum(1 for e in entries if e.get("status") == "In Progress"),
            "blocked": sum(1 for e in entries if e.get("status") == "Blocked"),
            "total_commits": sum(len(e.get("commits", [])) for e in entries),
            "total_insertions": sum(e.get("total_insertions", 0) for e in entries),
            "total_deletions": sum(e.get("total_deletions", 0) for e in entries),
            "total_files": sum(e.get("total_files_changed", 0) for e in entries),
            "work_items": [],
        }

        for entry in entries:
            stats["work_items"].extend(entry.get("work_items", []))

        stats["unique_work_items"] = len(set(wi.get("id") for wi in stats["work_items"]))

        return stats

    def generate_executive_summary(self, entries: List[Dict]) -> str:
        """Generate TL;DR executive summary."""
        stats = self.calculate_summary_stats(entries)

        # Calculate previous week stats for trends
        prev_stats = None
        if self.prev_data and self.prev_data.entries:
            prev_stats = self.calculate_summary_stats(self.prev_data.entries)

        if self.output_format == "html":
            lines = ['<div class="executive-summary">']
            lines.append("<h2>Executive Summary</h2>")
            lines.append('<div class="kpi-grid">')

            # Completed items
            completed_trend = ""
            if prev_stats:
                completed_trend = self.get_trend_indicator(stats["completed"], prev_stats["completed"])
            lines.append(f'''<div class="kpi-card">
                <div class="kpi-value">{stats["completed"]}</div>
                <div class="kpi-label">Items Completed {completed_trend}</div>
            </div>''')

            # In progress
            lines.append(f'''<div class="kpi-card">
                <div class="kpi-value">{stats["in_progress"]}</div>
                <div class="kpi-label">In Progress</div>
            </div>''')

            # Blocked
            if stats["blocked"] > 0:
                lines.append(f'''<div class="kpi-card">
                    <div class="kpi-value" style="color: var(--color-blocked)">{stats["blocked"]}</div>
                    <div class="kpi-label">Blocked</div>
                </div>''')

            # Work items
            lines.append(f'''<div class="kpi-card">
                <div class="kpi-value">{stats["unique_work_items"]}</div>
                <div class="kpi-label">Work Items</div>
            </div>''')

            lines.append("</div>")  # kpi-grid

            # Key highlights
            high_priority = [e for e in entries if e.get("priority") == "High"]
            if high_priority:
                lines.append("<p><strong>Key Focus Areas:</strong></p><ul>")
                for entry in high_priority[:3]:
                    status = self.get_status_indicator(entry.get("status", "In Progress"))
                    lines.append(f"<li>{status} {html.escape(entry['title'][:60])}</li>")
                lines.append("</ul>")

            lines.append("</div>")  # executive-summary
            return "\n".join(lines)

        else:
            # Markdown format
            lines = []
            lines.append("## Executive Summary")
            lines.append("")

            # Key metrics line
            metrics = []
            metrics.append(f"**{stats['completed']}** completed")
            if stats["in_progress"]:
                metrics.append(f"**{stats['in_progress']}** in progress")
            if stats["blocked"]:
                metrics.append(f"**{stats['blocked']}** blocked")
            if stats["unique_work_items"]:
                metrics.append(f"**{stats['unique_work_items']}** work items")

            lines.append(" | ".join(metrics))
            lines.append("")

            # Key highlights
            high_priority = [e for e in entries if e.get("priority") == "High"]
            if high_priority:
                lines.append("**Key Focus Areas:**")
                for entry in high_priority[:3]:
                    status_ind = STATUS_INDICATORS.get(entry.get("status", "In Progress"), STATUS_INDICATORS["In Progress"])
                    lines.append(f"- {status_ind['symbol']} {entry['title'][:60]}")
                lines.append("")

            return "\n".join(lines)

    def generate_entry_section(self, entry: Dict, index: int) -> str:
        """Generate section for a single entry."""
        settings = self.audience_settings

        if self.output_format == "html":
            return self._generate_entry_html(entry, index, settings)
        else:
            return self._generate_entry_markdown(entry, index, settings)

    def _generate_entry_html(self, entry: Dict, index: int, settings: Dict) -> str:
        """Generate HTML for a single entry."""
        lines = ['<div class="entry">']

        # Header with title and badges
        lines.append('<div class="entry-header">')
        lines.append(f'<h3 class="entry-title">{index}. {html.escape(entry["title"])}</h3>')
        lines.append('<div class="entry-badges">')
        lines.append(self.get_status_indicator(entry.get("status", "In Progress")))
        lines.append(self.get_priority_indicator(entry.get("priority", "Medium")))
        lines.append('</div></div>')

        # Meta information
        timeline = self.format_date_range(entry.get('timeline_start', ''), entry.get('timeline_end', ''))
        domain = entry.get("domain", "")
        meta_parts = [f"Domain: {domain}"] if domain else []
        if timeline and "to" not in timeline.lower():
            meta_parts.append(f"Timeline: {timeline}")
        if meta_parts:
            lines.append(f'<div class="entry-meta">{" | ".join(meta_parts)}</div>')

        # Content sections
        for section_key, section_title in [
            ("objective", "Objective/Background"),
            ("solution", "Solution/Approach"),
            ("business_impact", "Business Impact"),
            ("technical_impact", "Technical Impact"),
            ("risks", "Risk Assessment"),
            ("next_steps", "Next Steps"),
        ]:
            if section_key in settings["include_sections"] and entry.get(section_key):
                lines.append(f'<div class="section"><div class="section-title">{section_title}</div>')
                lines.append(f'<p>{html.escape(entry[section_key])}</p></div>')

        # Code stats
        if settings["include_code_stats"]:
            insertions = entry.get("total_insertions", 0)
            deletions = entry.get("total_deletions", 0)
            files = entry.get("total_files_changed", 0)
            if insertions or deletions or files:
                lines.append(f'<div class="code-stats">{files} files | +{insertions} / -{deletions} lines</div>')

        # References
        refs = []
        if settings["include_work_item_list"] and entry.get("work_items"):
            wi_links = self.format_work_item_links(entry["work_items"])
            refs.append(f"<strong>Work Items:</strong> {wi_links}")

        if entry.get("commits"):
            if settings["include_commit_details"]:
                refs.append(f"<strong>Commits:</strong> {self.format_commit_links(entry['commits'], include_details=True)}")
            else:
                refs.append(f"<strong>Commits:</strong> {self.format_commit_links(entry['commits'])}")

        if refs:
            lines.append('<div class="references">' + "<br>".join(refs) + '</div>')

        lines.append('</div>')  # entry
        return "\n".join(lines)

    def _generate_entry_markdown(self, entry: Dict, index: int, settings: Dict) -> str:
        """Generate markdown for a single entry."""
        lines = []

        # Title with status and priority badges
        status_ind = self.get_status_indicator(entry.get("status", "In Progress"))
        priority_ind = self.get_priority_indicator(entry.get("priority", "Medium"))

        lines.append(f"### {index}. {entry['title']}")
        lines.append("")
        lines.append(f"{status_ind} {priority_ind}")
        lines.append("")

        # Meta information
        domain = entry.get("domain", "")
        timeline = self.format_date_range(entry.get('timeline_start', ''), entry.get('timeline_end', ''))

        meta_line = []
        if domain:
            meta_line.append(f"**Domain:** {domain}")
        if timeline and "to" not in timeline.lower():
            meta_line.append(f"**Timeline:** {timeline}")
        if meta_line:
            lines.append(" | ".join(meta_line))
            lines.append("")

        # Content sections based on audience level
        for section_key, section_title in [
            ("objective", "Objective/Background"),
            ("solution", "Solution/Approach"),
            ("business_impact", "Business Impact"),
            ("technical_impact", "Technical Impact"),
            ("risks", "Risk Assessment & Mitigation"),
            ("next_steps", "Next Steps"),
        ]:
            if section_key in settings["include_sections"] and entry.get(section_key):
                lines.append(f"**{section_title}**")
                lines.append(entry[section_key])
                lines.append("")

        # Code stats
        if settings["include_code_stats"]:
            insertions = entry.get("total_insertions", 0)
            deletions = entry.get("total_deletions", 0)
            files = entry.get("total_files_changed", 0)
            if insertions or deletions or files:
                lines.append(f"*{files} files changed, +{insertions}/-{deletions} lines*")
                lines.append("")

        # References
        if settings["include_work_item_list"] and entry.get("work_items"):
            wi_links = self.format_work_item_links(entry["work_items"])
            lines.append(f"**Work Items:** {wi_links}")

        if entry.get("commits"):
            if settings["include_commit_details"]:
                lines.append("**Key Commits:**")
                lines.append(self.format_commit_links(entry["commits"], include_details=True))
            else:
                commit_links = self.format_commit_links(entry["commits"], include_details=False)
                lines.append(f"**Commits:** {commit_links}")

        lines.append("")
        lines.append("---")
        lines.append("")

        return "\n".join(lines)

    def generate_summary_table(self, entries: List[Dict]) -> str:
        """Generate summary table of all entries."""
        if not self.audience_settings.get("include_code_stats"):
            return ""

        # Group by repository
        by_repo = {}
        for entry in entries:
            repo = entry.get("repository", "Unknown")
            if repo not in by_repo:
                by_repo[repo] = {"commits": 0, "insertions": 0, "deletions": 0, "entries": []}
            by_repo[repo]["entries"].append(entry)
            by_repo[repo]["commits"] += len(entry.get("commits", []))
            by_repo[repo]["insertions"] += entry.get("total_insertions", 0)
            by_repo[repo]["deletions"] += entry.get("total_deletions", 0)

        if not by_repo:
            return ""

        if self.output_format == "html":
            lines = ["<h2>Summary</h2>"]
            lines.append("<table>")
            lines.append("<thead><tr><th>Repository</th><th>Entries</th><th>Commits</th><th>Lines Changed</th></tr></thead>")
            lines.append("<tbody>")

            total_entries = 0
            total_commits = 0

            for repo, stats in by_repo.items():
                entry_count = len(stats['entries'])
                lines.append(f"<tr><td>{html.escape(repo)}</td><td>{entry_count}</td><td>{stats['commits']}</td><td>+{stats['insertions']}/-{stats['deletions']}</td></tr>")
                total_entries += entry_count
                total_commits += stats['commits']

            if len(by_repo) > 1:
                total_ins = sum(s["insertions"] for s in by_repo.values())
                total_del = sum(s["deletions"] for s in by_repo.values())
                lines.append(f"<tr><td><strong>Total</strong></td><td><strong>{total_entries}</strong></td><td><strong>{total_commits}</strong></td><td><strong>+{total_ins}/-{total_del}</strong></td></tr>")

            lines.append("</tbody></table>")
            return "\n".join(lines)

        else:
            lines = ["## Summary", ""]
            lines.append("| Repository | Entries | Commits | Lines Changed |")
            lines.append("|------------|---------|---------|---------------|")

            total_entries = 0
            total_commits = 0
            total_lines = 0

            for repo, stats in by_repo.items():
                lines_changed = stats["insertions"] + stats["deletions"]
                lines.append(f"| {repo} | {len(stats['entries'])} | {stats['commits']} | +{stats['insertions']}/-{stats['deletions']} |")
                total_entries += len(stats['entries'])
                total_commits += stats['commits']
                total_lines += lines_changed

            if len(by_repo) > 1:
                total_ins = sum(s["insertions"] for s in by_repo.values())
                total_del = sum(s["deletions"] for s in by_repo.values())
                lines.append(f"| **Total** | **{total_entries}** | **{total_commits}** | **+{total_ins}/-{total_del}** |")

            lines.append("")
            return "\n".join(lines)

    def generate_status_overview(self, entries: List[Dict]) -> str:
        """Generate visual status overview."""
        stats = self.calculate_summary_stats(entries)

        if self.output_format == "html":
            lines = ['<h2>Status Overview</h2>']
            lines.append('<table>')
            lines.append('<thead><tr><th>Status</th><th>Count</th><th>Items</th></tr></thead>')
            lines.append('<tbody>')

            status_groups = {}
            for entry in entries:
                status = entry.get("status", "In Progress")
                if status not in status_groups:
                    status_groups[status] = []
                status_groups[status].append(entry)

            for status in ["Completed", "In Progress", "Blocked", "On Hold"]:
                if status in status_groups:
                    items = status_groups[status]
                    indicator = self.get_status_indicator(status)
                    item_list = ", ".join(html.escape(e["title"][:30]) for e in items[:3])
                    if len(items) > 3:
                        item_list += f" (+{len(items) - 3} more)"
                    lines.append(f'<tr><td>{indicator}</td><td>{len(items)}</td><td>{item_list}</td></tr>')

            lines.append('</tbody></table>')
            return "\n".join(lines)

        else:
            lines = ["## Status Overview", ""]
            lines.append("| Status | Count |")
            lines.append("|--------|-------|")

            status_groups = {}
            for entry in entries:
                status = entry.get("status", "In Progress")
                status_groups[status] = status_groups.get(status, 0) + 1

            for status in ["Completed", "In Progress", "Blocked", "On Hold"]:
                if status in status_groups:
                    indicator = STATUS_INDICATORS.get(status, STATUS_INDICATORS["In Progress"])
                    lines.append(f"| {indicator['symbol']} {status} | {status_groups[status]} |")

            lines.append("")
            return "\n".join(lines)

    def generate_report(self, audience: str = "standard", is_final: bool = False) -> str:
        """Generate the full WSR report."""
        self.set_audience(audience)
        settings = self.audience_settings

        entries = self.data.entries
        date_range = self.format_date_range(self.data.period_start, self.data.period_end)
        status_label = "Weekly Status Report" if is_final else "Weekly Status Report (Draft)"
        title = f"{status_label} - {date_range}"

        if self.output_format == "html":
            return self._generate_html_report(title, entries, audience, is_final, settings)
        else:
            return self._generate_markdown_report(title, entries, audience, is_final, settings)

    def _generate_html_report(self, title: str, entries: List[Dict], audience: str, is_final: bool, settings: Dict) -> str:
        """Generate HTML formatted report."""
        content_lines = []

        content_lines.append(f"<h1>{html.escape(title)}</h1>")

        if not is_final:
            content_lines.append(f'<p class="meta">Generated: {datetime.now().strftime("%Y-%m-%d %H:%M")} | Audience: {audience.title()}</p>')

        if not entries:
            content_lines.append("<p><em>No entries recorded for this week.</em></p>")
            return HTML_TEMPLATE.format(title=html.escape(title), content="\n".join(content_lines))

        # Executive summary (inverted pyramid - most important first)
        content_lines.append(self.generate_executive_summary(entries))

        # Sort entries by priority then status
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        status_order = {"Completed": 0, "In Progress": 1, "Blocked": 2, "On Hold": 3}
        entries_sorted = sorted(
            entries,
            key=lambda e: (priority_order.get(e.get("priority"), 9), status_order.get(e.get("status"), 9))
        )

        # Limit entries for executive summary
        if settings.get("summary_only"):
            max_entries = self.config.max_entries_per_report
            if len(entries_sorted) > max_entries:
                entries_sorted = entries_sorted[:max_entries]
                content_lines.append(f'<p><em>Showing top {max_entries} items. See full report for complete details.</em></p>')

        # Detailed entries (collapsible for technical audience)
        if audience == "technical":
            content_lines.append("<details open><summary>Detailed Entries</summary>")
        else:
            content_lines.append("<h2>Entries</h2>")

        for i, entry in enumerate(entries_sorted, 1):
            content_lines.append(self.generate_entry_section(entry, i))

        if audience == "technical":
            content_lines.append("</details>")

        # Summary table
        content_lines.append(self.generate_summary_table(entries))

        # Notes
        if self.data.notes:
            content_lines.append("<h2>Notes</h2>")
            content_lines.append(f"<p>{html.escape(self.data.notes)}</p>")

        return HTML_TEMPLATE.format(title=html.escape(title), content="\n".join(content_lines))

    def _generate_markdown_report(self, title: str, entries: List[Dict], audience: str, is_final: bool, settings: Dict) -> str:
        """Generate markdown formatted report."""
        lines = []

        lines.append(f"# {title}")
        lines.append("")

        if not is_final:
            lines.append(f"*Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} | Audience: {audience.title()}*")
            lines.append("")

        if not entries:
            lines.append("*No entries recorded for this week.*")
            return "\n".join(lines)

        # Executive summary (inverted pyramid - most important first)
        lines.append(self.generate_executive_summary(entries))

        # Status overview
        lines.append(self.generate_status_overview(entries))

        # Sort entries by priority then status
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        status_order = {"Completed": 0, "In Progress": 1, "Blocked": 2, "On Hold": 3}
        entries_sorted = sorted(
            entries,
            key=lambda e: (priority_order.get(e.get("priority"), 9), status_order.get(e.get("status"), 9))
        )

        # Limit entries for executive summary
        if settings.get("summary_only"):
            max_entries = self.config.max_entries_per_report
            if len(entries_sorted) > max_entries:
                entries_sorted = entries_sorted[:max_entries]
                lines.append(f"*Showing top {max_entries} items. See full report for complete details.*")
                lines.append("")

        # Generate entry sections
        lines.append("## Detailed Entries")
        lines.append("")

        for i, entry in enumerate(entries_sorted, 1):
            lines.append(self.generate_entry_section(entry, i))

        # Summary table
        lines.append(self.generate_summary_table(entries))

        # Notes
        if self.data.notes:
            lines.append("## Notes")
            lines.append("")
            lines.append(self.data.notes)
            lines.append("")

        return "\n".join(lines)


def get_previous_week_id(week_id: str) -> str:
    """Get the previous week's ID."""
    year = int(week_id[:4])
    week = int(week_id[6:])

    if week > 1:
        return f"{year}-W{week-1:02d}"
    else:
        # Go to previous year's last week
        return f"{year-1}-W52"


def main():
    parser = argparse.ArgumentParser(description="Generate WSR reports")
    parser.add_argument("--config", "-c", default=".wsr/config.json", help="Config file path")
    parser.add_argument("--week", "-w", help="Week ID (YYYY-WNN)")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # generate command
    gen_parser = subparsers.add_parser("generate", help="Generate a report")
    gen_parser.add_argument("--audience", "-a", default="standard",
                            choices=["executive", "standard", "technical"],
                            help="Audience level")
    gen_parser.add_argument("--format", "-F", default="markdown",
                            choices=["markdown", "html"],
                            help="Output format")
    gen_parser.add_argument("--final", "-f", action="store_true",
                            help="Mark as final report")
    gen_parser.add_argument("--output", "-o", help="Output file (default: auto-named in output_dir)")
    gen_parser.add_argument("--stdout", action="store_true", help="Print to stdout instead of file")
    gen_parser.add_argument("--with-trends", action="store_true",
                            help="Include trend comparisons with previous week")

    # preview command
    preview_parser = subparsers.add_parser("preview", help="Preview report structure")
    preview_parser.add_argument("--audience", "-a", default="standard")

    args = parser.parse_args()

    # Load config
    try:
        config = WSRConfig.load(args.config)
    except FileNotFoundError:
        print("WSR not configured. Run: python wsr_config.py init", file=sys.stderr)
        return 1

    week_id = args.week or get_week_id()
    weekly_data = WeeklyData.load(config.data_dir, week_id)

    # Load previous week for trend comparison
    prev_week_data = None
    if hasattr(args, 'with_trends') and args.with_trends:
        prev_week_id = get_previous_week_id(week_id)
        try:
            prev_week_data = WeeklyData.load(config.data_dir, prev_week_id)
        except:
            pass

    if args.command == "generate":
        generator = WSRReportGenerator(config, weekly_data, prev_week_data)
        generator.set_format(args.format)
        report = generator.generate_report(
            audience=args.audience,
            is_final=args.final
        )

        if args.stdout:
            print(report)
        else:
            # Determine output path
            if args.output:
                output_path = Path(args.output)
            else:
                config.ensure_directories()
                suffix = "final" if args.final else "draft"
                ext = "html" if args.format == "html" else "md"
                filename = f"{week_id}-{suffix}-{args.audience}.{ext}"
                output_path = Path(config.output_dir) / filename

            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(report)
            print(f"Report saved to: {output_path}")

            # Also save a copy as latest
            if args.final:
                ext = "html" if args.format == "html" else "md"
                latest_path = Path(config.output_dir) / f"latest-{args.audience}.{ext}"
                latest_path.write_text(report)
                print(f"Also saved as: {latest_path}")

    elif args.command == "preview":
        print(f"\nWeek {week_id} - {len(weekly_data.entries)} entries")
        print(f"Audience: {args.audience}")
        print(f"Sections: {', '.join(AUDIENCE_LEVELS[args.audience]['include_sections'])}")
        print(f"\nEntries:")
        for entry in weekly_data.entries:
            status_ind = STATUS_INDICATORS.get(entry.get('status', 'In Progress'), STATUS_INDICATORS['In Progress'])
            print(f"  {status_ind['symbol']} [{entry['status']}] {entry['title'][:50]}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

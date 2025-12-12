#!/usr/bin/env python3
"""
wsr_notify.py - Send WSR reports via email, Teams, Slack, or other channels.

Supports:
- Email with inline CSS (email-client safe)
- Microsoft Teams via Adaptive Cards (webhook)
- Slack via Block Kit (webhook)
- PDF generation for attachments

Usage:
    python wsr_notify.py send --channel email
    python wsr_notify.py send --channel teams
    python wsr_notify.py send --channel slack
    python wsr_notify.py send --channel all
    python wsr_notify.py configure email
    python wsr_notify.py configure teams
    python wsr_notify.py test email
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import smtplib
import ssl
import subprocess
import sys
import urllib.request
import urllib.error
from dataclasses import dataclass, field, asdict
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication
from pathlib import Path
from typing import Optional, List, Dict, Any

from wsr_config import WSRConfig, get_week_id, AUDIENCE_LEVELS
from wsr_entries import WeeklyData


# Default notification configuration
DEFAULT_NOTIFY_CONFIG = {
    "email": {
        "enabled": False,
        "smtp_server": "",
        "smtp_port": 587,
        "use_tls": True,
        "username": "",
        "password_env": "WSR_EMAIL_PASSWORD",  # Environment variable for password
        "from_address": "",
        "to_addresses": [],
        "cc_addresses": [],
        "subject_template": "Weekly Status Report - {date_range}",
        "include_pdf": False,
    },
    "email_cli": {
        "enabled": False,
        "cli_path": "wsr-email-cli",  # Path to CLI executable
        "template": "wsr-report",     # Template name
        "to_addresses": [],
        "cc_addresses": [],
        "subject_template": "Weekly Status Report - {date_range}",
        "branding": {
            "companyName": "",
            "productName": "",
            "primaryColor": "#007bff",
            "accentColor": "#28a745",
            "supportEmail": "",
            "websiteUrl": "",
        },
    },
    "teams": {
        "enabled": False,
        "webhook_url": "",
        "mention_users": [],  # List of user emails to @mention
    },
    "slack": {
        "enabled": False,
        "webhook_url": "",
        "channel": "",  # Optional channel override
    },
}


@dataclass
class NotifyConfig:
    """Notification configuration."""
    default_channel: str = "teams"
    email: Dict[str, Any] = field(default_factory=lambda: DEFAULT_NOTIFY_CONFIG["email"].copy())
    email_cli: Dict[str, Any] = field(default_factory=lambda: DEFAULT_NOTIFY_CONFIG["email_cli"].copy())
    teams: Dict[str, Any] = field(default_factory=lambda: DEFAULT_NOTIFY_CONFIG["teams"].copy())
    slack: Dict[str, Any] = field(default_factory=lambda: DEFAULT_NOTIFY_CONFIG["slack"].copy())

    @classmethod
    def load(cls, config_path: str = ".wsr/notify.json") -> "NotifyConfig":
        """Load notification configuration."""
        path = Path(config_path)
        if not path.exists():
            return cls()

        data = json.loads(path.read_text())
        return cls(
            default_channel=data.get("default_channel", "teams"),
            email=data.get("email", DEFAULT_NOTIFY_CONFIG["email"].copy()),
            email_cli=data.get("email_cli", DEFAULT_NOTIFY_CONFIG["email_cli"].copy()),
            teams=data.get("teams", DEFAULT_NOTIFY_CONFIG["teams"].copy()),
            slack=data.get("slack", DEFAULT_NOTIFY_CONFIG["slack"].copy()),
        )

    def save(self, config_path: str = ".wsr/notify.json"):
        """Save notification configuration."""
        path = Path(config_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(asdict(self), indent=2))


# =============================================================================
# Email Renderer - Table-based layout with inline CSS
# =============================================================================

class EmailRenderer:
    """Render WSR reports as email-safe HTML with inline CSS."""

    # Color palette (no CSS variables - inline everything)
    COLORS = {
        "completed": "#28a745",
        "completed_bg": "#d4edda",
        "completed_text": "#155724",
        "in_progress": "#007bff",
        "in_progress_bg": "#cce5ff",
        "in_progress_text": "#004085",
        "blocked": "#dc3545",
        "blocked_bg": "#f8d7da",
        "blocked_text": "#721c24",
        "on_hold": "#6c757d",
        "on_hold_bg": "#e2e3e5",
        "on_hold_text": "#383d41",
        "high": "#dc3545",
        "medium": "#ffc107",
        "low": "#28a745",
        "text": "#212529",
        "muted": "#6c757d",
        "border": "#dee2e6",
        "bg": "#ffffff",
        "bg_alt": "#f8f9fa",
    }

    STATUS_CONFIG = {
        "Completed": {"symbol": "●", "color": "completed"},
        "In Progress": {"symbol": "◐", "color": "in_progress"},
        "Blocked": {"symbol": "■", "color": "blocked"},
        "On Hold": {"symbol": "○", "color": "on_hold"},
    }

    PRIORITY_CONFIG = {
        "High": {"symbol": "▲", "color": "high"},
        "Medium": {"symbol": "●", "color": "medium"},
        "Low": {"symbol": "▽", "color": "low"},
    }

    def __init__(self, config: WSRConfig, weekly_data: WeeklyData):
        self.config = config
        self.data = weekly_data

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

    def render_status_badge(self, status: str) -> str:
        """Render an inline status badge."""
        cfg = self.STATUS_CONFIG.get(status, self.STATUS_CONFIG["In Progress"])
        bg = self.COLORS[f"{cfg['color']}_bg"]
        text = self.COLORS[f"{cfg['color']}_text"]
        return f'''<span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;background:{bg};color:{text};">{cfg["symbol"]} {status.upper()}</span>'''

    def render_priority_badge(self, priority: str) -> str:
        """Render an inline priority badge."""
        cfg = self.PRIORITY_CONFIG.get(priority, self.PRIORITY_CONFIG["Medium"])
        color = self.COLORS[cfg["color"]]
        return f'''<span style="display:inline-block;padding:2px 8px;border-radius:3px;font-size:11px;font-weight:600;background:#f8f9fa;color:{color};">{cfg["symbol"]} {priority.upper()}</span>'''

    def calculate_stats(self, entries: List[Dict]) -> Dict[str, Any]:
        """Calculate summary statistics."""
        stats = {
            "total": len(entries),
            "completed": sum(1 for e in entries if e.get("status") == "Completed"),
            "in_progress": sum(1 for e in entries if e.get("status") == "In Progress"),
            "blocked": sum(1 for e in entries if e.get("status") == "Blocked"),
            "work_items": set(),
        }
        for entry in entries:
            for wi in entry.get("work_items", []):
                stats["work_items"].add(wi.get("id"))
        stats["work_item_count"] = len(stats["work_items"])
        return stats

    def render(self, audience: str = "standard") -> str:
        """Render the full email HTML."""
        entries = self.data.entries
        date_range = self.format_date_range(self.data.period_start, self.data.period_end)
        stats = self.calculate_stats(entries)
        settings = AUDIENCE_LEVELS.get(audience, AUDIENCE_LEVELS["standard"])

        # Sort entries
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        status_order = {"Completed": 0, "In Progress": 1, "Blocked": 2, "On Hold": 3}
        entries_sorted = sorted(
            entries,
            key=lambda e: (priority_order.get(e.get("priority"), 9), status_order.get(e.get("status"), 9))
        )

        if settings.get("summary_only"):
            max_entries = self.config.max_entries_per_report
            entries_sorted = entries_sorted[:max_entries]

        # Build HTML with table-based layout
        html_parts = [self._render_doctype()]
        html_parts.append(self._render_header(date_range))
        html_parts.append(self._render_kpi_section(stats))

        if entries_sorted:
            html_parts.append(self._render_entries_section(entries_sorted, settings))

        html_parts.append(self._render_footer())

        return "\n".join(html_parts)

    def _render_doctype(self) -> str:
        return '''<!DOCTYPE html>
<html lang="en" xmlns="http://www.w3.org/1999/xhtml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width,initial-scale=1">
    <meta name="x-apple-disable-message-reformatting">
    <title>Weekly Status Report</title>
    <!--[if mso]>
    <noscript>
        <xml>
            <o:OfficeDocumentSettings>
                <o:PixelsPerInch>96</o:PixelsPerInch>
            </o:OfficeDocumentSettings>
        </xml>
    </noscript>
    <![endif]-->
</head>
<body style="margin:0;padding:0;background-color:#f4f4f4;font-family:Arial,Helvetica,sans-serif;">'''

    def _render_header(self, date_range: str) -> str:
        return f'''
    <table role="presentation" style="width:100%;border-collapse:collapse;border:0;border-spacing:0;background:#f4f4f4;">
        <tr>
            <td align="center" style="padding:40px 0;">
                <table role="presentation" style="width:600px;border-collapse:collapse;border:0;border-spacing:0;background:#ffffff;border-radius:8px;box-shadow:0 2px 8px rgba(0,0,0,0.1);">
                    <tr>
                        <td style="padding:30px 40px;background:{self.COLORS["in_progress"]};border-radius:8px 8px 0 0;">
                            <h1 style="margin:0;font-size:24px;color:#ffffff;font-weight:600;">Weekly Status Report</h1>
                            <p style="margin:8px 0 0 0;font-size:14px;color:rgba(255,255,255,0.9);">{date_range}</p>
                        </td>
                    </tr>'''

    def _render_kpi_section(self, stats: Dict[str, Any]) -> str:
        """Render KPI cards using tables."""
        return f'''
                    <tr>
                        <td style="padding:30px 40px;">
                            <table role="presentation" style="width:100%;border-collapse:collapse;border:0;border-spacing:0;">
                                <tr>
                                    <td style="width:25%;text-align:center;padding:15px;background:{self.COLORS["bg_alt"]};border-radius:6px;">
                                        <div style="font-size:32px;font-weight:700;color:{self.COLORS["completed"]};">{stats["completed"]}</div>
                                        <div style="font-size:12px;color:{self.COLORS["muted"]};text-transform:uppercase;letter-spacing:0.5px;">Completed</div>
                                    </td>
                                    <td style="width:8px;"></td>
                                    <td style="width:25%;text-align:center;padding:15px;background:{self.COLORS["bg_alt"]};border-radius:6px;">
                                        <div style="font-size:32px;font-weight:700;color:{self.COLORS["in_progress"]};">{stats["in_progress"]}</div>
                                        <div style="font-size:12px;color:{self.COLORS["muted"]};text-transform:uppercase;letter-spacing:0.5px;">In Progress</div>
                                    </td>
                                    <td style="width:8px;"></td>
                                    <td style="width:25%;text-align:center;padding:15px;background:{self.COLORS["bg_alt"]};border-radius:6px;">
                                        <div style="font-size:32px;font-weight:700;color:{self.COLORS["blocked"] if stats["blocked"] > 0 else self.COLORS["muted"]};">{stats["blocked"]}</div>
                                        <div style="font-size:12px;color:{self.COLORS["muted"]};text-transform:uppercase;letter-spacing:0.5px;">Blocked</div>
                                    </td>
                                    <td style="width:8px;"></td>
                                    <td style="width:25%;text-align:center;padding:15px;background:{self.COLORS["bg_alt"]};border-radius:6px;">
                                        <div style="font-size:32px;font-weight:700;color:{self.COLORS["text"]};">{stats["work_item_count"]}</div>
                                        <div style="font-size:12px;color:{self.COLORS["muted"]};text-transform:uppercase;letter-spacing:0.5px;">Work Items</div>
                                    </td>
                                </tr>
                            </table>
                        </td>
                    </tr>'''

    def _render_entries_section(self, entries: List[Dict], settings: Dict) -> str:
        """Render entries section."""
        html = '''
                    <tr>
                        <td style="padding:0 40px 30px 40px;">
                            <h2 style="margin:0 0 20px 0;font-size:18px;color:#212529;border-bottom:2px solid #dee2e6;padding-bottom:10px;">Entries</h2>'''

        for i, entry in enumerate(entries, 1):
            html += self._render_entry(entry, i, settings)

        html += '''
                        </td>
                    </tr>'''
        return html

    def _render_entry(self, entry: Dict, index: int, settings: Dict) -> str:
        """Render a single entry."""
        title = entry.get("title", "Untitled")[:80]
        status = entry.get("status", "In Progress")
        priority = entry.get("priority", "Medium")
        domain = entry.get("domain", "")

        html = f'''
                            <table role="presentation" style="width:100%;border-collapse:collapse;border:1px solid {self.COLORS["border"]};border-radius:6px;margin-bottom:15px;">
                                <tr>
                                    <td style="padding:15px;">
                                        <table role="presentation" style="width:100%;border-collapse:collapse;">
                                            <tr>
                                                <td style="vertical-align:top;">
                                                    <div style="font-size:16px;font-weight:600;color:{self.COLORS["text"]};margin-bottom:8px;">{index}. {title}</div>
                                                    <div style="margin-bottom:10px;">
                                                        {self.render_status_badge(status)}
                                                        &nbsp;
                                                        {self.render_priority_badge(priority)}
                                                    </div>'''

        if domain:
            html += f'''
                                                    <div style="font-size:12px;color:{self.COLORS["muted"]};margin-bottom:10px;">Domain: {domain}</div>'''

        # Content sections
        for section_key, section_title in [
            ("objective", "Objective"),
            ("business_impact", "Business Impact"),
            ("next_steps", "Next Steps"),
        ]:
            if section_key in settings.get("include_sections", []) and entry.get(section_key):
                content = entry[section_key][:300]
                if len(entry[section_key]) > 300:
                    content += "..."
                html += f'''
                                                    <div style="margin-top:10px;">
                                                        <div style="font-size:12px;font-weight:600;color:{self.COLORS["text"]};margin-bottom:4px;">{section_title}</div>
                                                        <div style="font-size:13px;color:{self.COLORS["text"]};line-height:1.5;">{content}</div>
                                                    </div>'''

        # Work items
        if settings.get("include_work_item_list") and entry.get("work_items"):
            wi_links = []
            for wi in entry["work_items"][:5]:
                wi_id = wi.get("id")
                # Use stored URL only if it's a valid HTTP URL, otherwise generate from config
                stored_url = wi.get("url", "")
                url = stored_url if stored_url.startswith("http") else self.config.get_work_item_url(wi_id)
                if url and url.startswith("http"):
                    wi_links.append(f'<a href="{url}" style="color:{self.COLORS["in_progress"]};text-decoration:none;">AB#{wi_id}</a>')
                else:
                    wi_links.append(f"AB#{wi_id}")
            html += f'''
                                                    <div style="margin-top:10px;font-size:12px;color:{self.COLORS["muted"]};">
                                                        <strong>Work Items:</strong> {", ".join(wi_links)}
                                                    </div>'''

        # Commits
        if entry.get("commits"):
            commit_links = []
            for c in entry["commits"][:5]:
                sha = c.get("sha", "")
                short_sha = c.get("short_sha", sha[:7] if sha else "")
                subject = c.get("subject", "")[:50]
                # Use stored URL only if it's a valid HTTP URL, otherwise generate from config
                stored_url = c.get("url", "")
                url = stored_url if stored_url.startswith("http") else self.config.get_commit_url(sha)
                if url and url.startswith("http"):
                    commit_links.append(f'<a href="{url}" style="color:{self.COLORS["in_progress"]};text-decoration:none;">{short_sha}</a>: {subject}')
                else:
                    commit_links.append(f"{short_sha}: {subject}")
            html += f'''
                                                    <div style="margin-top:8px;font-size:12px;color:{self.COLORS["muted"]};">
                                                        <strong>Commits:</strong><br>
                                                        {"<br>".join(commit_links)}
                                                    </div>'''

        html += '''
                                                </td>
                                            </tr>
                                        </table>
                                    </td>
                                </tr>
                            </table>'''
        return html

    def _render_footer(self) -> str:
        return f'''
                    <tr>
                        <td style="padding:20px 40px;background:{self.COLORS["bg_alt"]};border-radius:0 0 8px 8px;text-align:center;">
                            <p style="margin:0;font-size:12px;color:{self.COLORS["muted"]};">
                                Generated by WSR Generator | {datetime.now().strftime("%Y-%m-%d %H:%M")}
                            </p>
                        </td>
                    </tr>
                </table>
            </td>
        </tr>
    </table>
</body>
</html>'''

    def render_plain_text(self, audience: str = "standard") -> str:
        """Render plain text version for multipart email."""
        entries = self.data.entries
        date_range = self.format_date_range(self.data.period_start, self.data.period_end)
        stats = self.calculate_stats(entries)
        settings = AUDIENCE_LEVELS.get(audience, AUDIENCE_LEVELS["standard"])

        lines = []
        lines.append(f"WEEKLY STATUS REPORT - {date_range}")
        lines.append("=" * 50)
        lines.append("")
        lines.append(f"Completed: {stats['completed']} | In Progress: {stats['in_progress']} | Blocked: {stats['blocked']} | Work Items: {stats['work_item_count']}")
        lines.append("")
        lines.append("-" * 50)

        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        status_order = {"Completed": 0, "In Progress": 1, "Blocked": 2, "On Hold": 3}
        entries_sorted = sorted(
            entries,
            key=lambda e: (priority_order.get(e.get("priority"), 9), status_order.get(e.get("status"), 9))
        )

        for i, entry in enumerate(entries_sorted, 1):
            status_sym = self.STATUS_CONFIG.get(entry.get("status", ""), {}).get("symbol", "○")
            lines.append(f"\n{i}. {entry.get('title', 'Untitled')[:60]}")
            lines.append(f"   {status_sym} {entry.get('status', 'Unknown')} | {entry.get('priority', 'Medium')} Priority")

            if entry.get("objective") and "objective" in settings.get("include_sections", []):
                lines.append(f"   Objective: {entry['objective'][:100]}...")

            if entry.get("work_items"):
                wi_ids = [str(wi.get("id")) for wi in entry["work_items"][:5]]
                lines.append(f"   Work Items: {', '.join(wi_ids)}")

        lines.append("")
        lines.append("-" * 50)
        lines.append(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")

        return "\n".join(lines)


# =============================================================================
# Teams Renderer - Adaptive Cards
# =============================================================================

class TeamsRenderer:
    """Render WSR reports as Microsoft Teams Adaptive Cards."""

    STATUS_COLORS = {
        "Completed": "good",      # Green
        "In Progress": "accent",  # Blue
        "Blocked": "attention",   # Red
        "On Hold": "default",     # Gray
    }

    def __init__(self, config: WSRConfig, weekly_data: WeeklyData):
        self.config = config
        self.data = weekly_data

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

    def calculate_stats(self, entries: List[Dict]) -> Dict[str, int]:
        """Calculate summary statistics."""
        return {
            "total": len(entries),
            "completed": sum(1 for e in entries if e.get("status") == "Completed"),
            "in_progress": sum(1 for e in entries if e.get("status") == "In Progress"),
            "blocked": sum(1 for e in entries if e.get("status") == "Blocked"),
        }

    def render(self, audience: str = "standard") -> Dict[str, Any]:
        """Render Adaptive Card payload for Teams webhook."""
        entries = self.data.entries
        date_range = self.format_date_range(self.data.period_start, self.data.period_end)
        stats = self.calculate_stats(entries)

        # Sort entries
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        status_order = {"Completed": 0, "In Progress": 1, "Blocked": 2, "On Hold": 3}
        entries_sorted = sorted(
            entries,
            key=lambda e: (priority_order.get(e.get("priority"), 9), status_order.get(e.get("status"), 9))
        )[:5]  # Limit to 5 for Teams card

        card = {
            "type": "message",
            "attachments": [{
                "contentType": "application/vnd.microsoft.card.adaptive",
                "contentUrl": None,
                "content": {
                    "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
                    "type": "AdaptiveCard",
                    "version": "1.4",
                    "body": self._build_card_body(date_range, stats, entries_sorted),
                }
            }]
        }

        return card

    def _build_card_body(self, date_range: str, stats: Dict, entries: List[Dict]) -> List[Dict]:
        """Build the Adaptive Card body."""
        body = []

        # Header
        body.append({
            "type": "TextBlock",
            "text": "Weekly Status Report",
            "weight": "Bolder",
            "size": "Large",
            "wrap": True
        })
        body.append({
            "type": "TextBlock",
            "text": date_range,
            "spacing": "None",
            "isSubtle": True
        })

        # KPI Row
        body.append({
            "type": "ColumnSet",
            "columns": [
                self._kpi_column(str(stats["completed"]), "Completed", "good"),
                self._kpi_column(str(stats["in_progress"]), "In Progress", "accent"),
                self._kpi_column(str(stats["blocked"]), "Blocked", "attention" if stats["blocked"] > 0 else "default"),
            ]
        })

        body.append({"type": "TextBlock", "text": " ", "spacing": "Medium"})

        # Entries
        if entries:
            body.append({
                "type": "TextBlock",
                "text": "Key Items",
                "weight": "Bolder",
                "spacing": "Medium"
            })

            for entry in entries:
                body.append(self._render_entry_fact_set(entry))

        # Footer
        body.append({
            "type": "TextBlock",
            "text": f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}",
            "spacing": "Large",
            "isSubtle": True,
            "size": "Small"
        })

        return body

    def _kpi_column(self, value: str, label: str, color: str) -> Dict:
        """Build a KPI column."""
        return {
            "type": "Column",
            "width": "stretch",
            "items": [
                {
                    "type": "TextBlock",
                    "text": value,
                    "size": "ExtraLarge",
                    "weight": "Bolder",
                    "horizontalAlignment": "Center",
                    "color": color
                },
                {
                    "type": "TextBlock",
                    "text": label,
                    "size": "Small",
                    "horizontalAlignment": "Center",
                    "isSubtle": True,
                    "spacing": "None"
                }
            ]
        }

    def _render_entry_fact_set(self, entry: Dict) -> Dict:
        """Render an entry as a container with facts."""
        status = entry.get("status", "In Progress")
        status_indicator = {"Completed": "●", "In Progress": "◐", "Blocked": "■", "On Hold": "○"}.get(status, "○")
        color = self.STATUS_COLORS.get(status, "default")

        container = {
            "type": "Container",
            "style": color if color != "default" else None,
            "bleed": False,
            "spacing": "Small",
            "items": [
                {
                    "type": "TextBlock",
                    "text": f"{status_indicator} {entry.get('title', 'Untitled')[:50]}",
                    "weight": "Bolder",
                    "wrap": True
                },
                {
                    "type": "FactSet",
                    "facts": [
                        {"title": "Status", "value": status},
                        {"title": "Priority", "value": entry.get("priority", "Medium")},
                    ]
                }
            ]
        }

        # Add work item links (as clickable markdown links)
        if entry.get("work_items"):
            wi_links = []
            for wi in entry["work_items"][:3]:
                wi_id = wi.get("id")
                wi_url = wi.get("url") or self.config.get_work_item_url(wi_id)
                if wi_url:
                    wi_links.append(f"[AB#{wi_id}]({wi_url})")
                else:
                    wi_links.append(f"AB#{wi_id}")
            # Use TextBlock with markdown for links instead of FactSet
            container["items"].append({
                "type": "TextBlock",
                "text": f"**Work Items:** {', '.join(wi_links)}",
                "wrap": True,
                "size": "Small"
            })

        # Add commit links
        if entry.get("commits"):
            commit_links = []
            for c in entry["commits"][:3]:
                sha = c.get("sha", "")
                short_sha = c.get("short_sha", sha[:7])
                subject = c.get("subject", "")[:30]
                commit_url = c.get("url") or self.config.get_commit_url(sha)
                if commit_url:
                    commit_links.append(f"[{short_sha}]({commit_url})")
                else:
                    commit_links.append(short_sha)
            if commit_links:
                container["items"].append({
                    "type": "TextBlock",
                    "text": f"**Commits:** {', '.join(commit_links)}",
                    "wrap": True,
                    "size": "Small"
                })

        return container


# =============================================================================
# Slack Renderer - Block Kit
# =============================================================================

class SlackRenderer:
    """Render WSR reports as Slack Block Kit messages."""

    STATUS_EMOJI = {
        "Completed": ":white_check_mark:",
        "In Progress": ":arrows_counterclockwise:",
        "Blocked": ":no_entry:",
        "On Hold": ":pause_button:",
    }

    def __init__(self, config: WSRConfig, weekly_data: WeeklyData):
        self.config = config
        self.data = weekly_data

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

    def calculate_stats(self, entries: List[Dict]) -> Dict[str, int]:
        """Calculate summary statistics."""
        return {
            "total": len(entries),
            "completed": sum(1 for e in entries if e.get("status") == "Completed"),
            "in_progress": sum(1 for e in entries if e.get("status") == "In Progress"),
            "blocked": sum(1 for e in entries if e.get("status") == "Blocked"),
        }

    def render(self, audience: str = "standard") -> Dict[str, Any]:
        """Render Slack Block Kit payload."""
        entries = self.data.entries
        date_range = self.format_date_range(self.data.period_start, self.data.period_end)
        stats = self.calculate_stats(entries)

        # Sort entries
        priority_order = {"High": 0, "Medium": 1, "Low": 2}
        entries_sorted = sorted(
            entries,
            key=lambda e: priority_order.get(e.get("priority"), 9)
        )[:5]

        blocks = []

        # Header
        blocks.append({
            "type": "header",
            "text": {"type": "plain_text", "text": "Weekly Status Report"}
        })
        blocks.append({
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": f"*{date_range}*"}]
        })
        blocks.append({"type": "divider"})

        # KPIs
        kpi_text = f"*{stats['completed']}* completed  |  *{stats['in_progress']}* in progress  |  *{stats['blocked']}* blocked"
        blocks.append({
            "type": "section",
            "text": {"type": "mrkdwn", "text": kpi_text}
        })
        blocks.append({"type": "divider"})

        # Entries
        for entry in entries_sorted:
            status = entry.get("status", "In Progress")
            emoji = self.STATUS_EMOJI.get(status, ":grey_question:")
            title = entry.get("title", "Untitled")[:50]
            priority = entry.get("priority", "Medium")

            entry_text = f"{emoji} *{title}*\n`{status}` | `{priority} Priority`"

            if entry.get("work_items"):
                wi_ids = [str(wi.get("id")) for wi in entry["work_items"][:3]]
                entry_text += f"\nWork Items: {', '.join(wi_ids)}"

            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": entry_text}
            })

        # Footer
        blocks.append({"type": "divider"})
        blocks.append({
            "type": "context",
            "elements": [{
                "type": "mrkdwn",
                "text": f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}"
            }]
        })

        return {"blocks": blocks}


# =============================================================================
# Notification Senders
# =============================================================================

def send_email(config: WSRConfig, notify_config: NotifyConfig, weekly_data: WeeklyData, audience: str = "standard") -> bool:
    """Send report via email."""
    email_cfg = notify_config.email

    if not email_cfg.get("enabled"):
        print("Email notifications not enabled")
        return False

    if not email_cfg.get("smtp_server") or not email_cfg.get("to_addresses"):
        print("Email not configured. Run: python wsr_notify.py configure email")
        return False

    # Get password - check direct config first, then environment variable
    password = email_cfg.get("password", "")
    if not password:
        password = os.environ.get(email_cfg.get("password_env", "WSR_EMAIL_PASSWORD"), "")
    if not password and email_cfg.get("username"):
        print(f"Warning: No password found in config or ${email_cfg.get('password_env')}")

    # Render email
    renderer = EmailRenderer(config, weekly_data)
    html_content = renderer.render(audience)
    text_content = renderer.render_plain_text(audience)
    date_range = renderer.format_date_range(weekly_data.period_start, weekly_data.period_end)

    # Build message
    msg = MIMEMultipart("alternative")
    msg["Subject"] = email_cfg.get("subject_template", "Weekly Status Report - {date_range}").format(date_range=date_range)
    msg["From"] = email_cfg.get("from_address", "")
    msg["To"] = ", ".join(email_cfg.get("to_addresses", []))
    if email_cfg.get("cc_addresses"):
        msg["Cc"] = ", ".join(email_cfg["cc_addresses"])

    # Attach text and HTML parts
    msg.attach(MIMEText(text_content, "plain"))
    msg.attach(MIMEText(html_content, "html"))

    # Send
    try:
        if email_cfg.get("use_tls", True):
            context = ssl.create_default_context()
            with smtplib.SMTP(email_cfg["smtp_server"], email_cfg.get("smtp_port", 587)) as server:
                server.starttls(context=context)
                if email_cfg.get("username") and password:
                    server.login(email_cfg["username"], password)
                recipients = email_cfg["to_addresses"] + email_cfg.get("cc_addresses", [])
                server.sendmail(email_cfg["from_address"], recipients, msg.as_string())
        else:
            with smtplib.SMTP(email_cfg["smtp_server"], email_cfg.get("smtp_port", 25)) as server:
                if email_cfg.get("username") and password:
                    server.login(email_cfg["username"], password)
                recipients = email_cfg["to_addresses"] + email_cfg.get("cc_addresses", [])
                server.sendmail(email_cfg["from_address"], recipients, msg.as_string())

        print(f"Email sent to: {', '.join(email_cfg['to_addresses'])}")
        return True

    except Exception as e:
        print(f"Failed to send email: {e}")
        return False


def send_teams(config: WSRConfig, notify_config: NotifyConfig, weekly_data: WeeklyData, audience: str = "standard") -> bool:
    """Send report to Microsoft Teams via webhook."""
    teams_cfg = notify_config.teams

    if not teams_cfg.get("enabled"):
        print("Teams notifications not enabled")
        return False

    webhook_url = teams_cfg.get("webhook_url", "")
    if not webhook_url:
        print("Teams webhook URL not configured. Run: python wsr_notify.py configure teams")
        return False

    # Render Adaptive Card
    renderer = TeamsRenderer(config, weekly_data)
    payload = renderer.render(audience)

    # Send webhook
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status in (200, 202):
                print("Teams notification sent successfully")
                return True
            else:
                print(f"Teams webhook returned status {response.status}")
                return False

    except urllib.error.HTTPError as e:
        print(f"Teams webhook error: {e.code} - {e.reason}")
        return False
    except Exception as e:
        print(f"Failed to send Teams notification: {e}")
        return False


def send_slack(config: WSRConfig, notify_config: NotifyConfig, weekly_data: WeeklyData, audience: str = "standard") -> bool:
    """Send report to Slack via webhook."""
    slack_cfg = notify_config.slack

    if not slack_cfg.get("enabled"):
        print("Slack notifications not enabled")
        return False

    webhook_url = slack_cfg.get("webhook_url", "")
    if not webhook_url:
        print("Slack webhook URL not configured. Run: python wsr_notify.py configure slack")
        return False

    # Render Block Kit
    renderer = SlackRenderer(config, weekly_data)
    payload = renderer.render(audience)

    if slack_cfg.get("channel"):
        payload["channel"] = slack_cfg["channel"]

    # Send webhook
    try:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            webhook_url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status == 200:
                print("Slack notification sent successfully")
                return True
            else:
                print(f"Slack webhook returned status {response.status}")
                return False

    except urllib.error.HTTPError as e:
        print(f"Slack webhook error: {e.code} - {e.reason}")
        return False
    except Exception as e:
        print(f"Failed to send Slack notification: {e}")
        return False


# =============================================================================
# Email CLI Integration (Rich HTML via wsr-email-cli)
# =============================================================================

def transform_weekly_data_to_cli_format(weekly_data: WeeklyData, wsr_config: WSRConfig, cli_cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Transform WeeklyData to the JSON format expected by wsr-email-cli."""
    entries = weekly_data.entries

    # Calculate summary stats
    summary = {
        "completed": sum(1 for e in entries if e.get("status") == "Completed"),
        "inProgress": sum(1 for e in entries if e.get("status") == "In Progress"),
        "blocked": sum(1 for e in entries if e.get("status") == "Blocked"),
        "onHold": sum(1 for e in entries if e.get("status") == "On Hold"),
        "totalWorkItems": 0,
        "totalCommits": 0,
        "linesAdded": 0,
        "linesRemoved": 0,
    }

    transformed_entries = []
    for i, entry in enumerate(entries, 1):
        # Count totals
        summary["totalCommits"] += len(entry.get("commits", []))
        summary["linesAdded"] += entry.get("total_insertions", 0)
        summary["linesRemoved"] += entry.get("total_deletions", 0)

        work_items = entry.get("work_items", [])
        summary["totalWorkItems"] += len(work_items)

        transformed_entries.append({
            "index": i,
            "title": entry.get("title", ""),
            "status": entry.get("status", "In Progress"),
            "priority": entry.get("priority", "Medium"),
            "domain": entry.get("domain", ""),
            "timeline": "",  # Could compute from timeline_start/end
            "objective": entry.get("objective", ""),
            "solution": entry.get("solution", ""),
            "businessImpact": entry.get("business_impact", ""),
            "technicalImpact": entry.get("technical_impact", ""),
            "nextSteps": entry.get("next_steps", ""),
            "codeStats": {
                "filesChanged": entry.get("total_files_changed", 0),
                "insertions": entry.get("total_insertions", 0),
                "deletions": entry.get("total_deletions", 0),
            },
            "workItems": [
                {
                    "id": wi.get("id"),
                    "type": wi.get("type", "Item"),
                    "title": wi.get("title", ""),
                    "url": wi.get("url") or wsr_config.get_work_item_url(wi.get("id")),
                }
                for wi in work_items
            ],
            "commits": [
                {
                    "sha": c.get("sha", ""),
                    "shortSha": c.get("short_sha", c.get("sha", "")[:7]),
                    "subject": c.get("subject", ""),
                    "url": c.get("url") or wsr_config.get_commit_url(c.get("sha", "")),
                }
                for c in entry.get("commits", [])
            ],
        })

    # Extract blockers
    blockers = [
        {
            "title": e.get("title", ""),
            "dependency": "",
            "impact": e.get("next_steps", ""),
            "workItemId": e.get("work_items", [{}])[0].get("id") if e.get("work_items") else None,
            "workItemUrl": e.get("work_items", [{}])[0].get("url") if e.get("work_items") else None,
        }
        for e in entries if e.get("status") == "Blocked"
    ]

    # Build branding from config
    branding_cfg = cli_cfg.get("branding", {})
    branding = {
        "companyName": branding_cfg.get("companyName", ""),
        "productName": branding_cfg.get("productName", ""),
        "primaryColor": branding_cfg.get("primaryColor", "#007bff"),
        "accentColor": branding_cfg.get("accentColor", "#28a745"),
        "supportEmail": branding_cfg.get("supportEmail", ""),
        "websiteUrl": branding_cfg.get("websiteUrl", ""),
        "copyrightYear": datetime.now().year,
    }

    # Format date range
    date_range = ""
    try:
        start = datetime.fromisoformat(weekly_data.period_start)
        end = datetime.fromisoformat(weekly_data.period_end)
        if start.month == end.month:
            date_range = f"{start.strftime('%B')} {start.day}-{end.day}, {end.year}"
        else:
            date_range = f"{start.strftime('%B %d')} - {end.strftime('%B %d, %Y')}"
    except:
        date_range = f"{weekly_data.period_start} - {weekly_data.period_end}"

    return {
        "template": cli_cfg.get("template", "wsr-report"),
        "language": "en",
        "branding": branding,
        "data": {
            "reportTitle": "Weekly Status Report",
            "dateRange": date_range,
            "weekId": weekly_data.week_id,
            "author": {
                "name": "",
                "email": wsr_config.author_email or "",
                "team": "",
            },
            "summary": summary,
            "highlights": [],  # Could extract from high-priority completed items
            "entries": transformed_entries,
            "blockers": blockers,
            "upcomingWork": [],
            "notes": weekly_data.notes or "",
        },
    }


def send_email_cli(config: WSRConfig, notify_config: NotifyConfig, weekly_data: WeeklyData, audience: str = "standard") -> bool:
    """Send report via wsr-email-cli (rich HTML email)."""
    cli_cfg = notify_config.email_cli

    if not cli_cfg.get("enabled"):
        print("Email CLI notifications not enabled")
        return False

    cli_path = cli_cfg.get("cli_path", "wsr-email-cli")

    # Check if CLI is available
    if not shutil.which(cli_path):
        print(f"wsr-email-cli not found at '{cli_path}'")
        print("Install it or update the cli_path in .wsr/notify.json")
        return False

    to_addresses = cli_cfg.get("to_addresses", [])
    if not to_addresses:
        print("No recipients configured. Run: python wsr_notify.py configure email-cli")
        return False

    # Transform data to CLI format
    cli_data = transform_weekly_data_to_cli_format(weekly_data, config, cli_cfg)

    # Use executive template for executive audience
    if audience == "executive":
        cli_data["template"] = "wsr-executive"

    # Build subject
    date_range = cli_data["data"]["dateRange"]
    subject = cli_cfg.get("subject_template", "Weekly Status Report - {date_range}").format(date_range=date_range)

    # Build command
    cmd = [
        cli_path, "send",
        "--template", cli_data["template"],
        "--data", "-",  # Read from stdin
        "--to", ",".join(to_addresses),
        "--subject", subject,
    ]

    cc_addresses = cli_cfg.get("cc_addresses", [])
    if cc_addresses:
        cmd.extend(["--cc", ",".join(cc_addresses)])

    # Execute
    try:
        result = subprocess.run(
            cmd,
            input=json.dumps(cli_data),
            capture_output=True,
            text=True,
            timeout=60
        )

        # Parse response
        if result.stdout:
            try:
                response = json.loads(result.stdout)
                if response.get("success"):
                    print(f"Rich HTML email sent via wsr-email-cli to: {', '.join(to_addresses)}")
                    if response.get("messageId"):
                        print(f"  Message ID: {response['messageId']}")
                    return True
                else:
                    error = response.get("error", {})
                    print(f"Email CLI error: {error.get('code', 'UNKNOWN')} - {error.get('message', 'Unknown error')}")
                    return False
            except json.JSONDecodeError:
                print(f"CLI output: {result.stdout}")

        if result.returncode != 0:
            print(f"wsr-email-cli failed with exit code {result.returncode}")
            if result.stderr:
                print(f"  Error: {result.stderr}")
            return False

        return True

    except subprocess.TimeoutExpired:
        print("wsr-email-cli timed out after 60 seconds")
        return False
    except FileNotFoundError:
        print(f"wsr-email-cli not found: {cli_path}")
        return False
    except Exception as e:
        print(f"Failed to run wsr-email-cli: {e}")
        return False


def render_email_cli_preview(config: WSRConfig, notify_config: NotifyConfig, weekly_data: WeeklyData, audience: str = "standard") -> Optional[str]:
    """Render email HTML preview via wsr-email-cli (without sending)."""
    cli_cfg = notify_config.email_cli
    cli_path = cli_cfg.get("cli_path", "wsr-email-cli")

    if not shutil.which(cli_path):
        print(f"wsr-email-cli not found at '{cli_path}'")
        return None

    # Transform data
    cli_data = transform_weekly_data_to_cli_format(weekly_data, config, cli_cfg)
    if audience == "executive":
        cli_data["template"] = "wsr-executive"

    # Build command for render
    cmd = [
        cli_path, "render",
        "--template", cli_data["template"],
        "--data", "-",
        "--output", "-",
    ]

    try:
        result = subprocess.run(
            cmd,
            input=json.dumps(cli_data),
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode == 0 and result.stdout:
            response = json.loads(result.stdout)
            return response.get("html", "")
        else:
            print(f"Render failed: {result.stderr}")
            return None

    except Exception as e:
        print(f"Failed to render: {e}")
        return None


# =============================================================================
# Report Saving
# =============================================================================

def save_report_to_disk(config: WSRConfig, weekly_data: WeeklyData, audience: str = "standard") -> Dict[str, str]:
    """
    Save report to .wsr/reports directory in multiple formats.

    Returns dict with paths to saved files:
    {
        "html": ".wsr/reports/2025-W50-standard.html",
        "txt": ".wsr/reports/2025-W50-standard.txt",
        "json": ".wsr/reports/2025-W50-standard.json"
    }
    """
    reports_dir = Path(config.output_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    week_id = weekly_data.week_id
    timestamp = datetime.now().strftime("%Y%m%d-%H%M")
    base_name = f"{week_id}-{audience}-{timestamp}"

    saved_files = {}

    # Render HTML
    renderer = EmailRenderer(config, weekly_data)
    html_content = renderer.render(audience)
    html_path = reports_dir / f"{base_name}.html"
    html_path.write_text(html_content, encoding="utf-8")
    saved_files["html"] = str(html_path)

    # Render plain text
    txt_content = renderer.render_plain_text(audience)
    txt_path = reports_dir / f"{base_name}.txt"
    txt_path.write_text(txt_content, encoding="utf-8")
    saved_files["txt"] = str(txt_path)

    # Save JSON data (for reference/debugging)
    json_data = {
        "week_id": week_id,
        "period_start": weekly_data.period_start,
        "period_end": weekly_data.period_end,
        "audience": audience,
        "generated_at": datetime.now().isoformat(),
        "entries": weekly_data.entries,
    }
    json_path = reports_dir / f"{base_name}.json"
    json_path.write_text(json.dumps(json_data, indent=2, default=str), encoding="utf-8")
    saved_files["json"] = str(json_path)

    # Also create/update a "latest" symlink-style copy
    latest_html = reports_dir / f"latest-{audience}.html"
    latest_txt = reports_dir / f"latest-{audience}.txt"
    latest_html.write_text(html_content, encoding="utf-8")
    latest_txt.write_text(txt_content, encoding="utf-8")

    return saved_files


# =============================================================================
# CLI
# =============================================================================

def configure_channel(channel: str, notify_config: NotifyConfig, config_path: str):
    """Interactive configuration for a notification channel."""
    print(f"\nConfiguring {channel} notifications...\n")

    if channel == "email":
        cfg = notify_config.email
        cfg["enabled"] = True
        cfg["smtp_server"] = input(f"SMTP server [{cfg.get('smtp_server', 'smtp.office365.com')}]: ").strip() or cfg.get("smtp_server", "smtp.office365.com")
        cfg["smtp_port"] = int(input(f"SMTP port [{cfg.get('smtp_port', 587)}]: ").strip() or cfg.get("smtp_port", 587))
        cfg["use_tls"] = input(f"Use TLS? (y/n) [{('y' if cfg.get('use_tls', True) else 'n')}]: ").strip().lower() != "n"
        cfg["username"] = input(f"Username/email [{cfg.get('username', '')}]: ").strip() or cfg.get("username", "")
        cfg["from_address"] = input(f"From address [{cfg.get('from_address', cfg.get('username', ''))}]: ").strip() or cfg.get("from_address", cfg.get("username", ""))

        to_input = input(f"To addresses (comma-separated) [{','.join(cfg.get('to_addresses', []))}]: ").strip()
        if to_input:
            cfg["to_addresses"] = [a.strip() for a in to_input.split(",")]

        print(f"\nNote: Set password in environment variable ${cfg.get('password_env', 'WSR_EMAIL_PASSWORD')}")

    elif channel == "teams":
        cfg = notify_config.teams
        cfg["enabled"] = True
        cfg["webhook_url"] = input(f"Teams webhook URL [{cfg.get('webhook_url', '')}]: ").strip() or cfg.get("webhook_url", "")

        if not cfg["webhook_url"]:
            print("\nTo get a webhook URL:")
            print("1. In Teams, go to the channel you want to post to")
            print("2. Click ... > Connectors > Incoming Webhook")
            print("3. Configure and copy the webhook URL")

    elif channel == "slack":
        cfg = notify_config.slack
        cfg["enabled"] = True
        cfg["webhook_url"] = input(f"Slack webhook URL [{cfg.get('webhook_url', '')}]: ").strip() or cfg.get("webhook_url", "")
        cfg["channel"] = input(f"Channel override (optional) [{cfg.get('channel', '')}]: ").strip() or cfg.get("channel", "")

        if not cfg["webhook_url"]:
            print("\nTo get a webhook URL:")
            print("1. Go to https://api.slack.com/apps")
            print("2. Create/select an app > Incoming Webhooks")
            print("3. Add webhook to a channel and copy the URL")

    elif channel == "email-cli":
        cfg = notify_config.email_cli
        cfg["enabled"] = True

        # CLI path
        default_cli = shutil.which("wsr-email-cli") or "wsr-email-cli"
        cfg["cli_path"] = input(f"Path to wsr-email-cli [{cfg.get('cli_path', default_cli)}]: ").strip() or cfg.get("cli_path", default_cli)

        # Recipients
        to_input = input(f"To addresses (comma-separated) [{','.join(cfg.get('to_addresses', []))}]: ").strip()
        if to_input:
            cfg["to_addresses"] = [a.strip() for a in to_input.split(",")]

        # Branding
        print("\nBranding settings (press Enter to skip):")
        branding = cfg.get("branding", {})
        branding["companyName"] = input(f"  Company name [{branding.get('companyName', '')}]: ").strip() or branding.get("companyName", "")
        branding["productName"] = input(f"  Product name [{branding.get('productName', '')}]: ").strip() or branding.get("productName", "")
        branding["supportEmail"] = input(f"  Support email [{branding.get('supportEmail', '')}]: ").strip() or branding.get("supportEmail", "")
        branding["websiteUrl"] = input(f"  Website URL [{branding.get('websiteUrl', '')}]: ").strip() or branding.get("websiteUrl", "")
        cfg["branding"] = branding

        print("\nNote: wsr-email-cli uses its own SMTP configuration.")
        print("Run 'wsr-email-cli config init' to configure SMTP settings.")
        print("Set WSR_EMAIL_PASSWORD environment variable for the SMTP password.")

    notify_config.save(config_path)
    print(f"\nConfiguration saved to {config_path}")


def main():
    parser = argparse.ArgumentParser(description="Send WSR reports via various channels")
    parser.add_argument("--config", "-c", default=".wsr/config.json", help="WSR config file")
    parser.add_argument("--notify-config", "-n", default=".wsr/notify.json", help="Notification config file")
    parser.add_argument("--week", "-w", help="Week ID (YYYY-WNN)")

    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # send command
    send_parser = subparsers.add_parser("send", help="Send notifications")
    send_parser.add_argument("--channel", "-ch",
                             choices=["email", "email-cli", "teams", "slack", "all"],
                             help="Channel to send to (default: from config)")
    send_parser.add_argument("--audience", "-a", default="standard",
                             choices=["executive", "standard", "technical"],
                             help="Audience level")

    # configure command
    config_parser = subparsers.add_parser("configure", help="Configure a channel")
    config_parser.add_argument("channel", choices=["email", "email-cli", "teams", "slack"],
                               help="Channel to configure")

    # test command
    test_parser = subparsers.add_parser("test", help="Test a channel (sends test message)")
    test_parser.add_argument("channel", choices=["email", "email-cli", "teams", "slack"],
                             help="Channel to test")

    # show command
    show_parser = subparsers.add_parser("show", help="Show current configuration")

    args = parser.parse_args()

    # Load configs
    try:
        wsr_config = WSRConfig.load(args.config)
    except FileNotFoundError:
        print("WSR not configured. Run: python wsr_config.py init")
        return 1

    notify_config = NotifyConfig.load(args.notify_config)

    if args.command == "send":
        week_id = args.week or get_week_id()
        weekly_data = WeeklyData.load(wsr_config.data_dir, week_id)

        if not weekly_data.entries:
            print(f"No entries for week {week_id}. Run: python wsr_entries.py gather --since Monday")
            return 1

        # Always save report to disk first
        saved_files = save_report_to_disk(wsr_config, weekly_data, args.audience)
        print(f"\nReport saved to:")
        print(f"  HTML: {saved_files['html']}")
        print(f"  Text: {saved_files['txt']}")
        print(f"  JSON: {saved_files['json']}")
        print(f"\nLatest copies:")
        print(f"  {wsr_config.output_dir}/latest-{args.audience}.html")
        print(f"  {wsr_config.output_dir}/latest-{args.audience}.txt")
        print()

        # Use default channel if not specified
        channel = args.channel or notify_config.default_channel
        if not channel:
            print("No channel specified and no default_channel configured.")
            print("Reports saved to disk. Use --channel to also send notification.")
            return 0  # Success - reports are saved even without sending

        success = True
        channels = ["email", "email-cli", "teams", "slack"] if channel == "all" else [channel]

        for channel in channels:
            if channel == "email":
                success = send_email(wsr_config, notify_config, weekly_data, args.audience) and success
            elif channel == "email-cli":
                success = send_email_cli(wsr_config, notify_config, weekly_data, args.audience) and success
            elif channel == "teams":
                success = send_teams(wsr_config, notify_config, weekly_data, args.audience) and success
            elif channel == "slack":
                success = send_slack(wsr_config, notify_config, weekly_data, args.audience) and success

        return 0 if success else 1

    elif args.command == "configure":
        configure_channel(args.channel, notify_config, args.notify_config)

    elif args.command == "test":
        print(f"Testing {args.channel} channel...")
        # Create minimal test data
        test_data = WeeklyData(
            week_id=get_week_id(),
            period_start=datetime.now().isoformat()[:10],
            period_end=datetime.now().isoformat()[:10],
            entries=[{
                "id": "test-1",
                "title": "Test Entry - WSR Notification Test",
                "status": "Completed",
                "priority": "Medium",
                "domain": "Testing",
                "work_items": [],
                "commits": [],
            }],
        )

        if args.channel == "email":
            send_email(wsr_config, notify_config, test_data)
        elif args.channel == "email-cli":
            send_email_cli(wsr_config, notify_config, test_data)
        elif args.channel == "teams":
            send_teams(wsr_config, notify_config, test_data)
        elif args.channel == "slack":
            send_slack(wsr_config, notify_config, test_data)

    elif args.command == "show":
        print("\nNotification Configuration:")
        print("-" * 40)
        print(f"\nDefault Channel: {notify_config.default_channel}")
        for channel in ["email", "email_cli", "teams", "slack"]:
            cfg = getattr(notify_config, channel)
            enabled = "Enabled" if cfg.get("enabled") else "Disabled"
            display_name = "EMAIL-CLI" if channel == "email_cli" else channel.upper()
            print(f"\n{display_name}: {enabled}")
            if channel == "email" and cfg.get("enabled"):
                print(f"  Server: {cfg.get('smtp_server')}:{cfg.get('smtp_port')}")
                print(f"  From: {cfg.get('from_address')}")
                print(f"  To: {', '.join(cfg.get('to_addresses', []))}")
            elif channel == "email_cli" and cfg.get("enabled"):
                print(f"  CLI: {cfg.get('cli_path', 'wsr-email-cli')}")
                print(f"  Template: {cfg.get('template', 'wsr-report')}")
                print(f"  To: {', '.join(cfg.get('to_addresses', []))}")
                branding = cfg.get("branding", {})
                if branding.get("companyName"):
                    print(f"  Company: {branding['companyName']}")
            elif channel == "teams" and cfg.get("enabled"):
                url = cfg.get("webhook_url", "")
                print(f"  Webhook: {url[:50]}..." if len(url) > 50 else f"  Webhook: {url}")
            elif channel == "slack" and cfg.get("enabled"):
                url = cfg.get("webhook_url", "")
                print(f"  Webhook: {url[:50]}..." if len(url) > 50 else f"  Webhook: {url}")

    else:
        parser.print_help()
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())

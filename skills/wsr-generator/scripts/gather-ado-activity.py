#!/usr/bin/env python3
"""
gather-ado-activity.py - Extract Azure DevOps activity for WSR generation.

Usage:
    python gather-ado-activity.py --config .ado/config.json --since "7 days ago"
"""

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional


def parse_relative_date(date_str: str) -> datetime:
    date_str = date_str.lower().strip()
    match = re.match(r'(\d+)\s*(day|week|month)s?\s*ago', date_str)
    if match:
        amount, unit = int(match.group(1)), match.group(2)
        delta = {"day": timedelta(days=amount), "week": timedelta(weeks=amount), "month": timedelta(days=amount * 30)}
        return datetime.now() - delta[unit]
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        return datetime.strptime(date_str, '%Y-%m-%d')


def run_az_command(args: list) -> Optional[dict]:
    try:
        result = subprocess.run(["az"] + args + ["--output", "json"], capture_output=True, text=True, timeout=60)
        return json.loads(result.stdout) if result.returncode == 0 and result.stdout.strip() else None
    except Exception:
        return None


def query_work_items(org: str, project: str, wiql: str) -> list[dict]:
    result = run_az_command(["boards", "query", "--org", org, "--project", project, "--wiql", " ".join(wiql.split())])
    if not result:
        return []
    
    items = []
    for item in result:
        if "id" in item:
            details = run_az_command(["boards", "work-item", "show", "--org", org, "--id", str(item["id"]), "--expand", "relations"])
            if details:
                fields = details.get("fields", {})
                assigned = fields.get("System.AssignedTo")
                items.append({
                    "id": item["id"], "title": fields.get("System.Title"), "type": fields.get("System.WorkItemType"),
                    "state": fields.get("System.State"), "area_path": fields.get("System.AreaPath"),
                    "assigned_to": assigned.get("displayName") if isinstance(assigned, dict) else assigned,
                    "priority": fields.get("Microsoft.VSTS.Common.Priority"), "tags": fields.get("System.Tags", "").split(";") if fields.get("System.Tags") else [],
                    "changed_date": fields.get("System.ChangedDate"), "closed_date": fields.get("Microsoft.VSTS.Common.ClosedDate")
                })
    return items


def get_pipeline_runs(org: str, project: str, since: datetime, until: datetime) -> list[dict]:
    pipelines = run_az_command(["pipelines", "list", "--org", org, "--project", project])
    if not pipelines:
        return []
    
    runs = []
    for pipeline in pipelines[:10]:
        pipeline_runs = run_az_command(["pipelines", "runs", "list", "--org", org, "--project", project, "--pipeline-ids", str(pipeline.get("id"))])
        for run in (pipeline_runs or []):
            try:
                run_time = datetime.fromisoformat(run.get("createdDate", "").replace("Z", "+00:00")).replace(tzinfo=None)
                if since.replace(tzinfo=None) <= run_time <= until.replace(tzinfo=None):
                    runs.append({
                        "pipeline_name": pipeline.get("name"), "run_id": run.get("id"),
                        "status": run.get("status"), "result": run.get("result"),
                        "start_time": run.get("createdDate"), "source_branch": run.get("sourceBranch")
                    })
            except (ValueError, TypeError):
                continue
    return runs


def main():
    parser = argparse.ArgumentParser(description="Gather Azure DevOps activity for WSR.")
    parser.add_argument("--config", "-c", required=True, help="Path to .ado/config.json")
    parser.add_argument("--since", "-s", required=True, help="Start of time range")
    parser.add_argument("--until", "-u", help="End of time range")
    parser.add_argument("--output", "-o", help="Output file")
    args = parser.parse_args()
    
    config = json.loads(Path(args.config).read_text())
    org, project = config["organization"], config["project"]
    since_dt = parse_relative_date(args.since)
    until_dt = parse_relative_date(args.until) if args.until else datetime.now()
    
    print(f"Gathering ADO activity from {since_dt.date()} to {until_dt.date()}...", file=sys.stderr)
    
    since_str, until_str = since_dt.strftime("%Y-%m-%d"), until_dt.strftime("%Y-%m-%d")
    
    changed = query_work_items(org, project, f"SELECT [System.Id] FROM workitems WHERE [System.ChangedDate] >= '{since_str}' AND [System.ChangedDate] <= '{until_str}' AND [System.AssignedTo] = @Me")
    completed = query_work_items(org, project, f"SELECT [System.Id] FROM workitems WHERE [Microsoft.VSTS.Common.ClosedDate] >= '{since_str}' AND [Microsoft.VSTS.Common.ClosedDate] <= '{until_str}' AND [System.AssignedTo] = @Me")
    pipeline_runs = get_pipeline_runs(org, project, since_dt, until_dt)
    
    # Pipeline summary
    success_count = sum(1 for r in pipeline_runs if r.get("result") == "succeeded")
    pipeline_summary = {"total_runs": len(pipeline_runs), "success_rate": round(success_count / len(pipeline_runs) * 100, 1) if pipeline_runs else 0}
    
    activity = {
        "organization": org, "project": project, "period_start": since_str, "period_end": until_str,
        "work_items_changed": changed, "work_items_completed": completed, "pipeline_runs": pipeline_runs, "pipeline_summary": pipeline_summary
    }
    
    output = json.dumps(activity, indent=2, default=str)
    if args.output:
        Path(args.output).write_text(output)
        print(f"Activity written to {args.output}", file=sys.stderr)
    else:
        print(output)
    
    print(f"\nSummary: {len(changed)} changed, {len(completed)} completed, {len(pipeline_runs)} pipeline runs ({pipeline_summary['success_rate']}% success)", file=sys.stderr)


if __name__ == "__main__":
    main()

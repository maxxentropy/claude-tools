#!/usr/bin/env python3
"""
gather-ado-activity.py - Extract Azure DevOps activity for WSR generation.

Gathers work items changed/completed and pipeline runs from Azure DevOps.
Requires the azure-devops skill to be configured (.ado/config.json).

Usage:
    python gather-ado-activity.py --config .ado/config.json --since "7 days ago"
    python gather-ado-activity.py --config .ado/config.json --since "2024-01-01" --until "2024-01-15"
"""

import argparse
import json
import os
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import re


@dataclass
class WorkItem:
    """An Azure DevOps work item."""
    id: int
    title: str
    type: str
    state: str
    area_path: str
    iteration_path: str
    assigned_to: Optional[str]
    priority: Optional[int]
    parent_id: Optional[int]
    tags: list = field(default_factory=list)
    changed_date: Optional[str] = None
    created_date: Optional[str] = None
    closed_date: Optional[str] = None


@dataclass
class PipelineRun:
    """A pipeline run summary."""
    pipeline_id: int
    pipeline_name: str
    run_id: int
    status: str
    result: str
    start_time: str
    finish_time: Optional[str]
    source_branch: str


@dataclass 
class AdoActivity:
    """Summary of Azure DevOps activity."""
    organization: str
    project: str
    period_start: str
    period_end: str
    work_items_changed: list = field(default_factory=list)
    work_items_completed: list = field(default_factory=list)
    work_items_created: list = field(default_factory=list)
    pipeline_runs: list = field(default_factory=list)
    pipeline_summary: dict = field(default_factory=dict)
    work_item_hierarchy: dict = field(default_factory=dict)


def parse_relative_date(date_str: str) -> datetime:
    """Parse relative date strings like '7 days ago'."""
    date_str = date_str.lower().strip()
    
    # Check for relative patterns
    match = re.match(r'(\d+)\s*(day|week|month)s?\s*ago', date_str)
    if match:
        amount = int(match.group(1))
        unit = match.group(2)
        
        if unit == 'day':
            return datetime.now() - timedelta(days=amount)
        elif unit == 'week':
            return datetime.now() - timedelta(weeks=amount)
        elif unit == 'month':
            return datetime.now() - timedelta(days=amount * 30)
    
    # Try ISO format
    try:
        return datetime.fromisoformat(date_str.replace('Z', '+00:00'))
    except ValueError:
        pass
    
    # Try simple date format
    try:
        return datetime.strptime(date_str, '%Y-%m-%d')
    except ValueError:
        pass
    
    raise ValueError(f"Cannot parse date: {date_str}")


def run_az_command(args: list) -> Optional[dict]:
    """Run an az devops command and return JSON output."""
    cmd = ["az"] + args + ["--output", "json"]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"Warning: az command failed: {' '.join(args[:3])}...", file=sys.stderr)
            if result.stderr:
                print(f"  Error: {result.stderr[:200]}", file=sys.stderr)
            return None
        
        if result.stdout.strip():
            return json.loads(result.stdout)
        return None
        
    except subprocess.TimeoutExpired:
        print(f"Warning: az command timed out", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: az error: {e}", file=sys.stderr)
        return None


def load_config(config_path: str) -> dict:
    """Load ADO configuration from file."""
    path = Path(config_path)
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {config_path}")
    
    with open(path) as f:
        return json.load(f)


def get_current_user_email() -> Optional[str]:
    """Get the current Azure CLI user's email."""
    result = run_az_command(["account", "show"])
    if result and "user" in result:
        return result["user"].get("name")
    return None


def query_work_items(org: str, project: str, wiql: str) -> list[dict]:
    """Execute a WIQL query and return work items."""
    # Run the query
    result = run_az_command([
        "boards", "query",
        "--org", org,
        "--project", project,
        "--wiql", wiql
    ])
    
    if not result:
        return []
    
    # The query returns IDs, we need to fetch details
    work_item_ids = [item["id"] for item in result]
    
    if not work_item_ids:
        return []
    
    # Fetch work item details in batches
    all_items = []
    batch_size = 50
    
    for i in range(0, len(work_item_ids), batch_size):
        batch_ids = work_item_ids[i:i + batch_size]
        ids_str = ",".join(str(id) for id in batch_ids)
        
        items = run_az_command([
            "boards", "work-item", "show",
            "--org", org,
            "--ids", ids_str,
            "--expand", "relations"
        ])
        
        if items:
            if isinstance(items, list):
                all_items.extend(items)
            else:
                all_items.append(items)
    
    return all_items


def parse_work_item(item: dict) -> WorkItem:
    """Parse a work item from ADO API response."""
    fields = item.get("fields", {})
    
    # Extract parent ID from relations
    parent_id = None
    relations = item.get("relations", [])
    for rel in relations:
        if rel.get("rel") == "System.LinkTypes.Hierarchy-Reverse":
            # Parent link
            url = rel.get("url", "")
            # URL format: https://dev.azure.com/org/project/_apis/wit/workItems/123
            match = re.search(r'/workItems/(\d+)$', url)
            if match:
                parent_id = int(match.group(1))
                break
    
    # Parse tags
    tags_str = fields.get("System.Tags", "")
    tags = [t.strip() for t in tags_str.split(";")] if tags_str else []
    
    # Get assigned to
    assigned_to = None
    if "System.AssignedTo" in fields:
        assigned = fields["System.AssignedTo"]
        if isinstance(assigned, dict):
            assigned_to = assigned.get("displayName") or assigned.get("uniqueName")
        else:
            assigned_to = str(assigned)
    
    return WorkItem(
        id=item.get("id"),
        title=fields.get("System.Title", ""),
        type=fields.get("System.WorkItemType", ""),
        state=fields.get("System.State", ""),
        area_path=fields.get("System.AreaPath", ""),
        iteration_path=fields.get("System.IterationPath", ""),
        assigned_to=assigned_to,
        priority=fields.get("Microsoft.VSTS.Common.Priority"),
        parent_id=parent_id,
        tags=tags,
        changed_date=fields.get("System.ChangedDate"),
        created_date=fields.get("System.CreatedDate"),
        closed_date=fields.get("Microsoft.VSTS.Common.ClosedDate")
    )


def get_changed_work_items(org: str, project: str, since: datetime, until: datetime) -> list[WorkItem]:
    """Get work items changed in the date range."""
    since_str = since.strftime("%Y-%m-%d")
    until_str = until.strftime("%Y-%m-%d")
    
    wiql = f"""
    SELECT [System.Id]
    FROM WorkItems
    WHERE [System.TeamProject] = '{project}'
      AND [System.ChangedDate] >= '{since_str}'
      AND [System.ChangedDate] <= '{until_str}'
      AND [System.AssignedTo] = @Me
    ORDER BY [System.ChangedDate] DESC
    """
    
    items = query_work_items(org, project, wiql)
    return [parse_work_item(item) for item in items]


def get_completed_work_items(org: str, project: str, since: datetime, until: datetime) -> list[WorkItem]:
    """Get work items completed/closed in the date range."""
    since_str = since.strftime("%Y-%m-%d")
    until_str = until.strftime("%Y-%m-%d")
    
    wiql = f"""
    SELECT [System.Id]
    FROM WorkItems
    WHERE [System.TeamProject] = '{project}'
      AND [Microsoft.VSTS.Common.ClosedDate] >= '{since_str}'
      AND [Microsoft.VSTS.Common.ClosedDate] <= '{until_str}'
      AND [System.AssignedTo] = @Me
    ORDER BY [Microsoft.VSTS.Common.ClosedDate] DESC
    """
    
    items = query_work_items(org, project, wiql)
    return [parse_work_item(item) for item in items]


def get_created_work_items(org: str, project: str, since: datetime, until: datetime) -> list[WorkItem]:
    """Get work items created in the date range."""
    since_str = since.strftime("%Y-%m-%d")
    until_str = until.strftime("%Y-%m-%d")
    
    wiql = f"""
    SELECT [System.Id]
    FROM WorkItems
    WHERE [System.TeamProject] = '{project}'
      AND [System.CreatedDate] >= '{since_str}'
      AND [System.CreatedDate] <= '{until_str}'
      AND [System.CreatedBy] = @Me
    ORDER BY [System.CreatedDate] DESC
    """
    
    items = query_work_items(org, project, wiql)
    return [parse_work_item(item) for item in items]


def get_pipeline_runs(org: str, project: str, since: datetime, until: datetime) -> list[PipelineRun]:
    """Get pipeline runs in the date range."""
    # List pipelines first
    pipelines = run_az_command([
        "pipelines", "list",
        "--org", org,
        "--project", project
    ])
    
    if not pipelines:
        return []
    
    all_runs = []
    
    for pipeline in pipelines[:10]:  # Limit to first 10 pipelines
        pipeline_id = pipeline.get("id")
        pipeline_name = pipeline.get("name", "Unknown")
        
        # Get runs for this pipeline
        runs = run_az_command([
            "pipelines", "runs", "list",
            "--org", org,
            "--project", project,
            "--pipeline-ids", str(pipeline_id)
        ])
        
        if not runs:
            continue
        
        for run in runs:
            # Parse the run time
            created_date = run.get("createdDate", "")
            if created_date:
                try:
                    run_time = datetime.fromisoformat(created_date.replace("Z", "+00:00"))
                    # Make since/until timezone-aware for comparison
                    if run_time.tzinfo is None:
                        run_time = run_time.replace(tzinfo=None)
                    since_naive = since.replace(tzinfo=None) if since.tzinfo else since
                    until_naive = until.replace(tzinfo=None) if until.tzinfo else until
                    
                    if not (since_naive <= run_time.replace(tzinfo=None) <= until_naive):
                        continue
                except (ValueError, TypeError):
                    continue
            
            pipeline_run = PipelineRun(
                pipeline_id=pipeline_id,
                pipeline_name=pipeline_name,
                run_id=run.get("id"),
                status=run.get("status", ""),
                result=run.get("result", ""),
                start_time=run.get("createdDate", ""),
                finish_time=run.get("finishedDate"),
                source_branch=run.get("sourceBranch", "")
            )
            all_runs.append(pipeline_run)
    
    return all_runs


def build_work_item_hierarchy(work_items: list[WorkItem]) -> dict:
    """Build a hierarchy of work items (Tasks -> Stories -> Features -> Epics)."""
    items_by_id = {wi.id: wi for wi in work_items}
    
    hierarchy = {
        "epics": {},
        "features": {},
        "stories": {},
        "tasks": {},
        "bugs": {},
        "other": {}
    }
    
    # Categorize items
    for wi in work_items:
        wi_dict = asdict(wi)
        wi_type = wi.type.lower()
        
        if "epic" in wi_type:
            hierarchy["epics"][wi.id] = wi_dict
        elif "feature" in wi_type:
            hierarchy["features"][wi.id] = wi_dict
        elif "story" in wi_type or "user story" in wi_type or "product backlog item" in wi_type:
            hierarchy["stories"][wi.id] = wi_dict
        elif "task" in wi_type:
            hierarchy["tasks"][wi.id] = wi_dict
        elif "bug" in wi_type:
            hierarchy["bugs"][wi.id] = wi_dict
        else:
            hierarchy["other"][wi.id] = wi_dict
    
    return hierarchy


def summarize_pipelines(runs: list[PipelineRun]) -> dict:
    """Summarize pipeline runs."""
    summary = {
        "total_runs": len(runs),
        "by_result": {},
        "by_pipeline": {},
        "success_rate": 0.0
    }
    
    if not runs:
        return summary
    
    # Count by result
    for run in runs:
        result = run.result or "unknown"
        summary["by_result"][result] = summary["by_result"].get(result, 0) + 1
        
        # Count by pipeline
        if run.pipeline_name not in summary["by_pipeline"]:
            summary["by_pipeline"][run.pipeline_name] = {
                "total": 0,
                "succeeded": 0,
                "failed": 0,
                "other": 0
            }
        
        summary["by_pipeline"][run.pipeline_name]["total"] += 1
        
        if result == "succeeded":
            summary["by_pipeline"][run.pipeline_name]["succeeded"] += 1
        elif result == "failed":
            summary["by_pipeline"][run.pipeline_name]["failed"] += 1
        else:
            summary["by_pipeline"][run.pipeline_name]["other"] += 1
    
    # Calculate success rate
    succeeded = summary["by_result"].get("succeeded", 0)
    summary["success_rate"] = round((succeeded / len(runs)) * 100, 1) if runs else 0
    
    return summary


def gather_ado_activity(
    config_path: str,
    since: str,
    until: Optional[str] = None
) -> AdoActivity:
    """Gather all ADO activity for the specified period."""
    
    # Load config
    config = load_config(config_path)
    org = config.get("organization")
    project = config.get("project")
    
    if not org or not project:
        raise ValueError("Config must contain 'organization' and 'project'")
    
    # Parse dates
    since_dt = parse_relative_date(since)
    until_dt = parse_relative_date(until) if until else datetime.now()
    
    print(f"Gathering ADO activity from {since_dt.date()} to {until_dt.date()}...", file=sys.stderr)
    
    # Gather work items
    print("  Querying changed work items...", file=sys.stderr)
    changed = get_changed_work_items(org, project, since_dt, until_dt)
    
    print("  Querying completed work items...", file=sys.stderr)
    completed = get_completed_work_items(org, project, since_dt, until_dt)
    
    print("  Querying created work items...", file=sys.stderr)
    created = get_created_work_items(org, project, since_dt, until_dt)
    
    # Gather pipeline runs
    print("  Querying pipeline runs...", file=sys.stderr)
    pipeline_runs = get_pipeline_runs(org, project, since_dt, until_dt)
    
    # Build hierarchy from all items
    all_items = list({wi.id: wi for wi in changed + completed + created}.values())
    hierarchy = build_work_item_hierarchy(all_items)
    
    # Summarize pipelines
    pipeline_summary = summarize_pipelines(pipeline_runs)
    
    return AdoActivity(
        organization=org,
        project=project,
        period_start=since_dt.strftime("%Y-%m-%d"),
        period_end=until_dt.strftime("%Y-%m-%d"),
        work_items_changed=[asdict(wi) for wi in changed],
        work_items_completed=[asdict(wi) for wi in completed],
        work_items_created=[asdict(wi) for wi in created],
        pipeline_runs=[asdict(run) for run in pipeline_runs],
        pipeline_summary=pipeline_summary,
        work_item_hierarchy=hierarchy
    )


def main():
    parser = argparse.ArgumentParser(
        description="Gather Azure DevOps activity for WSR generation."
    )
    parser.add_argument(
        "--config", "-c",
        required=True,
        help="Path to ADO config file (.ado/config.json)"
    )
    parser.add_argument(
        "--since", "-s",
        required=True,
        help="Start of time range (e.g., '7 days ago', '2024-01-01')"
    )
    parser.add_argument(
        "--until", "-u",
        help="End of time range (default: now)"
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file (default: stdout)"
    )
    
    args = parser.parse_args()
    
    try:
        activity = gather_ado_activity(
            config_path=args.config,
            since=args.since,
            until=args.until
        )
        
        # Convert to JSON
        result = asdict(activity)
        json_output = json.dumps(result, indent=2, default=str)
        
        if args.output:
            Path(args.output).write_text(json_output)
            print(f"\nActivity written to {args.output}", file=sys.stderr)
        else:
            print(json_output)
        
        # Summary
        print(f"\nSummary:", file=sys.stderr)
        print(f"  Organization: {activity.organization}", file=sys.stderr)
        print(f"  Project: {activity.project}", file=sys.stderr)
        print(f"  Period: {activity.period_start} to {activity.period_end}", file=sys.stderr)
        print(f"  Work items changed: {len(activity.work_items_changed)}", file=sys.stderr)
        print(f"  Work items completed: {len(activity.work_items_completed)}", file=sys.stderr)
        print(f"  Work items created: {len(activity.work_items_created)}", file=sys.stderr)
        print(f"  Pipeline runs: {len(activity.pipeline_runs)}", file=sys.stderr)
        if activity.pipeline_summary:
            print(f"  Pipeline success rate: {activity.pipeline_summary.get('success_rate', 0)}%", file=sys.stderr)
        
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        print("Run 'az devops configure' or set up .ado/config.json first.", file=sys.stderr)
        sys.exit(1)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

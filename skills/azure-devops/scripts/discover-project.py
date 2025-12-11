#!/usr/bin/env python3
"""
discover-project.py - Discover Azure DevOps project structure.

Usage:
    python discover-project.py --config .ado/config.json --output .ado/project-metadata.json
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path


def run_az_command(args: list) -> dict | list | None:
    cmd = ["az"] + args + ["--output", "json"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        if result.returncode != 0:
            print(f"Warning: {' '.join(args[:3])} failed", file=sys.stderr)
            return None
        return json.loads(result.stdout) if result.stdout.strip() else None
    except Exception as e:
        print(f"Warning: {e}", file=sys.stderr)
        return None


def discover_areas(org: str, project: str) -> list:
    print("Discovering area paths...", file=sys.stderr)
    data = run_az_command(["boards", "area", "project", "list", "--organization", org, "--project", project, "--depth", "10"])
    if not data:
        return []
    
    def parse_area(node):
        area = {"id": node.get("id", 0), "name": node.get("name", ""), "path": node.get("path", ""), "children": []}
        if "children" in node:
            area["children"] = [parse_area(child) for child in node["children"]]
        return area
    
    return [parse_area(data)] if isinstance(data, dict) else [parse_area(item) for item in data]


def discover_iterations(org: str, project: str) -> list:
    print("Discovering iterations...", file=sys.stderr)
    data = run_az_command(["boards", "iteration", "project", "list", "--organization", org, "--project", project, "--depth", "10"])
    if not data:
        return []
    
    iterations = []
    def parse_iteration(node):
        attrs = node.get("attributes", {})
        iterations.append({
            "id": node.get("id", 0), "name": node.get("name", ""), "path": node.get("path", ""),
            "start_date": attrs.get("startDate"), "finish_date": attrs.get("finishDate"), "time_frame": attrs.get("timeFrame")
        })
        for child in node.get("children", []):
            parse_iteration(child)
    
    for item in (data if isinstance(data, list) else [data]):
        parse_iteration(item)
    return iterations


def discover_teams(org: str, project: str) -> list:
    print("Discovering teams...", file=sys.stderr)
    data = run_az_command(["devops", "team", "list", "--organization", org, "--project", project])
    return [{"id": t.get("id", ""), "name": t.get("name", ""), "description": t.get("description", "")} for t in (data or [])]


def discover_work_item_types(org: str, project: str) -> list:
    print("Discovering work item types...", file=sys.stderr)
    data = run_az_command(["boards", "work-item", "type", "list", "--organization", org, "--project", project])
    return [{"name": wit.get("name", ""), "description": wit.get("description", "")} for wit in (data or [])]


def discover_pipelines(org: str, project: str) -> list:
    print("Discovering pipelines...", file=sys.stderr)
    data = run_az_command(["pipelines", "list", "--organization", org, "--project", project])
    return [{"id": p.get("id", 0), "name": p.get("name", ""), "folder": p.get("folder", "")} for p in (data or [])]


def discover_repositories(org: str, project: str) -> list:
    print("Discovering repositories...", file=sys.stderr)
    data = run_az_command(["repos", "list", "--organization", org, "--project", project])
    return [{"id": r.get("id", ""), "name": r.get("name", ""), "default_branch": r.get("defaultBranch", "").replace("refs/heads/", "")} for r in (data or [])]


def main():
    parser = argparse.ArgumentParser(description="Discover Azure DevOps project structure.")
    parser.add_argument("--config", "-c", required=True, help="Path to .ado/config.json")
    parser.add_argument("--output", help="Output file path (default: stdout)")
    args = parser.parse_args()
    
    config = json.loads(Path(args.config).read_text())
    org, project = config["organization"], config["project"]
    
    print(f"Discovering project: {project} at {org}", file=sys.stderr)
    
    metadata = {
        "organization": org, "project": project, "discovered_at": datetime.utcnow().isoformat() + "Z",
        "areas": discover_areas(org, project),
        "iterations": discover_iterations(org, project),
        "teams": discover_teams(org, project),
        "work_item_types": discover_work_item_types(org, project),
        "pipelines": discover_pipelines(org, project),
        "repositories": discover_repositories(org, project)
    }
    
    output = json.dumps(metadata, indent=2)
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(output)
        print(f"Metadata written to {args.output}", file=sys.stderr)
    else:
        print(output)
    
    print(f"\nDiscovery complete: {len(metadata['areas'])} areas, {len(metadata['iterations'])} iterations, {len(metadata['teams'])} teams", file=sys.stderr)


if __name__ == "__main__":
    main()

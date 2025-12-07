#!/usr/bin/env python3
"""
discover-project.py - Discover Azure DevOps project structure.

Queries Azure DevOps via CLI to discover:
- Area paths
- Iteration paths (sprints)
- Teams
- Work item types
- Pipelines
- Repositories

Usage:
    python discover-project.py --config .ado/config.json --output .ado/project-metadata.json
    python discover-project.py --org "https://dev.azure.com/org" --project "Project"
"""

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class AreaNode:
    """An area path node."""
    id: int
    name: str
    path: str
    children: list = field(default_factory=list)


@dataclass
class Iteration:
    """An iteration/sprint."""
    id: int
    name: str
    path: str
    start_date: Optional[str] = None
    finish_date: Optional[str] = None
    time_frame: Optional[str] = None  # past, current, future


@dataclass
class Team:
    """A project team."""
    id: str
    name: str
    description: str = ""


@dataclass
class WorkItemType:
    """A work item type."""
    name: str
    description: str = ""
    icon: str = ""
    color: str = ""


@dataclass
class Pipeline:
    """A build/release pipeline."""
    id: int
    name: str
    folder: str = ""
    revision: int = 0


@dataclass
class Repository:
    """A git repository."""
    id: str
    name: str
    default_branch: str = ""
    web_url: str = ""


@dataclass
class ProjectMetadata:
    """Complete project metadata."""
    organization: str
    project: str
    discovered_at: str
    areas: list = field(default_factory=list)
    iterations: list = field(default_factory=list)
    teams: list = field(default_factory=list)
    work_item_types: list = field(default_factory=list)
    pipelines: list = field(default_factory=list)
    repositories: list = field(default_factory=list)


def run_az_command(args: list) -> dict | list | None:
    """Run an Azure CLI command and return parsed JSON output."""
    cmd = ["az"] + args + ["--output", "json"]
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode != 0:
            print(f"Warning: Command failed: {' '.join(cmd)}", file=sys.stderr)
            print(f"  Error: {result.stderr}", file=sys.stderr)
            return None
        
        if result.stdout.strip():
            return json.loads(result.stdout)
        return None
        
    except subprocess.TimeoutExpired:
        print(f"Warning: Command timed out: {' '.join(cmd)}", file=sys.stderr)
        return None
    except json.JSONDecodeError as e:
        print(f"Warning: Failed to parse JSON: {e}", file=sys.stderr)
        return None
    except Exception as e:
        print(f"Warning: Command error: {e}", file=sys.stderr)
        return None


def check_prerequisites() -> bool:
    """Check that Azure CLI and DevOps extension are available."""
    # Check az CLI
    result = subprocess.run(
        ["az", "--version"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("Error: Azure CLI not installed or not in PATH", file=sys.stderr)
        print("Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli", file=sys.stderr)
        return False
    
    # Check devops extension
    result = subprocess.run(
        ["az", "extension", "show", "--name", "azure-devops"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("Azure DevOps extension not installed. Installing...", file=sys.stderr)
        install_result = subprocess.run(
            ["az", "extension", "add", "--name", "azure-devops"],
            capture_output=True,
            text=True
        )
        if install_result.returncode != 0:
            print("Error: Failed to install azure-devops extension", file=sys.stderr)
            return False
        print("Azure DevOps extension installed successfully", file=sys.stderr)
    
    # Check authentication
    result = subprocess.run(
        ["az", "account", "show"],
        capture_output=True,
        text=True
    )
    if result.returncode != 0:
        print("Error: Not logged in to Azure CLI", file=sys.stderr)
        print("Run: az login", file=sys.stderr)
        return False
    
    return True


def discover_areas(org: str, project: str) -> list[dict]:
    """Discover area paths."""
    print("Discovering area paths...", file=sys.stderr)
    
    data = run_az_command([
        "boards", "area", "project", "list",
        "--organization", org,
        "--project", project,
        "--depth", "10"
    ])
    
    if not data:
        return []
    
    def parse_area(node: dict) -> dict:
        area = {
            "id": node.get("id", 0),
            "name": node.get("name", ""),
            "path": node.get("path", ""),
            "children": []
        }
        
        if "children" in node:
            area["children"] = [parse_area(child) for child in node["children"]]
        
        return area
    
    # Handle both single root and list response
    if isinstance(data, dict):
        return [parse_area(data)]
    elif isinstance(data, list):
        return [parse_area(item) for item in data]
    
    return []


def discover_iterations(org: str, project: str) -> list[dict]:
    """Discover iteration paths (sprints)."""
    print("Discovering iterations...", file=sys.stderr)
    
    data = run_az_command([
        "boards", "iteration", "project", "list",
        "--organization", org,
        "--project", project,
        "--depth", "10"
    ])
    
    if not data:
        return []
    
    iterations = []
    
    def parse_iteration(node: dict, parent_path: str = ""):
        iter_data = {
            "id": node.get("id", 0),
            "name": node.get("name", ""),
            "path": node.get("path", ""),
            "start_date": None,
            "finish_date": None,
            "time_frame": None
        }
        
        # Extract dates from attributes if present
        attrs = node.get("attributes", {})
        if attrs:
            iter_data["start_date"] = attrs.get("startDate")
            iter_data["finish_date"] = attrs.get("finishDate")
            iter_data["time_frame"] = attrs.get("timeFrame")
        
        iterations.append(iter_data)
        
        # Recurse into children
        if "children" in node:
            for child in node["children"]:
                parse_iteration(child, node.get("path", ""))
    
    if isinstance(data, dict):
        parse_iteration(data)
    elif isinstance(data, list):
        for item in data:
            parse_iteration(item)
    
    return iterations


def discover_teams(org: str, project: str) -> list[dict]:
    """Discover project teams."""
    print("Discovering teams...", file=sys.stderr)
    
    data = run_az_command([
        "devops", "team", "list",
        "--organization", org,
        "--project", project
    ])
    
    if not data:
        return []
    
    teams = []
    for team in data:
        teams.append({
            "id": team.get("id", ""),
            "name": team.get("name", ""),
            "description": team.get("description", "")
        })
    
    return teams


def discover_work_item_types(org: str, project: str) -> list[dict]:
    """Discover work item types."""
    print("Discovering work item types...", file=sys.stderr)
    
    data = run_az_command([
        "boards", "work-item", "type", "list",
        "--organization", org,
        "--project", project
    ])
    
    if not data:
        return []
    
    types = []
    for wit in data:
        types.append({
            "name": wit.get("name", ""),
            "description": wit.get("description", ""),
            "icon": wit.get("icon", {}).get("id", "") if isinstance(wit.get("icon"), dict) else "",
            "color": wit.get("color", "")
        })
    
    return types


def discover_pipelines(org: str, project: str) -> list[dict]:
    """Discover build pipelines."""
    print("Discovering pipelines...", file=sys.stderr)
    
    data = run_az_command([
        "pipelines", "list",
        "--organization", org,
        "--project", project
    ])
    
    if not data:
        return []
    
    pipelines = []
    for pipeline in data:
        pipelines.append({
            "id": pipeline.get("id", 0),
            "name": pipeline.get("name", ""),
            "folder": pipeline.get("folder", ""),
            "revision": pipeline.get("revision", 0)
        })
    
    return pipelines


def discover_repositories(org: str, project: str) -> list[dict]:
    """Discover git repositories."""
    print("Discovering repositories...", file=sys.stderr)
    
    data = run_az_command([
        "repos", "list",
        "--organization", org,
        "--project", project
    ])
    
    if not data:
        return []
    
    repos = []
    for repo in data:
        repos.append({
            "id": repo.get("id", ""),
            "name": repo.get("name", ""),
            "default_branch": repo.get("defaultBranch", "").replace("refs/heads/", ""),
            "web_url": repo.get("webUrl", "")
        })
    
    return repos


def discover_project(org: str, project: str) -> ProjectMetadata:
    """Discover all project metadata."""
    metadata = ProjectMetadata(
        organization=org,
        project=project,
        discovered_at=datetime.utcnow().isoformat() + "Z"
    )
    
    metadata.areas = discover_areas(org, project)
    metadata.iterations = discover_iterations(org, project)
    metadata.teams = discover_teams(org, project)
    metadata.work_item_types = discover_work_item_types(org, project)
    metadata.pipelines = discover_pipelines(org, project)
    metadata.repositories = discover_repositories(org, project)
    
    return metadata


def load_config(config_path: str) -> tuple[str, str]:
    """Load organization and project from config file."""
    config = json.loads(Path(config_path).read_text())
    return config["organization"], config["project"]


def main():
    parser = argparse.ArgumentParser(
        description="Discover Azure DevOps project structure."
    )
    parser.add_argument(
        "--config", "-c",
        help="Path to .ado/config.json file"
    )
    parser.add_argument(
        "--org", "-o",
        help="Azure DevOps organization URL"
    )
    parser.add_argument(
        "--project", "-p",
        help="Azure DevOps project name"
    )
    parser.add_argument(
        "--output",
        help="Output file path (default: stdout)",
        default=None
    )
    
    args = parser.parse_args()
    
    # Get org and project from config or arguments
    if args.config:
        org, project = load_config(args.config)
    elif args.org and args.project:
        org = args.org
        project = args.project
    else:
        print("Error: Provide either --config or both --org and --project", file=sys.stderr)
        sys.exit(1)
    
    # Check prerequisites
    if not check_prerequisites():
        sys.exit(1)
    
    print(f"Discovering project: {project} at {org}", file=sys.stderr)
    
    # Discover project
    metadata = discover_project(org, project)
    
    # Convert to dict for JSON serialization
    result = asdict(metadata)
    
    # Output
    json_output = json.dumps(result, indent=2)
    
    if args.output:
        Path(args.output).parent.mkdir(parents=True, exist_ok=True)
        Path(args.output).write_text(json_output)
        print(f"Metadata written to {args.output}", file=sys.stderr)
    else:
        print(json_output)
    
    # Summary
    print(f"\nDiscovery complete:", file=sys.stderr)
    print(f"  Areas: {len(metadata.areas)}", file=sys.stderr)
    print(f"  Iterations: {len(metadata.iterations)}", file=sys.stderr)
    print(f"  Teams: {len(metadata.teams)}", file=sys.stderr)
    print(f"  Work Item Types: {len(metadata.work_item_types)}", file=sys.stderr)
    print(f"  Pipelines: {len(metadata.pipelines)}", file=sys.stderr)
    print(f"  Repositories: {len(metadata.repositories)}", file=sys.stderr)


if __name__ == "__main__":
    main()

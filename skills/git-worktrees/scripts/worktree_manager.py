#!/usr/bin/env python3
"""
Git worktrees metadata management.

Tracks worktree state, provides cleanup suggestions, and manages configuration.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


class WorktreeManager:
    """Manages worktree metadata and operations."""

    def __init__(self, repo_root: Optional[str] = None):
        if repo_root is None:
            repo_root = subprocess.check_output(
                ["git", "rev-parse", "--show-toplevel"], text=True
            ).strip()

        self.repo_root = Path(repo_root)
        self.config_dir = self.repo_root / ".git" / "worktree"
        self.config_path = self.config_dir / "config.json"
        self.config = self.load_config()

    def load_config(self) -> Dict[str, Any]:
        """Load worktree configuration."""
        if self.config_path.exists():
            with open(self.config_path, "r") as f:
                config = json.load(f)
                # Ensure new fields exist for backwards compatibility
                if "baseBranch" not in config:
                    config["baseBranch"] = None
                if "branchingStrategy" not in config:
                    config["branchingStrategy"] = None
                return config
        else:
            # Default configuration
            return {
                "version": "1.0",
                "basePath": str(Path.home() / ".worktrees"),
                "baseBranch": None,  # Will be auto-detected on first use
                "branchingStrategy": None,  # gitflow, github-flow, or trunk
                "defaultIDE": "auto",
                "autoInstallDeps": True,
                "autoCleanup": False,
                "staleThresholdDays": 7,
                "sharedDeps": ["node_modules", ".npm"],
                "isolatedDeps": [".venv", "venv", "target", "bin", "obj"],
                "worktrees": {},
            }

    def save_config(self):
        """Save worktree configuration."""
        self.config_dir.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w") as f:
            json.dump(self.config, f, indent=2)

    def get_config_value(self, key: str) -> Any:
        """Get a configuration value by dotted key path."""
        parts = key.split(".")
        value = self.config
        for part in parts:
            if isinstance(value, dict) and part in value:
                value = value[part]
            else:
                return None
        return value

    def set_config_value(self, key: str, value: Any) -> bool:
        """Set a configuration value by dotted key path."""
        parts = key.split(".")
        config = self.config

        # Navigate to parent
        for part in parts[:-1]:
            if part not in config:
                config[part] = {}
            config = config[part]

        # Set value (with type coercion)
        final_key = parts[-1]
        if value.lower() in ("true", "false"):
            config[final_key] = value.lower() == "true"
        elif value.isdigit():
            config[final_key] = int(value)
        else:
            config[final_key] = value

        self.save_config()
        return True

    def detect_base_branch(self) -> Tuple[str, str]:
        """
        Detect base branch and branching strategy.

        Returns:
            Tuple of (branch_name, strategy_name)

        Raises:
            ValueError: If no standard base branch is found
        """
        # Get local branches
        result = subprocess.run(
            ["git", "branch", "--list"],
            capture_output=True,
            text=True,
            cwd=self.repo_root,
        )
        local_branches = {
            b.strip().lstrip("* ") for b in result.stdout.splitlines() if b.strip()
        }

        # Get remote branches
        result = subprocess.run(
            ["git", "branch", "-r", "--list", "origin/*"],
            capture_output=True,
            text=True,
            cwd=self.repo_root,
        )
        remote_branches = {
            b.strip().replace("origin/", "")
            for b in result.stdout.splitlines()
            if b.strip() and "HEAD" not in b
        }

        all_branches = local_branches | remote_branches

        # Priority: develop (GitFlow) > main (GitHub Flow) > master (Legacy)
        if "develop" in all_branches:
            return ("develop", "gitflow")
        elif "main" in all_branches:
            return ("main", "github-flow")
        elif "master" in all_branches:
            return ("master", "github-flow")
        else:
            # List available branches in error
            branch_list = sorted(all_branches)[:10]
            raise ValueError(
                f"No standard base branch found (develop, main, or master).\n"
                f"Available branches: {', '.join(branch_list)}\n"
                f"Set manually with: worktree config baseBranch <branch>"
            )

    def get_base_branch(self, explicit_override: Optional[str] = None) -> Tuple[str, str, bool]:
        """
        Get the base branch to use for worktree creation.

        Args:
            explicit_override: Explicit --base flag value (takes precedence)

        Returns:
            Tuple of (branch_name, source_description, was_auto_detected)
            source_description is one of: "explicit", "configured", "auto-detected"

        Raises:
            ValueError: If no base branch configured and detection fails
        """
        # 1. Explicit override wins
        if explicit_override:
            return (explicit_override, "explicit", False)

        # 2. Check config
        if self.config.get("baseBranch"):
            return (self.config["baseBranch"], "configured", False)

        # 3. Try auto-detection (first-time use)
        try:
            base_branch, strategy = self.detect_base_branch()
            # Save to config for future use
            self.config["baseBranch"] = base_branch
            self.config["branchingStrategy"] = strategy
            self.save_config()
            return (base_branch, "auto-detected", True)
        except ValueError as e:
            raise ValueError(
                f"No base branch configured and auto-detection failed.\n\n"
                f"{e}\n\n"
                f"Options:\n"
                f"  1. Configure permanently:  worktree config baseBranch <branch>\n"
                f"  2. Specify per-command:    worktree create feature 1234 --base <branch>"
            )

    def track_create(
        self,
        name: str,
        path: str,
        branch: str,
        work_item: Optional[str] = None,
        pr: Optional[str] = None,
    ):
        """Track newly created worktree."""
        self.config["worktrees"][name] = {
            "path": path,
            "branch": branch,
            "workItem": work_item,
            "pr": pr,
            "created": datetime.now().isoformat(),
            "lastActive": datetime.now().isoformat(),
        }
        self.save_config()

    def track_remove(self, name: str):
        """Remove worktree from tracking."""
        if name in self.config["worktrees"]:
            del self.config["worktrees"][name]
            self.save_config()

    def update_last_active(self, name: str):
        """Update lastActive timestamp."""
        if name in self.config["worktrees"]:
            self.config["worktrees"][name]["lastActive"] = datetime.now().isoformat()
            self.save_config()

    def get_worktree_path(self, name: str) -> Optional[str]:
        """Get path for worktree by name."""
        if name in self.config["worktrees"]:
            return self.config["worktrees"][name]["path"]
        return None

    def list_worktrees(self, stale_only: bool = False) -> List[Dict[str, Any]]:
        """List all worktrees with metadata."""
        # Get actual worktrees from git
        result = subprocess.run(
            ["git", "worktree", "list", "--porcelain"],
            capture_output=True,
            text=True,
            cwd=self.repo_root,
        )

        worktrees: List[Dict[str, Any]] = []
        current: Dict[str, Any] = {}

        for line in result.stdout.splitlines():
            if line.startswith("worktree "):
                if current:
                    worktrees.append(current)
                current = {"path": line.split(" ", 1)[1]}
            elif line.startswith("HEAD "):
                current["head"] = line.split(" ", 1)[1]
            elif line.startswith("branch "):
                branch_ref = line.split(" ", 1)[1]
                current["branch"] = branch_ref.replace("refs/heads/", "")

        if current:
            worktrees.append(current)

        # Enrich with metadata
        enriched: List[Dict[str, Any]] = []
        for wt in worktrees:
            name = os.path.basename(wt["path"])
            metadata = self.config["worktrees"].get(name, {})

            enriched_wt: Dict[str, Any] = {
                **wt,
                "name": name,
                "metadata": metadata,
            }

            # Check if stale
            if metadata and "lastActive" in metadata:
                last_active = datetime.fromisoformat(metadata["lastActive"])
                threshold = datetime.now() - timedelta(
                    days=self.config["staleThresholdDays"]
                )
                enriched_wt["isStale"] = last_active < threshold
            else:
                enriched_wt["isStale"] = False

            # Check if merged
            if "branch" in wt:
                is_merged = self.is_branch_merged(wt["branch"])
                enriched_wt["isMerged"] = is_merged
            else:
                enriched_wt["isMerged"] = False

            # Get uncommitted changes count
            if os.path.isdir(wt["path"]):
                try:
                    status_result = subprocess.run(
                        ["git", "status", "--porcelain"],
                        capture_output=True,
                        text=True,
                        cwd=wt["path"],
                    )
                    changes = [
                        line for line in status_result.stdout.splitlines() if line
                    ]
                    enriched_wt["uncommittedCount"] = len(changes)
                except Exception:
                    enriched_wt["uncommittedCount"] = 0
            else:
                enriched_wt["uncommittedCount"] = 0

            if stale_only and not (enriched_wt["isStale"] or enriched_wt["isMerged"]):
                continue

            enriched.append(enriched_wt)

        return enriched

    def is_branch_merged(self, branch: str) -> bool:
        """Check if branch is merged into base branch."""
        try:
            # Use configured base branch instead of hardcoded 'main'
            base_branch = self.config.get("baseBranch") or "main"
            result = subprocess.run(
                ["git", "branch", "--merged", base_branch],
                capture_output=True,
                text=True,
                cwd=self.repo_root,
            )
            return branch in result.stdout
        except subprocess.CalledProcessError:
            return False

    def get_cleanup_candidates(
        self, merged: bool = False, stale_days: int = 0, all_worktrees: bool = False
    ) -> List[str]:
        """Get list of worktree names eligible for cleanup."""
        candidates: List[str] = []
        worktrees = self.list_worktrees()

        # Get base branch to skip it
        base_branch = self.config.get("baseBranch") or "main"
        protected_branches = {base_branch, "main", "master", "develop"}

        for wt in worktrees:
            # Skip protected branches (base, main, master, develop)
            if wt.get("branch") in protected_branches:
                continue

            if all_worktrees:
                candidates.append(wt["name"])
                continue

            if merged and wt.get("isMerged"):
                candidates.append(wt["name"])
                continue

            if stale_days > 0:
                metadata = wt.get("metadata", {})
                if "lastActive" in metadata:
                    last_active = datetime.fromisoformat(metadata["lastActive"])
                    threshold = datetime.now() - timedelta(days=stale_days)
                    if last_active < threshold:
                        candidates.append(wt["name"])

        return candidates

    def get_status(self, name: str) -> Optional[Dict[str, Any]]:
        """Get detailed status for a worktree."""
        worktrees = self.list_worktrees()
        for wt in worktrees:
            if wt["name"] == name:
                return wt
        return None


def main():
    parser = argparse.ArgumentParser(description="Manage git worktrees")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # track-create
    track_create = subparsers.add_parser(
        "track-create", help="Track newly created worktree"
    )
    track_create.add_argument("--name", required=True)
    track_create.add_argument("--path", required=True)
    track_create.add_argument("--branch", required=True)
    track_create.add_argument("--work-item")
    track_create.add_argument("--pr")

    # track-remove
    track_remove = subparsers.add_parser(
        "track-remove", help="Remove worktree from tracking"
    )
    track_remove.add_argument("--name", required=True)

    # get-path
    get_path = subparsers.add_parser("get-path", help="Get path for worktree")
    get_path.add_argument("--name", required=True)

    # list
    list_cmd = subparsers.add_parser("list", help="List worktrees")
    list_cmd.add_argument("--json", action="store_true")
    list_cmd.add_argument("--stale", action="store_true")

    # cleanup-candidates
    cleanup = subparsers.add_parser("cleanup-candidates", help="Get cleanup candidates")
    cleanup.add_argument(
        "--merged", type=lambda x: x.lower() == "true", default=False
    )
    cleanup.add_argument("--stale-days", type=int, default=0)
    cleanup.add_argument("--all", type=lambda x: x.lower() == "true", default=False)

    # status
    status_cmd = subparsers.add_parser("status", help="Get worktree status")
    status_cmd.add_argument("--name", required=True)
    status_cmd.add_argument("--compact", action="store_true")

    # config
    config_cmd = subparsers.add_parser("config", help="Get/set configuration")
    config_cmd.add_argument("key", nargs="?")
    config_cmd.add_argument("value", nargs="?")

    # get-base
    get_base = subparsers.add_parser("get-base", help="Get base branch for worktree creation")
    get_base.add_argument("--explicit", help="Explicit override (--base flag value)")
    get_base.add_argument("--json", action="store_true", help="Output as JSON")

    args = parser.parse_args()

    try:
        manager = WorktreeManager()
    except subprocess.CalledProcessError:
        print("Error: Not in a git repository", file=sys.stderr)
        sys.exit(1)

    if args.command == "track-create":
        manager.track_create(
            args.name,
            args.path,
            args.branch,
            work_item=args.work_item,
            pr=args.pr,
        )
        print(f"Tracked worktree: {args.name}")

    elif args.command == "track-remove":
        manager.track_remove(args.name)
        print(f"Removed tracking for: {args.name}")

    elif args.command == "get-path":
        path = manager.get_worktree_path(args.name)
        if path:
            print(path)
        else:
            print(f"Worktree not found: {args.name}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "list":
        worktrees = manager.list_worktrees(stale_only=args.stale)
        if args.json:
            print(json.dumps(worktrees, indent=2, default=str))
        else:
            for wt in worktrees:
                print(wt["name"])

    elif args.command == "cleanup-candidates":
        candidates = manager.get_cleanup_candidates(
            merged=args.merged,
            stale_days=args.stale_days,
            all_worktrees=args.all,
        )
        for name in candidates:
            print(name)

    elif args.command == "status":
        status = manager.get_status(args.name)
        if status:
            if args.compact:
                uncommitted = status.get("uncommittedCount", 0)
                is_stale = status.get("isStale", False)
                is_merged = status.get("isMerged", False)
                flags = []
                if uncommitted > 0:
                    flags.append(f"{uncommitted} uncommitted")
                if is_stale:
                    flags.append("stale")
                if is_merged:
                    flags.append("merged")
                print(", ".join(flags) if flags else "clean")
            else:
                print(json.dumps(status, indent=2, default=str))
        else:
            print(f"Worktree not found: {args.name}", file=sys.stderr)
            sys.exit(1)

    elif args.command == "config":
        if args.key is None:
            # Show all config
            print(json.dumps(manager.config, indent=2))
        elif args.value is None:
            # Get single value
            value = manager.get_config_value(args.key)
            if value is not None:
                print(value)
            else:
                print(f"Config key not found: {args.key}", file=sys.stderr)
                sys.exit(1)
        else:
            # Set value
            manager.set_config_value(args.key, args.value)
            print(f"Set {args.key} = {args.value}")

    elif args.command == "get-base":
        try:
            branch, source, was_detected = manager.get_base_branch(
                explicit_override=args.explicit
            )
            if args.json:
                result = {
                    "branch": branch,
                    "source": source,
                    "wasAutoDetected": was_detected,
                    "strategy": manager.config.get("branchingStrategy"),
                }
                print(json.dumps(result))
            else:
                print(branch)
                if was_detected:
                    strategy = manager.config.get("branchingStrategy", "unknown")
                    print(f"# Auto-detected: {strategy} workflow", file=sys.stderr)
                    print(f"# Saved to config. Change with: worktree config baseBranch <branch>", file=sys.stderr)
        except ValueError as e:
            print(str(e), file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()

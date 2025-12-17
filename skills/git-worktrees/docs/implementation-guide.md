# Git Worktrees Skill - Implementation Guide

**Version:** 1.0
**Status:** Design Phase
**Date:** 2025-12-17

---

## Table of Contents

1. [Command Reference](#command-reference)
2. [Script Architecture](#script-architecture)
3. [Python Helpers](#python-helpers)
4. [Error Handling Patterns](#error-handling-patterns)
5. [Testing Strategy](#testing-strategy)
6. [Deployment & Setup](#deployment--setup)

---

## Command Reference

### Command: `worktree create`

**Full Signature:**
```bash
worktree create <type> <identifier> [options]
```

**Implementation Pattern:**

```bash
cmd_create() {
    local type="$1"
    local identifier="$2"
    shift 2

    # Parse options
    local path=""
    local base_branch="main"
    local no_track=false
    local no_deps=false
    local ide="auto"

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --path)
                path="$2"
                shift 2
                ;;
            --base)
                base_branch="$2"
                shift 2
                ;;
            --no-track)
                no_track=true
                shift
                ;;
            --no-deps)
                no_deps=true
                shift
                ;;
            --ide)
                ide="$2"
                shift 2
                ;;
            *)
                print_error "Unknown option: $1"
                exit 1
                ;;
        esac
    done

    # Dispatch to type-specific handler
    case "$type" in
        feature|fix|task)
            create_from_work_item "$type" "$identifier" "$path" "$base_branch" "$no_deps" "$ide"
            ;;
        pr)
            create_from_pr "$identifier" "$path" "$no_deps" "$ide"
            ;;
        branch)
            create_from_branch "$identifier" "$path" "$no_deps" "$ide"
            ;;
        main)
            create_from_main "${identifier:-stable}" "$path" "$no_deps" "$ide"
            ;;
        *)
            print_error "Unknown type: $type"
            echo "Valid types: feature, fix, task, pr, branch, main"
            exit 1
            ;;
    esac
}
```

**Type-Specific Handler Example (Feature):**

```bash
create_from_work_item() {
    local type="$1"
    local work_item_id="$2"
    local path="$3"
    local base_branch="$4"
    local no_deps="$5"
    local ide="$6"

    check_git_repo
    check_clean_working_tree

    # Fetch work item title (integrates with feature workflow)
    print_info "Fetching work item #$work_item_id from Azure DevOps..."
    local description=$(get_work_item_title "$work_item_id")

    if [[ -z "$description" ]]; then
        print_warning "Could not fetch work item title"
        description="AB#$work_item_id"
    else
        print_info "Found: $description"
    fi

    # Generate branch name
    local slug=$(slugify "$description")
    local branch_name="$type/AB#$work_item_id-$slug"

    # Generate worktree path if not provided
    if [[ -z "$path" ]]; then
        local repo_name=$(basename "$(git rev-parse --show-toplevel)")
        path="../${repo_name}-${type}-AB#${work_item_id}-${slug}"
    fi

    # Validate path doesn't exist
    if [[ -e "$path" ]]; then
        print_error "Path already exists: $path"
        exit 1
    fi

    # Check if branch exists
    local branch_exists=false
    if git show-ref --verify --quiet "refs/heads/$branch_name"; then
        branch_exists=true
        print_info "Branch '$branch_name' already exists, will use it"
    fi

    # Create worktree
    print_info "Creating worktree..."

    if $branch_exists; then
        git worktree add "$path" "$branch_name"
    else
        # Create new branch from base
        git worktree add -b "$branch_name" "$path" "$base_branch"
    fi

    print_success "Created worktree: $(basename "$path")"
    echo "  Path: $(cd "$path" && pwd)"
    echo "  Branch: $branch_name"
    echo "  Base: $base_branch"

    # Update tracking metadata
    python3 "$SCRIPT_DIR/../skills/git-worktrees/scripts/worktree_manager.py" \
        track-create \
        --name "$(basename "$path")" \
        --path "$(cd "$path" && pwd)" \
        --branch "$branch_name" \
        --work-item "AB#$work_item_id"

    # Install dependencies unless --no-deps
    if [[ "$no_deps" != "true" ]]; then
        install_dependencies "$path"
    fi

    # Open in IDE
    if [[ "$ide" != "none" ]]; then
        open_in_ide "$path" "$ide"
    fi

    # Print next steps
    echo ""
    print_success "Worktree ready!"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  cd $path"
    echo "  # Make your changes"
    echo "  git commit -am 'Your message'  # AB#$work_item_id auto-appended"
    echo "  feature pr  # Create pull request"
    echo ""
    echo "To return to main worktree:"
    echo "  worktree switch main"
}
```

**PR Creation Handler:**

```bash
create_from_pr() {
    local pr_id="$1"
    local path="$2"
    local no_deps="$3"
    local ide="$4"

    check_git_repo

    # Detect platform and fetch PR branch
    local platform=$(detect_platform)
    local pr_branch=""

    case "$platform" in
        github)
            print_info "Fetching PR #$pr_id from GitHub..."
            pr_branch=$(gh pr view "$pr_id" --json headRefName --jq '.headRefName')
            if [[ -z "$pr_branch" ]]; then
                print_error "Could not fetch PR #$pr_id"
                exit 1
            fi

            # Fetch PR branch
            gh pr checkout "$pr_id" --detach
            ;;

        azdo|azure-devops)
            print_info "Fetching PR #$pr_id from Azure DevOps..."
            pr_branch=$(az repos pr show --id "$pr_id" --query sourceRefName --output tsv | sed 's|refs/heads/||')
            if [[ -z "$pr_branch" ]]; then
                print_error "Could not fetch PR #$pr_id"
                exit 1
            fi

            # Fetch branch
            git fetch origin "$pr_branch"
            ;;

        *)
            print_error "Could not detect platform"
            exit 1
            ;;
    esac

    # Generate path
    if [[ -z "$path" ]]; then
        local repo_name=$(basename "$(git rev-parse --show-toplevel)")
        path="../${repo_name}-review-pr-${pr_id}"
    fi

    # Create worktree
    print_info "Creating review worktree..."
    git worktree add "$path" "$pr_branch"

    print_success "Created review worktree: $(basename "$path")"

    # Track metadata
    python3 "$SCRIPT_DIR/../skills/git-worktrees/scripts/worktree_manager.py" \
        track-create \
        --name "$(basename "$path")" \
        --path "$(cd "$path" && pwd)" \
        --branch "$pr_branch" \
        --pr "$pr_id"

    # Install dependencies
    if [[ "$no_deps" != "true" ]]; then
        install_dependencies "$path"
    fi

    # Open in IDE
    if [[ "$ide" != "none" ]]; then
        open_in_ide "$path" "$ide"
    fi

    echo ""
    print_success "PR review worktree ready!"
    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  cd $path"
    echo "  # Review code, run tests"
    echo "  $platform pr review $pr_id  # Leave feedback"
    echo ""
    echo "When done:"
    echo "  worktree remove review-pr-$pr_id"
}
```

---

### Command: `worktree list`

**Implementation:**

```bash
cmd_list() {
    local verbose=false
    local json=false
    local stale=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --verbose|-v)
                verbose=true
                shift
                ;;
            --json)
                json=true
                shift
                ;;
            --stale)
                stale=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    check_git_repo

    if $json; then
        # Use Python helper for JSON output
        python3 "$SCRIPT_DIR/../skills/git-worktrees/scripts/worktree_manager.py" list --json
        return
    fi

    if $stale; then
        # Show only stale worktrees
        python3 "$SCRIPT_DIR/../skills/git-worktrees/scripts/worktree_manager.py" list --stale
        return
    fi

    # Parse git worktree list output
    local current_worktree=$(git rev-parse --show-toplevel)

    echo -e "${CYAN}Current worktrees:${NC}"
    echo ""

    git worktree list --porcelain | while IFS= read -r line; do
        if [[ "$line" =~ ^worktree\ (.+)$ ]]; then
            local wt_path="${BASH_REMATCH[1]}"
            local wt_name=$(basename "$wt_path")

            # Read subsequent lines for this worktree
            read -r head_line
            local branch=""
            if [[ "$head_line" =~ ^HEAD\ (.+)$ ]]; then
                local head_sha="${BASH_REMATCH[1]}"
                read -r branch_line
                if [[ "$branch_line" =~ ^branch\ refs/heads/(.+)$ ]]; then
                    branch="${BASH_REMATCH[1]}"
                fi
            fi

            # Get status
            local status=$(cd "$wt_path" && git status --porcelain | wc -l | tr -d ' ')
            local status_text="clean"
            if [[ "$status" -gt 0 ]]; then
                status_text="$status uncommitted"
            fi

            # Mark current worktree
            local marker="  "
            if [[ "$wt_path" == "$current_worktree" ]]; then
                marker="* "
            fi

            echo -e "${marker}${GREEN}$wt_name${NC}  [$branch] ($status_text)"
            echo "    $wt_path"

            if $verbose; then
                # Show detailed info
                python3 "$SCRIPT_DIR/../skills/git-worktrees/scripts/worktree_manager.py" \
                    status --name "$wt_name" --compact
            fi

            echo ""
        fi
    done
}
```

---

### Command: `worktree remove`

**Implementation:**

```bash
cmd_remove() {
    local name="$1"
    local force=false
    local keep_branch=false

    shift

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --force)
                force=true
                shift
                ;;
            --keep-branch)
                keep_branch=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    if [[ -z "$name" ]]; then
        print_error "Worktree name required"
        echo "Usage: worktree remove <name> [--force] [--keep-branch]"
        exit 1
    fi

    check_git_repo

    # Get worktree path
    local wt_path=$(python3 "$SCRIPT_DIR/../skills/git-worktrees/scripts/worktree_manager.py" \
        get-path --name "$name")

    if [[ -z "$wt_path" ]] || [[ ! -d "$wt_path" ]]; then
        print_error "Worktree not found: $name"
        exit 1
    fi

    # Get branch name
    local branch=$(cd "$wt_path" && git rev-parse --abbrev-ref HEAD)

    # Safety checks (unless --force)
    if [[ "$force" != "true" ]]; then
        # Check for uncommitted changes
        local uncommitted=$(cd "$wt_path" && git status --porcelain)
        if [[ -n "$uncommitted" ]]; then
            print_warning "Worktree has uncommitted changes:"
            echo ""
            cd "$wt_path" && git status --short
            echo ""
            echo "Options:"
            echo "  1. Commit changes"
            echo "  2. Stash changes"
            echo "  3. Force delete (LOSE CHANGES)"
            echo "  4. Cancel"
            echo ""
            read -p "Your choice [4]: " choice
            choice=${choice:-4}

            case "$choice" in
                1)
                    cd "$wt_path"
                    git add -A
                    read -p "Commit message: " msg
                    git commit -m "$msg"
                    cd -
                    ;;
                2)
                    cd "$wt_path" && git stash push -m "Auto-stash before worktree removal"
                    cd -
                    print_info "Changes stashed. Restore with: git stash pop"
                    ;;
                3)
                    force=true
                    ;;
                *)
                    print_info "Cancelled"
                    exit 0
                    ;;
            esac
        fi

        # Check for unpushed commits
        local unpushed=$(cd "$wt_path" && git log @{u}.. --oneline 2>/dev/null)
        if [[ -n "$unpushed" ]]; then
            print_warning "Branch has unpushed commits:"
            echo ""
            echo "$unpushed"
            echo ""
            echo "Options:"
            echo "  1. Push now"
            echo "  2. Create backup branch"
            echo "  3. Force delete (LOSE COMMITS)"
            echo "  4. Cancel"
            echo ""
            read -p "Your choice [4]: " choice
            choice=${choice:-4}

            case "$choice" in
                1)
                    cd "$wt_path" && git push
                    cd -
                    ;;
                2)
                    local backup_branch="backup-${branch}-$(date +%Y%m%d-%H%M%S)"
                    cd "$wt_path" && git branch "$backup_branch"
                    print_success "Created backup branch: $backup_branch"
                    cd -
                    ;;
                3)
                    force=true
                    ;;
                *)
                    print_info "Cancelled"
                    exit 0
                    ;;
            esac
        fi
    fi

    # Remove worktree
    print_info "Removing worktree..."

    if $force; then
        git worktree remove --force "$wt_path"
    else
        git worktree remove "$wt_path"
    fi

    print_success "Removed worktree: $name"

    # Delete branch (unless --keep-branch)
    if [[ "$keep_branch" != "true" ]]; then
        read -p "Delete branch '$branch'? [y/N]: " delete_branch
        if [[ "$delete_branch" =~ ^[Yy]$ ]]; then
            git branch -d "$branch" 2>/dev/null || {
                print_warning "Branch not fully merged"
                read -p "Force delete? [y/N]: " force_delete
                if [[ "$force_delete" =~ ^[Yy]$ ]]; then
                    git branch -D "$branch"
                    print_success "Deleted branch: $branch"
                fi
            }
        fi
    fi

    # Update tracking metadata
    python3 "$SCRIPT_DIR/../skills/git-worktrees/scripts/worktree_manager.py" \
        track-remove --name "$name"

    print_success "Cleanup complete"
}
```

---

### Command: `worktree cleanup`

**Implementation:**

```bash
cmd_cleanup() {
    local dry_run=false
    local merged=false
    local stale_days=0
    local all=false

    while [[ $# -gt 0 ]]; do
        case "$1" in
            --dry-run)
                dry_run=true
                shift
                ;;
            --merged)
                merged=true
                shift
                ;;
            --stale)
                stale_days="$2"
                shift 2
                ;;
            --all)
                all=true
                shift
                ;;
            *)
                shift
                ;;
        esac
    done

    check_git_repo

    # Use Python helper to identify cleanup candidates
    local candidates=$(python3 "$SCRIPT_DIR/../skills/git-worktrees/scripts/worktree_manager.py" \
        cleanup-candidates \
        --merged=$merged \
        --stale-days=$stale_days \
        --all=$all)

    if [[ -z "$candidates" ]]; then
        print_info "No worktrees to clean up"
        exit 0
    fi

    echo -e "${CYAN}Cleanup candidates:${NC}"
    echo ""
    echo "$candidates"
    echo ""

    if $dry_run; then
        print_info "Dry run - no worktrees removed"
        exit 0
    fi

    read -p "Proceed with cleanup? [y/N]: " confirm
    if [[ ! "$confirm" =~ ^[Yy]$ ]]; then
        print_info "Cancelled"
        exit 0
    fi

    # Remove each candidate
    echo "$candidates" | while IFS= read -r name; do
        if [[ -n "$name" ]]; then
            print_info "Removing: $name"
            cmd_remove "$name" --force
        fi
    done

    print_success "Cleanup complete"
}
```

---

## Script Architecture

### Main Script Structure

**File:** `scripts/worktree.sh`

```bash
#!/bin/bash
# worktree.sh - Git worktree management
#
# Simplifies git worktree operations with smart defaults and safety checks.
#
# Usage:
#   worktree create <type> <id>      # Create worktree
#   worktree list                    # List worktrees
#   worktree remove <name>           # Remove worktree
#   worktree cleanup                 # Clean up stale worktrees
#   worktree status [name]           # Show worktree status
#   worktree sync [name]             # Sync with remote

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
SKILL_DIR="$SCRIPT_DIR/../skills/git-worktrees"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

# =============================================================================
# Helper Functions
# =============================================================================

print_error() {
    echo -e "${RED}Error:${NC} $1" >&2
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_info() {
    echo -e "${BLUE}→${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

check_git_repo() {
    if [[ -z "$REPO_ROOT" ]]; then
        print_error "Not in a git repository"
        exit 1
    fi
}

check_clean_working_tree() {
    if ! git diff --quiet HEAD 2>/dev/null; then
        print_error "You have uncommitted changes. Commit or stash them first."
        exit 1
    fi
}

slugify() {
    echo "$1" | \
        tr '[:upper:]' '[:lower:]' | \
        sed 's/[^a-z0-9]/-/g' | \
        sed 's/--*/-/g' | \
        sed 's/^-//' | \
        sed 's/-$//' | \
        cut -c1-50
}

# =============================================================================
# Integration with Feature Workflow
# =============================================================================

get_work_item_title() {
    local work_item_id="$1"
    local helper="$SCRIPT_DIR/feature_workflow.py"

    if [[ -f "$helper" ]]; then
        python3 "$helper" get-title "$work_item_id" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

detect_platform() {
    local detector="$SKILL_DIR/scripts/detect_platform.py"
    if [[ -f "$detector" ]]; then
        python3 "$detector" 2>/dev/null || echo "unknown"
    else
        echo "unknown"
    fi
}

# =============================================================================
# Dependency Management
# =============================================================================

install_dependencies() {
    local path="$1"

    print_info "Installing dependencies..."

    # Use Python helper to detect and install
    python3 "$SKILL_DIR/scripts/dependency_handler.py" \
        install --path "$path" --config "$REPO_ROOT/.git/worktree/config.json"

    if [[ $? -eq 0 ]]; then
        print_success "Dependencies installed"
    else
        print_warning "Some dependencies failed to install"
    fi
}

# =============================================================================
# IDE Integration
# =============================================================================

open_in_ide() {
    local path="$1"
    local ide="$2"

    python3 "$SKILL_DIR/scripts/ide_launcher.py" \
        launch --path "$path" --ide "$ide"
}

# =============================================================================
# Command Implementations
# =============================================================================

# [Insert cmd_create, cmd_list, cmd_remove, etc. from above]

usage() {
    echo "worktree - Git worktree management"
    echo ""
    echo -e "${CYAN}Usage:${NC}"
    echo "  worktree create <type> <id> [options]   Create worktree"
    echo "  worktree list [--verbose] [--stale]     List worktrees"
    echo "  worktree remove <name> [--force]        Remove worktree"
    echo "  worktree cleanup [--merged] [--stale N] Clean up worktrees"
    echo "  worktree status [name]                  Show worktree status"
    echo "  worktree sync [name] [--all]            Sync with remote"
    echo "  worktree open <name> [--ide <ide>]      Open in IDE"
    echo "  worktree config [key] [value]           Get/set configuration"
    echo ""
    echo -e "${CYAN}Create Types:${NC}"
    echo "  feature <work-item-id>   Create from work item"
    echo "  fix <work-item-id>       Create fix branch"
    echo "  pr <pr-id>               Create from PR"
    echo "  branch <branch-name>     Create from branch"
    echo "  main [name]              Create from main"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  worktree create feature 1234            # From work item"
    echo "  worktree create pr 5678                 # For PR review"
    echo "  worktree create branch experiment       # From branch"
    echo "  worktree list --verbose                 # Detailed list"
    echo "  worktree cleanup --merged               # Remove merged"
    echo ""
    echo -e "${CYAN}Integration:${NC}"
    echo "  Works with: feature workflow, Azure DevOps, GitHub"
    echo "  Pre-commit hooks: Automatic work item linking"
}

# =============================================================================
# Main Dispatch
# =============================================================================

case "${1:-}" in
    create)
        shift
        cmd_create "$@"
        ;;
    list|ls)
        shift
        cmd_list "$@"
        ;;
    remove|rm)
        shift
        cmd_remove "$@"
        ;;
    cleanup|clean)
        shift
        cmd_cleanup "$@"
        ;;
    status)
        shift
        cmd_status "$@"
        ;;
    sync)
        shift
        cmd_sync "$@"
        ;;
    open)
        shift
        cmd_open "$@"
        ;;
    config)
        shift
        cmd_config "$@"
        ;;
    switch|sw)
        shift
        cmd_switch "$@"
        ;;
    help|--help|-h)
        usage
        ;;
    "")
        usage
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        usage
        exit 1
        ;;
esac
```

---

## Python Helpers

### Worktree Manager

**File:** `skills/git-worktrees/scripts/worktree_manager.py`

```python
#!/usr/bin/env python3
"""
Git worktrees metadata management.

Tracks worktree state, provides cleanup suggestions, and manages configuration.
"""

import argparse
import json
import os
import subprocess
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional

class WorktreeManager:
    """Manages worktree metadata and operations."""

    def __init__(self, repo_root: Optional[str] = None):
        if repo_root is None:
            repo_root = subprocess.check_output(
                ['git', 'rev-parse', '--show-toplevel'],
                text=True
            ).strip()

        self.repo_root = Path(repo_root)
        self.config_path = self.repo_root / '.git' / 'worktree' / 'config.json'
        self.config = self.load_config()

    def load_config(self) -> Dict:
        """Load worktree configuration."""
        if self.config_path.exists():
            with open(self.config_path, 'r') as f:
                return json.load(f)
        else:
            # Default configuration
            return {
                'version': '1.0',
                'basePath': '../',
                'defaultIDE': 'code',
                'autoInstallDeps': True,
                'autoCleanup': False,
                'staleThresholdDays': 7,
                'sharedDeps': ['node_modules', '.npm'],
                'isolatedDeps': ['.venv', 'venv', 'target', 'bin', 'obj'],
                'worktrees': {}
            }

    def save_config(self):
        """Save worktree configuration."""
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(self.config, f, indent=2)

    def track_create(self, name: str, path: str, branch: str,
                     work_item: Optional[str] = None, pr: Optional[str] = None):
        """Track newly created worktree."""
        self.config['worktrees'][name] = {
            'path': path,
            'branch': branch,
            'workItem': work_item,
            'pr': pr,
            'created': datetime.now().isoformat(),
            'lastActive': datetime.now().isoformat()
        }
        self.save_config()

    def track_remove(self, name: str):
        """Remove worktree from tracking."""
        if name in self.config['worktrees']:
            del self.config['worktrees'][name]
            self.save_config()

    def update_last_active(self, name: str):
        """Update lastActive timestamp."""
        if name in self.config['worktrees']:
            self.config['worktrees'][name]['lastActive'] = datetime.now().isoformat()
            self.save_config()

    def get_worktree_path(self, name: str) -> Optional[str]:
        """Get path for worktree by name."""
        if name in self.config['worktrees']:
            return self.config['worktrees'][name]['path']
        return None

    def list_worktrees(self, stale_only: bool = False) -> List[Dict]:
        """List all worktrees with metadata."""
        # Get actual worktrees from git
        result = subprocess.run(
            ['git', 'worktree', 'list', '--porcelain'],
            capture_output=True,
            text=True,
            cwd=self.repo_root
        )

        worktrees = []
        current = {}

        for line in result.stdout.splitlines():
            if line.startswith('worktree '):
                if current:
                    worktrees.append(current)
                current = {'path': line.split(' ', 1)[1]}
            elif line.startswith('HEAD '):
                current['head'] = line.split(' ', 1)[1]
            elif line.startswith('branch '):
                current['branch'] = line.replace('refs/heads/', '').split(' ', 1)[1]

        if current:
            worktrees.append(current)

        # Enrich with metadata
        enriched = []
        for wt in worktrees:
            name = os.path.basename(wt['path'])
            metadata = self.config['worktrees'].get(name, {})

            enriched_wt = {
                **wt,
                'name': name,
                'metadata': metadata
            }

            # Check if stale
            if metadata and 'lastActive' in metadata:
                last_active = datetime.fromisoformat(metadata['lastActive'])
                threshold = datetime.now() - timedelta(days=self.config['staleThresholdDays'])
                enriched_wt['isStale'] = last_active < threshold
            else:
                enriched_wt['isStale'] = False

            # Check if merged
            if 'branch' in wt:
                is_merged = self.is_branch_merged(wt['branch'])
                enriched_wt['isMerged'] = is_merged
            else:
                enriched_wt['isMerged'] = False

            if stale_only and not (enriched_wt['isStale'] or enriched_wt['isMerged']):
                continue

            enriched.append(enriched_wt)

        return enriched

    def is_branch_merged(self, branch: str) -> bool:
        """Check if branch is merged into main."""
        try:
            result = subprocess.run(
                ['git', 'branch', '--merged', 'main'],
                capture_output=True,
                text=True,
                cwd=self.repo_root
            )
            return branch in result.stdout
        except subprocess.CalledProcessError:
            return False

    def get_cleanup_candidates(self, merged: bool = False,
                              stale_days: int = 0, all_worktrees: bool = False) -> List[str]:
        """Get list of worktree names eligible for cleanup."""
        candidates = []
        worktrees = self.list_worktrees()

        for wt in worktrees:
            # Skip main worktree
            if wt.get('branch') in ['main', 'master']:
                continue

            if all_worktrees:
                candidates.append(wt['name'])
                continue

            if merged and wt.get('isMerged'):
                candidates.append(wt['name'])
                continue

            if stale_days > 0:
                metadata = wt.get('metadata', {})
                if 'lastActive' in metadata:
                    last_active = datetime.fromisoformat(metadata['lastActive'])
                    threshold = datetime.now() - timedelta(days=stale_days)
                    if last_active < threshold:
                        candidates.append(wt['name'])

        return candidates


def main():
    parser = argparse.ArgumentParser(description='Manage git worktrees')
    subparsers = parser.add_subparsers(dest='command', required=True)

    # track-create
    track_create = subparsers.add_parser('track-create', help='Track newly created worktree')
    track_create.add_argument('--name', required=True)
    track_create.add_argument('--path', required=True)
    track_create.add_argument('--branch', required=True)
    track_create.add_argument('--work-item')
    track_create.add_argument('--pr')

    # track-remove
    track_remove = subparsers.add_parser('track-remove', help='Remove worktree from tracking')
    track_remove.add_argument('--name', required=True)

    # get-path
    get_path = subparsers.add_parser('get-path', help='Get path for worktree')
    get_path.add_argument('--name', required=True)

    # list
    list_cmd = subparsers.add_parser('list', help='List worktrees')
    list_cmd.add_argument('--json', action='store_true')
    list_cmd.add_argument('--stale', action='store_true')

    # cleanup-candidates
    cleanup = subparsers.add_parser('cleanup-candidates', help='Get cleanup candidates')
    cleanup.add_argument('--merged', type=lambda x: x.lower() == 'true', default=False)
    cleanup.add_argument('--stale-days', type=int, default=0)
    cleanup.add_argument('--all', type=lambda x: x.lower() == 'true', default=False)

    args = parser.parse_args()
    manager = WorktreeManager()

    if args.command == 'track-create':
        manager.track_create(
            args.name, args.path, args.branch,
            work_item=args.work_item, pr=args.pr
        )
        print(f"Tracked worktree: {args.name}")

    elif args.command == 'track-remove':
        manager.track_remove(args.name)
        print(f"Removed tracking for: {args.name}")

    elif args.command == 'get-path':
        path = manager.get_worktree_path(args.name)
        if path:
            print(path)
        else:
            print(f"Worktree not found: {args.name}", file=sys.stderr)
            sys.exit(1)

    elif args.command == 'list':
        worktrees = manager.list_worktrees(stale_only=args.stale)
        if args.json:
            print(json.dumps(worktrees, indent=2))
        else:
            for wt in worktrees:
                print(wt['name'])

    elif args.command == 'cleanup-candidates':
        candidates = manager.get_cleanup_candidates(
            merged=args.merged,
            stale_days=args.stale_days,
            all_worktrees=args.all
        )
        for name in candidates:
            print(name)


if __name__ == '__main__':
    main()
```

---

### Dependency Handler

**File:** `skills/git-worktrees/scripts/dependency_handler.py`

```python
#!/usr/bin/env python3
"""
Smart dependency management for worktrees.

Detects dependency systems and handles installation/sharing appropriately.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List

class DependencyHandler:
    """Handles dependency detection and installation."""

    def __init__(self, config_path: str):
        self.config = self.load_config(config_path)

    def load_config(self, config_path: str) -> Dict:
        """Load worktree configuration."""
        if os.path.exists(config_path):
            with open(config_path, 'r') as f:
                return json.load(f)
        return {}

    def detect_dependencies(self, worktree_path: str) -> Dict[str, str]:
        """Detect dependency systems in worktree."""
        deps = {}

        # Node.js
        if os.path.exists(f"{worktree_path}/package.json"):
            if os.path.exists(f"{worktree_path}/package-lock.json"):
                deps['nodejs'] = 'npm'
            elif os.path.exists(f"{worktree_path}/yarn.lock"):
                deps['nodejs'] = 'yarn'
            elif os.path.exists(f"{worktree_path}/pnpm-lock.yaml"):
                deps['nodejs'] = 'pnpm'
            else:
                deps['nodejs'] = 'npm'  # Default

        # Python
        if os.path.exists(f"{worktree_path}/requirements.txt"):
            deps['python'] = 'pip'
        elif os.path.exists(f"{worktree_path}/pyproject.toml"):
            deps['python'] = 'poetry'
        elif os.path.exists(f"{worktree_path}/Pipfile"):
            deps['python'] = 'pipenv'

        # .NET
        csproj_files = glob.glob(f"{worktree_path}/**/*.csproj", recursive=True)
        if csproj_files:
            deps['dotnet'] = 'nuget'

        # Rust
        if os.path.exists(f"{worktree_path}/Cargo.toml"):
            deps['rust'] = 'cargo'

        # Go
        if os.path.exists(f"{worktree_path}/go.mod"):
            deps['go'] = 'go'

        return deps

    def install_dependencies(self, worktree_path: str):
        """Install dependencies based on detected systems."""
        deps = self.detect_dependencies(worktree_path)

        if not deps:
            print("No dependencies detected")
            return

        for system, tool in deps.items():
            print(f"→ Installing {system} dependencies using {tool}...")

            try:
                if tool == 'npm':
                    subprocess.run(['npm', 'install'], cwd=worktree_path, check=True)
                elif tool == 'yarn':
                    subprocess.run(['yarn', 'install'], cwd=worktree_path, check=True)
                elif tool == 'pnpm':
                    subprocess.run(['pnpm', 'install'], cwd=worktree_path, check=True)
                elif tool == 'pip':
                    subprocess.run(
                        ['python3', '-m', 'venv', '.venv'],
                        cwd=worktree_path,
                        check=True
                    )
                    subprocess.run(
                        [f'{worktree_path}/.venv/bin/pip', 'install', '-r', 'requirements.txt'],
                        cwd=worktree_path,
                        check=True
                    )
                elif tool == 'poetry':
                    subprocess.run(['poetry', 'install'], cwd=worktree_path, check=True)
                elif tool == 'pipenv':
                    subprocess.run(['pipenv', 'install'], cwd=worktree_path, check=True)
                elif tool == 'nuget':
                    subprocess.run(['dotnet', 'restore'], cwd=worktree_path, check=True)
                elif tool == 'cargo':
                    subprocess.run(['cargo', 'fetch'], cwd=worktree_path, check=True)
                elif tool == 'go':
                    subprocess.run(['go', 'mod', 'download'], cwd=worktree_path, check=True)

                print(f"✓ {system} dependencies installed")

            except subprocess.CalledProcessError as e:
                print(f"⚠ Failed to install {system} dependencies: {e}", file=sys.stderr)


def main():
    parser = argparse.ArgumentParser(description='Handle worktree dependencies')
    parser.add_argument('command', choices=['install', 'detect'])
    parser.add_argument('--path', required=True, help='Worktree path')
    parser.add_argument('--config', help='Config file path')

    args = parser.parse_args()

    handler = DependencyHandler(args.config or '')

    if args.command == 'detect':
        deps = handler.detect_dependencies(args.path)
        print(json.dumps(deps, indent=2))

    elif args.command == 'install':
        handler.install_dependencies(args.path)


if __name__ == '__main__':
    main()
```

---

## Testing Strategy

### Unit Tests

**File:** `skills/git-worktrees/tests/test_worktree_manager.py`

```python
import pytest
import tempfile
import subprocess
from pathlib import Path
from worktree_manager import WorktreeManager

@pytest.fixture
def temp_repo():
    """Create a temporary git repository for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        repo_path = Path(tmpdir) / 'test-repo'
        repo_path.mkdir()

        # Initialize git repo
        subprocess.run(['git', 'init'], cwd=repo_path, check=True)
        subprocess.run(['git', 'config', 'user.name', 'Test'], cwd=repo_path, check=True)
        subprocess.run(['git', 'config', 'user.email', 'test@test.com'], cwd=repo_path, check=True)

        # Create initial commit
        (repo_path / 'README.md').write_text('# Test')
        subprocess.run(['git', 'add', '.'], cwd=repo_path, check=True)
        subprocess.run(['git', 'commit', '-m', 'Initial commit'], cwd=repo_path, check=True)

        yield repo_path

def test_track_create(temp_repo):
    """Test tracking a newly created worktree."""
    manager = WorktreeManager(str(temp_repo))

    manager.track_create(
        name='test-worktree',
        path='/path/to/test-worktree',
        branch='feature/test',
        work_item='AB#1234'
    )

    assert 'test-worktree' in manager.config['worktrees']
    assert manager.config['worktrees']['test-worktree']['branch'] == 'feature/test'
    assert manager.config['worktrees']['test-worktree']['workItem'] == 'AB#1234'

def test_get_worktree_path(temp_repo):
    """Test retrieving worktree path by name."""
    manager = WorktreeManager(str(temp_repo))

    manager.track_create(
        name='test-worktree',
        path='/path/to/test-worktree',
        branch='feature/test'
    )

    path = manager.get_worktree_path('test-worktree')
    assert path == '/path/to/test-worktree'

def test_cleanup_candidates_stale(temp_repo):
    """Test identifying stale worktrees for cleanup."""
    manager = WorktreeManager(str(temp_repo))

    # Create worktree with old lastActive
    manager.track_create(
        name='stale-worktree',
        path='/path/to/stale',
        branch='feature/stale'
    )

    # Manually set lastActive to 30 days ago
    from datetime import datetime, timedelta
    manager.config['worktrees']['stale-worktree']['lastActive'] = (
        datetime.now() - timedelta(days=30)
    ).isoformat()
    manager.save_config()

    candidates = manager.get_cleanup_candidates(stale_days=7)
    assert 'stale-worktree' in candidates
```

### Integration Tests

**File:** `skills/git-worktrees/tests/test_integration.sh`

```bash
#!/bin/bash
# Integration tests for worktree.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
WORKTREE_SCRIPT="$SCRIPT_DIR/../../scripts/worktree.sh"

# Setup test repository
setup_test_repo() {
    local test_dir=$(mktemp -d)
    cd "$test_dir"

    git init
    git config user.name "Test"
    git config user.email "test@test.com"

    echo "# Test" > README.md
    git add .
    git commit -m "Initial commit"

    echo "$test_dir"
}

# Cleanup
cleanup_test_repo() {
    local test_dir="$1"
    rm -rf "$test_dir"
}

# Test: Create feature worktree
test_create_feature() {
    echo "Testing: Create feature worktree"

    local test_repo=$(setup_test_repo)
    cd "$test_repo"

    # Mock work item fetching
    export MOCK_WORK_ITEM_TITLE="Add authentication"

    $WORKTREE_SCRIPT create branch test-feature --no-deps --ide none

    # Verify worktree exists
    if git worktree list | grep -q "test-feature"; then
        echo "✓ Feature worktree created"
    else
        echo "✗ Feature worktree not created"
        exit 1
    fi

    cleanup_test_repo "$test_repo"
}

# Test: List worktrees
test_list_worktrees() {
    echo "Testing: List worktrees"

    local test_repo=$(setup_test_repo)
    cd "$test_repo"

    $WORKTREE_SCRIPT create branch test-1 --no-deps --ide none
    $WORKTREE_SCRIPT create branch test-2 --no-deps --ide none

    local count=$($WORKTREE_SCRIPT list | grep -c "test-")

    if [[ "$count" -eq 2 ]]; then
        echo "✓ List shows correct worktrees"
    else
        echo "✗ List shows $count worktrees, expected 2"
        exit 1
    fi

    cleanup_test_repo "$test_repo"
}

# Test: Remove worktree
test_remove_worktree() {
    echo "Testing: Remove worktree"

    local test_repo=$(setup_test_repo)
    cd "$test_repo"

    $WORKTREE_SCRIPT create branch test-remove --no-deps --ide none

    # Remove with force (skip prompts)
    yes | $WORKTREE_SCRIPT remove test-remove --force

    if ! git worktree list | grep -q "test-remove"; then
        echo "✓ Worktree removed"
    else
        echo "✗ Worktree not removed"
        exit 1
    fi

    cleanup_test_repo "$test_repo"
}

# Run all tests
echo "Running integration tests..."
test_create_feature
test_list_worktrees
test_remove_worktree
echo "All tests passed!"
```

---

## Deployment & Setup

### Installation Script

**File:** `skills/git-worktrees/scripts/install.sh`

```bash
#!/bin/bash
# Install git-worktrees skill

set -e

CLAUDE_TOOLS_DIR="$HOME/source/tools/claude-tools"
SKILL_DIR="$CLAUDE_TOOLS_DIR/skills/git-worktrees"

echo "Installing git-worktrees skill..."

# Check prerequisites
echo "Checking prerequisites..."

# Git version
GIT_VERSION=$(git --version | grep -oE '[0-9]+\.[0-9]+' | head -1)
if [[ $(echo "$GIT_VERSION < 2.5" | bc) -eq 1 ]]; then
    echo "Error: Git 2.5+ required for worktree support"
    exit 1
fi

# Python 3
if ! command -v python3 &>/dev/null; then
    echo "Error: Python 3 required"
    exit 1
fi

echo "✓ Prerequisites met"

# Make scripts executable
echo "Setting up scripts..."
chmod +x "$CLAUDE_TOOLS_DIR/scripts/worktree.sh"
chmod +x "$SKILL_DIR/scripts/"*.py

echo "✓ Scripts ready"

# Add shell alias
echo "Adding shell alias..."

SHELL_RC="$HOME/.zshrc"
if [[ "$SHELL" == *"bash"* ]]; then
    SHELL_RC="$HOME/.bashrc"
fi

if ! grep -q "alias worktree=" "$SHELL_RC"; then
    echo "" >> "$SHELL_RC"
    echo "# Git worktrees skill" >> "$SHELL_RC"
    echo "alias worktree=\"$CLAUDE_TOOLS_DIR/scripts/worktree.sh\"" >> "$SHELL_RC"
    echo "✓ Alias added to $SHELL_RC"
else
    echo "✓ Alias already exists"
fi

echo ""
echo "Installation complete!"
echo ""
echo "To start using worktrees:"
echo "  1. Reload your shell: source $SHELL_RC"
echo "  2. Try: worktree create feature 1234"
echo ""
echo "Documentation: $SKILL_DIR/docs/"
```

### User Setup Checklist

1. **Install skill:**
   ```bash
   ./skills/git-worktrees/scripts/install.sh
   ```

2. **Reload shell:**
   ```bash
   source ~/.zshrc  # or ~/.bashrc
   ```

3. **Verify installation:**
   ```bash
   worktree --help
   ```

4. **Configure (optional):**
   ```bash
   worktree config worktree.defaultIDE code
   worktree config worktree.autoInstallDeps true
   ```

5. **Test:**
   ```bash
   cd your-repo
   worktree create branch test-worktree --no-deps
   worktree list
   worktree remove test-worktree --force
   ```

---

## Next Steps

1. **Implement core bash script** (`scripts/worktree.sh`)
2. **Implement Python helpers** (manager, dependencies, IDE launcher)
3. **Write comprehensive tests** (unit + integration)
4. **Create user documentation** (user-guide.md, troubleshooting.md)
5. **Create SKILL.md** (Claude integration instructions)
6. **Deploy and gather feedback**

This implementation guide provides all the patterns and code needed to build a production-ready git-worktrees skill that integrates seamlessly with your existing tooling.

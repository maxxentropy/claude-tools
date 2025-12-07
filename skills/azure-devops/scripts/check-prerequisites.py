#!/usr/bin/env python3
"""
check-prerequisites.py - Verify Azure DevOps prerequisites are met.

Checks:
1. Azure CLI is installed
2. Azure DevOps extension is installed
3. User is authenticated
4. (Optional) Can access specified organization

Usage:
    python check-prerequisites.py
    python check-prerequisites.py --org "https://dev.azure.com/val-controls"
"""

import argparse
import json
import subprocess
import sys


def check_az_cli() -> bool:
    """Check if Azure CLI is installed."""
    print("Checking Azure CLI installation...", end=" ")
    
    try:
        result = subprocess.run(
            ["az", "--version"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            # Extract version from first line
            version_line = result.stdout.split('\n')[0]
            print(f"✓ ({version_line.strip()})")
            return True
        else:
            print("✗")
            print("  Azure CLI not found or not working")
            return False
            
    except FileNotFoundError:
        print("✗")
        print("  Azure CLI not installed")
        print("  Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
        return False
    except subprocess.TimeoutExpired:
        print("✗")
        print("  Azure CLI command timed out")
        return False


def check_devops_extension() -> bool:
    """Check if Azure DevOps extension is installed."""
    print("Checking Azure DevOps extension...", end=" ")
    
    try:
        result = subprocess.run(
            ["az", "extension", "show", "--name", "azure-devops"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            ext_info = json.loads(result.stdout)
            version = ext_info.get("version", "unknown")
            print(f"✓ (v{version})")
            return True
        else:
            print("✗ (not installed)")
            print("  Install with: az extension add --name azure-devops")
            return False
            
    except Exception as e:
        print(f"✗ ({e})")
        return False


def check_authentication() -> bool:
    """Check if user is authenticated to Azure."""
    print("Checking Azure authentication...", end=" ")
    
    try:
        result = subprocess.run(
            ["az", "account", "show"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        if result.returncode == 0:
            account = json.loads(result.stdout)
            user = account.get("user", {}).get("name", "unknown")
            print(f"✓ ({user})")
            return True
        else:
            print("✗ (not logged in)")
            print("  Run: az login")
            return False
            
    except Exception as e:
        print(f"✗ ({e})")
        return False


def check_organization_access(org: str) -> bool:
    """Check if user can access the specified organization."""
    print(f"Checking organization access ({org})...", end=" ")
    
    try:
        result = subprocess.run(
            ["az", "devops", "project", "list",
             "--organization", org,
             "--output", "json"],
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0:
            projects = json.loads(result.stdout)
            count = len(projects) if isinstance(projects, list) else 0
            print(f"✓ ({count} projects accessible)")
            return True
        else:
            print("✗")
            error = result.stderr.strip()
            if "unauthorized" in error.lower() or "401" in error:
                print("  Not authorized to access this organization")
                print("  Verify you have access in Azure DevOps")
            else:
                print(f"  Error: {error[:100]}")
            return False
            
    except subprocess.TimeoutExpired:
        print("✗ (timeout)")
        print("  Request timed out - check network connectivity")
        return False
    except Exception as e:
        print(f"✗ ({e})")
        return False


def check_project_config() -> dict | None:
    """Check if local project configuration exists."""
    print("Checking local project configuration...", end=" ")
    
    from pathlib import Path
    config_path = Path(".ado/config.json")
    
    if config_path.exists():
        try:
            config = json.loads(config_path.read_text())
            project = config.get("project", "unknown")
            print(f"✓ (project: {project})")
            return config
        except Exception as e:
            print(f"✗ (invalid config: {e})")
            return None
    else:
        print("✗ (not configured)")
        print("  Run configuration wizard to set up this project")
        return None


def main():
    parser = argparse.ArgumentParser(
        description="Check Azure DevOps prerequisites."
    )
    parser.add_argument(
        "--org", "-o",
        help="Azure DevOps organization URL to verify access"
    )
    parser.add_argument(
        "--check-config",
        help="Also check for local project configuration",
        action="store_true"
    )
    
    args = parser.parse_args()
    
    print("=" * 50)
    print("Azure DevOps Prerequisites Check")
    print("=" * 50)
    print()
    
    all_passed = True
    
    # Core checks
    if not check_az_cli():
        all_passed = False
    
    if not check_devops_extension():
        all_passed = False
    
    if not check_authentication():
        all_passed = False
    
    # Optional: organization access
    if args.org:
        print()
        if not check_organization_access(args.org):
            all_passed = False
    
    # Optional: local config
    if args.check_config:
        print()
        config = check_project_config()
        if config and args.org is None:
            # If we have config but didn't check org, check it now
            org = config.get("organization")
            if org:
                print()
                if not check_organization_access(org):
                    all_passed = False
    
    print()
    print("=" * 50)
    
    if all_passed:
        print("✓ All prerequisites met")
        return 0
    else:
        print("✗ Some prerequisites not met")
        return 1


if __name__ == "__main__":
    sys.exit(main())

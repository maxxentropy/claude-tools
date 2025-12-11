#!/usr/bin/env python3
"""
check-prerequisites.py - Verify Azure DevOps prerequisites are met.

Usage:
    python check-prerequisites.py
    python check-prerequisites.py --org "https://dev.azure.com/org-name"
"""

import argparse
import json
import subprocess
import sys


def check_az_cli() -> bool:
    print("Checking Azure CLI installation...", end=" ")
    try:
        result = subprocess.run(["az", "--version"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            version_line = result.stdout.split('\n')[0]
            print(f"✓ ({version_line.strip()})")
            return True
        print("✗")
        return False
    except FileNotFoundError:
        print("✗ - Not installed")
        print("  Install from: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
        return False
    except subprocess.TimeoutExpired:
        print("✗ - Timed out")
        return False


def check_devops_extension() -> bool:
    print("Checking Azure DevOps extension...", end=" ")
    try:
        result = subprocess.run(
            ["az", "extension", "show", "--name", "azure-devops"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            ext_info = json.loads(result.stdout)
            print(f"✓ (v{ext_info.get('version', 'unknown')})")
            return True
        print("✗ - Not installed")
        print("  Install with: az extension add --name azure-devops")
        return False
    except Exception as e:
        print(f"✗ ({e})")
        return False


def check_authentication() -> bool:
    print("Checking Azure authentication...", end=" ")
    try:
        result = subprocess.run(["az", "account", "show"], capture_output=True, text=True, timeout=10)
        if result.returncode == 0:
            account = json.loads(result.stdout)
            user = account.get("user", {}).get("name", "unknown")
            print(f"✓ ({user})")
            return True
        print("✗ - Not logged in")
        print("  Run: az login")
        return False
    except Exception as e:
        print(f"✗ ({e})")
        return False


def check_organization_access(org: str) -> bool:
    print(f"Checking organization access ({org})...", end=" ")
    try:
        result = subprocess.run(
            ["az", "devops", "project", "list", "--organization", org, "--output", "json"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            projects = json.loads(result.stdout)
            print(f"✓ ({len(projects)} projects)")
            return True
        print("✗ - Access denied or invalid URL")
        return False
    except subprocess.TimeoutExpired:
        print("✗ - Timed out")
        return False
    except Exception as e:
        print(f"✗ ({e})")
        return False


def main():
    parser = argparse.ArgumentParser(description="Check Azure DevOps prerequisites.")
    parser.add_argument("--org", "-o", help="Azure DevOps organization URL to verify access")
    args = parser.parse_args()
    
    print("=" * 50)
    print("Azure DevOps Prerequisites Check")
    print("=" * 50)
    print()
    
    all_passed = True
    all_passed &= check_az_cli()
    all_passed &= check_devops_extension()
    all_passed &= check_authentication()
    
    if args.org:
        print()
        all_passed &= check_organization_access(args.org)
    
    print()
    print("=" * 50)
    print("✓ All prerequisites met" if all_passed else "✗ Some prerequisites not met")
    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())

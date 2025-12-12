#!/usr/bin/env python3
"""
check-prerequisites.py - Verify GitHub CLI setup for the github skill.

Checks:
1. GitHub CLI (gh) is installed
2. User is authenticated
3. Token has required scopes

Usage:
    python3 check-prerequisites.py
"""

import subprocess
import sys
import json
from typing import Tuple, Optional


def run_command(cmd: list[str]) -> Tuple[int, str, str]:
    """Run a command and return exit code, stdout, stderr."""
    try:
        result = subprocess.run(cmd, capture_output=True, text=True)
        return result.returncode, result.stdout, result.stderr
    except FileNotFoundError:
        return 1, "", f"Command not found: {cmd[0]}"


def check_gh_installed() -> Tuple[bool, str]:
    """Check if GitHub CLI is installed."""
    code, stdout, stderr = run_command(["gh", "--version"])
    if code == 0:
        version = stdout.split("\n")[0] if stdout else "unknown"
        return True, version
    return False, stderr


def check_gh_authenticated() -> Tuple[bool, str, Optional[str]]:
    """Check if user is authenticated with gh."""
    code, stdout, stderr = run_command(["gh", "auth", "status"])

    # gh auth status outputs to stderr even on success
    output = stderr if stderr else stdout

    if code == 0:
        # Extract username from output
        username = None
        for line in output.split("\n"):
            if "Logged in to github.com account" in line:
                # Format: "Logged in to github.com account USERNAME"
                parts = line.strip().split()
                if parts:
                    username = parts[-1].strip("()")
                break
            elif "as " in line.lower():
                # Alternative format
                parts = line.split("as ")
                if len(parts) > 1:
                    username = parts[1].split()[0].strip()
                break
        return True, output, username
    return False, output, None


def check_token_scopes() -> Tuple[bool, list[str]]:
    """Check token scopes."""
    code, stdout, stderr = run_command([
        "gh", "api", "user", "--jq", ".login"
    ])

    if code != 0:
        return False, []

    # If we can access /user, we have basic scopes
    # Check for additional scopes by testing endpoints
    scopes = ["user"]

    # Test repo scope
    code, _, _ = run_command(["gh", "repo", "list", "--limit", "1"])
    if code == 0:
        scopes.append("repo")

    # Test read:org scope
    code, _, _ = run_command(["gh", "api", "user/orgs", "--jq", "length"])
    if code == 0:
        scopes.append("read:org")

    return True, scopes


def check_rate_limit() -> Tuple[bool, dict]:
    """Check API rate limit status."""
    code, stdout, stderr = run_command([
        "gh", "api", "rate_limit", "--jq", ".rate"
    ])

    if code == 0:
        try:
            rate = json.loads(stdout)
            return True, rate
        except json.JSONDecodeError:
            return False, {}
    return False, {}


def main():
    print("GitHub Skill Prerequisites Check")
    print("=" * 40)

    all_passed = True

    # 1. Check gh installed
    print("\n1. GitHub CLI Installation")
    installed, version = check_gh_installed()
    if installed:
        print(f"   ✓ Installed: {version}")
    else:
        print(f"   ✗ Not installed")
        print(f"     Install: https://cli.github.com/")
        print(f"     macOS: brew install gh")
        print(f"     Windows: winget install GitHub.cli")
        all_passed = False
        # Can't continue without gh
        print("\n" + "=" * 40)
        print("FAILED: Install GitHub CLI to continue")
        return 1

    # 2. Check authentication
    print("\n2. Authentication")
    authenticated, output, username = check_gh_authenticated()
    if authenticated:
        print(f"   ✓ Authenticated as: {username or 'unknown'}")
    else:
        print(f"   ✗ Not authenticated")
        print(f"     Run: gh auth login")
        all_passed = False
        print("\n" + "=" * 40)
        print("FAILED: Run 'gh auth login' to authenticate")
        return 1

    # 3. Check token scopes
    print("\n3. Token Scopes")
    has_scopes, scopes = check_token_scopes()
    if has_scopes:
        print(f"   ✓ Available scopes: {', '.join(scopes)}")
        if "repo" not in scopes:
            print(f"   ! Warning: 'repo' scope missing - some features limited")
            print(f"     Run: gh auth refresh -s repo")
    else:
        print(f"   ! Could not verify scopes")

    # 4. Check rate limit
    print("\n4. API Rate Limit")
    has_rate, rate = check_rate_limit()
    if has_rate:
        remaining = rate.get("remaining", 0)
        limit = rate.get("limit", 0)
        print(f"   ✓ {remaining}/{limit} requests remaining")
        if remaining < 100:
            print(f"   ! Warning: Low rate limit remaining")
    else:
        print(f"   ! Could not check rate limit")

    # Summary
    print("\n" + "=" * 40)
    if all_passed:
        print("PASSED: All prerequisites met")
        print("\nYou can now use the github skill:")
        print("  python3 skills/github/scripts/query-issues.py --preset my-open")
        return 0
    else:
        print("FAILED: Some prerequisites not met")
        return 1


if __name__ == "__main__":
    sys.exit(main())

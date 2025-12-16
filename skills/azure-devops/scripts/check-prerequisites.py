#!/usr/bin/env python3
"""
check-prerequisites.py - Verify Azure DevOps prerequisites are met.

Checks:
1. Azure CLI installation and version
2. Azure DevOps extension installed
3. Azure authentication status
4. Organization access (optional)
5. Configuration file validity
6. Python requests library (optional, for batch API)

Usage:
    python check-prerequisites.py
    python check-prerequisites.py --org "https://dev.azure.com/org-name"
    python check-prerequisites.py --config .ado/config.json
"""

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Optional, Tuple


class Colors:
    """ANSI color codes for terminal output."""
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


def color(text: str, color_code: str) -> str:
    """Apply color to text if terminal supports it."""
    if sys.stdout.isatty():
        return f"{color_code}{text}{Colors.RESET}"
    return text


def check_mark(passed: bool) -> str:
    """Return colored check or X mark."""
    if passed:
        return color("✓", Colors.GREEN)
    return color("✗", Colors.RED)


def run_command(args: list, timeout: int = 30) -> Tuple[bool, str, str]:
    """Run command and return (success, stdout, stderr)."""
    try:
        result = subprocess.run(args, capture_output=True, text=True, timeout=timeout)
        return result.returncode == 0, result.stdout.strip(), result.stderr.strip()
    except FileNotFoundError:
        return False, "", "Command not found"
    except subprocess.TimeoutExpired:
        return False, "", "Command timed out"
    except Exception as e:
        return False, "", str(e)


def check_az_cli() -> Tuple[bool, Optional[str]]:
    """Check Azure CLI installation and return version."""
    print(f"  Checking Azure CLI installation...", end=" ")

    success, stdout, stderr = run_command(["az", "--version"])

    if not success:
        print(f"{check_mark(False)} Not installed")
        print(f"    {color('Install from:', Colors.CYAN)} https://docs.microsoft.com/en-us/cli/azure/install-azure-cli")
        return False, None

    # Extract version from first line
    version_line = stdout.split('\n')[0] if stdout else "unknown"
    version = version_line.replace("azure-cli", "").strip()
    print(f"{check_mark(True)} {color(version, Colors.CYAN)}")
    return True, version


def check_devops_extension() -> Tuple[bool, Optional[str]]:
    """Check Azure DevOps extension and return version."""
    print(f"  Checking Azure DevOps extension...", end=" ")

    success, stdout, stderr = run_command(
        ["az", "extension", "show", "--name", "azure-devops"]
    )

    if not success:
        print(f"{check_mark(False)} Not installed")
        print(f"    {color('Install with:', Colors.CYAN)} az extension add --name azure-devops")
        return False, None

    try:
        ext_info = json.loads(stdout)
        version = ext_info.get("version", "unknown")
        print(f"{check_mark(True)} v{color(version, Colors.CYAN)}")
        return True, version
    except json.JSONDecodeError:
        print(f"{check_mark(True)} (version unknown)")
        return True, None


def check_authentication() -> Tuple[bool, Optional[str]]:
    """Check Azure authentication and return user info."""
    print(f"  Checking Azure authentication...", end=" ")

    success, stdout, stderr = run_command(["az", "account", "show"])

    if not success:
        print(f"{check_mark(False)} Not logged in")
        print(f"    {color('Run:', Colors.CYAN)} az login")
        return False, None

    try:
        account = json.loads(stdout)
        user = account.get("user", {}).get("name", "unknown")
        tenant = account.get("tenantId", "")[:8] + "..." if account.get("tenantId") else ""
        print(f"{check_mark(True)} {color(user, Colors.CYAN)}")
        return True, user
    except json.JSONDecodeError:
        print(f"{check_mark(True)} (user unknown)")
        return True, None


def check_organization_access(org: str) -> Tuple[bool, int]:
    """Check organization access and return project count."""
    print(f"  Checking organization access...", end=" ")
    print(f"\n    URL: {color(org, Colors.CYAN)}", end=" ")

    success, stdout, stderr = run_command(
        ["az", "devops", "project", "list", "--organization", org, "--output", "json"],
        timeout=60
    )

    if not success:
        print(f"{check_mark(False)}")
        if "401" in stderr or "unauthorized" in stderr.lower():
            print(f"    {color('Error:', Colors.RED)} Authentication failed for this organization")
            print(f"    {color('Try:', Colors.CYAN)} az login --allow-no-subscriptions")
        elif "404" in stderr:
            print(f"    {color('Error:', Colors.RED)} Organization not found")
        else:
            print(f"    {color('Error:', Colors.RED)} {stderr[:200]}")
        return False, 0

    try:
        projects = json.loads(stdout)
        count = len(projects) if isinstance(projects, list) else 0
        print(f"{check_mark(True)} ({color(str(count), Colors.CYAN)} projects)")
        return True, count
    except json.JSONDecodeError:
        print(f"{check_mark(False)} Invalid response")
        return False, 0


def check_config_file(config_path: str) -> Tuple[bool, Optional[dict]]:
    """Check configuration file and return parsed config."""
    print(f"  Checking configuration file...", end=" ")
    print(f"\n    Path: {color(config_path, Colors.CYAN)}", end=" ")

    path = Path(config_path)
    if not path.exists():
        print(f"{check_mark(False)} Not found")
        print(f"    {color('Run configuration wizard to create', Colors.YELLOW)}")
        return False, None

    try:
        config = json.loads(path.read_text())

        # Validate required fields
        required = ["organization", "project"]
        missing = [f for f in required if f not in config]

        if missing:
            print(f"{check_mark(False)} Missing fields: {', '.join(missing)}")
            return False, None

        print(f"{check_mark(True)}")
        print(f"    Organization: {color(config['organization'], Colors.CYAN)}")
        print(f"    Project: {color(config['project'], Colors.CYAN)}")

        return True, config

    except json.JSONDecodeError as e:
        print(f"{check_mark(False)} Invalid JSON: {e}")
        return False, None


def check_requests_library() -> bool:
    """Check if requests library is available."""
    print(f"  Checking Python requests library...", end=" ")

    try:
        import requests
        print(f"{check_mark(True)} v{color(requests.__version__, Colors.CYAN)}")
        return True
    except ImportError:
        print(f"{color('○', Colors.YELLOW)} Not installed (optional)")
        print(f"    {color('Install with:', Colors.CYAN)} pip install requests")
        print(f"    {color('Note:', Colors.YELLOW)} Batch API will use CLI fallback")
        return False


def check_project_access(org: str, project: str) -> bool:
    """Check access to specific project."""
    print(f"  Checking project access...", end=" ")
    print(f"\n    Project: {color(project, Colors.CYAN)}", end=" ")

    success, stdout, stderr = run_command(
        ["az", "devops", "project", "show",
         "--organization", org,
         "--project", project,
         "--output", "json"],
        timeout=30
    )

    if not success:
        print(f"{check_mark(False)}")
        print(f"    {color('Error:', Colors.RED)} Cannot access project")
        return False

    print(f"{check_mark(True)}")
    return True


def main():
    parser = argparse.ArgumentParser(
        description="Check Azure DevOps prerequisites.",
        epilog="""
Examples:
  %(prog)s                                    # Basic checks
  %(prog)s --org https://dev.azure.com/myorg  # Check organization access
  %(prog)s --config .ado/config.json          # Check with config file
        """
    )
    parser.add_argument("--org", "-o",
                        help="Azure DevOps organization URL to verify access")
    parser.add_argument("--config", "-c",
                        help="Path to config file to validate")
    parser.add_argument("--verbose", "-v", action="store_true",
                        help="Show detailed output")
    parser.add_argument("--auth-only", action="store_true",
                        help="Quick auth check only - returns 0 if authenticated, 1 if not")
    parser.add_argument("--json", action="store_true",
                        help="Output results as JSON (for programmatic use)")
    args = parser.parse_args()

    # Quick auth-only check mode
    if args.auth_only:
        success, stdout, stderr = run_command(["az", "account", "show"])
        if args.json:
            import json as json_module
            result = {"authenticated": success}
            if success:
                try:
                    account = json_module.loads(stdout)
                    result["user"] = account.get("user", {}).get("name", "unknown")
                except:
                    pass
            else:
                result["error"] = "Not authenticated. Run: az login"
            print(json_module.dumps(result))
        else:
            if success:
                print("OK")
            else:
                print("NOT_AUTHENTICATED")
                print("Run: az login")
        return 0 if success else 1

    print()
    print(color("=" * 60, Colors.BOLD))
    print(color(" Azure DevOps Prerequisites Check", Colors.BOLD))
    print(color("=" * 60, Colors.BOLD))
    print()

    results = {}

    # Core prerequisites
    print(color("Core Prerequisites:", Colors.BOLD))
    results["az_cli"] = check_az_cli()[0]
    results["devops_ext"] = check_devops_extension()[0]
    results["auth"] = check_authentication()[0]
    print()

    # Optional: requests library
    print(color("Optional Dependencies:", Colors.BOLD))
    results["requests"] = check_requests_library()
    print()

    # Configuration check
    if args.config:
        print(color("Configuration:", Colors.BOLD))
        config_ok, config = check_config_file(args.config)
        results["config"] = config_ok

        if config_ok and config:
            # Also check org/project access
            org = config["organization"]
            project = config["project"]
            results["org_access"] = check_organization_access(org)[0]
            results["project_access"] = check_project_access(org, project)
        print()

    # Organization check (without config)
    elif args.org:
        print(color("Organization Access:", Colors.BOLD))
        results["org_access"] = check_organization_access(args.org)[0]
        print()

    # Summary
    print(color("=" * 60, Colors.BOLD))

    core_ok = results.get("az_cli", False) and results.get("devops_ext", False) and results.get("auth", False)
    config_ok = results.get("config", True)  # True if not checked
    access_ok = results.get("org_access", True) and results.get("project_access", True)  # True if not checked

    all_ok = core_ok and config_ok and access_ok

    if all_ok:
        print(color(" ✓ All prerequisites met", Colors.GREEN + Colors.BOLD))
        if not results.get("requests", True):
            print(color("   (requests library recommended for best performance)", Colors.YELLOW))
    else:
        print(color(" ✗ Some prerequisites not met", Colors.RED + Colors.BOLD))
        print()
        print(color("Issues found:", Colors.BOLD))
        if not results.get("az_cli", False):
            print(f"  - Azure CLI not installed")
        if not results.get("devops_ext", False):
            print(f"  - Azure DevOps extension not installed")
        if not results.get("auth", False):
            print(f"  - Not authenticated (run: az login)")
        if not results.get("config", True):
            print(f"  - Configuration file invalid or missing")
        if not results.get("org_access", True):
            print(f"  - Cannot access organization")
        if not results.get("project_access", True):
            print(f"  - Cannot access project")

    print(color("=" * 60, Colors.BOLD))
    print()

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Master image validation for XTConnect Pi nodes.

Runs comprehensive checks to verify a master image is ready for
provisioning new production nodes.

Usage:
    python3 master-image-verify.py                  # Full validation
    python3 master-image-verify.py --check docker   # Check specific component
    python3 master-image-verify.py --check serial
    python3 master-image-verify.py --check config
    python3 master-image-verify.py --check network
"""

import argparse
import json
import os
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pi_client import PiClient
from node_context import load_context, get_current_hostname, Colors, color


@dataclass
class CheckResult:
    """Result of a single validation check."""
    name: str
    passed: bool
    message: str
    details: Optional[str] = None


@dataclass
class ValidationReport:
    """Complete validation report."""
    hostname: str
    timestamp: str
    checks: list[CheckResult] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks)

    @property
    def passed_count(self) -> int:
        return sum(1 for c in self.checks if c.passed)

    @property
    def failed_count(self) -> int:
        return sum(1 for c in self.checks if not c.passed)


def check_ssh(client: PiClient) -> CheckResult:
    """Verify SSH connectivity."""
    connected, msg = client.test_connection()
    return CheckResult(
        name="SSH Connection",
        passed=connected,
        message="Connected successfully" if connected else msg
    )


def check_docker_service(client: PiClient) -> CheckResult:
    """Verify Docker service is running and enabled."""
    status = client.check_service_status("docker")

    if status.get("active") and status.get("enabled"):
        return CheckResult(
            name="Docker Service",
            passed=True,
            message="Running and enabled"
        )
    elif status.get("active"):
        return CheckResult(
            name="Docker Service",
            passed=False,
            message="Running but not enabled for boot"
        )
    else:
        return CheckResult(
            name="Docker Service",
            passed=False,
            message="Not running"
        )


def check_boot_manager(client: PiClient) -> CheckResult:
    """Verify boot manager service is configured."""
    status = client.check_service_status("xtconnect-boot-manager")

    if status.get("active") and status.get("enabled"):
        return CheckResult(
            name="Boot Manager Service",
            passed=True,
            message="Running and enabled"
        )
    elif status.get("enabled"):
        return CheckResult(
            name="Boot Manager Service",
            passed=True,
            message="Enabled (may not be active on master)"
        )
    else:
        return CheckResult(
            name="Boot Manager Service",
            passed=False,
            message="Not configured"
        )


def check_network_config(client: PiClient) -> CheckResult:
    """Verify network configuration."""
    # Check hostname
    result = client.run_command("hostname")
    hostname = result.stdout.strip() if result.success else "unknown"

    # Check network interfaces
    result = client.run_command("ip -o link show | grep -v 'lo:' | wc -l")
    interface_count = int(result.stdout.strip()) if result.success else 0

    # Check if connected to network
    result = client.run_command("ip route get 8.8.8.8 2>/dev/null && echo connected")
    has_route = "connected" in result.stdout

    details = f"Hostname: {hostname}, Interfaces: {interface_count}"

    if has_route:
        return CheckResult(
            name="Network Configuration",
            passed=True,
            message="Network connectivity verified",
            details=details
        )
    else:
        return CheckResult(
            name="Network Configuration",
            passed=False,
            message="No internet connectivity",
            details=details
        )


def check_disk_space(client: PiClient) -> CheckResult:
    """Verify adequate disk space."""
    disk = client.get_disk_usage()

    if not disk:
        return CheckResult(
            name="Disk Space",
            passed=False,
            message="Could not determine disk usage"
        )

    # Parse percentage
    use_percent = int(disk.get("use_percent", "100%").rstrip("%"))
    available = disk.get("available", "0")

    if use_percent < 80:
        return CheckResult(
            name="Disk Space",
            passed=True,
            message=f"{available} free ({100 - use_percent}% available)"
        )
    else:
        return CheckResult(
            name="Disk Space",
            passed=False,
            message=f"Low disk space: {available} free ({100 - use_percent}% available)"
        )


def check_serial_port(client: PiClient) -> CheckResult:
    """Verify serial port configuration."""
    port_status = client.get_serial_port_status()

    if not port_status.exists:
        return CheckResult(
            name="Serial Port",
            passed=False,
            message=f"{port_status.device_path} not found",
            details="USB-serial adapter may not be connected"
        )

    details = f"Device: {port_status.symlink_target or port_status.device_path}"
    if port_status.device_info:
        details += f", {port_status.device_info}"

    return CheckResult(
        name="Serial Port",
        passed=True,
        message="Device present and configured",
        details=details
    )


def check_udev_rules(client: PiClient) -> CheckResult:
    """Verify udev rules for serial port symlink."""
    result = client.run_command("test -f /etc/udev/rules.d/99-xtconnect.rules && echo exists")

    if "exists" in result.stdout:
        # Check rule content
        rule_content = client.get_file("/etc/udev/rules.d/99-xtconnect.rules")
        if rule_content and "xtconnect-serial" in rule_content:
            return CheckResult(
                name="udev Rules",
                passed=True,
                message="Serial port symlink rule configured"
            )
        else:
            return CheckResult(
                name="udev Rules",
                passed=False,
                message="Rule file exists but may be misconfigured"
            )
    else:
        return CheckResult(
            name="udev Rules",
            passed=False,
            message="/etc/udev/rules.d/99-xtconnect.rules not found"
        )


def check_config_directory(client: PiClient) -> CheckResult:
    """Verify config directory structure."""
    checks = []

    # Check /data directory exists
    if client.dir_exists("/data"):
        checks.append("✓ /data")
    else:
        checks.append("✗ /data missing")

    # Check /data/config exists
    if client.dir_exists("/data/config"):
        checks.append("✓ /data/config")
    else:
        checks.append("✗ /data/config missing")

    # For master image, config files may not exist yet (auto-generated on first boot)
    # But the directory structure should be present

    all_passed = all("✓" in c for c in checks)

    return CheckResult(
        name="Config Directory",
        passed=all_passed,
        message="Directory structure ready" if all_passed else "Missing directories",
        details=", ".join(checks)
    )


def check_docker_images(client: PiClient) -> CheckResult:
    """Check if Docker images are available."""
    result = client.run_command("docker images --format '{{.Repository}}:{{.Tag}}' | grep -i xtconnect")

    if result.success and result.stdout:
        images = result.stdout.strip().split("\n")
        return CheckResult(
            name="Docker Images",
            passed=True,
            message=f"{len(images)} image(s) available",
            details=", ".join(images[:3])  # Show first 3
        )
    else:
        # Images might be pulled on first boot by boot manager
        return CheckResult(
            name="Docker Images",
            passed=True,
            message="No pre-pulled images (will be pulled on first boot)"
        )


def check_docker_compose(client: PiClient) -> CheckResult:
    """Check for Docker Compose configuration."""
    compose_paths = [
        "/data/docker-compose.yml",
        "/data/docker-compose.prod.yml",
        "/home/pi/docker-compose.yml"
    ]

    found = []
    for path in compose_paths:
        if client.file_exists(path):
            found.append(path)

    if found:
        return CheckResult(
            name="Docker Compose",
            passed=True,
            message=f"Found {len(found)} compose file(s)",
            details=", ".join(found)
        )
    else:
        return CheckResult(
            name="Docker Compose",
            passed=True,
            message="No compose files (boot manager handles container lifecycle)"
        )


def check_readonly_scripts(client: PiClient) -> CheckResult:
    """Check for read-only filesystem toggle scripts."""
    scripts = [
        "/usr/local/bin/set-readonly.sh",
        "/usr/local/bin/set-writable.sh"
    ]

    found = []
    for script in scripts:
        result = client.run_command(f"test -x {script} && echo exists")
        if "exists" in result.stdout:
            found.append(os.path.basename(script))

    if len(found) == 2:
        return CheckResult(
            name="Read-Only Scripts",
            passed=True,
            message="Filesystem toggle scripts installed"
        )
    elif found:
        return CheckResult(
            name="Read-Only Scripts",
            passed=False,
            message=f"Partial: only {', '.join(found)} found"
        )
    else:
        return CheckResult(
            name="Read-Only Scripts",
            passed=False,
            message="Toggle scripts not installed"
        )


def run_full_validation(client: PiClient) -> ValidationReport:
    """Run all validation checks."""
    hostname = client.hostname

    report = ValidationReport(
        hostname=hostname,
        timestamp=datetime.now().isoformat()
    )

    print(f"{color('Master Image Validation:', Colors.BOLD)} {hostname}")
    print("=" * 50)
    print()

    # System checks
    print(f"{color('System Checks:', Colors.BOLD)}")

    checks = [
        ("SSH", check_ssh),
        ("Docker Service", check_docker_service),
        ("Boot Manager", check_boot_manager),
        ("Network", check_network_config),
        ("Disk Space", check_disk_space),
    ]

    for name, check_func in checks:
        result = check_func(client)
        report.checks.append(result)
        status = color("✓", Colors.GREEN) if result.passed else color("✗", Colors.RED)
        print(f"  {status} {result.name}: {result.message}")
        if result.details:
            print(f"      {color(result.details, Colors.DIM)}")

    # Application checks
    print()
    print(f"{color('Application Checks:', Colors.BOLD)}")

    app_checks = [
        ("Serial Port", check_serial_port),
        ("udev Rules", check_udev_rules),
        ("Config Directory", check_config_directory),
        ("Docker Images", check_docker_images),
        ("Docker Compose", check_docker_compose),
        ("Read-Only Scripts", check_readonly_scripts),
    ]

    for name, check_func in app_checks:
        result = check_func(client)
        report.checks.append(result)
        status = color("✓", Colors.GREEN) if result.passed else color("✗", Colors.RED)
        print(f"  {status} {result.name}: {result.message}")
        if result.details:
            print(f"      {color(result.details, Colors.DIM)}")

    # Summary
    print()
    print("=" * 50)
    if report.passed:
        print(f"Validation Result: {color('PASSED', Colors.GREEN)}")
        print("Master image ready for provisioning")
    else:
        print(f"Validation Result: {color('FAILED', Colors.RED)}")
        print(f"  Passed: {report.passed_count}")
        print(f"  Failed: {report.failed_count}")
        print()
        print("Failed checks:")
        for check in report.checks:
            if not check.passed:
                print(f"  - {check.name}: {check.message}")

    return report


def run_single_check(client: PiClient, check_name: str) -> bool:
    """Run a single validation check by name."""
    check_map = {
        "ssh": check_ssh,
        "docker": check_docker_service,
        "boot": check_boot_manager,
        "network": check_network_config,
        "disk": check_disk_space,
        "serial": check_serial_port,
        "udev": check_udev_rules,
        "config": check_config_directory,
        "images": check_docker_images,
        "compose": check_docker_compose,
        "readonly": check_readonly_scripts,
    }

    check_func = check_map.get(check_name.lower())
    if not check_func:
        print(color(f"Unknown check: {check_name}", Colors.RED))
        print(f"Available checks: {', '.join(check_map.keys())}")
        return False

    result = check_func(client)

    status = color("✓ PASSED", Colors.GREEN) if result.passed else color("✗ FAILED", Colors.RED)
    print(f"{result.name}: {status}")
    print(f"  {result.message}")
    if result.details:
        print(f"  {result.details}")

    return result.passed


def main():
    parser = argparse.ArgumentParser(
        description="Validate XTConnect master image for provisioning"
    )
    parser.add_argument(
        "--check", "-c",
        metavar="NAME",
        help="Run specific check (ssh, docker, serial, config, network, etc.)"
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output results as JSON"
    )
    parser.add_argument(
        "hostname",
        nargs="?",
        default="xtconnect-master.local",
        help="Target hostname (default: xtconnect-master.local)"
    )

    args = parser.parse_args()
    context = load_context()

    # Use provided hostname or default to master
    hostname = args.hostname

    # Normalize hostname
    if not hostname.endswith(".local") and "." not in hostname:
        hostname = f"{hostname}.local"

    # Create client
    ssh_config = context.get("ssh_config", {})
    client = PiClient(
        hostname=hostname,
        user=ssh_config.get("user", "pi"),
        key_path=os.path.expanduser(ssh_config.get("key_path", "~/.ssh/id_rsa")),
        timeout=ssh_config.get("timeout", 10)
    )

    # Run validation
    if args.check:
        success = run_single_check(client, args.check)
        sys.exit(0 if success else 1)
    else:
        report = run_full_validation(client)

        if args.json:
            print()
            print(json.dumps({
                "hostname": report.hostname,
                "timestamp": report.timestamp,
                "passed": report.passed,
                "checks": [
                    {
                        "name": c.name,
                        "passed": c.passed,
                        "message": c.message,
                        "details": c.details
                    }
                    for c in report.checks
                ]
            }, indent=2))

        sys.exit(0 if report.passed else 1)


if __name__ == "__main__":
    main()

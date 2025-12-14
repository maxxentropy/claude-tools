#!/usr/bin/env python3
"""
SSH connection testing and management for XTConnect Pi nodes.

Tests connectivity, Docker status, and overall health of a Pi node.

Usage:
    python3 connect.py --test           # Test connection to current node
    python3 connect.py --test HOST      # Test specific hostname
    python3 connect.py --ssh            # Open interactive SSH session
    python3 connect.py --ssh HOST       # SSH to specific hostname
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pi_client import PiClient
from node_context import load_context, get_current_hostname, Colors, color


def test_connection(hostname: str, context: dict, verbose: bool = False) -> bool:
    """
    Test connection to a Pi node and report status.

    Returns True if all checks pass.
    """
    ssh_config = context.get("ssh_config", {})
    client = PiClient(
        hostname=hostname,
        user=ssh_config.get("user", "pi"),
        key_path=os.path.expanduser(ssh_config.get("key_path", "~/.ssh/id_rsa")),
        timeout=ssh_config.get("timeout", 10)
    )

    print(f"Testing connection to {color(hostname, Colors.CYAN)}...")
    print()

    all_passed = True

    # Test 1: SSH connection
    connected, msg = client.test_connection()
    if connected:
        print(f"  SSH: {color('✓', Colors.GREEN)} Connected")
    else:
        print(f"  SSH: {color('✗', Colors.RED)} {msg}")
        all_passed = False
        # Can't continue without SSH
        print()
        print(f"Connection Status: {color('FAILED', Colors.RED)}")
        return False

    # Test 2: Docker service
    docker_status = client.check_service_status("docker")
    if docker_status.get("active"):
        print(f"  Docker: {color('✓', Colors.GREEN)} Running")
    else:
        print(f"  Docker: {color('✗', Colors.RED)} Not running")
        all_passed = False

    # Test 3: Container status
    containers = client.docker_ps()
    xtconnect_container = next(
        (c for c in containers if "xtconnect" in c.name.lower()),
        None
    )
    if xtconnect_container:
        health = client.docker_health(xtconnect_container.name)
        health_status = f" ({health})" if health else ""
        print(f"  Container: {color('✓', Colors.GREEN)} {xtconnect_container.name} (RUNNING{health_status})")
    else:
        print(f"  Container: {color('✗', Colors.YELLOW)} No xtconnect container running")
        # Not a failure, might be expected during setup

    # Test 4: Serial port
    port_status = client.get_serial_port_status()
    if port_status.exists:
        status_str = "OPEN" if port_status.is_open else "AVAILABLE"
        target = f" → {port_status.symlink_target}" if port_status.symlink_target else ""
        print(f"  Serial: {color('✓', Colors.GREEN)} {port_status.device_path} ({status_str}){target}")
    else:
        print(f"  Serial: {color('✗', Colors.YELLOW)} {port_status.device_path} not found")

    # Additional info if verbose
    if verbose:
        print()
        print(f"{color('System Info:', Colors.BOLD)}")

        # Uptime
        uptime = client.get_uptime()
        if uptime:
            print(f"  Uptime: {uptime}")

        # Memory
        memory = client.get_memory_usage()
        if memory:
            total = memory.get("total_mb", 0)
            used = memory.get("used_mb", 0)
            print(f"  Memory: {used} MB / {total} MB")

        # Disk
        disk = client.get_disk_usage()
        if disk:
            print(f"  Disk: {disk.get('used')} / {disk.get('total')} ({disk.get('use_percent')} used)")

        # CPU
        cpu = client.get_cpu_usage()
        if cpu is not None:
            print(f"  CPU: {cpu:.1f}%")

        # Node info
        node_info = client.get_node_info()
        if node_info:
            print()
            print(f"{color('Node Info:', Colors.BOLD)}")
            print(f"  Node ID: {node_info.get('nodeId', 'Unknown')}")
            print(f"  Hostname: {node_info.get('hostname', 'Unknown')}")
            if node_info.get("serialNumber"):
                print(f"  Serial: {node_info.get('serialNumber')}")

    print()
    if all_passed:
        print(f"Connection Status: {color('HEALTHY', Colors.GREEN)}")
    else:
        print(f"Connection Status: {color('DEGRADED', Colors.YELLOW)}")

    return all_passed


def open_ssh_session(hostname: str, context: dict) -> None:
    """Open an interactive SSH session to the Pi."""
    ssh_config = context.get("ssh_config", {})
    user = ssh_config.get("user", "pi")
    key_path = os.path.expanduser(ssh_config.get("key_path", "~/.ssh/id_rsa"))

    print(f"Connecting to {color(hostname, Colors.CYAN)}...")
    print(f"(Use 'exit' or Ctrl+D to disconnect)")
    print()

    # Build SSH command
    cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-i", key_path,
        f"{user}@{hostname}"
    ]

    # Replace current process with SSH
    os.execvp("ssh", cmd)


def run_command(hostname: str, command: str, context: dict) -> int:
    """Run a single command on the Pi and return exit code."""
    ssh_config = context.get("ssh_config", {})
    client = PiClient(
        hostname=hostname,
        user=ssh_config.get("user", "pi"),
        key_path=os.path.expanduser(ssh_config.get("key_path", "~/.ssh/id_rsa")),
        timeout=ssh_config.get("timeout", 10)
    )

    result = client.run_command(command, timeout=60)
    if result.stdout:
        print(result.stdout)
    if result.stderr and not result.success:
        print(result.stderr, file=sys.stderr)

    return result.exit_code


def main():
    parser = argparse.ArgumentParser(
        description="Test and manage SSH connections to XTConnect Pi nodes"
    )
    parser.add_argument(
        "--test", "-t",
        nargs="?",
        const=True,
        metavar="HOSTNAME",
        help="Test connection (current node or specified hostname)"
    )
    parser.add_argument(
        "--ssh", "-s",
        nargs="?",
        const=True,
        metavar="HOSTNAME",
        help="Open interactive SSH session"
    )
    parser.add_argument(
        "--run", "-r",
        metavar="COMMAND",
        help="Run a single command on the Pi"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed system information"
    )
    parser.add_argument(
        "hostname",
        nargs="?",
        help="Target hostname (uses current context if not specified)"
    )

    args = parser.parse_args()
    context = load_context()

    # Determine target hostname
    hostname = None
    if args.hostname:
        hostname = args.hostname
    elif isinstance(args.test, str):
        hostname = args.test
    elif isinstance(args.ssh, str):
        hostname = args.ssh
    else:
        hostname = get_current_hostname()

    if not hostname:
        print(color("No target node specified.", Colors.RED))
        print("Use --set to configure current node or specify hostname.")
        sys.exit(1)

    # Normalize hostname
    if not hostname.endswith(".local") and "." not in hostname:
        hostname = f"{hostname}.local"
    if not hostname.startswith("xtconnect-") and hostname.endswith(".local"):
        hostname = f"xtconnect-{hostname}"

    # Execute requested action
    if args.test:
        success = test_connection(hostname, context, verbose=args.verbose)
        sys.exit(0 if success else 1)
    elif args.ssh:
        open_ssh_session(hostname, context)
    elif args.run:
        exit_code = run_command(hostname, args.run, context)
        sys.exit(exit_code)
    else:
        # Default: test connection
        success = test_connection(hostname, context, verbose=args.verbose)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

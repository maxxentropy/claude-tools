#!/usr/bin/env python3
"""
Deployment verification for XTConnect Pi nodes.

Check deployment status, view logs, and inspect configuration
of a deployed XTConnect node.

Usage:
    python3 check-deployment.py                    # Full status check
    python3 check-deployment.py --logs             # View recent logs
    python3 check-deployment.py --logs --follow    # Follow logs
    python3 check-deployment.py --config           # View configuration
    python3 check-deployment.py --config --diff    # Compare with local
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pi_client import PiClient
from node_context import load_context, get_current_hostname, Colors, color


def show_deployment_status(client: PiClient, verbose: bool = False) -> bool:
    """Display comprehensive deployment status."""
    hostname = client.hostname

    print(f"{color('Deployment Status:', Colors.BOLD)} {hostname}")
    print("=" * 50)
    print()

    # Container status
    print(f"{color('Container:', Colors.BOLD)}")
    containers = client.docker_ps()
    xtconnect_container = next(
        (c for c in containers if "xtconnect" in c.name.lower()),
        None
    )

    if xtconnect_container:
        health = client.docker_health(xtconnect_container.name)
        health_str = f" ({health})" if health else ""

        print(f"  Name: {xtconnect_container.name}")
        print(f"  Image: {xtconnect_container.image}")
        print(f"  Status: {color('RUNNING', Colors.GREEN)}{health_str}")
        print(f"  Uptime: {xtconnect_container.uptime}")

        # Get container details
        result = client.run_command(
            f"docker inspect --format='{{{{.Created}}}}' {xtconnect_container.name}"
        )
        if result.success:
            print(f"  Created: {result.stdout[:19]}")
    else:
        print(f"  Status: {color('NOT RUNNING', Colors.RED)}")
        print("  No xtconnect container found")

    # Node configuration
    print()
    print(f"{color('Configuration:', Colors.BOLD)}")

    node_info = client.get_node_info()
    if node_info:
        print(f"  Node ID: {node_info.get('nodeId', 'Unknown')}")
        print(f"  Hostname: {node_info.get('hostname', 'Unknown')}")
        if node_info.get("serialNumber"):
            print(f"  Pi Serial: {node_info.get('serialNumber')}")
    else:
        print(f"  {color('node-info.json not found', Colors.YELLOW)}")

    # Check config files
    config_files = [
        ("/data/config/appsettings.json", "App Settings"),
        ("/data/config/node-info.json", "Node Info"),
    ]

    for path, name in config_files:
        if client.file_exists(path):
            print(f"  {color('✓', Colors.GREEN)} {name}: {path}")
        else:
            print(f"  {color('✗', Colors.YELLOW)} {name}: not found")

    # Serial port
    port_status = client.get_serial_port_status()
    if port_status.exists:
        status = "OPEN" if port_status.is_open else "AVAILABLE"
        print(f"  Serial Port: {port_status.device_path} ({status})")
    else:
        print(f"  Serial Port: {color('NOT FOUND', Colors.YELLOW)}")

    # System resources
    print()
    print(f"{color('Performance:', Colors.BOLD)}")

    cpu = client.get_cpu_usage()
    if cpu is not None:
        print(f"  CPU: {cpu:.1f}%")

    memory = client.get_memory_usage()
    if memory:
        total = memory.get("total_mb", 0)
        used = memory.get("used_mb", 0)
        percent = (used / total * 100) if total > 0 else 0
        print(f"  Memory: {used} MB / {total} MB ({percent:.0f}%)")

    disk = client.get_disk_usage()
    if disk:
        print(f"  Disk: {disk.get('used')} / {disk.get('total')} ({disk.get('use_percent')} used)")

    uptime = client.get_uptime()
    if uptime:
        print(f"  System Uptime: {uptime}")

    # Recent activity (from logs)
    print()
    print(f"{color('Recent Activity:', Colors.BOLD)}")

    if xtconnect_container:
        # Check for recent poll/upload activity
        result = client.run_command(
            f"docker logs --tail 50 {xtconnect_container.name} 2>&1 | "
            "grep -i -E '(poll|upload|collected|sent)' | tail -3"
        )
        if result.stdout:
            for line in result.stdout.strip().split("\n"):
                if line.strip():
                    # Truncate long lines
                    display = line[:80] + "..." if len(line) > 80 else line
                    print(f"  {display}")
        else:
            print(f"  {color('No recent activity found in logs', Colors.DIM)}")

        # Check for errors
        result = client.run_command(
            f"docker logs --since 24h {xtconnect_container.name} 2>&1 | "
            "grep -i -c error || echo 0"
        )
        error_count = int(result.stdout.strip()) if result.success else 0
        if error_count > 0:
            print(f"  {color(f'Errors (24h): {error_count}', Colors.YELLOW)}")
        else:
            print(f"  Errors (24h): {color('0', Colors.GREEN)}")

    return True


def show_logs(
    client: PiClient,
    lines: int = 50,
    follow: bool = False,
    level: Optional[str] = None,
    since: Optional[str] = None,
    export_file: Optional[str] = None
) -> None:
    """Display or export container logs."""
    containers = client.docker_ps()
    container = next(
        (c for c in containers if "xtconnect" in c.name.lower()),
        None
    )

    if not container:
        print(color("No xtconnect container found", Colors.RED))
        return

    container_name = container.name

    # Build docker logs command
    cmd_parts = ["docker", "logs"]

    if since:
        cmd_parts.extend(["--since", since])
    else:
        cmd_parts.extend(["--tail", str(lines)])

    if follow:
        cmd_parts.append("-f")

    cmd_parts.append(container_name)
    cmd_parts.append("2>&1")

    # Add level filter if specified
    if level:
        level_filter = f" | grep -i '{level}'"
        cmd = " ".join(cmd_parts) + level_filter
    else:
        cmd = " ".join(cmd_parts)

    if export_file:
        # Export to file
        print(f"Exporting logs to {export_file}...")
        result = client.run_command(cmd, timeout=60)
        if result.success:
            with open(export_file, "w") as f:
                f.write(f"# Logs from {client.hostname}\n")
                f.write(f"# Container: {container_name}\n")
                f.write(f"# Exported: {datetime.now().isoformat()}\n")
                f.write("#\n")
                f.write(result.stdout)
            print(f"Exported {len(result.stdout.split(chr(10)))} lines to {export_file}")
        else:
            print(color(f"Error: {result.stderr}", Colors.RED))
    elif follow:
        # Stream logs
        print(f"Following logs from {color(container_name, Colors.CYAN)}...")
        print("Press Ctrl+C to stop")
        print("-" * 60)

        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={client.timeout}",
            "-i", client.key_path,
            f"{client.user}@{client.hostname}",
            cmd
        ]

        try:
            subprocess.run(ssh_cmd)
        except KeyboardInterrupt:
            print()
            print(color("Stopped following logs", Colors.DIM))
    else:
        # Show logs
        result = client.run_command(cmd, timeout=30)
        if result.success:
            print(result.stdout)
        else:
            print(color(f"Error: {result.stderr}", Colors.RED))


def show_config(client: PiClient, diff: bool = False) -> None:
    """Display configuration from the Pi."""
    print(f"{color('Configuration Files:', Colors.BOLD)}")
    print()

    # appsettings.json
    print(f"{color('/data/config/appsettings.json:', Colors.CYAN)}")
    config = client.get_app_config()
    if config:
        # Redact sensitive values
        if "ApiKey" in str(config):
            config_str = json.dumps(config, indent=2)
            # Simple redaction
            import re
            config_str = re.sub(
                r'"(ApiKey|BearerToken|Password|Secret)":\s*"[^"]*"',
                r'"\1": "***REDACTED***"',
                config_str
            )
            print(config_str)
        else:
            print(json.dumps(config, indent=2))
    else:
        print(color("  File not found or invalid JSON", Colors.YELLOW))

    print()

    # node-info.json
    print(f"{color('/data/config/node-info.json:', Colors.CYAN)}")
    node_info = client.get_node_info()
    if node_info:
        print(json.dumps(node_info, indent=2))
    else:
        print(color("  File not found or invalid JSON", Colors.YELLOW))

    # Diff with local if requested
    if diff:
        print()
        print(f"{color('Comparing with local project:', Colors.BOLD)}")

        # Try to find local project
        local_paths = [
            Path.home() / "source/projects/xtconnect.nodeservice",
            Path.cwd() / "xtconnect.nodeservice",
            Path.cwd()
        ]

        local_config = None
        for path in local_paths:
            config_file = path / "src/XTConnect.Node/appsettings.json"
            if config_file.exists():
                try:
                    local_config = json.loads(config_file.read_text())
                    print(f"  Local: {config_file}")
                    break
                except json.JSONDecodeError:
                    pass

        if local_config and config:
            # Simple key comparison
            remote_keys = set(_flatten_keys(config))
            local_keys = set(_flatten_keys(local_config))

            only_remote = remote_keys - local_keys
            only_local = local_keys - remote_keys

            if only_remote:
                print(f"  {color('Keys only in remote:', Colors.YELLOW)}")
                for key in sorted(only_remote)[:10]:
                    print(f"    + {key}")

            if only_local:
                print(f"  {color('Keys only in local:', Colors.CYAN)}")
                for key in sorted(only_local)[:10]:
                    print(f"    - {key}")

            if not only_remote and not only_local:
                print(f"  {color('Configuration keys match', Colors.GREEN)}")
        else:
            print(color("  Could not find local project for comparison", Colors.DIM))


def _flatten_keys(d: dict, prefix: str = "") -> list[str]:
    """Flatten nested dict keys for comparison."""
    keys = []
    for k, v in d.items():
        full_key = f"{prefix}.{k}" if prefix else k
        keys.append(full_key)
        if isinstance(v, dict):
            keys.extend(_flatten_keys(v, full_key))
    return keys


def restart_container(client: PiClient) -> bool:
    """Restart the xtconnect container."""
    containers = client.docker_ps()
    container = next(
        (c for c in containers if "xtconnect" in c.name.lower()),
        None
    )

    if not container:
        print(color("No xtconnect container found", Colors.RED))
        return False

    print(f"Restarting {container.name}...")
    success = client.docker_restart(container.name)

    if success:
        print(color("Container restarted successfully", Colors.GREEN))
    else:
        print(color("Failed to restart container", Colors.RED))

    return success


def main():
    parser = argparse.ArgumentParser(
        description="Check deployment status of XTConnect Pi nodes"
    )
    parser.add_argument(
        "--logs", "-l",
        action="store_true",
        help="View container logs"
    )
    parser.add_argument(
        "--follow", "-f",
        action="store_true",
        help="Follow logs (tail -f style)"
    )
    parser.add_argument(
        "--lines", "-n",
        type=int,
        default=50,
        help="Number of log lines to show (default: 50)"
    )
    parser.add_argument(
        "--level",
        choices=["DEBUG", "INFO", "WARN", "ERROR"],
        help="Filter logs by level"
    )
    parser.add_argument(
        "--since",
        help="Show logs since duration (e.g., 24h, 30m)"
    )
    parser.add_argument(
        "--export",
        metavar="FILE",
        help="Export logs to file"
    )
    parser.add_argument(
        "--config", "-c",
        action="store_true",
        help="View configuration files"
    )
    parser.add_argument(
        "--diff",
        action="store_true",
        help="Compare remote config with local project"
    )
    parser.add_argument(
        "--restart",
        action="store_true",
        help="Restart the container"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="Show detailed information"
    )
    parser.add_argument(
        "hostname",
        nargs="?",
        help="Target hostname (uses current context if not specified)"
    )

    args = parser.parse_args()
    context = load_context()

    # Determine target hostname
    hostname = args.hostname or get_current_hostname()

    if not hostname:
        print(color("No target node specified.", Colors.RED))
        print("Use node-context.py --set to configure current node.")
        sys.exit(1)

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

    # Test connection first
    connected, msg = client.test_connection()
    if not connected:
        print(color(f"Cannot connect to {hostname}: {msg}", Colors.RED))
        sys.exit(1)

    # Execute requested action
    if args.logs:
        show_logs(
            client,
            lines=args.lines,
            follow=args.follow,
            level=args.level,
            since=args.since,
            export_file=args.export
        )
    elif args.config:
        show_config(client, diff=args.diff)
    elif args.restart:
        success = restart_container(client)
        sys.exit(0 if success else 1)
    else:
        show_deployment_status(client, verbose=args.verbose)


if __name__ == "__main__":
    main()

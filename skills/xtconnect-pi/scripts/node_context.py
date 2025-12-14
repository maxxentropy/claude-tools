#!/usr/bin/env python3
"""
Node context management for XTConnect Pi debugging.

Tracks current node connection, history, and SSH configuration.
State is stored in .xtconnect/context.json in the project root.

Usage:
    python3 node-context.py                    # Show current context
    python3 node-context.py --discover         # Discover nodes on network
    python3 node-context.py --set HOSTNAME     # Set current node
    python3 node-context.py --set -            # Switch to previous node
    python3 node-context.py --history          # Show connection history
    python3 node-context.py --config           # Show/modify SSH config
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pi_client import PiClient, NodeInfo, discover_nodes, resolve_hostname


# ANSI colors for terminal output
class Colors:
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    CYAN = "\033[96m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def color(text: str, c: str) -> str:
    """Wrap text in ANSI color codes."""
    return f"{c}{text}{Colors.RESET}"


def find_context_dir() -> Path:
    """Find or create the .xtconnect directory in project root."""
    # Walk up from current directory looking for .git or use cwd
    cwd = Path.cwd()
    check_dir = cwd

    while check_dir != check_dir.parent:
        if (check_dir / ".git").exists():
            context_dir = check_dir / ".xtconnect"
            context_dir.mkdir(exist_ok=True)
            return context_dir
        check_dir = check_dir.parent

    # No git repo found, use current directory
    context_dir = cwd / ".xtconnect"
    context_dir.mkdir(exist_ok=True)
    return context_dir


def get_default_ssh_key() -> str:
    """Determine the best default SSH key for XTConnect Pi nodes."""
    # Prefer xtconnect_pi key if it exists
    preferred_keys = [
        "~/.ssh/xtconnect_pi",
        "~/.ssh/xtconnect",
        "~/.ssh/id_ed25519",
        "~/.ssh/id_rsa",
    ]
    for key_path in preferred_keys:
        expanded = os.path.expanduser(key_path)
        if os.path.exists(expanded):
            return key_path
    return "~/.ssh/id_rsa"


def load_context() -> dict:
    """Load the current context from file."""
    context_file = find_context_dir() / "context.json"
    if context_file.exists():
        try:
            return json.loads(context_file.read_text())
        except json.JSONDecodeError:
            pass

    # Create new context with best available SSH key
    return {
        "version": "1.0",
        "current_node": None,
        "ssh_config": {
            "key_path": get_default_ssh_key(),
            "user": "pi",
            "timeout": 10
        },
        "recent_nodes": []
    }


def save_context(context: dict) -> None:
    """Save the context to file."""
    context_file = find_context_dir() / "context.json"
    context_file.write_text(json.dumps(context, indent=2))


def get_current_hostname() -> Optional[str]:
    """Get the current node hostname from environment or context."""
    # Priority 1: Environment variable
    env_node = os.environ.get("XTCONNECT_NODE")
    if env_node:
        return env_node

    # Priority 2: Context file
    context = load_context()
    if context.get("current_node"):
        return context["current_node"].get("hostname")

    return None


def show_current_context(context: dict) -> None:
    """Display the current connection context."""
    current = context.get("current_node")

    if not current:
        print(color("No current node context set.", Colors.YELLOW))
        print("\nUse --discover to find nodes or --set to specify a hostname.")
        return

    hostname = current.get("hostname", "Unknown")
    node_id = current.get("node_id", "Unknown")
    last_connected = current.get("last_connected", "Never")

    # Parse and format timestamp
    if last_connected and last_connected != "Never":
        try:
            dt = datetime.fromisoformat(last_connected.replace("Z", "+00:00"))
            age = datetime.now().astimezone() - dt
            if age.total_seconds() < 60:
                time_ago = "just now"
            elif age.total_seconds() < 3600:
                time_ago = f"{int(age.total_seconds() / 60)} minutes ago"
            elif age.total_seconds() < 86400:
                time_ago = f"{int(age.total_seconds() / 3600)} hours ago"
            else:
                time_ago = f"{int(age.total_seconds() / 86400)} days ago"
        except (ValueError, TypeError):
            time_ago = last_connected
    else:
        time_ago = "Never"

    print(f"{color('Current Node:', Colors.BOLD)} {color(hostname, Colors.CYAN)}")
    print(f"  Node ID: {node_id}")

    # Test connection
    ssh_config = context.get("ssh_config", {})
    client = PiClient(
        hostname=hostname,
        user=ssh_config.get("user", "pi"),
        key_path=os.path.expanduser(ssh_config.get("key_path", "~/.ssh/id_rsa")),
        timeout=ssh_config.get("timeout", 10)
    )

    connected, msg = client.test_connection()
    if connected:
        print(f"  Connection: {color('CONNECTED', Colors.GREEN)}")
    else:
        print(f"  Connection: {color('OFFLINE', Colors.RED)} ({msg})")

    print(f"  Last Seen: {time_ago}")

    # Get serial port status if connected
    if connected:
        port_status = client.get_serial_port_status()
        if port_status.exists:
            status = "OPEN" if port_status.is_open else "AVAILABLE"
            print(f"  Serial Port: {port_status.device_path} ({status})")
        else:
            print(f"  Serial Port: {color('NOT FOUND', Colors.YELLOW)}")


def discover_and_display() -> list[NodeInfo]:
    """Discover nodes and display results."""
    print("Discovering XTConnect nodes on network...")
    print(color("(This may take a few seconds)", Colors.DIM))
    print()

    nodes = discover_nodes(timeout=5)
    existing_hostnames = {n.hostname for n in nodes}

    # Also try common hostnames
    common_hosts = ["xtconnect-master.local"]

    for hostname in common_hosts:
        if hostname not in existing_hostnames:
            ip = resolve_hostname(hostname)
            if ip:
                existing_hostnames.add(hostname)
                node_id = hostname.replace("xtconnect-", "").replace(".local", "")
                nodes.append(NodeInfo(
                    hostname=hostname,
                    node_id=node_id,
                    node_type="master" if node_id == "master" else "production",
                    online=True,
                    ip_address=ip
                ))

    # Check recent nodes from context (they may not advertise via mDNS)
    context = load_context()
    recent_nodes = context.get("recent_nodes", [])
    for recent in recent_nodes:
        hostname = recent.get("hostname")
        if hostname and hostname not in existing_hostnames:
            ip = resolve_hostname(hostname)
            if ip:
                existing_hostnames.add(hostname)
                node_id = hostname.replace("xtconnect-", "").replace(".local", "")
                nodes.append(NodeInfo(
                    hostname=hostname,
                    node_id=node_id,
                    node_type="master" if node_id == "master" else "production",
                    online=True,
                    ip_address=ip
                ))

    if not nodes:
        print(color("No nodes discovered.", Colors.YELLOW))
        print("\nTips:")
        print("  - Ensure Pi is powered on and connected to network")
        print("  - Check that mDNS/Bonjour is working on your network")
        print("  - Try specifying hostname directly: --set xtconnect-xxx.local")
        return []

    print(f"{color('Discovered Nodes:', Colors.BOLD)}")
    for node in nodes:
        node_type_label = "(Master Image)" if node.node_type == "master" else "(Production)"
        status = color("ONLINE", Colors.GREEN) if node.online else color("OFFLINE", Colors.RED)
        ip_info = f" [{node.ip_address}]" if node.ip_address else ""
        print(f"  {color(node.hostname, Colors.CYAN)} {node_type_label} - {status}{ip_info}")

    print(f"\nTotal: {len(nodes)} node(s)")
    return nodes


def set_node_context(hostname: str, context: dict) -> bool:
    """Set the current node context."""
    # Handle "-" for previous node
    if hostname == "-":
        recent = context.get("recent_nodes", [])
        if len(recent) < 2:
            print(color("No previous node in history.", Colors.YELLOW))
            return False
        # Find the previous node (not the current one)
        current_hostname = context.get("current_node", {}).get("hostname")
        for node in recent:
            if node.get("hostname") != current_hostname:
                hostname = node["hostname"]
                break
        else:
            print(color("No previous node found.", Colors.YELLOW))
            return False

    # Normalize hostname
    if not hostname.endswith(".local"):
        hostname = f"{hostname}.local"
    if not hostname.startswith("xtconnect-"):
        hostname = f"xtconnect-{hostname}"

    # Extract node ID
    node_id = hostname.replace("xtconnect-", "").replace(".local", "")

    # Test connection
    ssh_config = context.get("ssh_config", {})
    client = PiClient(
        hostname=hostname,
        user=ssh_config.get("user", "pi"),
        key_path=os.path.expanduser(ssh_config.get("key_path", "~/.ssh/id_rsa")),
        timeout=ssh_config.get("timeout", 10)
    )

    print(f"Testing connection to {color(hostname, Colors.CYAN)}...")
    connected, msg = client.test_connection()

    if not connected:
        print(color(f"Warning: Could not connect ({msg})", Colors.YELLOW))
        print("Setting context anyway. Use --test to retry connection.")

    # Update context
    now = datetime.now().astimezone().isoformat()
    new_node = {
        "hostname": hostname,
        "node_id": node_id,
        "last_connected": now if connected else None,
        "connection_status": "connected" if connected else "unknown"
    }

    # Update recent nodes (keep last 10, no duplicates)
    recent = context.get("recent_nodes", [])
    recent = [n for n in recent if n.get("hostname") != hostname]
    recent.insert(0, {"hostname": hostname, "last_connected": now})
    recent = recent[:10]

    context["current_node"] = new_node
    context["recent_nodes"] = recent
    save_context(context)

    status = color("CONNECTED", Colors.GREEN) if connected else color("SET (not verified)", Colors.YELLOW)
    print(f"Current node: {color(hostname, Colors.CYAN)} [{status}]")
    return True


def show_history(context: dict) -> None:
    """Show connection history."""
    recent = context.get("recent_nodes", [])

    if not recent:
        print(color("No connection history.", Colors.DIM))
        return

    print(f"{color('Connection History:', Colors.BOLD)}")
    current_hostname = context.get("current_node", {}).get("hostname")

    for node in recent:
        hostname = node.get("hostname", "Unknown")
        last_connected = node.get("last_connected", "Unknown")

        # Format timestamp
        try:
            dt = datetime.fromisoformat(last_connected.replace("Z", "+00:00"))
            formatted_time = dt.strftime("%Y-%m-%d %H:%M")
        except (ValueError, TypeError):
            formatted_time = last_connected

        # Mark current
        current_marker = " (current)" if hostname == current_hostname else ""
        print(f"  {color(hostname, Colors.CYAN)}{current_marker}")
        print(f"    Last connected: {formatted_time}")


def show_config(context: dict) -> None:
    """Show SSH configuration."""
    ssh_config = context.get("ssh_config", {})

    print(f"{color('SSH Configuration:', Colors.BOLD)}")
    print(f"  User: {ssh_config.get('user', 'pi')}")
    print(f"  Key Path: {ssh_config.get('key_path', '~/.ssh/id_rsa')}")
    print(f"  Timeout: {ssh_config.get('timeout', 10)}s")

    # Check if key exists
    key_path = os.path.expanduser(ssh_config.get("key_path", "~/.ssh/id_rsa"))
    if os.path.exists(key_path):
        print(f"  Key Status: {color('EXISTS', Colors.GREEN)}")
    else:
        print(f"  Key Status: {color('NOT FOUND', Colors.RED)}")


def update_config(context: dict, key_path: Optional[str], timeout: Optional[int], user: Optional[str]) -> None:
    """Update SSH configuration."""
    ssh_config = context.get("ssh_config", {})

    if key_path:
        ssh_config["key_path"] = key_path
        print(f"Set key_path: {key_path}")

    if timeout:
        ssh_config["timeout"] = timeout
        print(f"Set timeout: {timeout}s")

    if user:
        ssh_config["user"] = user
        print(f"Set user: {user}")

    context["ssh_config"] = ssh_config
    save_context(context)


def main():
    parser = argparse.ArgumentParser(
        description="Manage XTConnect Pi node connection context"
    )
    parser.add_argument(
        "--discover", "-d",
        action="store_true",
        help="Discover nodes on network"
    )
    parser.add_argument(
        "--set", "-s",
        metavar="HOSTNAME",
        help="Set current node context (use '-' for previous)"
    )
    parser.add_argument(
        "--history",
        action="store_true",
        help="Show connection history"
    )
    parser.add_argument(
        "--config",
        action="store_true",
        help="Show SSH configuration"
    )
    parser.add_argument(
        "--key-path",
        help="Set SSH key path"
    )
    parser.add_argument(
        "--timeout",
        type=int,
        help="Set SSH timeout in seconds"
    )
    parser.add_argument(
        "--user",
        help="Set SSH user"
    )

    args = parser.parse_args()
    context = load_context()

    # Handle config updates
    if args.key_path or args.timeout or args.user:
        update_config(context, args.key_path, args.timeout, args.user)
        return

    # Handle main commands
    if args.discover:
        discover_and_display()
    elif args.set:
        set_node_context(args.set, context)
    elif args.history:
        show_history(context)
    elif args.config:
        show_config(context)
    else:
        show_current_context(context)


if __name__ == "__main__":
    main()

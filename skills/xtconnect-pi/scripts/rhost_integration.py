#!/usr/bin/env python3
"""
Integration with the remote-hosts (rhost) skill.

Provides:
- Auto-registration of discovered Pi nodes in rhost config
- Hostname lookup from rhost as fallback when mDNS fails
- Centralized SSH key management via rhost
"""

import json
import os
from pathlib import Path
from typing import Optional, Dict, Any, List

# Try to import PyYAML (same as rhost)
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False


RHOST_CONFIG_DIR = Path.home() / ".remote-hosts"
RHOST_HOSTS_FILE = RHOST_CONFIG_DIR / "hosts.yaml"
XTCONNECT_ENVIRONMENT = "xtconnect"  # Environment tag for Pi nodes


def rhost_available() -> bool:
    """Check if rhost is configured (config dir exists)."""
    return RHOST_CONFIG_DIR.exists()


def ensure_rhost_config() -> None:
    """Ensure rhost config directory exists."""
    RHOST_CONFIG_DIR.mkdir(parents=True, exist_ok=True)


def load_rhost_hosts() -> Dict[str, Any]:
    """Load rhost hosts configuration."""
    if not RHOST_HOSTS_FILE.exists():
        return {"hosts": {}}

    content = RHOST_HOSTS_FILE.read_text()
    if HAS_YAML:
        return yaml.safe_load(content) or {"hosts": {}}
    else:
        # Fallback to JSON if YAML not available
        try:
            return json.loads(content)
        except json.JSONDecodeError:
            return {"hosts": {}}


def save_rhost_hosts(data: Dict[str, Any]) -> None:
    """Save rhost hosts configuration."""
    ensure_rhost_config()
    if HAS_YAML:
        content = yaml.dump(data, default_flow_style=False, sort_keys=False)
    else:
        content = json.dumps(data, indent=2)
    RHOST_HOSTS_FILE.write_text(content)


def get_rhost_host(host_id: str) -> Optional[Dict[str, Any]]:
    """Get a host by ID from rhost config."""
    data = load_rhost_hosts()
    return data.get("hosts", {}).get(host_id)


def find_xtconnect_host(identifier: str) -> Optional[Dict[str, Any]]:
    """
    Find an XTConnect host by various identifiers.

    Searches for:
    - Exact host_id match
    - xtconnect-{identifier} match
    - Hostname contains identifier

    Returns the host config dict with 'host_id' added, or None.
    """
    data = load_rhost_hosts()
    hosts = data.get("hosts", {})

    # Normalize identifier
    identifier = identifier.lower().strip()
    if identifier.endswith(".local"):
        identifier = identifier[:-6]

    # Try exact match first
    if identifier in hosts:
        host = hosts[identifier].copy()
        host["host_id"] = identifier
        return host

    # Try with xtconnect- prefix
    prefixed = f"xtconnect-{identifier}"
    if prefixed in hosts:
        host = hosts[prefixed].copy()
        host["host_id"] = prefixed
        return host

    # Search by hostname substring (for xtconnect hosts only)
    for host_id, host in hosts.items():
        if host.get("environment") != XTCONNECT_ENVIRONMENT:
            continue
        hostname = host.get("hostname", "").lower()
        if identifier in hostname or identifier in host_id.lower():
            result = host.copy()
            result["host_id"] = host_id
            return result

    return None


def register_pi_node(
    hostname: str,
    node_id: str,
    ip_address: Optional[str] = None,
    ssh_key: Optional[str] = None,
    user: str = "pi",
    node_type: str = "production",
    force: bool = False,
) -> bool:
    """
    Register a Pi node in rhost config.

    Args:
        hostname: Full hostname (e.g., xtconnect-master.local)
        node_id: Node ID (e.g., master, d9f50b55)
        ip_address: Optional IP address
        ssh_key: SSH key path (defaults to ~/.ssh/xtconnect_pi or similar)
        user: SSH user (default: pi)
        node_type: master or production
        force: Overwrite existing entry

    Returns:
        True if registered/updated, False if already exists and force=False
    """
    data = load_rhost_hosts()
    hosts = data.setdefault("hosts", {})

    # Generate host_id from hostname
    host_id = hostname.replace(".local", "")

    # Check if already exists
    if host_id in hosts and not force:
        return False

    # Find best SSH key if not provided
    if not ssh_key:
        ssh_key = _find_best_ssh_key()

    # Build host entry
    host_entry = {
        "hostname": hostname,
        "user": user,
        "description": f"XTConnect Pi ({node_type})",
        "environment": XTCONNECT_ENVIRONMENT,
        "docker": True,  # All XTConnect nodes run Docker
    }

    if ssh_key:
        host_entry["key"] = ssh_key

    if ip_address:
        host_entry["ip_address"] = ip_address  # Extra field for reference

    # Add node metadata
    host_entry["xtconnect"] = {
        "node_id": node_id,
        "node_type": node_type,
    }

    hosts[host_id] = host_entry
    save_rhost_hosts(data)
    return True


def register_nodes_batch(nodes: List[Dict[str, Any]], ssh_key: Optional[str] = None) -> int:
    """
    Register multiple Pi nodes in rhost config.

    Args:
        nodes: List of node dicts with hostname, node_id, ip_address, node_type
        ssh_key: SSH key to use for all nodes

    Returns:
        Number of nodes registered (excludes already existing)
    """
    if not nodes:
        return 0

    data = load_rhost_hosts()
    hosts = data.setdefault("hosts", {})

    if not ssh_key:
        ssh_key = _find_best_ssh_key()

    registered = 0
    for node in nodes:
        hostname = node.get("hostname", "")
        if not hostname:
            continue

        host_id = hostname.replace(".local", "")

        # Skip if already exists
        if host_id in hosts:
            continue

        node_id = node.get("node_id", host_id.replace("xtconnect-", ""))
        node_type = node.get("node_type", "production")
        ip_address = node.get("ip_address")

        host_entry = {
            "hostname": hostname,
            "user": "pi",
            "description": f"XTConnect Pi ({node_type})",
            "environment": XTCONNECT_ENVIRONMENT,
            "docker": True,
        }

        if ssh_key:
            host_entry["key"] = ssh_key

        if ip_address:
            host_entry["ip_address"] = ip_address

        host_entry["xtconnect"] = {
            "node_id": node_id,
            "node_type": node_type,
        }

        hosts[host_id] = host_entry
        registered += 1

    if registered > 0:
        save_rhost_hosts(data)

    return registered


def list_xtconnect_hosts() -> List[Dict[str, Any]]:
    """List all XTConnect hosts from rhost config."""
    data = load_rhost_hosts()
    hosts = data.get("hosts", {})

    result = []
    for host_id, host in hosts.items():
        if host.get("environment") == XTCONNECT_ENVIRONMENT:
            entry = host.copy()
            entry["host_id"] = host_id
            result.append(entry)

    return result


def _find_best_ssh_key() -> Optional[str]:
    """Find the best available SSH key for XTConnect nodes."""
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
    return None


def get_ssh_config_from_rhost(host_id: str) -> Optional[Dict[str, Any]]:
    """
    Get SSH config for a host from rhost.

    Returns dict with: hostname, user, key_path, or None if not found.
    """
    host = find_xtconnect_host(host_id)
    if not host:
        return None

    return {
        "hostname": host.get("hostname"),
        "user": host.get("user", "pi"),
        "key_path": host.get("key"),
    }

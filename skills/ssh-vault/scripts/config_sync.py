"""
SSH config synchronization for SSH Vault.

Manages a section of ~/.ssh/config based on the inventory.
"""

import re
from pathlib import Path
from typing import List, Tuple, Optional

from models import Inventory, Host, SSHKey
from inventory import InventoryManager


# Markers for managed section
MANAGED_START = "# === SSH-VAULT MANAGED - DO NOT EDIT BELOW ==="
MANAGED_END = "# === SSH-VAULT MANAGED - DO NOT EDIT ABOVE ==="


class ConfigSyncError(Exception):
    """Error during config synchronization."""
    pass


def _get_ssh_config_path() -> Path:
    """Get the path to ~/.ssh/config."""
    return Path.home() / ".ssh" / "config"


def _read_config() -> str:
    """Read the current SSH config file."""
    config_path = _get_ssh_config_path()
    if config_path.exists():
        return config_path.read_text()
    return ""


def _write_config(content: str) -> None:
    """Write the SSH config file."""
    config_path = _get_ssh_config_path()
    config_path.parent.mkdir(mode=0o700, exist_ok=True)
    config_path.write_text(content)
    config_path.chmod(0o600)


def _split_config(content: str) -> Tuple[str, str, str]:
    """
    Split config into user section, managed section, and trailing content.

    Returns:
        Tuple of (before_managed, managed, after_managed)
    """
    start_idx = content.find(MANAGED_START)
    end_idx = content.find(MANAGED_END)

    if start_idx == -1 and end_idx == -1:
        # No managed section exists
        return content.rstrip(), "", ""

    if start_idx == -1 or end_idx == -1:
        raise ConfigSyncError(
            "Corrupted SSH config: found only one managed section marker. "
            f"Please fix or remove the markers in {_get_ssh_config_path()}"
        )

    if start_idx > end_idx:
        raise ConfigSyncError(
            "Corrupted SSH config: managed section markers are in wrong order. "
            f"Please fix or remove the markers in {_get_ssh_config_path()}"
        )

    before = content[:start_idx].rstrip()
    managed = content[start_idx:end_idx + len(MANAGED_END)]
    after = content[end_idx + len(MANAGED_END):].strip()

    return before, managed, after


def _generate_host_entry(host: Host, key: Optional[SSHKey]) -> str:
    """Generate a single Host entry for the config."""
    lines = [f"Host {host.id}"]
    lines.append(f"    HostName {host.hostname}")
    lines.append(f"    User {host.user}")

    if host.port != 22:
        lines.append(f"    Port {host.port}")

    if key:
        lines.append(f"    IdentityFile {key.private_key_path}")
        lines.append("    IdentitiesOnly yes")

    return "\n".join(lines)


def _generate_managed_section(inventory: Inventory) -> str:
    """Generate the managed section content from inventory."""
    if not inventory.hosts:
        return ""

    entries = []

    for host in inventory.hosts.values():
        # Find the preferred key for this host
        # Use the first key that's deployed to this host
        key = None
        deployed_keys = inventory.get_keys_for_host(host.id)
        if deployed_keys:
            key = deployed_keys[0]

        entry = _generate_host_entry(host, key)
        entries.append(entry)

    if not entries:
        return ""

    content = [MANAGED_START, ""]
    content.extend(entries)
    content.append("")
    content.append(MANAGED_END)

    return "\n".join(content)


def sync_config(
    manager: InventoryManager,
    dry_run: bool = False,
) -> Tuple[str, List[str]]:
    """
    Synchronize the SSH config with the inventory.

    Args:
        manager: Inventory manager
        dry_run: If True, return what would change without writing

    Returns:
        Tuple of (new_config_content, list_of_changes)
    """
    inventory = manager.load()
    current_config = _read_config()

    try:
        before, _, after = _split_config(current_config)
    except ConfigSyncError:
        raise

    # Generate new managed section
    managed_section = _generate_managed_section(inventory)

    # Build new config
    parts = []
    if before:
        parts.append(before)
    if managed_section:
        if parts:
            parts.append("")  # Add blank line separator
        parts.append(managed_section)
    if after:
        if parts:
            parts.append("")
        parts.append(after)

    new_config = "\n".join(parts)
    if new_config and not new_config.endswith("\n"):
        new_config += "\n"

    # Determine changes
    changes = []
    if new_config != current_config:
        # Parse host entries to report specific changes
        for host in inventory.hosts.values():
            deployed_keys = inventory.get_keys_for_host(host.id)
            key_info = f" (key: {deployed_keys[0].id})" if deployed_keys else ""
            changes.append(f"Host {host.id}: {host.user}@{host.hostname}{key_info}")

    if not dry_run and changes:
        _write_config(new_config)

    return new_config, changes


def show_managed_entries(manager: InventoryManager) -> List[dict]:
    """
    Show the currently managed entries.

    Returns:
        List of host configuration dictionaries
    """
    inventory = manager.load()
    entries = []

    for host in inventory.hosts.values():
        deployed_keys = inventory.get_keys_for_host(host.id)
        entry = {
            "host_alias": host.id,
            "hostname": host.hostname,
            "user": host.user,
            "port": host.port,
            "identity_file": deployed_keys[0].private_key_path if deployed_keys else None,
        }
        entries.append(entry)

    return entries


def clean_managed_section(dry_run: bool = False) -> bool:
    """
    Remove the managed section from the config.

    Args:
        dry_run: If True, don't actually modify the file

    Returns:
        True if section was removed
    """
    current_config = _read_config()

    try:
        before, managed, after = _split_config(current_config)
    except ConfigSyncError:
        raise

    if not managed:
        return False  # Nothing to clean

    # Rebuild without managed section
    parts = []
    if before:
        parts.append(before)
    if after:
        if parts:
            parts.append("")
        parts.append(after)

    new_config = "\n".join(parts)
    if new_config and not new_config.endswith("\n"):
        new_config += "\n"

    if not dry_run:
        _write_config(new_config)

    return True


def get_config_status() -> dict:
    """
    Get the current status of the SSH config.

    Returns:
        Dictionary with config status information
    """
    config_path = _get_ssh_config_path()
    current_config = _read_config()

    status = {
        "config_path": str(config_path),
        "config_exists": config_path.exists(),
        "has_managed_section": False,
        "managed_host_count": 0,
    }

    if current_config:
        try:
            _, managed, _ = _split_config(current_config)
            if managed:
                status["has_managed_section"] = True
                # Count Host entries in managed section
                host_count = len(re.findall(r'^Host\s+', managed, re.MULTILINE))
                status["managed_host_count"] = host_count
        except ConfigSyncError:
            status["error"] = "Corrupted managed section markers"

    return status

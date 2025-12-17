"""
Host operations for SSH Vault.

Handles host management, key deployment, verification, and revocation.
"""

import subprocess
import sys
from pathlib import Path
from typing import Optional, List, Tuple

from models import Host, Inventory, now_utc
from inventory import InventoryManager


class HostOperationError(Exception):
    """Error during host operation."""
    pass


def add_host(
    manager: InventoryManager,
    host_id: str,
    hostname: str,
    user: Optional[str] = None,
    port: int = 22,
) -> Host:
    """
    Add a host to the inventory.

    Args:
        manager: Inventory manager
        host_id: Unique identifier for this host
        hostname: IP address or DNS name
        user: SSH username (defaults to current user)
        port: SSH port (default: 22)

    Returns:
        The created Host

    Raises:
        HostOperationError: If host already exists
    """
    inventory = manager.load()

    if host_id in inventory.hosts:
        raise HostOperationError(f"Host '{host_id}' already exists")

    # Default to current user if not specified
    if not user:
        import os
        user = os.environ.get("USER", "root")

    host = Host(
        id=host_id,
        hostname=hostname,
        user=user,
        port=port,
    )

    inventory.add_host(host)
    manager.save(inventory)

    return host


def list_hosts(manager: InventoryManager) -> List[Host]:
    """List all hosts in the inventory."""
    inventory = manager.load()
    return list(inventory.hosts.values())


def get_host(manager: InventoryManager, host_id: str) -> Optional[Host]:
    """Get a specific host by ID."""
    inventory = manager.load()
    return inventory.get_host(host_id)


def remove_host(
    manager: InventoryManager,
    host_id: str,
    force: bool = False,
) -> bool:
    """
    Remove a host from the inventory.

    Args:
        manager: Inventory manager
        host_id: Host to remove
        force: Remove even if keys are deployed

    Returns:
        True if removed

    Raises:
        HostOperationError: If removal fails
    """
    inventory = manager.load()
    host = inventory.get_host(host_id)

    if not host:
        raise HostOperationError(f"Host '{host_id}' not found")

    # Check if any keys are deployed to this host
    deployed_keys = inventory.get_keys_for_host(host_id)
    if deployed_keys and not force:
        key_ids = [k.id for k in deployed_keys]
        raise HostOperationError(
            f"Host '{host_id}' has {len(deployed_keys)} key(s) deployed: {', '.join(key_ids)}. "
            "Revoke first or use --force to remove anyway."
        )

    inventory.remove_host(host_id)
    manager.save(inventory)

    return True


def _run_ssh_command(
    host: Host,
    command: str,
    key_path: Optional[str] = None,
    timeout: int = 30,
) -> Tuple[int, str, str]:
    """
    Run a command on a remote host via SSH.

    Returns:
        Tuple of (return_code, stdout, stderr)
    """
    ssh_cmd = ["ssh"]

    # Add port if non-default
    if host.port != 22:
        ssh_cmd.extend(["-p", str(host.port)])

    # Add identity file if specified
    if key_path:
        ssh_cmd.extend(["-i", key_path])

    # Add common options
    ssh_cmd.extend([
        "-o", "BatchMode=yes",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", "ConnectTimeout=10",
        host.ssh_destination(),
        command,
    ])

    try:
        result = subprocess.run(
            ssh_cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return result.returncode, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return -1, "", "SSH connection timed out"
    except Exception as e:
        return -1, "", str(e)


def deploy_key(
    manager: InventoryManager,
    key_id: str,
    host_id: str,
    verify: bool = True,
) -> bool:
    """
    Deploy an SSH key to a host's authorized_keys.

    This uses ssh-copy-id if available, otherwise manually appends to authorized_keys.

    Args:
        manager: Inventory manager
        key_id: Key to deploy
        host_id: Target host
        verify: Verify deployment after copying

    Returns:
        True if successful

    Raises:
        HostOperationError: If deployment fails
    """
    inventory = manager.load()

    key = inventory.get_key(key_id)
    if not key:
        raise HostOperationError(f"Key '{key_id}' not found")

    host = inventory.get_host(host_id)
    if not host:
        raise HostOperationError(f"Host '{host_id}' not found")

    # Read the public key
    public_key = key.get_public_key_content()
    if not public_key:
        raise HostOperationError(
            f"Public key file not found: {key.public_key_path}"
        )

    # Try ssh-copy-id first (most reliable)
    ssh_copy_cmd = [
        "ssh-copy-id",
        "-i", key.public_key_path,
    ]
    if host.port != 22:
        ssh_copy_cmd.extend(["-p", str(host.port)])
    ssh_copy_cmd.append(host.ssh_destination())

    try:
        result = subprocess.run(
            ssh_copy_cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            # ssh-copy-id failed, try manual method
            raise subprocess.SubprocessError("ssh-copy-id failed")
    except (subprocess.TimeoutExpired, subprocess.SubprocessError, FileNotFoundError):
        # Fall back to manual deployment
        # This requires existing SSH access to the host
        escaped_key = public_key.replace("'", "'\\''")
        deploy_cmd = (
            f"mkdir -p ~/.ssh && chmod 700 ~/.ssh && "
            f"echo '{escaped_key}' >> ~/.ssh/authorized_keys && "
            f"chmod 600 ~/.ssh/authorized_keys"
        )

        ret, _, stderr = _run_ssh_command(host, deploy_cmd)
        if ret != 0:
            raise HostOperationError(
                f"Failed to deploy key to {host_id}: {stderr}"
            )

    # Record deployment
    key.add_deployment(host_id)
    if host_id not in host.keys:
        host.keys.append(key_id)
    manager.save(inventory)

    # Verify if requested
    if verify:
        if not verify_deployment(manager, key_id, host_id):
            raise HostOperationError(
                f"Key deployed but verification failed. "
                "The key may not be properly configured."
            )

    return True


def verify_deployment(
    manager: InventoryManager,
    key_id: str,
    host_id: str,
) -> bool:
    """
    Verify a key is deployed and working on a host.

    Args:
        manager: Inventory manager
        key_id: Key to verify
        host_id: Target host

    Returns:
        True if key is working

    Raises:
        HostOperationError: If verification setup fails
    """
    inventory = manager.load()

    key = inventory.get_key(key_id)
    if not key:
        raise HostOperationError(f"Key '{key_id}' not found")

    host = inventory.get_host(host_id)
    if not host:
        raise HostOperationError(f"Host '{host_id}' not found")

    # Try to connect using the specific key
    ret, stdout, stderr = _run_ssh_command(
        host,
        "echo 'SSH_VAULT_VERIFY_OK'",
        key_path=key.private_key_path,
    )

    if ret == 0 and "SSH_VAULT_VERIFY_OK" in stdout:
        # Update verification timestamp
        deployment = key.get_deployment(host_id)
        if deployment:
            deployment.verified_at = now_utc()
            manager.save(inventory)
        return True

    return False


def verify_all_deployments(
    manager: InventoryManager,
) -> List[Tuple[str, str, bool, Optional[str]]]:
    """
    Verify all key deployments.

    Returns:
        List of (key_id, host_id, success, error_message) tuples
    """
    inventory = manager.load()
    results = []

    for key in inventory.keys.values():
        for deployment in key.deployments:
            host = inventory.get_host(deployment.host_id)
            if not host:
                results.append((key.id, deployment.host_id, False, "Host not found"))
                continue

            try:
                success = verify_deployment(manager, key.id, deployment.host_id)
                results.append((key.id, deployment.host_id, success, None if success else "Connection failed"))
            except HostOperationError as e:
                results.append((key.id, deployment.host_id, False, str(e)))

    return results


def revoke_key(
    manager: InventoryManager,
    key_id: str,
    host_id: str,
) -> bool:
    """
    Revoke (remove) an SSH key from a host's authorized_keys.

    Args:
        manager: Inventory manager
        key_id: Key to revoke
        host_id: Target host

    Returns:
        True if successful

    Raises:
        HostOperationError: If revocation fails
    """
    inventory = manager.load()

    key = inventory.get_key(key_id)
    if not key:
        raise HostOperationError(f"Key '{key_id}' not found")

    host = inventory.get_host(host_id)
    if not host:
        raise HostOperationError(f"Host '{host_id}' not found")

    # Get the fingerprint to identify the key
    fingerprint = key.fingerprint

    # Get the public key content for exact matching
    public_key = key.get_public_key_content()
    if not public_key:
        raise HostOperationError(
            f"Public key file not found: {key.public_key_path}"
        )

    # Create a command to remove the key from authorized_keys
    # We use grep -v to filter out lines containing the key
    # Need to escape special characters for the pattern
    escaped_key = public_key.replace("/", "\\/").replace("+", "\\+")

    revoke_cmd = (
        f"if [ -f ~/.ssh/authorized_keys ]; then "
        f"grep -v '{escaped_key}' ~/.ssh/authorized_keys > ~/.ssh/authorized_keys.tmp && "
        f"mv ~/.ssh/authorized_keys.tmp ~/.ssh/authorized_keys && "
        f"chmod 600 ~/.ssh/authorized_keys; "
        f"fi"
    )

    # We need to connect with a different key to revoke
    # Try to find another key that's deployed to this host
    other_key_path = None
    for other_key in inventory.keys.values():
        if other_key.id != key_id and other_key.get_deployment(host_id):
            other_key_path = other_key.private_key_path
            break

    ret, _, stderr = _run_ssh_command(host, revoke_cmd, key_path=other_key_path)
    if ret != 0:
        raise HostOperationError(
            f"Failed to revoke key from {host_id}: {stderr}"
        )

    # Remove deployment record
    key.remove_deployment(host_id)
    if key_id in host.keys:
        host.keys.remove(key_id)
    manager.save(inventory)

    return True


def revoke_key_from_all_hosts(
    manager: InventoryManager,
    key_id: str,
) -> List[Tuple[str, bool, Optional[str]]]:
    """
    Revoke a key from all hosts where it's deployed.

    Returns:
        List of (host_id, success, error_message) tuples
    """
    inventory = manager.load()

    key = inventory.get_key(key_id)
    if not key:
        raise HostOperationError(f"Key '{key_id}' not found")

    results = []
    # Copy deployments list since we'll be modifying it
    deployments = list(key.deployments)

    for deployment in deployments:
        try:
            success = revoke_key(manager, key_id, deployment.host_id)
            results.append((deployment.host_id, success, None))
        except HostOperationError as e:
            results.append((deployment.host_id, False, str(e)))

    return results


def test_host_connection(
    manager: InventoryManager,
    host_id: str,
) -> Tuple[bool, str]:
    """
    Test if we can connect to a host.

    Returns:
        Tuple of (success, message)
    """
    inventory = manager.load()

    host = inventory.get_host(host_id)
    if not host:
        return False, f"Host '{host_id}' not found"

    ret, stdout, stderr = _run_ssh_command(
        host,
        "echo 'SSH_VAULT_CONNECTION_OK'",
    )

    if ret == 0 and "SSH_VAULT_CONNECTION_OK" in stdout:
        return True, "Connection successful"

    return False, stderr or "Connection failed"

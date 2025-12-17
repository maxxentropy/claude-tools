"""
Key operations for SSH Vault.

Handles key creation, listing, rotation, and deletion.
"""

import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Dict, Any, List

from models import (
    SSHKey, Inventory, Deployment, Service,
    DEFAULT_ALGORITHM, DEFAULT_EXPIRY_YEARS, ALGORITHMS, BUILTIN_SERVICES,
    now_utc, parse_duration, get_key_fingerprint, check_key_has_passphrase,
    get_service_algorithm, list_builtin_services,
)
from inventory import InventoryManager


class KeyOperationError(Exception):
    """Error during key operation."""
    pass


def create_key(
    manager: InventoryManager,
    key_id: str,
    purpose: str = "",
    expires: str = "2y",
    algorithm: Optional[str] = None,
    passphrase: Optional[str] = None,
    no_passphrase: bool = False,
    for_service: Optional[str] = None,
) -> SSHKey:
    """
    Create a new SSH key.

    Args:
        manager: Inventory manager
        key_id: Unique identifier for this key
        purpose: Description of what this key is for
        expires: Duration until rotation reminder (e.g., '2y', '6m')
        algorithm: Key algorithm (ed25519, ecdsa, rsa). Auto-selected if for_service is set.
        passphrase: Passphrase for the key (None to prompt)
        no_passphrase: If True, create without passphrase
        for_service: Service ID to auto-select algorithm (e.g., 'azure-devops', 'github')

    Returns:
        The created SSHKey

    Raises:
        KeyOperationError: If key creation fails
    """
    inventory = manager.load()

    # Check if key ID already exists
    if key_id in inventory.keys:
        raise KeyOperationError(f"Key '{key_id}' already exists")

    # Determine algorithm - service requirements take precedence
    if for_service:
        service = inventory.get_service(for_service)
        if service:
            service_algo = service.get_algorithm()
            if algorithm and algorithm != service_algo and service.required_algorithm:
                raise KeyOperationError(
                    f"Service '{for_service}' requires {service_algo.upper()} keys. "
                    f"Cannot use --algorithm {algorithm}."
                )
            algorithm = service_algo
        elif for_service in BUILTIN_SERVICES:
            service_algo = get_service_algorithm(for_service)
            if algorithm and algorithm != service_algo:
                builtin = BUILTIN_SERVICES[for_service]
                if builtin.get("required_algorithm"):
                    raise KeyOperationError(
                        f"Service '{for_service}' requires {service_algo.upper()} keys. "
                        f"Cannot use --algorithm {algorithm}."
                    )
            algorithm = service_algo
        else:
            raise KeyOperationError(
                f"Unknown service: {for_service}. "
                f"Available: {', '.join(BUILTIN_SERVICES.keys())}"
            )

    # Default algorithm if not specified
    if not algorithm:
        algorithm = DEFAULT_ALGORITHM

    # Validate algorithm
    if algorithm not in ALGORITHMS:
        raise KeyOperationError(
            f"Unknown algorithm: {algorithm}. Use one of: {', '.join(ALGORITHMS)}"
        )

    # Check if key files already exist
    private_path = manager.get_key_path(key_id, public=False)
    public_path = manager.get_key_path(key_id, public=True)

    if private_path.exists() or public_path.exists():
        raise KeyOperationError(
            f"Key files already exist at {private_path}. "
            "Remove them first or choose a different key ID."
        )

    # Calculate expiry date
    try:
        days = parse_duration(expires)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError as e:
        raise KeyOperationError(str(e))

    # Build ssh-keygen command
    cmd = [
        "ssh-keygen",
        "-t", algorithm,
        "-f", str(private_path),
        "-C", f"{key_id} - {purpose}" if purpose else key_id,
    ]

    # Handle passphrase
    if no_passphrase:
        cmd.extend(["-N", ""])
    elif passphrase is not None:
        cmd.extend(["-N", passphrase])
    # If neither, ssh-keygen will prompt interactively

    # Add algorithm-specific options
    if algorithm == "rsa":
        cmd.extend(["-b", "4096"])
    elif algorithm == "ecdsa":
        cmd.extend(["-b", "521"])

    # Ensure ~/.ssh exists
    manager.ssh_dir.mkdir(mode=0o700, exist_ok=True)

    # Run ssh-keygen
    try:
        result = subprocess.run(
            cmd,
            capture_output=not (passphrase is None and not no_passphrase),
            text=True,
            timeout=60,
        )
        if result.returncode != 0:
            raise KeyOperationError(
                f"ssh-keygen failed: {result.stderr if result.stderr else 'unknown error'}"
            )
    except subprocess.TimeoutExpired:
        raise KeyOperationError("ssh-keygen timed out")
    except FileNotFoundError:
        raise KeyOperationError("ssh-keygen not found. Is OpenSSH installed?")

    # Get fingerprint
    fingerprint = get_key_fingerprint(str(public_path))
    if not fingerprint:
        raise KeyOperationError("Failed to get key fingerprint")

    # Check if key has passphrase
    has_passphrase = not no_passphrase and (
        passphrase is not None or check_key_has_passphrase(str(private_path))
    )

    # Create key object
    key = SSHKey(
        id=key_id,
        algorithm=algorithm,
        created_at=now_utc(),
        expires_at=expires_at,
        purpose=purpose,
        public_key_path=str(public_path),
        private_key_path=str(private_path),
        fingerprint=fingerprint,
        has_passphrase=has_passphrase,
    )

    # Save to inventory
    inventory.add_key(key)
    manager.save(inventory)

    return key


def list_keys(manager: InventoryManager) -> List[SSHKey]:
    """List all keys in the inventory."""
    inventory = manager.load()
    return list(inventory.keys.values())


def get_key(manager: InventoryManager, key_id: str) -> Optional[SSHKey]:
    """Get a specific key by ID."""
    inventory = manager.load()
    return inventory.get_key(key_id)


def delete_key(
    manager: InventoryManager,
    key_id: str,
    force: bool = False,
    delete_files: bool = False,
) -> bool:
    """
    Delete a key from the inventory.

    Args:
        manager: Inventory manager
        key_id: Key to delete
        force: Delete even if key is deployed somewhere
        delete_files: Also delete the key files from ~/.ssh

    Returns:
        True if deleted

    Raises:
        KeyOperationError: If deletion fails
    """
    inventory = manager.load()
    key = inventory.get_key(key_id)

    if not key:
        raise KeyOperationError(f"Key '{key_id}' not found")

    # Check if key is deployed
    if key.deployments and not force:
        hosts = [d.host_id for d in key.deployments]
        raise KeyOperationError(
            f"Key '{key_id}' is deployed to {len(hosts)} host(s): {', '.join(hosts)}. "
            "Revoke first or use --force to delete anyway."
        )

    # Remove from inventory
    inventory.remove_key(key_id)
    manager.save(inventory)

    # Optionally delete files
    if delete_files:
        private_path = Path(key.private_key_path).expanduser()
        public_path = Path(key.public_key_path).expanduser()

        if private_path.exists():
            private_path.unlink()
        if public_path.exists():
            public_path.unlink()

    return True


def rotate_key(
    manager: InventoryManager,
    old_key_id: str,
    new_key_id: Optional[str] = None,
    purpose: Optional[str] = None,
) -> SSHKey:
    """
    Rotate a key by creating a new one.

    This creates a new key but does NOT automatically deploy it.
    Use deploy operations to update hosts.

    Args:
        manager: Inventory manager
        old_key_id: Key to rotate
        new_key_id: ID for new key (default: old_id with year updated)
        purpose: Purpose for new key (default: same as old)

    Returns:
        The new SSHKey

    Raises:
        KeyOperationError: If rotation fails
    """
    inventory = manager.load()
    old_key = inventory.get_key(old_key_id)

    if not old_key:
        raise KeyOperationError(f"Key '{old_key_id}' not found")

    # Generate new key ID if not provided
    if not new_key_id:
        # Try to update year in key name
        year = datetime.now().year
        import re
        # Replace year pattern (4 digits) with current year
        new_key_id = re.sub(r'\d{4}', str(year), old_key_id)
        if new_key_id == old_key_id:
            # No year in name, append -rotated
            new_key_id = f"{old_key_id}-{year}"

    # Create new key with same settings
    new_key = create_key(
        manager=manager,
        key_id=new_key_id,
        purpose=purpose or old_key.purpose,
        algorithm=old_key.algorithm,
        no_passphrase=not old_key.has_passphrase,
    )

    return new_key


def import_existing_key(
    manager: InventoryManager,
    key_id: str,
    private_key_path: str,
    purpose: str = "",
    expires: str = "2y",
) -> SSHKey:
    """
    Import an existing SSH key into the inventory.

    Args:
        manager: Inventory manager
        key_id: Unique identifier for this key
        private_key_path: Path to existing private key
        purpose: Description of what this key is for
        expires: Duration until rotation reminder

    Returns:
        The imported SSHKey

    Raises:
        KeyOperationError: If import fails
    """
    inventory = manager.load()

    # Check if key ID already exists
    if key_id in inventory.keys:
        raise KeyOperationError(f"Key '{key_id}' already exists in inventory")

    # Resolve paths
    private_path = Path(private_key_path).expanduser().resolve()
    public_path = private_path.with_suffix(private_path.suffix + ".pub")

    if not private_path.exists():
        raise KeyOperationError(f"Private key not found: {private_path}")

    if not public_path.exists():
        # Try to generate public key from private
        try:
            result = subprocess.run(
                ["ssh-keygen", "-y", "-f", str(private_path)],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                public_path.write_text(result.stdout)
            else:
                raise KeyOperationError(
                    f"Public key not found and could not be generated: {public_path}"
                )
        except Exception as e:
            raise KeyOperationError(f"Failed to generate public key: {e}")

    # Get fingerprint
    fingerprint = get_key_fingerprint(str(public_path))
    if not fingerprint:
        raise KeyOperationError("Failed to get key fingerprint")

    # Detect algorithm from fingerprint output
    algorithm = "unknown"
    try:
        result = subprocess.run(
            ["ssh-keygen", "-lf", str(public_path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        output = result.stdout.lower()
        if "ed25519" in output:
            algorithm = "ed25519"
        elif "ecdsa" in output:
            algorithm = "ecdsa"
        elif "rsa" in output:
            algorithm = "rsa"
    except Exception:
        pass

    # Calculate expiry
    try:
        days = parse_duration(expires)
        expires_at = (
            datetime.now(timezone.utc) + timedelta(days=days)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")
    except ValueError as e:
        raise KeyOperationError(str(e))

    # Check passphrase
    has_passphrase = check_key_has_passphrase(str(private_path))

    # Create key object
    key = SSHKey(
        id=key_id,
        algorithm=algorithm,
        created_at=now_utc(),  # Use import time as we don't know actual creation
        expires_at=expires_at,
        purpose=purpose,
        public_key_path=str(public_path),
        private_key_path=str(private_path),
        fingerprint=fingerprint,
        has_passphrase=has_passphrase,
    )

    # Save to inventory
    inventory.add_key(key)
    manager.save(inventory)

    return key

"""
Inventory management for SSH Vault.

Handles loading, saving, and managing the inventory file.
"""

import os
from pathlib import Path
from typing import Optional

from models import Inventory

# Try to import PyYAML, fall back to JSON if not available
try:
    import yaml
    HAS_YAML = True
except ImportError:
    HAS_YAML = False
    import json


# Default paths
DEFAULT_VAULT_DIR = Path.home() / ".ssh-vault"
DEFAULT_INVENTORY_FILE = "inventory.yaml"
DEFAULT_SSH_DIR = Path.home() / ".ssh"


class InventoryManager:
    """Manages the SSH Vault inventory."""

    def __init__(self, vault_dir: Optional[Path] = None):
        """
        Initialize the inventory manager.

        Args:
            vault_dir: Path to the vault directory. Defaults to ~/.ssh-vault
        """
        self.vault_dir = vault_dir or DEFAULT_VAULT_DIR
        self.inventory_path = self.vault_dir / DEFAULT_INVENTORY_FILE
        self.ssh_dir = DEFAULT_SSH_DIR
        self._inventory: Optional[Inventory] = None

    def ensure_initialized(self) -> None:
        """Ensure the vault directory exists."""
        self.vault_dir.mkdir(parents=True, exist_ok=True)

        # Create .gitignore to prevent accidental commits
        gitignore = self.vault_dir / ".gitignore"
        if not gitignore.exists():
            gitignore.write_text("# SSH Vault data - do not commit\n*\n")

    def load(self) -> Inventory:
        """Load the inventory from disk."""
        if self._inventory is not None:
            return self._inventory

        if not self.inventory_path.exists():
            self._inventory = Inventory()
            return self._inventory

        content = self.inventory_path.read_text()

        if HAS_YAML:
            data = yaml.safe_load(content) or {}
        else:
            # Fall back to JSON (file might be .yaml but contain JSON)
            try:
                data = json.loads(content)
            except json.JSONDecodeError:
                # Try to parse as simple key-value if YAML not available
                raise RuntimeError(
                    "PyYAML not installed. Install with: pip install pyyaml"
                )

        self._inventory = Inventory.from_dict(data)
        return self._inventory

    def save(self, inventory: Optional[Inventory] = None) -> None:
        """Save the inventory to disk."""
        self.ensure_initialized()

        inv = inventory or self._inventory
        if inv is None:
            inv = Inventory()

        data = inv.to_dict()

        if HAS_YAML:
            content = yaml.dump(
                data,
                default_flow_style=False,
                sort_keys=False,
                allow_unicode=True,
            )
        else:
            content = json.dumps(data, indent=2)

        self.inventory_path.write_text(content)
        self._inventory = inv

    def reload(self) -> Inventory:
        """Force reload from disk."""
        self._inventory = None
        return self.load()

    @property
    def inventory(self) -> Inventory:
        """Get the current inventory, loading if necessary."""
        if self._inventory is None:
            self.load()
        return self._inventory

    def get_key_path(self, key_id: str, public: bool = False) -> Path:
        """Get the path where a key should be stored."""
        suffix = ".pub" if public else ""
        return self.ssh_dir / f"{key_id}{suffix}"

    def key_files_exist(self, key_id: str) -> bool:
        """Check if key files exist in ~/.ssh."""
        private = self.get_key_path(key_id, public=False)
        public = self.get_key_path(key_id, public=True)
        return private.exists() and public.exists()


def get_manager(vault_dir: Optional[Path] = None) -> InventoryManager:
    """Get an inventory manager instance."""
    return InventoryManager(vault_dir)

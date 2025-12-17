"""Tests for SSH Vault inventory management."""

import pytest
from pathlib import Path
import tempfile
import shutil

from inventory import InventoryManager, DEFAULT_INVENTORY_FILE
from models import SSHKey, Host, Inventory


@pytest.fixture
def temp_vault_dir():
    """Create a temporary vault directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


class TestInventoryManager:
    """Tests for InventoryManager class."""

    def test_init_default_paths(self):
        manager = InventoryManager()
        assert manager.vault_dir == Path.home() / ".ssh-vault"
        assert manager.inventory_path == Path.home() / ".ssh-vault" / DEFAULT_INVENTORY_FILE

    def test_init_custom_path(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        assert manager.vault_dir == temp_vault_dir
        assert manager.inventory_path == temp_vault_dir / DEFAULT_INVENTORY_FILE

    def test_ensure_initialized(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        manager.ensure_initialized()

        assert temp_vault_dir.exists()
        gitignore = temp_vault_dir / ".gitignore"
        assert gitignore.exists()
        assert "*" in gitignore.read_text()

    def test_load_empty_inventory(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        inventory = manager.load()

        assert isinstance(inventory, Inventory)
        assert inventory.version == "1.0"
        assert len(inventory.keys) == 0
        assert len(inventory.hosts) == 0

    def test_save_and_load(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        inventory = Inventory()

        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
            purpose="Test key",
        )
        inventory.add_key(key)

        host = Host(
            id="test-host",
            hostname="192.168.1.1",
            user="admin",
        )
        inventory.add_host(host)

        manager.save(inventory)

        # Create new manager to load from disk
        manager2 = InventoryManager(vault_dir=temp_vault_dir)
        loaded = manager2.load()

        assert "test-key" in loaded.keys
        assert "test-host" in loaded.hosts
        assert loaded.keys["test-key"].purpose == "Test key"

    def test_reload(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        inventory = manager.load()

        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        inventory.add_key(key)
        manager.save(inventory)

        # Modify cached inventory
        inventory.keys["test-key"].purpose = "Modified"

        # Reload should get original from disk
        reloaded = manager.reload()
        assert reloaded.keys["test-key"].purpose == ""

    def test_inventory_property(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        # Access via property should auto-load
        inv = manager.inventory
        assert isinstance(inv, Inventory)

    def test_get_key_path(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)

        private_path = manager.get_key_path("my-key", public=False)
        public_path = manager.get_key_path("my-key", public=True)

        assert private_path.name == "my-key"
        assert public_path.name == "my-key.pub"

    def test_key_files_exist(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)

        # Create fake key files
        manager.ssh_dir.mkdir(parents=True, exist_ok=True)
        (manager.ssh_dir / "test-key").touch()
        (manager.ssh_dir / "test-key.pub").touch()

        assert manager.key_files_exist("test-key") is True
        assert manager.key_files_exist("nonexistent") is False

        # Cleanup
        (manager.ssh_dir / "test-key").unlink()
        (manager.ssh_dir / "test-key.pub").unlink()

"""Tests for SSH Vault data models."""

import pytest
from datetime import datetime, timezone, timedelta

from models import (
    SSHKey, Host, Deployment, Inventory,
    parse_duration, now_utc, ALGORITHMS,
)


class TestParseDuration:
    """Tests for parse_duration function."""

    def test_years(self):
        assert parse_duration("1y") == 365
        assert parse_duration("2y") == 730
        assert parse_duration("2Y") == 730

    def test_months(self):
        assert parse_duration("1m") == 30
        assert parse_duration("6m") == 180
        assert parse_duration("6M") == 180

    def test_days(self):
        assert parse_duration("1d") == 1
        assert parse_duration("30d") == 30
        assert parse_duration("30D") == 30

    def test_invalid_format(self):
        with pytest.raises(ValueError):
            parse_duration("invalid")

    def test_missing_unit(self):
        with pytest.raises(ValueError):
            parse_duration("30")

    def test_empty_string(self):
        with pytest.raises(ValueError):
            parse_duration("")


class TestDeployment:
    """Tests for Deployment dataclass."""

    def test_to_dict_basic(self):
        d = Deployment(
            host_id="test-host",
            deployed_at="2024-01-01T00:00:00Z",
        )
        result = d.to_dict()
        assert result["host_id"] == "test-host"
        assert result["deployed_at"] == "2024-01-01T00:00:00Z"
        assert "verified_at" not in result

    def test_to_dict_with_verified(self):
        d = Deployment(
            host_id="test-host",
            deployed_at="2024-01-01T00:00:00Z",
            verified_at="2024-01-02T00:00:00Z",
        )
        result = d.to_dict()
        assert result["verified_at"] == "2024-01-02T00:00:00Z"

    def test_from_dict(self):
        data = {
            "host_id": "test-host",
            "deployed_at": "2024-01-01T00:00:00Z",
            "verified_at": "2024-01-02T00:00:00Z",
        }
        d = Deployment.from_dict(data)
        assert d.host_id == "test-host"
        assert d.deployed_at == "2024-01-01T00:00:00Z"
        assert d.verified_at == "2024-01-02T00:00:00Z"


class TestSSHKey:
    """Tests for SSHKey dataclass."""

    def test_to_dict_minimal(self):
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        result = key.to_dict()
        assert result["algorithm"] == "ed25519"
        assert result["fingerprint"] == "SHA256:abc123"
        assert "purpose" not in result
        assert "expires_at" not in result

    def test_to_dict_full(self):
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            expires_at="2026-01-01T00:00:00Z",
            purpose="Test key",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
            has_passphrase=True,
            deployments=[
                Deployment(host_id="host1", deployed_at="2024-01-02T00:00:00Z"),
            ],
        )
        result = key.to_dict()
        assert result["purpose"] == "Test key"
        assert result["expires_at"] == "2026-01-01T00:00:00Z"
        assert result["has_passphrase"] is True
        assert len(result["deployments"]) == 1

    def test_is_expired_not_set(self):
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        assert not key.is_expired()

    def test_is_expired_past(self):
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            expires_at="2020-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        assert key.is_expired()

    def test_is_expired_future(self):
        future = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            expires_at=future,
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        assert not key.is_expired()

    def test_days_until_expiry(self):
        future = (datetime.now(timezone.utc) + timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            expires_at=future,
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        days = key.days_until_expiry()
        assert 29 <= days <= 31

    def test_add_deployment(self):
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        d = key.add_deployment("host1")
        assert d.host_id == "host1"
        assert len(key.deployments) == 1

    def test_add_deployment_updates_existing(self):
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
            deployments=[
                Deployment(host_id="host1", deployed_at="2024-01-01T00:00:00Z"),
            ],
        )
        d = key.add_deployment("host1")
        assert len(key.deployments) == 1
        assert d.deployed_at != "2024-01-01T00:00:00Z"

    def test_remove_deployment(self):
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
            deployments=[
                Deployment(host_id="host1", deployed_at="2024-01-01T00:00:00Z"),
            ],
        )
        assert key.remove_deployment("host1") is True
        assert len(key.deployments) == 0
        assert key.remove_deployment("nonexistent") is False


class TestHost:
    """Tests for Host dataclass."""

    def test_to_dict_minimal(self):
        host = Host(
            id="test-host",
            hostname="192.168.1.1",
            user="admin",
        )
        result = host.to_dict()
        assert result["hostname"] == "192.168.1.1"
        assert result["user"] == "admin"
        assert "port" not in result
        assert "keys" not in result

    def test_to_dict_full(self):
        host = Host(
            id="test-host",
            hostname="192.168.1.1",
            user="admin",
            port=2222,
            keys=["key1", "key2"],
        )
        result = host.to_dict()
        assert result["port"] == 2222
        assert result["keys"] == ["key1", "key2"]

    def test_ssh_destination(self):
        host = Host(id="test", hostname="example.com", user="admin")
        assert host.ssh_destination() == "admin@example.com"

    def test_ssh_args_default_port(self):
        host = Host(id="test", hostname="example.com", user="admin")
        assert host.ssh_args() == []

    def test_ssh_args_custom_port(self):
        host = Host(id="test", hostname="example.com", user="admin", port=2222)
        assert host.ssh_args() == ["-p", "2222"]


class TestInventory:
    """Tests for Inventory dataclass."""

    def test_empty_inventory(self):
        inv = Inventory()
        assert inv.version == "1.0"
        assert len(inv.keys) == 0
        assert len(inv.hosts) == 0

    def test_add_and_get_key(self):
        inv = Inventory()
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        inv.add_key(key)
        assert inv.get_key("test-key") == key
        assert inv.get_key("nonexistent") is None

    def test_add_and_get_host(self):
        inv = Inventory()
        host = Host(id="test-host", hostname="192.168.1.1", user="admin")
        inv.add_host(host)
        assert inv.get_host("test-host") == host
        assert inv.get_host("nonexistent") is None

    def test_remove_key(self):
        inv = Inventory()
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        inv.add_key(key)
        assert inv.remove_key("test-key") is True
        assert inv.get_key("test-key") is None
        assert inv.remove_key("test-key") is False

    def test_remove_host(self):
        inv = Inventory()
        host = Host(id="test-host", hostname="192.168.1.1", user="admin")
        inv.add_host(host)
        assert inv.remove_host("test-host") is True
        assert inv.get_host("test-host") is None
        assert inv.remove_host("test-host") is False

    def test_get_keys_for_host(self):
        inv = Inventory()
        key1 = SSHKey(
            id="key1",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/key1.pub",
            private_key_path="~/.ssh/key1",
            fingerprint="SHA256:abc123",
            deployments=[Deployment(host_id="host1", deployed_at="2024-01-01T00:00:00Z")],
        )
        key2 = SSHKey(
            id="key2",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/key2.pub",
            private_key_path="~/.ssh/key2",
            fingerprint="SHA256:def456",
        )
        inv.add_key(key1)
        inv.add_key(key2)

        keys = inv.get_keys_for_host("host1")
        assert len(keys) == 1
        assert keys[0].id == "key1"

    def test_to_dict_and_from_dict(self):
        inv = Inventory()
        key = SSHKey(
            id="test-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            public_key_path="~/.ssh/test.pub",
            private_key_path="~/.ssh/test",
            fingerprint="SHA256:abc123",
        )
        host = Host(id="test-host", hostname="192.168.1.1", user="admin")
        inv.add_key(key)
        inv.add_host(host)

        data = inv.to_dict()
        restored = Inventory.from_dict(data)

        assert restored.version == inv.version
        assert "test-key" in restored.keys
        assert "test-host" in restored.hosts

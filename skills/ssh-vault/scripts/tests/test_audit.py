"""Tests for SSH Vault security audit."""

import pytest
from datetime import datetime, timezone, timedelta
from pathlib import Path
import tempfile
import shutil
import os

from audit import (
    run_audit, AuditReport, AuditFinding,
    _check_file_permissions, get_audit_summary,
)
from inventory import InventoryManager
from models import SSHKey, Host, Deployment, Inventory


@pytest.fixture
def temp_vault_dir():
    """Create a temporary vault directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    yield temp_dir
    shutil.rmtree(temp_dir)


@pytest.fixture
def temp_ssh_dir():
    """Create a temporary SSH directory for testing."""
    temp_dir = Path(tempfile.mkdtemp())
    temp_dir.chmod(0o700)
    yield temp_dir
    shutil.rmtree(temp_dir)


class TestAuditReport:
    """Tests for AuditReport class."""

    def test_empty_report(self):
        report = AuditReport(timestamp="2024-01-01T00:00:00Z")
        assert report.critical_count == 0
        assert report.warning_count == 0
        assert report.info_count == 0
        assert report.is_healthy() is True

    def test_counts(self):
        report = AuditReport(
            timestamp="2024-01-01T00:00:00Z",
            findings=[
                AuditFinding("critical", "key1", "msg", "rec"),
                AuditFinding("critical", "key2", "msg", "rec"),
                AuditFinding("warning", "key3", "msg", "rec"),
                AuditFinding("info", None, "msg", "rec"),
            ]
        )
        assert report.critical_count == 2
        assert report.warning_count == 1
        assert report.info_count == 1
        assert report.is_healthy() is False

    def test_to_dict(self):
        report = AuditReport(
            timestamp="2024-01-01T00:00:00Z",
            keys_checked=5,
            hosts_checked=3,
            findings=[
                AuditFinding("warning", "key1", "test message", "test rec"),
            ]
        )
        result = report.to_dict()
        assert result["timestamp"] == "2024-01-01T00:00:00Z"
        assert result["summary"]["keys_checked"] == 5
        assert result["summary"]["hosts_checked"] == 3
        assert result["summary"]["healthy"] is True
        assert len(result["findings"]) == 1


class TestFilePermissions:
    """Tests for file permission checking."""

    def test_private_key_correct_permissions(self, temp_ssh_dir):
        key_file = temp_ssh_dir / "test_key"
        key_file.touch()
        key_file.chmod(0o600)
        assert _check_file_permissions(key_file) is None

    def test_private_key_too_open(self, temp_ssh_dir):
        key_file = temp_ssh_dir / "test_key"
        key_file.touch()
        key_file.chmod(0o644)
        result = _check_file_permissions(key_file)
        assert result is not None
        assert "too open" in result

    def test_public_key_correct_permissions(self, temp_ssh_dir):
        key_file = temp_ssh_dir / "test_key.pub"
        key_file.touch()
        key_file.chmod(0o644)
        assert _check_file_permissions(key_file) is None

    def test_nonexistent_file(self, temp_ssh_dir):
        result = _check_file_permissions(temp_ssh_dir / "nonexistent")
        assert result is None


class TestRunAudit:
    """Tests for run_audit function."""

    def test_audit_empty_inventory(self, temp_vault_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        report = run_audit(manager)
        assert report.keys_checked == 0
        assert report.hosts_checked == 0

    def test_audit_expired_key(self, temp_vault_dir, temp_ssh_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        manager.ssh_dir = temp_ssh_dir

        # Create key files
        private_key = temp_ssh_dir / "expired-key"
        public_key = temp_ssh_dir / "expired-key.pub"
        private_key.write_text("fake private key")
        public_key.write_text("fake public key")
        private_key.chmod(0o600)
        public_key.chmod(0o644)

        inventory = Inventory()
        key = SSHKey(
            id="expired-key",
            algorithm="ed25519",
            created_at="2020-01-01T00:00:00Z",
            expires_at="2021-01-01T00:00:00Z",  # Expired
            public_key_path=str(public_key),
            private_key_path=str(private_key),
            fingerprint="SHA256:abc123",
        )
        inventory.add_key(key)
        manager.save(inventory)

        report = run_audit(manager)
        assert report.keys_checked == 1
        assert report.critical_count >= 1
        # Should have an expired key finding
        expired_findings = [f for f in report.findings if "expired" in f.message.lower()]
        assert len(expired_findings) >= 1

    def test_audit_key_no_passphrase(self, temp_vault_dir, temp_ssh_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        manager.ssh_dir = temp_ssh_dir

        # Create key files
        private_key = temp_ssh_dir / "no-pass-key"
        public_key = temp_ssh_dir / "no-pass-key.pub"
        private_key.write_text("fake private key")
        public_key.write_text("fake public key")
        private_key.chmod(0o600)
        public_key.chmod(0o644)

        inventory = Inventory()
        future = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
        key = SSHKey(
            id="no-pass-key",
            algorithm="ed25519",
            created_at="2024-01-01T00:00:00Z",
            expires_at=future,
            public_key_path=str(public_key),
            private_key_path=str(private_key),
            fingerprint="SHA256:abc123",
            has_passphrase=False,
        )
        inventory.add_key(key)
        manager.save(inventory)

        report = run_audit(manager)
        # Should have a warning about no passphrase
        passphrase_findings = [f for f in report.findings if "passphrase" in f.message.lower()]
        assert len(passphrase_findings) >= 1

    def test_audit_specific_key(self, temp_vault_dir, temp_ssh_dir):
        manager = InventoryManager(vault_dir=temp_vault_dir)
        manager.ssh_dir = temp_ssh_dir

        # Create key files for two keys
        for key_id in ["key1", "key2"]:
            private_key = temp_ssh_dir / key_id
            public_key = temp_ssh_dir / f"{key_id}.pub"
            private_key.write_text("fake private key")
            public_key.write_text("fake public key")
            private_key.chmod(0o600)
            public_key.chmod(0o644)

        inventory = Inventory()
        future = (datetime.now(timezone.utc) + timedelta(days=365)).strftime("%Y-%m-%dT%H:%M:%SZ")
        for key_id in ["key1", "key2"]:
            key = SSHKey(
                id=key_id,
                algorithm="ed25519",
                created_at="2024-01-01T00:00:00Z",
                expires_at=future,
                public_key_path=str(temp_ssh_dir / f"{key_id}.pub"),
                private_key_path=str(temp_ssh_dir / key_id),
                fingerprint=f"SHA256:{key_id}",
            )
            inventory.add_key(key)
        manager.save(inventory)

        # Audit only key1
        report = run_audit(manager, key_id="key1")
        assert report.keys_checked == 1


class TestGetAuditSummary:
    """Tests for get_audit_summary function."""

    def test_healthy_summary(self):
        report = AuditReport(
            timestamp="2024-01-01T00:00:00Z",
            keys_checked=5,
            hosts_checked=3,
        )
        summary = get_audit_summary(report)
        assert "HEALTHY" in summary
        assert "Keys checked: 5" in summary

    def test_unhealthy_summary(self):
        report = AuditReport(
            timestamp="2024-01-01T00:00:00Z",
            findings=[
                AuditFinding("critical", "key1", "Key expired", "Rotate key"),
            ]
        )
        summary = get_audit_summary(report)
        assert "ISSUES FOUND" in summary
        assert "Key expired" in summary
        assert "Rotate key" in summary

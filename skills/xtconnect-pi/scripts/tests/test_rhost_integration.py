"""Tests for rhost_integration module."""

import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest

# Import the module under test
import sys
sys.path.insert(0, str(Path(__file__).parent.parent))

from rhost_integration import (
    find_xtconnect_host,
    register_pi_node,
    register_nodes_batch,
    list_xtconnect_hosts,
    _find_best_ssh_key,
    XTCONNECT_ENVIRONMENT,
)


class TestFindXtconnectHost:
    """Tests for find_xtconnect_host function."""

    def test_exact_match(self):
        """Should find host by exact host_id."""
        mock_hosts = {
            "hosts": {
                "xtconnect-master": {
                    "hostname": "xtconnect-master.local",
                    "user": "pi",
                    "environment": XTCONNECT_ENVIRONMENT,
                }
            }
        }
        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            result = find_xtconnect_host("xtconnect-master")
            assert result is not None
            assert result["hostname"] == "xtconnect-master.local"
            assert result["host_id"] == "xtconnect-master"

    def test_partial_match_adds_prefix(self):
        """Should find host when given partial identifier."""
        mock_hosts = {
            "hosts": {
                "xtconnect-master": {
                    "hostname": "xtconnect-master.local",
                    "user": "pi",
                    "environment": XTCONNECT_ENVIRONMENT,
                }
            }
        }
        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            result = find_xtconnect_host("master")
            assert result is not None
            assert result["host_id"] == "xtconnect-master"

    def test_strips_local_suffix(self):
        """Should strip .local suffix when searching."""
        mock_hosts = {
            "hosts": {
                "xtconnect-master": {
                    "hostname": "xtconnect-master.local",
                    "user": "pi",
                    "environment": XTCONNECT_ENVIRONMENT,
                }
            }
        }
        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            result = find_xtconnect_host("xtconnect-master.local")
            assert result is not None
            assert result["host_id"] == "xtconnect-master"

    def test_not_found_returns_none(self):
        """Should return None when host not found."""
        mock_hosts = {"hosts": {}}
        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            result = find_xtconnect_host("nonexistent")
            assert result is None


class TestRegisterPiNode:
    """Tests for register_pi_node function."""

    def test_registers_new_node(self):
        """Should register a new node."""
        mock_hosts = {"hosts": {}}
        saved_data = {}

        def mock_save(data):
            saved_data.update(data)

        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            with patch("rhost_integration.save_rhost_hosts", side_effect=mock_save):
                with patch("rhost_integration._find_best_ssh_key", return_value="~/.ssh/test"):
                    result = register_pi_node(
                        hostname="xtconnect-test.local",
                        node_id="test",
                        node_type="production",
                    )

        assert result is True
        assert "xtconnect-test" in saved_data["hosts"]
        host = saved_data["hosts"]["xtconnect-test"]
        assert host["hostname"] == "xtconnect-test.local"
        assert host["user"] == "pi"
        assert host["environment"] == XTCONNECT_ENVIRONMENT
        assert host["docker"] is True

    def test_skips_existing_node(self):
        """Should not overwrite existing node without force."""
        mock_hosts = {
            "hosts": {
                "xtconnect-test": {"hostname": "old.local"}
            }
        }

        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            result = register_pi_node(
                hostname="xtconnect-test.local",
                node_id="test",
                force=False,
            )

        assert result is False

    def test_force_overwrites(self):
        """Should overwrite existing node with force=True."""
        mock_hosts = {
            "hosts": {
                "xtconnect-test": {"hostname": "old.local"}
            }
        }
        saved_data = {}

        def mock_save(data):
            saved_data.update(data)

        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            with patch("rhost_integration.save_rhost_hosts", side_effect=mock_save):
                with patch("rhost_integration._find_best_ssh_key", return_value=None):
                    result = register_pi_node(
                        hostname="xtconnect-test.local",
                        node_id="test",
                        force=True,
                    )

        assert result is True
        assert saved_data["hosts"]["xtconnect-test"]["hostname"] == "xtconnect-test.local"


class TestRegisterNodesBatch:
    """Tests for register_nodes_batch function."""

    def test_registers_multiple_nodes(self):
        """Should register multiple nodes at once."""
        mock_hosts = {"hosts": {}}
        saved_data = {}

        def mock_save(data):
            saved_data.update(data)

        nodes = [
            {"hostname": "xtconnect-a.local", "node_id": "a", "node_type": "production"},
            {"hostname": "xtconnect-b.local", "node_id": "b", "node_type": "master"},
        ]

        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            with patch("rhost_integration.save_rhost_hosts", side_effect=mock_save):
                with patch("rhost_integration._find_best_ssh_key", return_value="~/.ssh/test"):
                    count = register_nodes_batch(nodes)

        assert count == 2
        assert "xtconnect-a" in saved_data["hosts"]
        assert "xtconnect-b" in saved_data["hosts"]

    def test_skips_existing_nodes(self):
        """Should skip nodes that already exist."""
        mock_hosts = {
            "hosts": {
                "xtconnect-a": {"hostname": "existing.local"}
            }
        }
        saved_data = {}

        def mock_save(data):
            saved_data.update(data)

        nodes = [
            {"hostname": "xtconnect-a.local", "node_id": "a"},
            {"hostname": "xtconnect-b.local", "node_id": "b"},
        ]

        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            with patch("rhost_integration.save_rhost_hosts", side_effect=mock_save):
                with patch("rhost_integration._find_best_ssh_key", return_value=None):
                    count = register_nodes_batch(nodes)

        assert count == 1  # Only b was registered
        # Existing node should not be overwritten
        assert saved_data["hosts"]["xtconnect-a"]["hostname"] == "existing.local"


class TestListXtconnectHosts:
    """Tests for list_xtconnect_hosts function."""

    def test_lists_only_xtconnect_hosts(self):
        """Should only return hosts with xtconnect environment."""
        mock_hosts = {
            "hosts": {
                "xtconnect-pi": {
                    "hostname": "pi.local",
                    "environment": XTCONNECT_ENVIRONMENT,
                },
                "other-server": {
                    "hostname": "server.local",
                    "environment": "prod",
                },
            }
        }

        with patch("rhost_integration.load_rhost_hosts", return_value=mock_hosts):
            result = list_xtconnect_hosts()

        assert len(result) == 1
        assert result[0]["host_id"] == "xtconnect-pi"

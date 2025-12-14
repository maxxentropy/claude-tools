"""Tests for pi_client module."""

import pytest
from unittest.mock import patch, MagicMock

import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from pi_client import (
    PiClient,
    CommandResult,
    ContainerInfo,
    NodeInfo,
    PortStatus,
    discover_nodes,
)


class TestCommandResult:
    """Tests for CommandResult dataclass."""

    def test_success_true_when_exit_code_zero(self):
        result = CommandResult(
            stdout="output",
            stderr="",
            exit_code=0,
            duration_ms=100
        )
        assert result.success is True

    def test_success_false_when_exit_code_nonzero(self):
        result = CommandResult(
            stdout="",
            stderr="error",
            exit_code=1,
            duration_ms=100
        )
        assert result.success is False

    def test_output_returns_stdout_on_success(self):
        result = CommandResult(
            stdout="hello",
            stderr="warning",
            exit_code=0,
            duration_ms=100
        )
        assert result.output == "hello"

    def test_output_returns_combined_on_failure(self):
        result = CommandResult(
            stdout="partial",
            stderr="error message",
            exit_code=1,
            duration_ms=100
        )
        assert "partial" in result.output
        assert "error message" in result.output


class TestPiClient:
    """Tests for PiClient class."""

    def test_init_default_values(self):
        client = PiClient("test.local")
        assert client.hostname == "test.local"
        assert client.user == "pi"
        assert client.timeout == 10

    def test_init_custom_values(self):
        client = PiClient(
            hostname="custom.local",
            user="admin",
            key_path="/custom/key",
            timeout=30
        )
        assert client.hostname == "custom.local"
        assert client.user == "admin"
        assert client.key_path == "/custom/key"
        assert client.timeout == 30

    def test_ssh_target(self):
        client = PiClient("test.local", user="pi")
        assert client.ssh_target == "pi@test.local"

    @patch("subprocess.run")
    def test_test_connection_success(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="connected",
            stderr="",
            returncode=0
        )
        client = PiClient("test.local")
        success, msg = client.test_connection()
        assert success is True
        assert "success" in msg.lower()

    @patch("subprocess.run")
    def test_test_connection_failure(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout="",
            stderr="Connection refused",
            returncode=1
        )
        client = PiClient("test.local")
        success, msg = client.test_connection()
        assert success is False


class TestNodeInfo:
    """Tests for NodeInfo dataclass."""

    def test_production_node(self):
        node = NodeInfo(
            hostname="xtconnect-abc123.local",
            node_id="abc123",
            node_type="production",
            online=True
        )
        assert node.node_type == "production"
        assert node.online is True

    def test_master_node(self):
        node = NodeInfo(
            hostname="xtconnect-master.local",
            node_id="master",
            node_type="master",
            online=True
        )
        assert node.node_type == "master"


class TestPortStatus:
    """Tests for PortStatus dataclass."""

    def test_port_not_found(self):
        status = PortStatus(
            exists=False,
            device_path="/dev/xtconnect-serial"
        )
        assert status.exists is False
        assert status.is_open is False

    def test_port_available(self):
        status = PortStatus(
            exists=True,
            device_path="/dev/xtconnect-serial",
            symlink_target="/dev/ttyUSB0",
            is_open=False
        )
        assert status.exists is True
        assert status.is_open is False

    def test_port_in_use(self):
        status = PortStatus(
            exists=True,
            device_path="/dev/xtconnect-serial",
            symlink_target="/dev/ttyUSB0",
            is_open=True,
            owner_process="docker"
        )
        assert status.exists is True
        assert status.is_open is True
        assert status.owner_process == "docker"

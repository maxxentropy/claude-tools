"""
Shared SSH client library for connecting to XTConnect Pi nodes.

Provides:
- SSH connection management with retry
- Command execution with timeout
- Docker command wrappers
- File operations via SFTP
"""

import json
import os
import subprocess
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional


@dataclass
class CommandResult:
    """Result of a remote command execution."""
    stdout: str
    stderr: str
    exit_code: int
    duration_ms: int

    @property
    def success(self) -> bool:
        return self.exit_code == 0

    @property
    def output(self) -> str:
        """Combined stdout/stderr for convenience."""
        return self.stdout if self.success else f"{self.stdout}\n{self.stderr}".strip()


@dataclass
class ContainerInfo:
    """Docker container information."""
    name: str
    image: str
    status: str
    uptime: str
    health: Optional[str] = None


@dataclass
class NodeInfo:
    """Information about a discovered node."""
    hostname: str
    node_id: str
    node_type: str  # 'production' or 'master'
    online: bool = False
    ip_address: Optional[str] = None


@dataclass
class PortStatus:
    """Serial port status information."""
    exists: bool
    device_path: str
    symlink_target: Optional[str] = None
    is_open: bool = False
    owner_process: Optional[str] = None
    baud_rate: Optional[int] = None
    device_info: Optional[str] = None


class PiClient:
    """SSH client for XTConnect Pi node operations."""

    def __init__(
        self,
        hostname: str,
        user: str = "pi",
        key_path: Optional[str] = None,
        timeout: int = 10
    ):
        self.hostname = hostname
        self.user = user
        self.key_path = key_path or os.path.expanduser("~/.ssh/id_rsa")
        self.timeout = timeout
        self._connected = False

    @property
    def ssh_target(self) -> str:
        """SSH connection string."""
        return f"{self.user}@{self.hostname}"

    def _build_ssh_cmd(self, command: str, allocate_tty: bool = False) -> list[str]:
        """Build SSH command with options."""
        cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={self.timeout}",
            "-o", "BatchMode=yes",
            "-i", self.key_path,
        ]
        if allocate_tty:
            cmd.append("-t")
        cmd.extend([self.ssh_target, command])
        return cmd

    def test_connection(self) -> tuple[bool, str]:
        """Test SSH connectivity to the node."""
        try:
            result = self.run_command("echo connected", timeout=self.timeout)
            if result.success and "connected" in result.stdout:
                self._connected = True
                return True, "Connected successfully"
            return False, f"Unexpected response: {result.output}"
        except Exception as e:
            return False, str(e)

    def run_command(
        self,
        command: str,
        timeout: Optional[int] = None,
        check: bool = False
    ) -> CommandResult:
        """Execute a command on the remote Pi."""
        timeout = timeout or 30
        ssh_cmd = self._build_ssh_cmd(command)

        start = time.time()
        try:
            result = subprocess.run(
                ssh_cmd,
                capture_output=True,
                text=True,
                timeout=timeout
            )
            duration_ms = int((time.time() - start) * 1000)

            cmd_result = CommandResult(
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
                exit_code=result.returncode,
                duration_ms=duration_ms
            )

            if check and not cmd_result.success:
                raise RuntimeError(f"Command failed: {cmd_result.stderr}")

            return cmd_result

        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start) * 1000)
            return CommandResult(
                stdout="",
                stderr=f"Command timed out after {timeout}s",
                exit_code=-1,
                duration_ms=duration_ms
            )

    def get_file(self, remote_path: str) -> Optional[str]:
        """Read a file from the remote Pi."""
        result = self.run_command(f"cat {remote_path}")
        return result.stdout if result.success else None

    def file_exists(self, remote_path: str) -> bool:
        """Check if a file exists on the remote Pi."""
        result = self.run_command(f"test -f {remote_path} && echo exists")
        return result.success and "exists" in result.stdout

    def dir_exists(self, remote_path: str) -> bool:
        """Check if a directory exists on the remote Pi."""
        result = self.run_command(f"test -d {remote_path} && echo exists")
        return result.success and "exists" in result.stdout

    # Docker operations

    def docker_ps(self) -> list[ContainerInfo]:
        """List running Docker containers."""
        result = self.run_command(
            "docker ps --format '{{.Names}}|{{.Image}}|{{.Status}}' 2>/dev/null"
        )
        if not result.success:
            return []

        containers = []
        for line in result.stdout.strip().split("\n"):
            if not line or "|" not in line:
                continue
            parts = line.split("|")
            if len(parts) >= 3:
                containers.append(ContainerInfo(
                    name=parts[0],
                    image=parts[1],
                    status=parts[2],
                    uptime=parts[2]  # Status includes uptime info
                ))
        return containers

    def docker_logs(
        self,
        container: str = "xtconnect-node",
        lines: int = 100,
        follow: bool = False
    ) -> CommandResult:
        """Get Docker container logs."""
        cmd = f"docker logs --tail {lines}"
        if follow:
            cmd += " -f"
        cmd += f" {container} 2>&1"
        return self.run_command(cmd, timeout=60 if follow else 30)

    def docker_health(self, container: str = "xtconnect-node") -> Optional[str]:
        """Check container health status."""
        result = self.run_command(
            f"docker inspect --format='{{{{.State.Health.Status}}}}' {container} 2>/dev/null"
        )
        return result.stdout if result.success else None

    def docker_restart(self, container: str = "xtconnect-node") -> bool:
        """Restart a Docker container."""
        result = self.run_command(f"docker restart {container}", timeout=60)
        return result.success

    # System operations

    def get_node_info(self) -> Optional[dict]:
        """Get node-info.json from the Pi."""
        content = self.get_file("/data/config/node-info.json")
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        return None

    def get_app_config(self) -> Optional[dict]:
        """Get appsettings.json from the Pi."""
        content = self.get_file("/data/config/appsettings.json")
        if content:
            try:
                return json.loads(content)
            except json.JSONDecodeError:
                return None
        return None

    def get_disk_usage(self) -> Optional[dict]:
        """Get disk usage information."""
        result = self.run_command("df -h / | tail -1")
        if not result.success:
            return None

        parts = result.stdout.split()
        if len(parts) >= 5:
            return {
                "total": parts[1],
                "used": parts[2],
                "available": parts[3],
                "use_percent": parts[4]
            }
        return None

    def get_memory_usage(self) -> Optional[dict]:
        """Get memory usage information."""
        result = self.run_command("free -m | grep Mem")
        if not result.success:
            return None

        parts = result.stdout.split()
        if len(parts) >= 3:
            return {
                "total_mb": int(parts[1]),
                "used_mb": int(parts[2]),
                "available_mb": int(parts[6]) if len(parts) > 6 else None
            }
        return None

    def get_cpu_usage(self) -> Optional[float]:
        """Get current CPU usage percentage."""
        result = self.run_command(
            "top -bn1 | grep 'Cpu(s)' | awk '{print $2}'"
        )
        if result.success and result.stdout:
            try:
                return float(result.stdout.replace(",", "."))
            except ValueError:
                pass
        return None

    def get_uptime(self) -> Optional[str]:
        """Get system uptime."""
        result = self.run_command("uptime -p")
        return result.stdout if result.success else None

    # Serial port operations

    def get_serial_port_status(self) -> PortStatus:
        """Check serial port status."""
        device_path = "/dev/xtconnect-serial"

        # Check if device exists
        exists_result = self.run_command(f"test -e {device_path} && echo exists")
        exists = "exists" in exists_result.stdout

        if not exists:
            return PortStatus(exists=False, device_path=device_path)

        # Get symlink target
        link_result = self.run_command(f"readlink -f {device_path}")
        symlink_target = link_result.stdout if link_result.success else None

        # Check if port is open (by any process)
        lsof_result = self.run_command(f"lsof {device_path} 2>/dev/null | tail -1")
        is_open = bool(lsof_result.stdout)
        owner_process = lsof_result.stdout.split()[0] if is_open else None

        # Get device info (FTDI details)
        device_info = None
        if symlink_target:
            usb_path = symlink_target.replace("/dev/", "")
            info_result = self.run_command(
                f"udevadm info -q property -n {symlink_target} 2>/dev/null | grep -E '(ID_MODEL|ID_VENDOR)'"
            )
            if info_result.success:
                device_info = info_result.stdout.replace("\n", ", ")

        return PortStatus(
            exists=True,
            device_path=device_path,
            symlink_target=symlink_target,
            is_open=is_open,
            owner_process=owner_process,
            device_info=device_info
        )

    def check_service_status(self, service: str) -> dict:
        """Check systemd service status."""
        result = self.run_command(
            f"systemctl is-active {service} 2>/dev/null && systemctl is-enabled {service} 2>/dev/null"
        )
        lines = result.stdout.strip().split("\n") if result.stdout else []
        return {
            "active": lines[0] == "active" if lines else False,
            "enabled": lines[1] == "enabled" if len(lines) > 1 else False
        }


def discover_nodes(timeout: int = 5) -> list[NodeInfo]:
    """Discover XTConnect nodes on the local network using mDNS."""
    nodes = []
    found_hostnames = set()

    # Method 1: Try avahi-browse (Linux) for _xtconnect._tcp
    try:
        result = subprocess.run(
            ["avahi-browse", "-tpr", "_xtconnect._tcp"],
            capture_output=True,
            text=True,
            timeout=timeout
        )
        for line in result.stdout.split("\n"):
            if line.startswith("=") and "xtconnect" in line:
                parts = line.split(";")
                if len(parts) >= 4:
                    hostname = f"{parts[3]}.local"
                    if hostname not in found_hostnames:
                        found_hostnames.add(hostname)
                        node_id = parts[3].replace("xtconnect-", "")
                        nodes.append(NodeInfo(
                            hostname=hostname,
                            node_id=node_id,
                            node_type="master" if node_id == "master" else "production",
                            online=True
                        ))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Method 2: Use dns-sd on macOS (runs briefly then terminates)
    try:
        import threading

        proc = subprocess.Popen(
            ["dns-sd", "-B", "_ssh._tcp", "local"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        output_lines = []

        def read_output():
            try:
                for line in proc.stdout:
                    output_lines.append(line)
            except:
                pass

        reader = threading.Thread(target=read_output, daemon=True)
        reader.start()
        reader.join(timeout=timeout)
        proc.terminate()
        try:
            proc.wait(timeout=1)
        except:
            proc.kill()

        for line in output_lines:
            if "xtconnect" in line.lower():
                # Parse: "11:45:21.799  Add  2  18 local.  _ssh._tcp.  xtconnect-d9f50b55"
                parts = line.split()
                if len(parts) >= 7:
                    instance_name = parts[-1].strip()
                    if instance_name.startswith("xtconnect-"):
                        hostname = f"{instance_name}.local"
                        if hostname not in found_hostnames:
                            found_hostnames.add(hostname)
                            node_id = instance_name.replace("xtconnect-", "")
                            nodes.append(NodeInfo(
                                hostname=hostname,
                                node_id=node_id,
                                node_type="master" if node_id == "master" else "production",
                                online=True
                            ))
    except (FileNotFoundError, Exception):
        pass

    # Method 3: Check ARP cache for Raspberry Pi MAC prefixes
    try:
        result = subprocess.run(
            ["arp", "-a"],
            capture_output=True,
            text=True,
            timeout=5
        )
        # Raspberry Pi MAC prefixes: b8:27:eb, dc:a6:32, e4:5f:01, d8:3a:dd
        pi_macs = ["b8:27:eb", "dc:a6:32", "e4:5f:01", "d8:3a:dd"]
        for line in result.stdout.split("\n"):
            line_lower = line.lower()
            for mac_prefix in pi_macs:
                if mac_prefix in line_lower:
                    # Try to extract hostname: "hostname.local (ip) at mac..."
                    if "xtconnect" in line_lower:
                        import re
                        match = re.search(r'(xtconnect-\w+)\.local', line_lower)
                        if match:
                            hostname = f"{match.group(1)}.local"
                            if hostname not in found_hostnames:
                                found_hostnames.add(hostname)
                                node_id = match.group(1).replace("xtconnect-", "")
                                nodes.append(NodeInfo(
                                    hostname=hostname,
                                    node_id=node_id,
                                    node_type="master" if node_id == "master" else "production",
                                    online=True
                                ))
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass

    # Method 4: Try common/known hostnames with ping
    common_hosts = [
        "xtconnect-master.local",
    ]
    for hostname in common_hosts:
            try:
                result = subprocess.run(
                    ["ping", "-c", "1", "-W", "1", hostname],
                    capture_output=True,
                    timeout=2
                )
                if result.returncode == 0:
                    node_id = hostname.replace("xtconnect-", "").replace(".local", "")
                    nodes.append(NodeInfo(
                        hostname=hostname,
                        node_id=node_id,
                        node_type="master" if node_id == "master" else "production",
                        online=True
                    ))
            except (subprocess.TimeoutExpired, FileNotFoundError):
                pass

    return nodes


def resolve_hostname(hostname: str) -> Optional[str]:
    """Resolve a hostname to an IP address."""
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", hostname],
            capture_output=True,
            text=True,
            timeout=3
        )
        if result.returncode == 0:
            # Extract IP from ping output
            import re
            match = re.search(r'\((\d+\.\d+\.\d+\.\d+)\)', result.stdout)
            if match:
                return match.group(1)
    except (subprocess.TimeoutExpired, FileNotFoundError):
        pass
    return None

#!/usr/bin/env python3
"""
Serial port monitoring and debugging for XTConnect Pi nodes.

Monitor RS-485 communication with agricultural controllers via the
SignalR protocol trace hub or direct serial port inspection.

Usage:
    python3 serial-monitor.py --status          # Check port status
    python3 serial-monitor.py --live            # Live traffic monitoring
    python3 serial-monitor.py --live --ascii    # With ASCII interpretation
    python3 serial-monitor.py --capture FILE    # Capture to file
"""

import argparse
import json
import os
import signal
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

# Add scripts directory to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from pi_client import PiClient
from node_context import load_context, get_current_hostname, Colors, color


def show_port_status(client: PiClient) -> bool:
    """Display detailed serial port status."""
    print(f"{color('Serial Port Status:', Colors.BOLD)}")
    print()

    port_status = client.get_serial_port_status()

    if not port_status.exists:
        print(f"  Device: {color(port_status.device_path, Colors.RED)}")
        print(f"  Status: {color('NOT FOUND', Colors.RED)}")
        print()
        print("Troubleshooting:")
        print("  - Check USB-serial adapter is connected")
        print("  - Verify FTDI adapter (idVendor=0403, idProduct=6001)")
        print("  - Check udev rule: /etc/udev/rules.d/99-xtconnect.rules")
        print("  - Run 'lsusb' to list USB devices")
        return False

    print(f"  Device: {color(port_status.device_path, Colors.CYAN)}")

    if port_status.symlink_target:
        print(f"  Target: {port_status.symlink_target}")

    if port_status.is_open:
        owner = port_status.owner_process or "unknown"
        print(f"  Status: {color('OPEN', Colors.GREEN)} (by {owner})")
    else:
        print(f"  Status: {color('AVAILABLE', Colors.YELLOW)} (not currently open)")

    if port_status.device_info:
        print(f"  Device Info: {port_status.device_info}")

    # Get configuration from appsettings
    config = client.get_app_config()
    if config:
        serial_config = config.get("NodeConfiguration", {}).get("SerialPort", {})
        if serial_config:
            print()
            print(f"{color('Configuration:', Colors.BOLD)}")
            print(f"  Port Name: {serial_config.get('PortName', 'N/A')}")
            print(f"  Baud Rate: {serial_config.get('BaudRate', 19200)}")
            print(f"  Data Bits: 8")
            print(f"  Stop Bits: 1")
            print(f"  Parity: None")
            if serial_config.get("UseFtdiPort"):
                print(f"  FTDI Mode: Enabled")
            if serial_config.get("FtdiSerialNumber"):
                print(f"  FTDI Serial: {serial_config.get('FtdiSerialNumber')}")

    # Check recent activity via container logs
    result = client.run_command(
        "docker logs --tail 20 xtconnect-node 2>&1 | grep -i serial | tail -5"
    )
    if result.success and result.stdout:
        print()
        print(f"{color('Recent Serial Activity:', Colors.BOLD)}")
        for line in result.stdout.split("\n"):
            if line.strip():
                print(f"  {line.strip()}")

    return True


def monitor_live(
    client: PiClient,
    show_ascii: bool = False,
    decode_modbus: bool = False,
    filter_addr: Optional[str] = None
) -> None:
    """
    Monitor serial traffic in real-time.

    Uses container logs to show protocol trace output from the SignalR hub.
    """
    hostname = client.hostname
    print(f"{color('Live Serial Monitor:', Colors.BOLD)} {hostname}")
    print(f"Monitoring /dev/xtconnect-serial (19200 baud)")
    print(f"Press Ctrl+C to stop")
    print()
    print("-" * 60)

    # Set up signal handler for clean exit
    def signal_handler(sig, frame):
        print()
        print(color("Monitoring stopped.", Colors.DIM))
        sys.exit(0)

    signal.signal(signal.SIGINT, signal_handler)

    # Follow container logs filtered for serial/protocol messages
    # The XTConnect service uses SignalR ProtocolTraceHub for real-time tracing
    cmd = (
        "docker logs -f xtconnect-node 2>&1 | "
        "grep -E --line-buffered '(TX|RX|Serial|Protocol|→|←)'"
    )

    import subprocess
    ssh_config = {
        "user": client.user,
        "key_path": client.key_path,
        "timeout": client.timeout
    }

    ssh_cmd = [
        "ssh",
        "-o", "StrictHostKeyChecking=accept-new",
        "-o", f"ConnectTimeout={client.timeout}",
        "-i", client.key_path,
        f"{client.user}@{client.hostname}",
        cmd
    ]

    try:
        process = subprocess.Popen(
            ssh_cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )

        for line in process.stdout:
            line = line.strip()
            if not line:
                continue

            # Format output
            timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]

            # Detect TX/RX direction
            if "TX" in line or "→" in line:
                direction = color("TX →", Colors.CYAN)
            elif "RX" in line or "←" in line:
                direction = color("RX ←", Colors.GREEN)
            else:
                direction = "    "

            # Extract hex data if present
            # Try to find hex patterns like "01 03 00 00" or "0x01 0x03"
            import re
            hex_match = re.search(r'([0-9A-Fa-f]{2}(?:\s+[0-9A-Fa-f]{2})+)', line)

            if hex_match:
                hex_data = hex_match.group(1)

                # Apply filter if specified
                if filter_addr:
                    if not hex_data.startswith(filter_addr):
                        continue

                output = f"[{timestamp}] {direction} {hex_data}"

                # Add ASCII interpretation if requested
                if show_ascii:
                    try:
                        bytes_data = bytes.fromhex(hex_data.replace(" ", ""))
                        ascii_repr = "".join(
                            chr(b) if 32 <= b < 127 else "."
                            for b in bytes_data
                        )
                        output += f"  |{ascii_repr}|"
                    except ValueError:
                        pass

                # Add Modbus decoding if requested
                if decode_modbus:
                    decoded = decode_modbus_frame(hex_data)
                    if decoded:
                        output += f"\n           {color(decoded, Colors.DIM)}"

                print(output)
            else:
                # Print raw log line if no hex data found
                print(f"[{timestamp}] {line}")

    except Exception as e:
        print(color(f"Error: {e}", Colors.RED))


def decode_modbus_frame(hex_data: str) -> Optional[str]:
    """Decode a Modbus RTU frame (basic decoding)."""
    try:
        bytes_list = [int(b, 16) for b in hex_data.split()]
        if len(bytes_list) < 4:
            return None

        addr = bytes_list[0]
        func = bytes_list[1]

        func_names = {
            0x01: "Read Coils",
            0x02: "Read Discrete Inputs",
            0x03: "Read Holding Registers",
            0x04: "Read Input Registers",
            0x05: "Write Single Coil",
            0x06: "Write Single Register",
            0x0F: "Write Multiple Coils",
            0x10: "Write Multiple Registers",
        }

        func_name = func_names.get(func, f"Function 0x{func:02X}")
        return f"Addr={addr} {func_name}"

    except (ValueError, IndexError):
        return None


def capture_traffic(
    client: PiClient,
    output_file: str,
    duration: int
) -> None:
    """Capture serial traffic to a file for analysis."""
    hostname = client.hostname
    print(f"{color('Capturing Serial Traffic:', Colors.BOLD)}")
    print(f"  Node: {hostname}")
    print(f"  Output: {output_file}")
    print(f"  Duration: {duration} seconds")
    print()
    print("Press Ctrl+C to stop early")
    print()

    # Set up signal handler
    stop_capture = False

    def signal_handler(sig, frame):
        nonlocal stop_capture
        stop_capture = True
        print()
        print(color("Stopping capture...", Colors.YELLOW))

    signal.signal(signal.SIGINT, signal_handler)

    start_time = time.time()
    packet_count = 0
    tx_count = 0
    rx_count = 0

    with open(output_file, "w") as f:
        f.write(f"# XTConnect Serial Capture\n")
        f.write(f"# Node: {hostname}\n")
        f.write(f"# Started: {datetime.now().isoformat()}\n")
        f.write(f"# Duration: {duration}s\n")
        f.write("#\n")

        # Get logs for the duration
        cmd = (
            f"timeout {duration} docker logs -f xtconnect-node 2>&1 | "
            "grep -E --line-buffered '(TX|RX|→|←)'"
        )

        import subprocess
        ssh_cmd = [
            "ssh",
            "-o", "StrictHostKeyChecking=accept-new",
            "-o", f"ConnectTimeout={client.timeout}",
            "-i", client.key_path,
            f"{client.user}@{client.hostname}",
            cmd
        ]

        try:
            process = subprocess.Popen(
                ssh_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            for line in process.stdout:
                if stop_capture:
                    process.terminate()
                    break

                elapsed = time.time() - start_time
                if elapsed >= duration:
                    break

                line = line.strip()
                if not line:
                    continue

                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

                # Count packets
                packet_count += 1
                if "TX" in line or "→" in line:
                    tx_count += 1
                elif "RX" in line or "←" in line:
                    rx_count += 1

                f.write(f"{timestamp} {line}\n")

                # Progress indicator
                if packet_count % 10 == 0:
                    elapsed = time.time() - start_time
                    print(f"\r  Captured: {packet_count} packets ({elapsed:.0f}s)", end="", flush=True)

        except Exception as e:
            print(color(f"\nError during capture: {e}", Colors.RED))

    # Final statistics
    elapsed = time.time() - start_time
    file_size = os.path.getsize(output_file)

    print()
    print()
    print(f"{color('Capture Complete:', Colors.GREEN)}")
    print(f"  Packets: {packet_count}")
    print(f"  TX: {tx_count} packets")
    print(f"  RX: {rx_count} packets")
    print(f"  Duration: {elapsed:.2f} seconds")
    print(f"  File: {output_file} ({file_size / 1024:.1f} KB)")


def main():
    parser = argparse.ArgumentParser(
        description="Monitor RS-485 serial port on XTConnect Pi nodes"
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="Show serial port status and configuration"
    )
    parser.add_argument(
        "--live",
        action="store_true",
        help="Monitor serial traffic in real-time"
    )
    parser.add_argument(
        "--ascii",
        action="store_true",
        help="Show ASCII interpretation of data (with --live)"
    )
    parser.add_argument(
        "--decode",
        choices=["modbus"],
        help="Decode protocol frames (with --live)"
    )
    parser.add_argument(
        "--filter",
        metavar="ADDR",
        help="Filter by Modbus address, e.g., '01' (with --live)"
    )
    parser.add_argument(
        "--capture",
        metavar="FILE",
        help="Capture traffic to file"
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=60,
        help="Capture duration in seconds (default: 60)"
    )
    parser.add_argument(
        "hostname",
        nargs="?",
        help="Target hostname (uses current context if not specified)"
    )

    args = parser.parse_args()
    context = load_context()

    # Determine target hostname
    hostname = args.hostname or get_current_hostname()

    if not hostname:
        print(color("No target node specified.", Colors.RED))
        print("Use node-context.py --set to configure current node.")
        sys.exit(1)

    # Normalize hostname
    if not hostname.endswith(".local") and "." not in hostname:
        hostname = f"{hostname}.local"

    # Create client
    ssh_config = context.get("ssh_config", {})
    client = PiClient(
        hostname=hostname,
        user=ssh_config.get("user", "pi"),
        key_path=os.path.expanduser(ssh_config.get("key_path", "~/.ssh/id_rsa")),
        timeout=ssh_config.get("timeout", 10)
    )

    # Test connection first
    connected, msg = client.test_connection()
    if not connected:
        print(color(f"Cannot connect to {hostname}: {msg}", Colors.RED))
        sys.exit(1)

    # Execute requested action
    if args.live:
        monitor_live(
            client,
            show_ascii=args.ascii,
            decode_modbus=(args.decode == "modbus"),
            filter_addr=args.filter
        )
    elif args.capture:
        capture_traffic(client, args.capture, args.duration)
    else:
        # Default: show status
        success = show_port_status(client)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

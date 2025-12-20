# New Tool: xtpi - XTConnect Pi Node Management CLI

Hi team,

I've created a new command-line tool to streamline debugging and managing our XTConnect Raspberry Pi nodes. This should significantly speed up master image verification and field node troubleshooting.

---

## What is it?

`xtpi` is a unified CLI that lets you quickly connect to, monitor, and debug XTConnect Pi nodes on the network. It handles SSH connection management, serial port debugging, container logs, and fleet-wide status checks.

**Key features:**
- **Auto-discovery** of nodes on the network
- **Connection context** - remembers which node you're working with
- **Serial port debugging** - live monitoring, raw access, hex dumps
- **Fleet management** - status of all known nodes at a glance
- **Config comparison** - diff remote config vs local project
- **One-command deployment** - wraps our deploy.sh script

---

## Installation

### 1. Get the latest code

```bash
cd ~/source/tools/claude-tools
git pull origin main
```

### 2. Run the installer

```bash
./skills/xtconnect-pi/install.sh
```

### 3. Add to your PATH (if needed)

Add this to your `~/.zshrc` or `~/.bashrc`:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

Then reload:

```bash
source ~/.zshrc
```

### 4. Verify installation

```bash
xtpi --help
```

---

## Quick Start

```bash
# Find nodes on the network
xtpi discover

# Connect to a node (by ID or full hostname)
xtpi connect d9f50b55
# or
xtpi connect xtconnect-d9f50b55.local

# Check node status
xtpi status

# View container logs
xtpi logs
xtpi logs -f              # follow mode

# Check serial port
xtpi serial               # status
xtpi serial --live        # monitor traffic

# Open SSH session
xtpi ssh
```

---

## Command Reference

| Command | Description |
|---------|-------------|
| `xtpi discover` | Find XTConnect nodes on network |
| `xtpi discover --scan` | Deeper subnet scan (slower) |
| `xtpi connect <id>` | Connect to node by ID (e.g., `d9f50b55`) |
| `xtpi connect -` | Switch to previous node |
| `xtpi status` | Full node status |
| `xtpi test` | Quick connection test |
| `xtpi serial` | Serial port status |
| `xtpi serial --live` | Monitor serial traffic via docker logs |
| `xtpi serial --raw` | Interactive serial session (picocom) |
| `xtpi serial --dump` | Raw hex dump from port |
| `xtpi logs` | View container logs (last 50 lines) |
| `xtpi logs -f` | Follow logs in real-time |
| `xtpi logs --level ERROR` | Filter by log level |
| `xtpi deploy` | Deploy to current node |
| `xtpi deploy --build` | Build first, then deploy |
| `xtpi fleet` | Status of all known nodes |
| `xtpi config` | View remote configuration |
| `xtpi config --diff` | Compare remote vs local config |
| `xtpi config --pull` | Download config files locally |
| `xtpi ssh` | Open SSH session |
| `xtpi restart` | Restart container |

---

## Common Workflows

### Testing a Master Image

```bash
xtpi connect master
xtpi status
xtpi serial
xtpi logs --level ERROR
```

### Debugging a Field Node

```bash
xtpi discover                    # Find the node
xtpi connect d9f50b55            # Connect to it
xtpi status                      # Check overall health
xtpi serial --live               # Watch serial traffic
xtpi logs -f                     # Follow container logs
```

### Checking Multiple Nodes

```bash
xtpi fleet                       # Status of all known nodes
xtpi fleet --discover            # Also scan for new nodes
```

### Comparing Configurations

```bash
xtpi config --diff               # Compare remote vs local project
xtpi config --pull               # Download remote config for inspection
```

---

## SSH Key Setup

The tool automatically looks for SSH keys in this order:
1. `~/.ssh/xtconnect_pi` (preferred)
2. `~/.ssh/xtconnect`
3. `~/.ssh/id_ed25519`
4. `~/.ssh/id_rsa`

If you have connection issues, ensure your public key is on the Pi's `authorized_keys`.

---

## Example Output

```
$ xtpi status

Node Status: xtconnect-d9f50b55.local
=======================================================

Identity:
  Node ID: D9F50B55
  Hostname: xtconnect-d9f50b55

Container:
  Name: xtconnect-node-blue
  Status: RUNNING (healthy)
  Uptime: Up 22 hours (healthy)

Serial Port:
  Device: /dev/xtconnect-serial → /dev/ttyUSB0
  Status: AVAILABLE

System:
  Uptime: up 22 hours, 41 minutes
  Memory: 425 MB / 1845 MB (23%)
  Disk: 4.9G / 14G (38% used)
  CPU: 0.0%
```

---

## Troubleshooting

**"No nodes discovered"**
- Ensure Pi is powered on and on the same network
- Try connecting directly: `xtpi connect xtconnect-XXXXXX.local`
- Check mDNS is working: `ping xtconnect-master.local`

**"Permission denied (publickey)"**
- Your SSH key isn't authorized on the Pi
- Copy your key: `ssh-copy-id -i ~/.ssh/xtconnect_pi pi@xtconnect-xxx.local`

**"Serial port not found"**
- USB-serial adapter may not be connected
- Check with: `xtpi ssh` then `lsusb | grep FTDI`

---

## Source Code

The tool lives in our claude-tools repo:

```
~/source/tools/claude-tools/skills/xtconnect-pi/
├── scripts/xtpi          # Main CLI
├── SKILL.md              # Full documentation
├── install.sh            # Installer
└── references/           # Troubleshooting guides
```

---

Let me know if you run into any issues or have feature requests!

Sean

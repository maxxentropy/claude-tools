---
name: remote-hosts
description: |
  Connect to and manage remote hosts. Run commands, check logs, debug issues on remote servers.
  Use when asked about: ssh to server, connect to host, check remote logs, debug remote,
  run command on server, PPE server, db server, webservice server, remote debug.
---

# Remote Hosts - Remote Server Access for Claude

Allows Claude to connect to predefined remote hosts and run commands without needing credentials repeated each time.

## Quick Start

```bash
# List configured hosts
rhost list

# Run a command on a host
rhost exec <host-id> "command"

# Interactive shell (for user, not Claude)
rhost shell <host-id>

# Check host connectivity
rhost ping <host-id>

# View recent logs
rhost logs <host-id> [service]
```

## Host Configuration

Hosts are stored in `~/.remote-hosts/hosts.yaml`:

```yaml
hosts:
  ppe-db:
    hostname: 10.0.0.50
    user: admin
    key: ~/.ssh/ppe-access-2025
    description: "PPE environment database server"
    environment: ppe

  ppe-web:
    hostname: 10.0.0.51
    user: admin
    key: ~/.ssh/ppe-access-2025
    description: "PPE webservice server (container host)"
    environment: ppe
    docker: true  # Has docker installed
```

## CLI Reference

### Host Management

```bash
# Add a host
rhost add <host-id> --hostname <ip> --user <user> --key <path>
  --description "description"
  --environment dev|ppe|prod
  --docker                    # Mark as docker host

# List all hosts
rhost list
  --environment <env>         # Filter by environment

# Show host details
rhost show <host-id>

# Remove a host
rhost remove <host-id>

# Test connectivity
rhost ping <host-id>
```

### Remote Execution

```bash
# Run a command
rhost exec <host-id> "command"
  --timeout 30                # Command timeout in seconds

# Run command with sudo
rhost exec <host-id> --sudo "command"

# Get a file
rhost get <host-id> <remote-path> [local-path]

# Put a file
rhost put <host-id> <local-path> <remote-path>
```

### Docker Commands (for docker hosts)

```bash
# List containers
rhost docker <host-id> ps

# View container logs
rhost docker <host-id> logs <container>
  --tail 100
  --follow

# Exec into container
rhost docker <host-id> exec <container> "command"

# Restart container
rhost docker <host-id> restart <container>
```

### Logs & Debugging

```bash
# View system logs
rhost logs <host-id>
  --service <name>            # journalctl -u <service>
  --tail 100
  --since "1 hour ago"

# Check disk space
rhost df <host-id>

# Check memory
rhost free <host-id>

# Check processes
rhost top <host-id>
```

## Environment Tags

Hosts can be tagged with environments for organization:
- `dev` - Development servers
- `ppe` - Pre-production/staging
- `prod` - Production (commands require confirmation)

## Security Notes

1. **Keys stay local** - Only key paths are stored, not key contents
2. **No passwords stored** - Use SSH keys only
3. **Prod safeguards** - Production hosts require confirmation for destructive commands
4. **Audit trail** - Commands are logged to `~/.remote-hosts/history.log`

## For Claude

When debugging remote issues:
1. Use `rhost ping` first to verify connectivity
2. Use `rhost exec` to run diagnostic commands
3. For docker hosts, use `rhost docker logs` to check container logs
4. Check `rhost df` and `rhost free` for resource issues

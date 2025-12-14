# XTConnect Pi Troubleshooting Guide

Common issues and solutions for XTConnect Pi nodes.

## Connection Issues

### Cannot resolve hostname (mDNS)

**Symptoms:**
- `ssh: Could not resolve hostname xtconnect-xxx.local`
- Ping to `.local` hostname fails

**Causes:**
- Pi not powered on or booting
- Network connectivity issues
- mDNS/Bonjour not working on network

**Solutions:**
1. Verify Pi is powered (LED activity)
2. Check Pi is on same network segment
3. Try using IP address instead:
   ```bash
   # Find IP via router admin or network scan
   nmap -sn 192.168.1.0/24 | grep -i raspberry
   ```
4. On macOS, restart mDNS responder:
   ```bash
   sudo killall -HUP mDNSResponder
   ```

### Permission denied (publickey)

**Symptoms:**
- SSH connects but authentication fails
- `Permission denied (publickey)`

**Causes:**
- Wrong SSH key
- Key not added to authorized_keys on Pi
- Key permissions incorrect

**Solutions:**
1. Specify correct key:
   ```bash
   python3 connect.py --test --key-path ~/.ssh/correct_key
   ```
2. Copy key to Pi (if accessible):
   ```bash
   ssh-copy-id -i ~/.ssh/id_rsa pi@xtconnect-xxx.local
   ```
3. Check key permissions (must be 600):
   ```bash
   chmod 600 ~/.ssh/id_rsa
   ```

### Connection timeout

**Symptoms:**
- SSH hangs then times out
- `Connection timed out` error

**Causes:**
- Network firewall blocking port 22
- Pi not responding (crashed/hung)
- Wrong IP/hostname

**Solutions:**
1. Verify network path:
   ```bash
   ping xtconnect-xxx.local
   traceroute xtconnect-xxx.local
   ```
2. Check for firewall rules
3. Physical access: check Pi status, power cycle if needed

## Serial Port Issues

### Device not found

**Symptoms:**
- `/dev/xtconnect-serial` does not exist
- `No such file or directory` errors

**Causes:**
- USB-serial adapter not connected
- Wrong adapter (not FTDI)
- udev rules not configured

**Solutions:**
1. Check USB device:
   ```bash
   ssh pi@xtconnect-xxx.local "lsusb | grep -i ftdi"
   ```
2. Check for ttyUSB devices:
   ```bash
   ssh pi@xtconnect-xxx.local "ls -la /dev/ttyUSB*"
   ```
3. Verify udev rules:
   ```bash
   ssh pi@xtconnect-xxx.local "cat /etc/udev/rules.d/99-xtconnect.rules"
   ```
4. Reload udev:
   ```bash
   ssh pi@xtconnect-xxx.local "sudo udevadm control --reload && sudo udevadm trigger"
   ```

### Permission denied on serial port

**Symptoms:**
- Port exists but cannot be opened
- `Permission denied: /dev/xtconnect-serial`

**Causes:**
- Docker container not configured for device access
- Wrong permissions on device

**Solutions:**
1. Check device permissions:
   ```bash
   ssh pi@xtconnect-xxx.local "ls -la /dev/xtconnect-serial"
   ```
2. Add pi user to dialout group:
   ```bash
   ssh pi@xtconnect-xxx.local "sudo usermod -a -G dialout pi"
   ```
3. Check docker-compose device mapping

### No serial traffic

**Symptoms:**
- Port opens but no data
- Monitor shows no TX/RX

**Causes:**
- Controller not powered
- Wrong baud rate
- RS-485 wiring incorrect
- Termination resistor issues

**Solutions:**
1. Verify controller power
2. Check baud rate in config (should be 19200)
3. Verify RS-485 A/B wiring (may need to swap)
4. Check termination resistors on RS-485 bus

## Container Issues

### Container not running

**Symptoms:**
- `docker ps` shows no xtconnect container
- Health check fails

**Causes:**
- Container crashed
- Image not pulled
- Docker service issue

**Solutions:**
1. Check container status:
   ```bash
   ssh pi@xtconnect-xxx.local "docker ps -a"
   ```
2. View container logs:
   ```bash
   ssh pi@xtconnect-xxx.local "docker logs xtconnect-node --tail 50"
   ```
3. Try starting container:
   ```bash
   ssh pi@xtconnect-xxx.local "docker start xtconnect-node"
   ```
4. Pull fresh image:
   ```bash
   ssh pi@xtconnect-xxx.local "docker pull xtconnect/node:latest"
   ```

### Container unhealthy

**Symptoms:**
- Container running but health check failing
- `unhealthy` status in docker ps

**Causes:**
- Service inside container crashed
- Port not accessible
- Configuration error

**Solutions:**
1. Check container health:
   ```bash
   python3 check-deployment.py --logs --level ERROR
   ```
2. Restart container:
   ```bash
   python3 check-deployment.py --restart
   ```
3. Verify configuration files exist and are valid

## Configuration Issues

### Missing configuration files

**Symptoms:**
- `/data/config/appsettings.json` not found
- Service starts but doesn't work

**Causes:**
- First boot provisioning failed
- Volume mount issues
- Files deleted accidentally

**Solutions:**
1. Check if auto-provisioning ran:
   ```bash
   ssh pi@xtconnect-xxx.local "cat /data/config/node-info.json"
   ```
2. Manually trigger provisioning:
   ```bash
   ssh pi@xtconnect-xxx.local "sudo systemctl restart xtconnect-boot-manager"
   ```
3. Create configuration manually if needed

### Invalid JSON configuration

**Symptoms:**
- Service fails to start
- JSON parse errors in logs

**Solutions:**
1. Validate JSON:
   ```bash
   python3 check-deployment.py --config
   ```
2. Check for common issues:
   - Trailing commas
   - Missing quotes
   - Unescaped characters

## Disk Space Issues

### SD card full

**Symptoms:**
- Writes failing
- Container cannot start
- System sluggish

**Causes:**
- Logs filling disk
- Docker images accumulating
- Read-write mode left enabled

**Solutions:**
1. Check disk usage:
   ```bash
   ssh pi@xtconnect-xxx.local "df -h"
   ```
2. Clean Docker:
   ```bash
   ssh pi@xtconnect-xxx.local "docker system prune -f"
   ```
3. Remove old logs:
   ```bash
   ssh pi@xtconnect-xxx.local "sudo journalctl --vacuum-time=7d"
   ```
4. Enable read-only mode:
   ```bash
   ssh pi@xtconnect-xxx.local "sudo /usr/local/bin/set-readonly.sh"
   ```

## Network Issues

### Cannot connect to XTConnect API

**Symptoms:**
- Data collection works but upload fails
- API timeout errors in logs

**Causes:**
- Internet connectivity
- DNS resolution
- API endpoint down
- Bearer token invalid

**Solutions:**
1. Test internet connectivity:
   ```bash
   ssh pi@xtconnect-xxx.local "curl -s https://google.com > /dev/null && echo OK"
   ```
2. Test API endpoint:
   ```bash
   ssh pi@xtconnect-xxx.local "curl -I https://dev.xtcwebsvc.valproducts.com/health"
   ```
3. Verify bearer token in configuration

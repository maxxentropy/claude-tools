# XTConnect Pi Deployment Checklist

Reference checklist for deploying and verifying XTConnect Pi nodes.

## Master Image Verification

Before cloning a master image to production units, verify:

### System Checks
- [ ] SSH accessible at `xtconnect-master.local`
- [ ] Docker service running and enabled
- [ ] Boot manager service configured
- [ ] Network connectivity (can reach internet)
- [ ] Adequate disk space (>20% free)

### Application Checks
- [ ] Serial port device exists (`/dev/xtconnect-serial`)
- [ ] udev rules configured (`/etc/udev/rules.d/99-xtconnect.rules`)
- [ ] Config directory structure exists (`/data/config/`)
- [ ] Read-only filesystem scripts installed

### Provisioning Readiness
- [ ] First-boot service configured
- [ ] Auto-provisioning tested (generates Node ID from Pi serial)
- [ ] Hotspot mode functional for WiFi setup

## Production Node Deployment

After imaging a production unit:

### Initial Verification
1. Power on and wait for blue LED (setup mode)
2. Connect to setup hotspot: `Setup-XTConnect-{NodeID}`
3. Configure WiFi via captive portal
4. Verify green LED (connected)

### Remote Verification
```bash
# Discover node
python3 skills/xtconnect-pi/scripts/node-context.py --discover

# Connect and test
python3 skills/xtconnect-pi/scripts/node-context.py --set xtconnect-{nodeid}.local
python3 skills/xtconnect-pi/scripts/connect.py --test -v

# Check deployment
python3 skills/xtconnect-pi/scripts/check-deployment.py
```

### Functional Checks
- [ ] Container running and healthy
- [ ] Serial port detected
- [ ] Communication with controllers (if connected)
- [ ] Data upload to XTConnect API

## Troubleshooting Quick Reference

| Symptom | Check | Fix |
|---------|-------|-----|
| No mDNS hostname | Pi powered? Network? | Check cables, router |
| SSH refused | Key? User? | Check key permissions |
| Container not running | Docker? Image? | Check logs, restart docker |
| Serial port missing | USB adapter? | Reconnect, check lsusb |
| No communication | Baud rate? Wiring? | Verify RS-485 connections |

## Related Scripts

- `master-image-verify.py` - Automated master image validation
- `check-deployment.py` - Production deployment verification
- `connect.py` - Connection testing
- `serial-monitor.py` - Serial port debugging

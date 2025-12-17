"""
Security audit for SSH Vault.

Checks for common security issues with SSH keys.
"""

import os
import stat
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

from models import SSHKey, Inventory
from inventory import InventoryManager, DEFAULT_SSH_DIR


@dataclass
class AuditFinding:
    """A single audit finding."""
    severity: str  # "critical", "warning", "info"
    key_id: Optional[str]
    message: str
    recommendation: str
    auto_fixable: bool = False


@dataclass
class AuditReport:
    """Complete audit report."""
    timestamp: str
    findings: List[AuditFinding] = field(default_factory=list)
    keys_checked: int = 0
    hosts_checked: int = 0

    @property
    def critical_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "critical")

    @property
    def warning_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "warning")

    @property
    def info_count(self) -> int:
        return sum(1 for f in self.findings if f.severity == "info")

    def is_healthy(self) -> bool:
        return self.critical_count == 0

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "summary": {
                "keys_checked": self.keys_checked,
                "hosts_checked": self.hosts_checked,
                "critical": self.critical_count,
                "warnings": self.warning_count,
                "info": self.info_count,
                "healthy": self.is_healthy(),
            },
            "findings": [
                {
                    "severity": f.severity,
                    "key_id": f.key_id,
                    "message": f.message,
                    "recommendation": f.recommendation,
                    "auto_fixable": f.auto_fixable,
                }
                for f in self.findings
            ],
        }


def _check_file_permissions(path: Path) -> Optional[str]:
    """Check if file permissions are secure."""
    if not path.exists():
        return None

    mode = path.stat().st_mode

    # Private keys should be 600 (owner read/write only)
    if path.suffix != ".pub":
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            return f"Permissions too open: {oct(mode)[-3:]}. Should be 600."

    # Public keys can be 644
    else:
        if mode & stat.S_IWGRP or mode & stat.S_IWOTH:
            return f"World/group writable: {oct(mode)[-3:]}. Should be 644 or 600."

    return None


def _check_ssh_dir_permissions() -> Optional[str]:
    """Check if ~/.ssh directory permissions are secure."""
    ssh_dir = DEFAULT_SSH_DIR

    if not ssh_dir.exists():
        return None

    mode = ssh_dir.stat().st_mode
    if mode & (stat.S_IRWXG | stat.S_IRWXO):
        return f"~/.ssh permissions too open: {oct(mode)[-3:]}. Should be 700."

    return None


def _find_untracked_keys(inventory: Inventory) -> List[Path]:
    """Find SSH keys in ~/.ssh that aren't in the inventory."""
    ssh_dir = DEFAULT_SSH_DIR
    if not ssh_dir.exists():
        return []

    untracked = []
    tracked_paths = set()

    for key in inventory.keys.values():
        tracked_paths.add(Path(key.private_key_path).resolve())
        tracked_paths.add(Path(key.public_key_path).resolve())

    # Common key file patterns
    key_patterns = ["id_*", "*_rsa", "*_ed25519", "*_ecdsa", "*_dsa"]

    for pattern in key_patterns:
        for path in ssh_dir.glob(pattern):
            if path.suffix == ".pub":
                continue  # Skip public keys, check private ones
            if path.resolve() not in tracked_paths:
                # Verify it's actually a key file
                try:
                    content = path.read_text(errors="ignore")
                    if "PRIVATE KEY" in content:
                        untracked.append(path)
                except Exception:
                    pass

    return untracked


def run_audit(
    manager: InventoryManager,
    key_id: Optional[str] = None,
) -> AuditReport:
    """
    Run a security audit on managed SSH keys.

    Args:
        manager: Inventory manager
        key_id: Optional specific key to audit (all if None)

    Returns:
        AuditReport with findings
    """
    inventory = manager.load()
    now = datetime.now(timezone.utc)

    report = AuditReport(
        timestamp=now.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )

    # Determine which keys to check
    if key_id:
        key = inventory.get_key(key_id)
        keys_to_check = [key] if key else []
    else:
        keys_to_check = list(inventory.keys.values())

    report.keys_checked = len(keys_to_check)
    report.hosts_checked = len(inventory.hosts)

    # Check ~/.ssh directory permissions
    ssh_dir_issue = _check_ssh_dir_permissions()
    if ssh_dir_issue:
        report.findings.append(AuditFinding(
            severity="warning",
            key_id=None,
            message=ssh_dir_issue,
            recommendation="Run: chmod 700 ~/.ssh",
            auto_fixable=True,
        ))

    # Check each key
    for key in keys_to_check:
        # Check expiration
        if key.is_expired():
            report.findings.append(AuditFinding(
                severity="critical",
                key_id=key.id,
                message=f"Key expired on {key.expires_at}",
                recommendation=f"Rotate with: sshv key rotate {key.id}",
            ))
        else:
            days = key.days_until_expiry()
            if days is not None and days <= 30:
                report.findings.append(AuditFinding(
                    severity="warning",
                    key_id=key.id,
                    message=f"Key expires in {days} days ({key.expires_at})",
                    recommendation=f"Plan rotation: sshv key rotate {key.id}",
                ))
            elif days is not None and days <= 90:
                report.findings.append(AuditFinding(
                    severity="info",
                    key_id=key.id,
                    message=f"Key expires in {days} days",
                    recommendation="Consider scheduling rotation",
                ))

        # Check passphrase
        if not key.has_passphrase:
            report.findings.append(AuditFinding(
                severity="warning",
                key_id=key.id,
                message="Key has no passphrase",
                recommendation="Consider adding passphrase: ssh-keygen -p -f <key>",
            ))

        # Check algorithm
        if key.algorithm == "rsa":
            report.findings.append(AuditFinding(
                severity="info",
                key_id=key.id,
                message="Using RSA algorithm",
                recommendation="Consider ed25519 for better security and performance",
            ))
        elif key.algorithm == "dsa":
            report.findings.append(AuditFinding(
                severity="critical",
                key_id=key.id,
                message="Using deprecated DSA algorithm",
                recommendation="DSA is deprecated. Create new ed25519 key immediately.",
            ))
        elif key.algorithm == "unknown":
            report.findings.append(AuditFinding(
                severity="warning",
                key_id=key.id,
                message="Unknown key algorithm",
                recommendation="Verify key format and consider recreating",
            ))

        # Check file permissions
        private_path = Path(key.private_key_path).expanduser()
        public_path = Path(key.public_key_path).expanduser()

        if not private_path.exists():
            report.findings.append(AuditFinding(
                severity="critical",
                key_id=key.id,
                message=f"Private key file missing: {private_path}",
                recommendation="Restore from backup or remove from inventory",
            ))
        else:
            perm_issue = _check_file_permissions(private_path)
            if perm_issue:
                report.findings.append(AuditFinding(
                    severity="critical",
                    key_id=key.id,
                    message=f"Private key {perm_issue}",
                    recommendation=f"Run: chmod 600 {private_path}",
                    auto_fixable=True,
                ))

        if not public_path.exists():
            report.findings.append(AuditFinding(
                severity="warning",
                key_id=key.id,
                message=f"Public key file missing: {public_path}",
                recommendation="Regenerate from private: ssh-keygen -y -f <private> > <public>",
            ))
        else:
            perm_issue = _check_file_permissions(public_path)
            if perm_issue:
                report.findings.append(AuditFinding(
                    severity="warning",
                    key_id=key.id,
                    message=f"Public key {perm_issue}",
                    recommendation=f"Run: chmod 644 {public_path}",
                    auto_fixable=True,
                ))

        # Check deployments without recent verification
        for deployment in key.deployments:
            if not deployment.verified_at:
                report.findings.append(AuditFinding(
                    severity="info",
                    key_id=key.id,
                    message=f"Deployment to {deployment.host_id} never verified",
                    recommendation=f"Run: sshv verify {key.id} {deployment.host_id}",
                ))
            else:
                # Check if verified recently (within 30 days)
                try:
                    verified = datetime.fromisoformat(
                        deployment.verified_at.replace("Z", "+00:00")
                    )
                    days_since = (now - verified).days
                    if days_since > 30:
                        report.findings.append(AuditFinding(
                            severity="info",
                            key_id=key.id,
                            message=f"Deployment to {deployment.host_id} not verified in {days_since} days",
                            recommendation=f"Run: sshv verify {key.id} {deployment.host_id}",
                        ))
                except ValueError:
                    pass

    # Check for untracked keys (only in full audit)
    if not key_id:
        untracked = _find_untracked_keys(inventory)
        for path in untracked:
            report.findings.append(AuditFinding(
                severity="info",
                key_id=None,
                message=f"Untracked SSH key found: {path}",
                recommendation=f"Import with: sshv key import <id> {path}",
            ))

    return report


def fix_permissions(manager: InventoryManager) -> List[str]:
    """
    Automatically fix file permission issues.

    Returns:
        List of fixes applied
    """
    inventory = manager.load()
    fixes = []

    # Fix ~/.ssh directory
    ssh_dir = DEFAULT_SSH_DIR
    if ssh_dir.exists():
        mode = ssh_dir.stat().st_mode
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            ssh_dir.chmod(0o700)
            fixes.append(f"Fixed ~/.ssh directory permissions to 700")

    # Fix key files
    for key in inventory.keys.values():
        private_path = Path(key.private_key_path).expanduser()
        public_path = Path(key.public_key_path).expanduser()

        if private_path.exists():
            mode = private_path.stat().st_mode
            if mode & (stat.S_IRWXG | stat.S_IRWXO):
                private_path.chmod(0o600)
                fixes.append(f"Fixed {key.id} private key permissions to 600")

        if public_path.exists():
            mode = public_path.stat().st_mode
            if mode & stat.S_IWGRP or mode & stat.S_IWOTH:
                public_path.chmod(0o644)
                fixes.append(f"Fixed {key.id} public key permissions to 644")

    return fixes


def get_audit_summary(report: AuditReport) -> str:
    """Generate a human-readable audit summary."""
    lines = []
    lines.append(f"SSH Vault Security Audit - {report.timestamp}")
    lines.append("=" * 50)
    lines.append(f"Keys checked: {report.keys_checked}")
    lines.append(f"Hosts checked: {report.hosts_checked}")
    lines.append("")

    if report.is_healthy():
        lines.append("Status: HEALTHY")
    else:
        lines.append("Status: ISSUES FOUND")

    lines.append(f"  Critical: {report.critical_count}")
    lines.append(f"  Warnings: {report.warning_count}")
    lines.append(f"  Info: {report.info_count}")
    lines.append("")

    if report.findings:
        lines.append("Findings:")
        lines.append("-" * 50)

        for finding in report.findings:
            severity_icon = {
                "critical": "[!]",
                "warning": "[*]",
                "info": "[i]",
            }.get(finding.severity, "[?]")

            key_info = f" ({finding.key_id})" if finding.key_id else ""
            lines.append(f"{severity_icon}{key_info} {finding.message}")
            lines.append(f"    -> {finding.recommendation}")
            lines.append("")

    return "\n".join(lines)

"""
Data models for SSH Vault.

Defines the core entities: Key, Host, Deployment, and Inventory.
"""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any, Tuple
import subprocess
import re


# Supported algorithms in order of preference
ALGORITHMS = ["ed25519", "ecdsa", "rsa"]
DEFAULT_ALGORITHM = "ed25519"
DEFAULT_EXPIRY_YEARS = 2


# Built-in service profiles with their SSH key requirements
BUILTIN_SERVICES: Dict[str, Dict[str, Any]] = {
    "azure-devops": {
        "name": "Azure DevOps",
        "required_algorithm": "rsa",
        "min_key_bits": 2048,
        "notes": "Azure DevOps only supports RSA keys. ED25519 is not supported.",
        "fingerprints": {
            "md5": "97:70:33:82:fd:29:3a:73:39:af:6a:07:ad:f8:80:49",
            "sha256": "ohD8VZEXGWo6Ez8GSEJQ9WpafgLFsOfLOtGGQCQo6Og",
        },
        "docs_url": "https://docs.microsoft.com/en-us/azure/devops/repos/git/use-ssh-keys-to-authenticate",
    },
    "github": {
        "name": "GitHub",
        "required_algorithm": None,  # Supports all
        "preferred_algorithm": "ed25519",
        "notes": "GitHub supports RSA, ECDSA, and ED25519. ED25519 recommended.",
        "fingerprints": {
            "sha256_rsa": "uNiVztksCsDhcc0u9e8BujQXVUpKZIDTMczCvj3tD2s",
            "sha256_ecdsa": "p2QAMXNIC1TJYWeIOttrVc98/R1BUFWu3/LiyKgUfQM",
            "sha256_ed25519": "+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU",
        },
        "docs_url": "https://docs.github.com/en/authentication/connecting-to-github-with-ssh",
    },
    "gitlab": {
        "name": "GitLab",
        "required_algorithm": None,
        "preferred_algorithm": "ed25519",
        "notes": "GitLab supports RSA, ECDSA, ED25519, and DSA (deprecated). ED25519 recommended.",
        "docs_url": "https://docs.gitlab.com/ee/user/ssh.html",
    },
    "bitbucket": {
        "name": "Bitbucket",
        "required_algorithm": None,
        "preferred_algorithm": "ed25519",
        "notes": "Bitbucket supports RSA and ED25519. ED25519 recommended.",
        "docs_url": "https://support.atlassian.com/bitbucket-cloud/docs/configure-ssh-and-two-step-verification/",
    },
}


def now_utc() -> str:
    """Get current UTC timestamp in ISO format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def parse_duration(duration_str: str) -> int:
    """
    Parse a duration string like '2y', '6m', '30d' into days.

    Supported units: y (years), m (months), d (days)
    """
    match = re.match(r'^(\d+)([ymdYMD])$', duration_str.strip())
    if not match:
        raise ValueError(f"Invalid duration format: {duration_str}. Use format like '2y', '6m', '30d'")

    value = int(match.group(1))
    unit = match.group(2).lower()

    if unit == 'y':
        return value * 365
    elif unit == 'm':
        return value * 30
    elif unit == 'd':
        return value
    else:
        raise ValueError(f"Unknown unit: {unit}")


@dataclass
class Deployment:
    """Represents a key deployment to a host."""
    host_id: str
    deployed_at: str
    verified_at: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "host_id": self.host_id,
            "deployed_at": self.deployed_at,
        }
        if self.verified_at:
            result["verified_at"] = self.verified_at
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Deployment":
        return cls(
            host_id=data["host_id"],
            deployed_at=data["deployed_at"],
            verified_at=data.get("verified_at"),
        )


@dataclass
class SSHKey:
    """Represents an SSH key with metadata."""
    id: str
    algorithm: str
    created_at: str
    public_key_path: str
    private_key_path: str
    fingerprint: str
    purpose: str = ""
    expires_at: Optional[str] = None
    has_passphrase: bool = False
    deployments: List[Deployment] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "algorithm": self.algorithm,
            "created_at": self.created_at,
            "public_key_path": self.public_key_path,
            "private_key_path": self.private_key_path,
            "fingerprint": self.fingerprint,
        }
        if self.purpose:
            result["purpose"] = self.purpose
        if self.expires_at:
            result["expires_at"] = self.expires_at
        if self.has_passphrase:
            result["has_passphrase"] = True
        if self.deployments:
            result["deployments"] = [d.to_dict() for d in self.deployments]
        return result

    @classmethod
    def from_dict(cls, key_id: str, data: Dict[str, Any]) -> "SSHKey":
        deployments = [
            Deployment.from_dict(d) for d in data.get("deployments", [])
        ]
        return cls(
            id=key_id,
            algorithm=data["algorithm"],
            created_at=data["created_at"],
            public_key_path=data["public_key_path"],
            private_key_path=data["private_key_path"],
            fingerprint=data["fingerprint"],
            purpose=data.get("purpose", ""),
            expires_at=data.get("expires_at"),
            has_passphrase=data.get("has_passphrase", False),
            deployments=deployments,
        )

    def is_expired(self) -> bool:
        """Check if key is past its expiration date."""
        if not self.expires_at:
            return False
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            return datetime.now(timezone.utc) > expires
        except ValueError:
            return False

    def days_until_expiry(self) -> Optional[int]:
        """Get days until expiration, or None if no expiry set."""
        if not self.expires_at:
            return None
        try:
            expires = datetime.fromisoformat(self.expires_at.replace("Z", "+00:00"))
            delta = expires - datetime.now(timezone.utc)
            return delta.days
        except ValueError:
            return None

    def get_deployment(self, host_id: str) -> Optional[Deployment]:
        """Get deployment for a specific host."""
        for d in self.deployments:
            if d.host_id == host_id:
                return d
        return None

    def add_deployment(self, host_id: str) -> Deployment:
        """Add or update a deployment."""
        existing = self.get_deployment(host_id)
        if existing:
            existing.deployed_at = now_utc()
            existing.verified_at = now_utc()
            return existing

        deployment = Deployment(
            host_id=host_id,
            deployed_at=now_utc(),
            verified_at=now_utc(),
        )
        self.deployments.append(deployment)
        return deployment

    def remove_deployment(self, host_id: str) -> bool:
        """Remove a deployment. Returns True if found and removed."""
        for i, d in enumerate(self.deployments):
            if d.host_id == host_id:
                self.deployments.pop(i)
                return True
        return False

    def get_public_key_content(self) -> Optional[str]:
        """Read the public key file content."""
        path = Path(self.public_key_path).expanduser()
        if path.exists():
            return path.read_text().strip()
        return None


@dataclass
class Service:
    """Represents a service/platform with SSH key requirements."""
    id: str
    name: str
    required_algorithm: Optional[str] = None  # None means any algorithm
    preferred_algorithm: str = "ed25519"
    min_key_bits: Optional[int] = None
    notes: str = ""
    fingerprints: Dict[str, str] = field(default_factory=dict)
    docs_url: str = ""

    def to_dict(self) -> Dict[str, Any]:
        result = {"name": self.name}
        if self.required_algorithm:
            result["required_algorithm"] = self.required_algorithm
        if self.preferred_algorithm != "ed25519":
            result["preferred_algorithm"] = self.preferred_algorithm
        if self.min_key_bits:
            result["min_key_bits"] = self.min_key_bits
        if self.notes:
            result["notes"] = self.notes
        if self.fingerprints:
            result["fingerprints"] = self.fingerprints
        if self.docs_url:
            result["docs_url"] = self.docs_url
        return result

    @classmethod
    def from_dict(cls, service_id: str, data: Dict[str, Any]) -> "Service":
        return cls(
            id=service_id,
            name=data["name"],
            required_algorithm=data.get("required_algorithm"),
            preferred_algorithm=data.get("preferred_algorithm", "ed25519"),
            min_key_bits=data.get("min_key_bits"),
            notes=data.get("notes", ""),
            fingerprints=data.get("fingerprints", {}),
            docs_url=data.get("docs_url", ""),
        )

    @classmethod
    def from_builtin(cls, service_id: str) -> Optional["Service"]:
        """Create a Service from built-in profiles."""
        if service_id not in BUILTIN_SERVICES:
            return None
        data = BUILTIN_SERVICES[service_id]
        return cls(
            id=service_id,
            name=data["name"],
            required_algorithm=data.get("required_algorithm"),
            preferred_algorithm=data.get("preferred_algorithm", "ed25519"),
            min_key_bits=data.get("min_key_bits"),
            notes=data.get("notes", ""),
            fingerprints=data.get("fingerprints", {}),
            docs_url=data.get("docs_url", ""),
        )

    def get_algorithm(self) -> str:
        """Get the algorithm to use for this service."""
        return self.required_algorithm or self.preferred_algorithm

    def validate_key(self, key: "SSHKey") -> Tuple[bool, Optional[str]]:
        """
        Validate that a key meets this service's requirements.

        Returns:
            Tuple of (is_valid, error_message)
        """
        if self.required_algorithm and key.algorithm != self.required_algorithm:
            return False, (
                f"Service '{self.name}' requires {self.required_algorithm.upper()} keys, "
                f"but key '{key.id}' uses {key.algorithm.upper()}"
            )
        return True, None


@dataclass
class Host:
    """Represents a remote host."""
    id: str
    hostname: str
    user: str
    port: int = 22
    service: Optional[str] = None  # Service ID this host belongs to
    keys: List[str] = field(default_factory=list)  # Key IDs

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "hostname": self.hostname,
            "user": self.user,
        }
        if self.port != 22:
            result["port"] = self.port
        if self.service:
            result["service"] = self.service
        if self.keys:
            result["keys"] = self.keys
        return result

    @classmethod
    def from_dict(cls, host_id: str, data: Dict[str, Any]) -> "Host":
        return cls(
            id=host_id,
            hostname=data["hostname"],
            user=data["user"],
            port=data.get("port", 22),
            service=data.get("service"),
            keys=data.get("keys", []),
        )

    def ssh_destination(self) -> str:
        """Get the SSH destination string (user@host)."""
        return f"{self.user}@{self.hostname}"

    def ssh_args(self) -> List[str]:
        """Get SSH command arguments for this host."""
        args = ["-p", str(self.port)] if self.port != 22 else []
        return args


@dataclass
class Inventory:
    """The complete SSH Vault inventory."""
    version: str = "1.0"
    keys: Dict[str, SSHKey] = field(default_factory=dict)
    hosts: Dict[str, Host] = field(default_factory=dict)
    services: Dict[str, Service] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        result = {
            "version": self.version,
            "keys": {k: v.to_dict() for k, v in self.keys.items()},
            "hosts": {k: v.to_dict() for k, v in self.hosts.items()},
        }
        if self.services:
            result["services"] = {k: v.to_dict() for k, v in self.services.items()}
        return result

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Inventory":
        keys = {
            key_id: SSHKey.from_dict(key_id, key_data)
            for key_id, key_data in data.get("keys", {}).items()
        }
        hosts = {
            host_id: Host.from_dict(host_id, host_data)
            for host_id, host_data in data.get("hosts", {}).items()
        }
        services = {
            service_id: Service.from_dict(service_id, service_data)
            for service_id, service_data in data.get("services", {}).items()
        }
        return cls(
            version=data.get("version", "1.0"),
            keys=keys,
            hosts=hosts,
            services=services,
        )

    def get_key(self, key_id: str) -> Optional[SSHKey]:
        """Get a key by ID."""
        return self.keys.get(key_id)

    def get_host(self, host_id: str) -> Optional[Host]:
        """Get a host by ID."""
        return self.hosts.get(host_id)

    def add_key(self, key: SSHKey) -> None:
        """Add or update a key."""
        self.keys[key.id] = key

    def add_host(self, host: Host) -> None:
        """Add or update a host."""
        self.hosts[host.id] = host

    def remove_key(self, key_id: str) -> bool:
        """Remove a key. Returns True if found and removed."""
        if key_id in self.keys:
            del self.keys[key_id]
            # Also remove from host key lists
            for host in self.hosts.values():
                if key_id in host.keys:
                    host.keys.remove(key_id)
            return True
        return False

    def remove_host(self, host_id: str) -> bool:
        """Remove a host. Returns True if found and removed."""
        if host_id in self.hosts:
            del self.hosts[host_id]
            # Also remove deployments referencing this host
            for key in self.keys.values():
                key.remove_deployment(host_id)
            return True
        return False

    def get_keys_for_host(self, host_id: str) -> List[SSHKey]:
        """Get all keys deployed to a host."""
        result = []
        for key in self.keys.values():
            if key.get_deployment(host_id):
                result.append(key)
        return result

    def get_hosts_for_key(self, key_id: str) -> List[Host]:
        """Get all hosts where a key is deployed."""
        key = self.get_key(key_id)
        if not key:
            return []
        return [
            self.hosts[d.host_id]
            for d in key.deployments
            if d.host_id in self.hosts
        ]

    def get_service(self, service_id: str) -> Optional[Service]:
        """Get a service by ID, checking inventory first, then builtins."""
        if service_id in self.services:
            return self.services[service_id]
        return Service.from_builtin(service_id)

    def add_service(self, service: Service) -> None:
        """Add or update a service."""
        self.services[service.id] = service

    def remove_service(self, service_id: str) -> bool:
        """Remove a service. Returns True if found and removed."""
        if service_id in self.services:
            del self.services[service_id]
            return True
        return False

    def get_hosts_for_service(self, service_id: str) -> List[Host]:
        """Get all hosts associated with a service."""
        return [h for h in self.hosts.values() if h.service == service_id]


def get_service_algorithm(service_id: str, inventory: Optional["Inventory"] = None) -> str:
    """
    Get the correct algorithm for a service.

    Checks inventory first for custom services, then falls back to builtins.
    Returns ed25519 if service not found.
    """
    if inventory:
        service = inventory.get_service(service_id)
        if service:
            return service.get_algorithm()

    if service_id in BUILTIN_SERVICES:
        data = BUILTIN_SERVICES[service_id]
        return data.get("required_algorithm") or data.get("preferred_algorithm", "ed25519")

    return DEFAULT_ALGORITHM


def list_builtin_services() -> List[Dict[str, Any]]:
    """List all built-in service profiles."""
    return [
        {
            "id": service_id,
            "name": data["name"],
            "algorithm": data.get("required_algorithm") or data.get("preferred_algorithm", "ed25519"),
            "required": data.get("required_algorithm") is not None,
            "notes": data.get("notes", ""),
        }
        for service_id, data in BUILTIN_SERVICES.items()
    ]


def get_key_fingerprint(public_key_path: str) -> Optional[str]:
    """Get the fingerprint of a public key file."""
    path = Path(public_key_path).expanduser()
    if not path.exists():
        return None

    try:
        result = subprocess.run(
            ["ssh-keygen", "-lf", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if result.returncode == 0:
            # Output format: "256 SHA256:xxx comment (ED25519)"
            parts = result.stdout.strip().split()
            if len(parts) >= 2:
                return parts[1]  # SHA256:xxx
        return None
    except Exception:
        return None


def check_key_has_passphrase(private_key_path: str) -> bool:
    """Check if a private key has a passphrase."""
    path = Path(private_key_path).expanduser()
    if not path.exists():
        return False

    try:
        # Try to load key without passphrase
        result = subprocess.run(
            ["ssh-keygen", "-y", "-P", "", "-f", str(path)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        # If it succeeds with empty passphrase, key has no passphrase
        return result.returncode != 0
    except Exception:
        return False

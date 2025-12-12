#!/usr/bin/env python3
"""
Area Analyzer - Detect component structure from codebase.

Scans multiple sources to identify logical components:
- Directory structure (src/, lib/, packages/)
- .NET solution and project files (.sln, .csproj)
- C# namespaces
- CODEOWNERS file
- Package.json workspaces (Node.js)
- Docker Compose services
- Python project files

Usage:
    python area_analyzer.py                           # Analyze current directory
    python area_analyzer.py --path /path/to/repo      # Analyze specific path
    python area_analyzer.py --output analysis.json    # Save to file
    python area_analyzer.py --format tree             # Display as tree
"""

import json
import os
import re
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import xml.etree.ElementTree as ET


class ComponentType(Enum):
    """Type of detected component."""
    DIRECTORY = "directory"
    DOTNET_PROJECT = "dotnet_project"
    DOTNET_SOLUTION = "dotnet_solution"
    NAMESPACE = "namespace"
    CODEOWNERS = "codeowners"
    NPM_PACKAGE = "npm_package"
    NPM_WORKSPACE = "npm_workspace"
    DOCKER_SERVICE = "docker_service"
    PYTHON_PACKAGE = "python_package"


class ArchitecturePattern(Enum):
    """Detected architecture patterns."""
    CLEAN_ARCHITECTURE = "clean_architecture"
    DDD = "domain_driven_design"
    MICROSERVICES = "microservices"
    MONOLITH = "monolith"
    MODULAR_MONOLITH = "modular_monolith"
    LAYERED = "layered"
    UNKNOWN = "unknown"


@dataclass
class CodeComponent:
    """A detected code component."""
    name: str
    path: str
    component_type: ComponentType
    confidence: float  # 0.0 to 1.0
    source: str  # What detected this component
    children: List["CodeComponent"] = field(default_factory=list)
    metadata: Dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "path": self.path,
            "component_type": self.component_type.value,
            "confidence": self.confidence,
            "source": self.source,
            "children": [c.to_dict() for c in self.children],
            "metadata": self.metadata
        }

    def suggested_area_path(self, project_prefix: str = "") -> str:
        """Generate suggested ADO area path for this component."""
        # Clean the name for area path
        area_name = self._clean_name_for_area(self.name)
        if project_prefix:
            return f"{project_prefix}\\{area_name}"
        return area_name

    @staticmethod
    def _clean_name_for_area(name: str) -> str:
        """Clean a name for use in an area path."""
        # Remove common prefixes/suffixes
        name = re.sub(r'^(src|lib|packages?|apps?)[/\\]', '', name, flags=re.IGNORECASE)
        name = re.sub(r'\.(api|core|domain|infrastructure|application|web|service)$', '', name, flags=re.IGNORECASE)
        # Convert to PascalCase
        parts = re.split(r'[-_./\\]', name)
        name = ''.join(p.capitalize() for p in parts if p)
        return name


@dataclass
class OwnershipMapping:
    """CODEOWNERS-style ownership mapping."""
    pattern: str
    owners: List[str]
    component_hint: Optional[str] = None


@dataclass
class CodebaseAnalysis:
    """Complete codebase analysis result."""
    root_path: str
    components: List[CodeComponent]
    architecture_patterns: List[ArchitecturePattern]
    ownership_mappings: List[OwnershipMapping]
    suggested_area_structure: Dict[str, List[str]]  # Category -> [areas]
    analysis_timestamp: datetime
    statistics: Dict[str, int]

    def to_dict(self) -> dict:
        return {
            "root_path": self.root_path,
            "components": [c.to_dict() for c in self.components],
            "architecture_patterns": [p.value for p in self.architecture_patterns],
            "ownership_mappings": [
                {"pattern": o.pattern, "owners": o.owners, "component_hint": o.component_hint}
                for o in self.ownership_mappings
            ],
            "suggested_area_structure": self.suggested_area_structure,
            "analysis_timestamp": self.analysis_timestamp.isoformat(),
            "statistics": self.statistics
        }


# Directories to skip during analysis
SKIP_DIRS = {
    '.git', '.svn', '.hg',
    'node_modules', 'bower_components',
    'bin', 'obj', 'out', 'dist', 'build', 'target',
    '.vs', '.vscode', '.idea',
    '__pycache__', '.pytest_cache', '.mypy_cache',
    'venv', '.venv', 'env', '.env',
    'coverage', '.coverage',
    'vendor', 'packages',  # NuGet packages folder
    '.terraform', '.pulumi',
}

# Common source directories that contain components
SOURCE_DIRS = {'src', 'lib', 'packages', 'apps', 'services', 'modules', 'components'}

# Clean Architecture layer names
CLEAN_ARCH_LAYERS = {'domain', 'application', 'infrastructure', 'presentation', 'api', 'web', 'ui'}

# DDD patterns
DDD_PATTERNS = {'domain', 'aggregates', 'entities', 'valueobjects', 'repositories', 'services'}


class DirectoryAnalyzer:
    """Analyze directory structure for components."""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.components: List[CodeComponent] = []

    def analyze(self) -> List[CodeComponent]:
        """Analyze directory structure."""
        # Find source directories
        source_roots = self._find_source_roots()

        for source_root in source_roots:
            self._analyze_directory(source_root, depth=0, max_depth=3)

        # If no source dirs found, analyze from root
        if not source_roots:
            self._analyze_directory(self.root_path, depth=0, max_depth=3)

        return self.components

    def _find_source_roots(self) -> List[Path]:
        """Find common source root directories."""
        roots = []
        for name in SOURCE_DIRS:
            path = self.root_path / name
            if path.is_dir():
                roots.append(path)
        return roots

    def _analyze_directory(self, path: Path, depth: int, max_depth: int) -> None:
        """Recursively analyze a directory."""
        if depth > max_depth:
            return

        try:
            entries = list(path.iterdir())
        except PermissionError:
            return

        # Skip if this looks like a leaf directory (mostly files)
        subdirs = [e for e in entries if e.is_dir() and e.name not in SKIP_DIRS]
        files = [e for e in entries if e.is_file()]

        # Heuristic: if directory has significant code and subdirs, it might be a component
        code_files = [f for f in files if self._is_code_file(f)]

        if depth > 0 and (len(code_files) > 3 or len(subdirs) > 0):
            # This looks like a component
            rel_path = path.relative_to(self.root_path)
            confidence = self._calculate_confidence(path, code_files, subdirs)

            if confidence > 0.3:  # Threshold for considering as component
                component = CodeComponent(
                    name=path.name,
                    path=str(rel_path),
                    component_type=ComponentType.DIRECTORY,
                    confidence=confidence,
                    source="directory_structure",
                    metadata={
                        "file_count": len(files),
                        "code_file_count": len(code_files),
                        "subdir_count": len(subdirs)
                    }
                )
                self.components.append(component)

        # Recurse into subdirectories
        for subdir in subdirs:
            if subdir.name.lower() not in SKIP_DIRS:
                self._analyze_directory(subdir, depth + 1, max_depth)

    def _is_code_file(self, path: Path) -> bool:
        """Check if a file is a code file."""
        code_extensions = {
            '.cs', '.fs', '.vb',  # .NET
            '.py', '.pyx',  # Python
            '.js', '.ts', '.jsx', '.tsx',  # JavaScript/TypeScript
            '.java', '.kt', '.scala',  # JVM
            '.go',  # Go
            '.rs',  # Rust
            '.cpp', '.c', '.h', '.hpp',  # C/C++
            '.rb',  # Ruby
            '.php',  # PHP
        }
        return path.suffix.lower() in code_extensions

    def _calculate_confidence(self, path: Path, code_files: List[Path], subdirs: List[Path]) -> float:
        """Calculate confidence that this directory is a component."""
        confidence = 0.0
        name_lower = path.name.lower()

        # Boost for meaningful names
        if name_lower not in {'src', 'lib', 'common', 'shared', 'utils', 'helpers'}:
            confidence += 0.3

        # Boost for having significant code
        if len(code_files) >= 5:
            confidence += 0.2
        elif len(code_files) >= 2:
            confidence += 0.1

        # Boost for having subdirectories (indicates structure)
        if len(subdirs) >= 2:
            confidence += 0.2

        # Boost for domain-sounding names
        domain_indicators = {
            'orders', 'order', 'inventory', 'customer', 'customers', 'user', 'users',
            'auth', 'authentication', 'authorization', 'payment', 'payments',
            'shipping', 'notification', 'notifications', 'catalog', 'product', 'products',
            'reporting', 'analytics', 'billing', 'subscription', 'subscriptions',
            'messaging', 'integration', 'integrations', 'workflow', 'workflows'
        }
        if name_lower in domain_indicators:
            confidence += 0.3

        # Cap at 1.0
        return min(confidence, 1.0)


class DotNetAnalyzer:
    """Analyze .NET solution and project files."""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.components: List[CodeComponent] = []

    def analyze(self) -> List[CodeComponent]:
        """Analyze .NET projects."""
        # Find all .csproj files
        csproj_files = list(self.root_path.rglob("*.csproj"))

        for csproj in csproj_files:
            if any(skip in str(csproj) for skip in SKIP_DIRS):
                continue
            component = self._analyze_csproj(csproj)
            if component:
                self.components.append(component)

        return self.components

    def _analyze_csproj(self, csproj_path: Path) -> Optional[CodeComponent]:
        """Analyze a .csproj file."""
        try:
            tree = ET.parse(csproj_path)
            root = tree.getroot()

            # Get project name from file or AssemblyName
            project_name = csproj_path.stem

            # Try to find AssemblyName in the project
            for elem in root.iter():
                if elem.tag.endswith('AssemblyName') and elem.text:
                    project_name = elem.text
                    break

            # Extract component name from project name
            # e.g., "MyApp.Orders.Api" -> "Orders"
            component_name = self._extract_component_name(project_name)

            if not component_name:
                return None

            rel_path = csproj_path.parent.relative_to(self.root_path)

            # Determine project type
            project_type = self._detect_project_type(root, project_name)

            return CodeComponent(
                name=component_name,
                path=str(rel_path),
                component_type=ComponentType.DOTNET_PROJECT,
                confidence=0.8,
                source="csproj_analysis",
                metadata={
                    "project_name": project_name,
                    "project_type": project_type,
                    "csproj_file": csproj_path.name
                }
            )
        except Exception:
            return None

    def _extract_component_name(self, project_name: str) -> Optional[str]:
        """Extract meaningful component name from project name."""
        # Split by dots
        parts = project_name.split('.')

        # Filter out common prefixes/suffixes
        ignore_parts = {
            'api', 'web', 'core', 'domain', 'application', 'infrastructure',
            'data', 'services', 'service', 'common', 'shared', 'tests', 'test',
            'client', 'server', 'host', 'worker'
        }

        # Find the meaningful part (usually in the middle)
        meaningful_parts = [p for p in parts[1:] if p.lower() not in ignore_parts]

        if meaningful_parts:
            return meaningful_parts[0]
        elif len(parts) > 1:
            return parts[1]  # Return second part as fallback
        return None

    def _detect_project_type(self, root: ET.Element, project_name: str) -> str:
        """Detect the type of .NET project."""
        name_lower = project_name.lower()

        # Check SDK
        sdk = root.get('Sdk', '')
        if 'Web' in sdk or 'Blazor' in sdk:
            return 'web'
        if 'Worker' in sdk:
            return 'worker'

        # Check name patterns
        if '.api' in name_lower or '.web' in name_lower:
            return 'web'
        if '.domain' in name_lower or '.core' in name_lower:
            return 'domain'
        if '.infrastructure' in name_lower or '.data' in name_lower:
            return 'infrastructure'
        if '.application' in name_lower:
            return 'application'
        if '.test' in name_lower:
            return 'test'

        return 'library'


class NamespaceAnalyzer:
    """Analyze C# namespaces to detect domain components."""

    def __init__(self, root_path: Path):
        self.root_path = root_path
        self.namespaces: Dict[str, int] = {}  # namespace -> file count

    def analyze(self) -> List[CodeComponent]:
        """Analyze namespaces in C# files."""
        cs_files = list(self.root_path.rglob("*.cs"))

        for cs_file in cs_files:
            if any(skip in str(cs_file) for skip in SKIP_DIRS):
                continue
            self._analyze_file(cs_file)

        return self._extract_components()

    def _analyze_file(self, file_path: Path) -> None:
        """Extract namespace from a C# file."""
        try:
            content = file_path.read_text(encoding='utf-8', errors='ignore')

            # Find namespace declarations
            # Handles both traditional and file-scoped namespaces
            patterns = [
                r'namespace\s+([\w.]+)\s*{',  # Traditional
                r'namespace\s+([\w.]+)\s*;',  # File-scoped
            ]

            for pattern in patterns:
                matches = re.findall(pattern, content)
                for ns in matches:
                    self.namespaces[ns] = self.namespaces.get(ns, 0) + 1
        except Exception:
            pass

    def _extract_components(self) -> List[CodeComponent]:
        """Extract components from namespace analysis."""
        components = []

        # Group namespaces by their domain component
        # e.g., "MyApp.Orders.Domain" and "MyApp.Orders.Api" both -> "Orders"
        component_namespaces: Dict[str, List[str]] = {}

        for ns, count in self.namespaces.items():
            parts = ns.split('.')
            if len(parts) >= 2:
                # Skip test namespaces
                if any('test' in p.lower() for p in parts):
                    continue

                # Find the domain component (usually 2nd level, after company/app name)
                component = None
                for i, part in enumerate(parts[1:], 1):
                    if part.lower() not in CLEAN_ARCH_LAYERS and part.lower() not in {'common', 'shared'}:
                        component = part
                        break

                if component:
                    if component not in component_namespaces:
                        component_namespaces[component] = []
                    component_namespaces[component].append(ns)

        # Create components from grouped namespaces
        for name, namespaces in component_namespaces.items():
            if len(namespaces) >= 2 or any(self.namespaces[ns] >= 3 for ns in namespaces):
                total_files = sum(self.namespaces[ns] for ns in namespaces)
                components.append(CodeComponent(
                    name=name,
                    path=f"(namespace: {name})",
                    component_type=ComponentType.NAMESPACE,
                    confidence=min(0.5 + (total_files / 20), 0.9),
                    source="namespace_analysis",
                    metadata={
                        "namespaces": namespaces,
                        "file_count": total_files
                    }
                ))

        return components


class CodeOwnersAnalyzer:
    """Analyze CODEOWNERS file for ownership and component hints."""

    def __init__(self, root_path: Path):
        self.root_path = root_path

    def analyze(self) -> Tuple[List[CodeComponent], List[OwnershipMapping]]:
        """Analyze CODEOWNERS file."""
        components = []
        mappings = []

        codeowners_paths = [
            self.root_path / 'CODEOWNERS',
            self.root_path / '.github' / 'CODEOWNERS',
            self.root_path / 'docs' / 'CODEOWNERS',
        ]

        for path in codeowners_paths:
            if path.exists():
                components, mappings = self._parse_codeowners(path)
                break

        return components, mappings

    def _parse_codeowners(self, path: Path) -> Tuple[List[CodeComponent], List[OwnershipMapping]]:
        """Parse CODEOWNERS file."""
        components = []
        mappings = []

        try:
            content = path.read_text()

            for line in content.splitlines():
                line = line.strip()
                if not line or line.startswith('#'):
                    continue

                parts = line.split()
                if len(parts) >= 2:
                    pattern = parts[0]
                    owners = parts[1:]

                    # Extract component hint from pattern
                    component_hint = self._extract_component_from_pattern(pattern)

                    mappings.append(OwnershipMapping(
                        pattern=pattern,
                        owners=owners,
                        component_hint=component_hint
                    ))

                    # Create component if pattern suggests one
                    if component_hint:
                        components.append(CodeComponent(
                            name=component_hint,
                            path=pattern,
                            component_type=ComponentType.CODEOWNERS,
                            confidence=0.7,
                            source="codeowners",
                            metadata={
                                "owners": owners,
                                "pattern": pattern
                            }
                        ))
        except Exception:
            pass

        return components, mappings

    def _extract_component_from_pattern(self, pattern: str) -> Optional[str]:
        """Extract component name from CODEOWNERS pattern."""
        # Patterns like /src/Orders/** or /packages/auth/**
        match = re.search(r'/(?:src|lib|packages|services|apps)/([^/*]+)', pattern)
        if match:
            return match.group(1).replace('-', ' ').title().replace(' ', '')
        return None


class DockerAnalyzer:
    """Analyze Docker Compose files for service components."""

    def __init__(self, root_path: Path):
        self.root_path = root_path

    def analyze(self) -> List[CodeComponent]:
        """Analyze Docker Compose files."""
        components = []

        compose_files = [
            'docker-compose.yml',
            'docker-compose.yaml',
            'compose.yml',
            'compose.yaml',
        ]

        for filename in compose_files:
            path = self.root_path / filename
            if path.exists():
                components.extend(self._parse_compose(path))

        return components

    def _parse_compose(self, path: Path) -> List[CodeComponent]:
        """Parse Docker Compose file for services."""
        components = []

        try:
            # Simple YAML parsing without external dependency
            content = path.read_text()

            # Find services section and extract service names
            in_services = False
            indent_level = 0

            for line in content.splitlines():
                stripped = line.strip()

                if stripped == 'services:':
                    in_services = True
                    indent_level = len(line) - len(line.lstrip())
                    continue

                if in_services:
                    current_indent = len(line) - len(line.lstrip())

                    # Check if we've left the services section
                    if current_indent <= indent_level and stripped and not stripped.startswith('#'):
                        if ':' in stripped and not stripped.startswith('-'):
                            # New top-level section
                            in_services = False
                            continue

                    # Check for service name (one level deeper than services:)
                    if current_indent == indent_level + 2:
                        if stripped.endswith(':') and not stripped.startswith('#'):
                            service_name = stripped[:-1].strip()

                            # Skip common infrastructure services
                            infra_services = {'redis', 'postgres', 'mysql', 'mongodb', 'rabbitmq',
                                            'elasticsearch', 'nginx', 'traefik', 'consul', 'vault'}

                            if service_name.lower() not in infra_services:
                                components.append(CodeComponent(
                                    name=self._clean_service_name(service_name),
                                    path=f"(docker: {service_name})",
                                    component_type=ComponentType.DOCKER_SERVICE,
                                    confidence=0.6,
                                    source="docker_compose",
                                    metadata={
                                        "service_name": service_name,
                                        "compose_file": path.name
                                    }
                                ))
        except Exception:
            pass

        return components

    def _clean_service_name(self, name: str) -> str:
        """Clean service name for component naming."""
        # Remove common suffixes
        name = re.sub(r'[-_](service|svc|api|worker)$', '', name, flags=re.IGNORECASE)
        # Convert to PascalCase
        parts = re.split(r'[-_]', name)
        return ''.join(p.capitalize() for p in parts)


class PackageJsonAnalyzer:
    """Analyze package.json files for Node.js/TypeScript components."""

    def __init__(self, root_path: Path):
        self.root_path = root_path

    def analyze(self) -> List[CodeComponent]:
        """Analyze package.json files."""
        components = []

        # Check root package.json for workspaces
        root_pkg = self.root_path / 'package.json'
        if root_pkg.exists():
            components.extend(self._analyze_workspaces(root_pkg))

        # Find all package.json files in common locations
        for subdir in ['packages', 'apps', 'libs', 'services']:
            packages_dir = self.root_path / subdir
            if packages_dir.exists():
                for pkg_json in packages_dir.glob('*/package.json'):
                    component = self._analyze_package(pkg_json)
                    if component:
                        components.append(component)

        return components

    def _analyze_workspaces(self, root_pkg: Path) -> List[CodeComponent]:
        """Analyze workspaces from root package.json."""
        components = []

        try:
            data = json.loads(root_pkg.read_text())
            workspaces = data.get('workspaces', [])

            # Handle both array and object format
            if isinstance(workspaces, dict):
                workspaces = workspaces.get('packages', [])

            for workspace in workspaces:
                # Workspace can be a glob pattern
                if '*' not in workspace:
                    name = Path(workspace).name
                    components.append(CodeComponent(
                        name=self._clean_package_name(name),
                        path=workspace,
                        component_type=ComponentType.NPM_WORKSPACE,
                        confidence=0.7,
                        source="package_json_workspace",
                        metadata={"workspace_pattern": workspace}
                    ))
        except Exception:
            pass

        return components

    def _analyze_package(self, pkg_path: Path) -> Optional[CodeComponent]:
        """Analyze individual package.json."""
        try:
            data = json.loads(pkg_path.read_text())
            name = data.get('name', pkg_path.parent.name)

            # Skip private infrastructure packages
            if data.get('private') and name.startswith('@') and '/config' in name:
                return None

            rel_path = pkg_path.parent.relative_to(self.root_path)

            return CodeComponent(
                name=self._clean_package_name(name),
                path=str(rel_path),
                component_type=ComponentType.NPM_PACKAGE,
                confidence=0.7,
                source="package_json",
                metadata={
                    "package_name": name,
                    "version": data.get('version'),
                    "description": data.get('description')
                }
            )
        except Exception:
            return None

    def _clean_package_name(self, name: str) -> str:
        """Clean package name for component naming."""
        # Remove scope (@org/)
        if name.startswith('@'):
            name = name.split('/', 1)[-1] if '/' in name else name[1:]
        # Convert to PascalCase
        parts = re.split(r'[-_]', name)
        return ''.join(p.capitalize() for p in parts)


class ArchitectureDetector:
    """Detect architecture patterns from codebase structure."""

    def __init__(self, root_path: Path, components: List[CodeComponent]):
        self.root_path = root_path
        self.components = components

    def detect(self) -> List[ArchitecturePattern]:
        """Detect architecture patterns."""
        patterns = []

        # Collect all directory names
        all_dirs = set()
        for component in self.components:
            all_dirs.add(component.name.lower())
            if component.metadata.get('project_type'):
                all_dirs.add(component.metadata['project_type'])

        # Check for Clean Architecture
        clean_arch_indicators = {'domain', 'application', 'infrastructure', 'presentation'}
        if len(clean_arch_indicators & all_dirs) >= 3:
            patterns.append(ArchitecturePattern.CLEAN_ARCHITECTURE)

        # Check for DDD
        ddd_indicators = {'domain', 'aggregates', 'entities', 'valueobjects', 'repositories'}
        if len(ddd_indicators & all_dirs) >= 2:
            patterns.append(ArchitecturePattern.DDD)

        # Check for Microservices
        docker_services = [c for c in self.components if c.component_type == ComponentType.DOCKER_SERVICE]
        if len(docker_services) >= 3:
            patterns.append(ArchitecturePattern.MICROSERVICES)

        # Check for Layered architecture
        layered_indicators = {'api', 'business', 'data', 'web', 'dal', 'bll'}
        if len(layered_indicators & all_dirs) >= 2:
            patterns.append(ArchitecturePattern.LAYERED)

        # Check for Modular Monolith
        if len(self.components) >= 3 and ArchitecturePattern.MICROSERVICES not in patterns:
            # Multiple modules but single deployable
            compose_files = list(self.root_path.glob('*compose*.y*ml'))
            if len(compose_files) <= 1:
                patterns.append(ArchitecturePattern.MODULAR_MONOLITH)

        if not patterns:
            patterns.append(ArchitecturePattern.UNKNOWN)

        return patterns


class AreaStructureSuggester:
    """Suggest ADO area structure based on components."""

    # Best practice categories
    CATEGORIES = {
        'Platform': ['authentication', 'authorization', 'infrastructure', 'shared', 'common', 'core', 'platform'],
        'Core': [],  # Will contain domain components
        'Integrations': ['integration', 'gateway', 'external', 'api', 'connector'],
        'Operations': ['monitoring', 'logging', 'devops', 'deployment', 'operations'],
        'Clients': ['web', 'mobile', 'desktop', 'cli', 'client', 'frontend', 'ui'],
    }

    def suggest(self, components: List[CodeComponent], project_name: str = "") -> Dict[str, List[str]]:
        """Generate suggested area structure."""
        structure: Dict[str, List[str]] = {cat: [] for cat in self.CATEGORIES}

        used_components = set()

        # First pass: categorize known patterns
        for component in components:
            name_lower = component.name.lower()

            for category, keywords in self.CATEGORIES.items():
                if any(kw in name_lower for kw in keywords):
                    area_name = component.suggested_area_path()
                    if area_name not in structure[category]:
                        structure[category].append(area_name)
                    used_components.add(component.name)
                    break

        # Second pass: remaining components go to Core (domain)
        for component in components:
            if component.name not in used_components:
                # High-confidence components or those from namespace/project analysis
                if component.confidence >= 0.5 or component.component_type in {
                    ComponentType.DOTNET_PROJECT, ComponentType.NAMESPACE
                }:
                    area_name = component.suggested_area_path()
                    if area_name not in structure['Core']:
                        structure['Core'].append(area_name)

        # Add project prefix if provided
        if project_name:
            prefixed = {}
            for category, areas in structure.items():
                if areas:
                    prefixed[f"{project_name}\\{category}"] = [
                        f"{project_name}\\{category}\\{area}" for area in areas
                    ]
            return prefixed

        return {k: v for k, v in structure.items() if v}


class CodebaseAnalyzer:
    """Main analyzer that coordinates all sub-analyzers."""

    def __init__(self, root_path: str):
        self.root_path = Path(root_path).resolve()

    def analyze(self) -> CodebaseAnalysis:
        """Perform complete codebase analysis."""
        all_components: List[CodeComponent] = []
        ownership_mappings: List[OwnershipMapping] = []

        # Run all analyzers
        analyzers = [
            ('directory', DirectoryAnalyzer(self.root_path)),
            ('dotnet', DotNetAnalyzer(self.root_path)),
            ('namespace', NamespaceAnalyzer(self.root_path)),
            ('docker', DockerAnalyzer(self.root_path)),
            ('npm', PackageJsonAnalyzer(self.root_path)),
        ]

        for name, analyzer in analyzers:
            try:
                components = analyzer.analyze()
                all_components.extend(components)
            except Exception as e:
                pass  # Continue with other analyzers

        # CODEOWNERS analysis
        try:
            codeowners_analyzer = CodeOwnersAnalyzer(self.root_path)
            codeowners_components, ownership_mappings = codeowners_analyzer.analyze()
            all_components.extend(codeowners_components)
        except Exception:
            pass

        # Deduplicate components by name
        all_components = self._deduplicate_components(all_components)

        # Detect architecture patterns
        arch_detector = ArchitectureDetector(self.root_path, all_components)
        patterns = arch_detector.detect()

        # Generate suggested area structure
        suggester = AreaStructureSuggester()
        project_name = self.root_path.name
        suggested_structure = suggester.suggest(all_components, project_name)

        # Calculate statistics
        statistics = {
            'total_components': len(all_components),
            'by_type': {},
            'by_confidence': {'high': 0, 'medium': 0, 'low': 0}
        }

        for component in all_components:
            type_name = component.component_type.value
            statistics['by_type'][type_name] = statistics['by_type'].get(type_name, 0) + 1

            if component.confidence >= 0.7:
                statistics['by_confidence']['high'] += 1
            elif component.confidence >= 0.4:
                statistics['by_confidence']['medium'] += 1
            else:
                statistics['by_confidence']['low'] += 1

        return CodebaseAnalysis(
            root_path=str(self.root_path),
            components=all_components,
            architecture_patterns=patterns,
            ownership_mappings=ownership_mappings,
            suggested_area_structure=suggested_structure,
            analysis_timestamp=datetime.utcnow(),
            statistics=statistics
        )

    def _deduplicate_components(self, components: List[CodeComponent]) -> List[CodeComponent]:
        """Deduplicate components, keeping highest confidence."""
        by_name: Dict[str, CodeComponent] = {}

        for component in components:
            name = component.name.lower()
            if name not in by_name or component.confidence > by_name[name].confidence:
                by_name[name] = component

        return list(by_name.values())


def format_as_tree(analysis: CodebaseAnalysis) -> str:
    """Format analysis as a tree structure."""
    lines = []
    lines.append(f"Codebase Analysis: {Path(analysis.root_path).name}")
    lines.append("=" * 60)
    lines.append("")

    # Architecture patterns
    lines.append("Architecture Patterns Detected:")
    for pattern in analysis.architecture_patterns:
        lines.append(f"  - {pattern.value.replace('_', ' ').title()}")
    lines.append("")

    # Components by type
    lines.append("Components Detected:")
    by_type: Dict[str, List[CodeComponent]] = {}
    for c in analysis.components:
        type_name = c.component_type.value
        if type_name not in by_type:
            by_type[type_name] = []
        by_type[type_name].append(c)

    for type_name, components in sorted(by_type.items()):
        lines.append(f"\n  [{type_name}]")
        for c in sorted(components, key=lambda x: -x.confidence):
            conf_bar = "█" * int(c.confidence * 5) + "░" * (5 - int(c.confidence * 5))
            lines.append(f"    {conf_bar} {c.name} ({c.path})")

    lines.append("")

    # Suggested area structure
    lines.append("Suggested Area Structure:")
    for category, areas in analysis.suggested_area_structure.items():
        lines.append(f"\n  {category}")
        for area in sorted(areas):
            lines.append(f"    └── {area.split(chr(92))[-1]}")  # chr(92) is backslash

    lines.append("")

    # Statistics
    lines.append("Statistics:")
    lines.append(f"  Total components: {analysis.statistics['total_components']}")
    lines.append(f"  High confidence: {analysis.statistics['by_confidence']['high']}")
    lines.append(f"  Medium confidence: {analysis.statistics['by_confidence']['medium']}")
    lines.append(f"  Low confidence: {analysis.statistics['by_confidence']['low']}")

    return "\n".join(lines)


def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Analyze codebase structure for ADO area mapping",
        epilog="""
Examples:
  %(prog)s                              # Analyze current directory
  %(prog)s --path /path/to/repo         # Analyze specific path
  %(prog)s --format tree                # Display as tree
  %(prog)s --output analysis.json       # Save to JSON file
        """
    )
    parser.add_argument("--path", "-p", default=".",
                        help="Path to codebase root (default: current directory)")
    parser.add_argument("--output", "-o",
                        help="Output file for JSON results")
    parser.add_argument("--format", "-f", choices=["json", "tree"], default="tree",
                        help="Output format (default: tree)")

    args = parser.parse_args()

    # Run analysis
    analyzer = CodebaseAnalyzer(args.path)
    analysis = analyzer.analyze()

    # Output results
    if args.format == "json" or args.output:
        output = json.dumps(analysis.to_dict(), indent=2)
        if args.output:
            Path(args.output).write_text(output)
            print(f"Analysis saved to {args.output}")
        else:
            print(output)
    else:
        print(format_as_tree(analysis))


if __name__ == "__main__":
    main()

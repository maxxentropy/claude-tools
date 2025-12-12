#!/usr/bin/env python3
"""
scan_dotnet.py - Scan a .NET codebase and output structured analysis as JSON.

Usage:
    python scan_dotnet.py /path/to/codebase
    python scan_dotnet.py /path/to/codebase --output analysis.json

Output includes:
    - Solution and project structure
    - Project types and frameworks
    - Package references
    - Detected patterns (Repository, CQRS, DDD, etc.)
    - File statistics
"""

import argparse
import json
import re
import sys
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional


@dataclass
class ProjectInfo:
    """Information about a single .NET project."""
    name: str
    path: str
    relative_path: str
    sdk: str = ""
    target_framework: str = ""
    output_type: str = "Library"
    package_references: list = field(default_factory=list)
    project_references: list = field(default_factory=list)
    is_test_project: bool = False
    detected_patterns: list = field(default_factory=list)
    namespaces: list = field(default_factory=list)
    file_counts: dict = field(default_factory=dict)


@dataclass
class SolutionInfo:
    """Information about the entire solution/codebase."""
    root_path: str
    solution_file: Optional[str] = None
    projects: list = field(default_factory=list)
    detected_architecture: str = "Unknown"
    detected_patterns: list = field(default_factory=list)
    frameworks_used: list = field(default_factory=list)
    total_cs_files: int = 0
    total_lines_of_code: int = 0


PATTERN_SIGNATURES = {
    "Repository": [r"class\s+\w*Repository", r"interface\s+I\w*Repository", r":\s*IRepository<"],
    "CQRS": [r"class\s+\w+Command\b", r"class\s+\w+Query\b", r"IRequestHandler<", r"ICommandHandler<"],
    "MediatR": [r"IMediator", r"IRequest<", r"IRequestHandler<", r"INotification\b"],
    "DomainEvents": [r"class\s+\w+Event\b", r"IDomainEvent", r"INotificationHandler<"],
    "Specification": [r"class\s+\w+Specification", r"ISpecification<"],
    "UnitOfWork": [r"IUnitOfWork", r"class\s+UnitOfWork"],
    "CleanArchitecture": [r"\.Domain\.", r"\.Application\.", r"\.Infrastructure\.", r"\.Api\."],
    "DDD": [r"AggregateRoot", r"ValueObject", r"Entity<", r"DomainService"],
    "FluentValidation": [r"AbstractValidator<", r"RuleFor\("],
    "AutoMapper": [r"IMapper", r"CreateMap<"],
    "EntityFramework": [r"DbContext", r"DbSet<", r"OnModelCreating"],
}

FRAMEWORK_PACKAGES = {
    "MediatR": ["MediatR"],
    "FluentValidation": ["FluentValidation"],
    "AutoMapper": ["AutoMapper"],
    "EntityFrameworkCore": ["Microsoft.EntityFrameworkCore"],
    "Serilog": ["Serilog"],
    "Swagger": ["Swashbuckle.AspNetCore"],
    "xUnit": ["xunit"],
    "NUnit": ["NUnit"],
    "Moq": ["Moq"],
}


def find_solution_file(root_path: Path) -> Optional[str]:
    sln_files = list(root_path.glob("*.sln"))
    return str(sln_files[0].relative_to(root_path)) if sln_files else None


def find_project_files(root_path: Path) -> list[Path]:
    return list(root_path.rglob("*.csproj"))


def parse_csproj(csproj_path: Path, root_path: Path) -> ProjectInfo:
    project = ProjectInfo(
        name=csproj_path.stem,
        path=str(csproj_path),
        relative_path=str(csproj_path.relative_to(root_path)),
    )

    try:
        tree = ET.parse(csproj_path)
        root = tree.getroot()
        ns = root.tag.split("}")[0] + "}" if root.tag.startswith("{") else ""

        project.sdk = root.attrib.get("Sdk", "")

        tf = root.find(f".//{ns}TargetFramework")
        if tf is not None and tf.text:
            project.target_framework = tf.text

        ot = root.find(f".//{ns}OutputType")
        if ot is not None and ot.text:
            project.output_type = ot.text

        for pkg_ref in root.findall(f".//{ns}PackageReference"):
            pkg_name = pkg_ref.attrib.get("Include", "")
            pkg_version = pkg_ref.attrib.get("Version", "")
            if pkg_name:
                project.package_references.append({"name": pkg_name, "version": pkg_version})

        for proj_ref in root.findall(f".//{ns}ProjectReference"):
            ref_path = proj_ref.attrib.get("Include", "")
            if ref_path:
                project.project_references.append(Path(ref_path).stem)

        project.is_test_project = any(
            "test" in project.name.lower() or
            any(pkg["name"].lower() in ["xunit", "nunit", "mstest.testframework"]
                for pkg in project.package_references)
            for _ in [1]
        )
    except ET.ParseError as e:
        print(f"Warning: Could not parse {csproj_path}: {e}", file=sys.stderr)

    return project


def scan_cs_files(project_path: Path) -> tuple[list[str], dict[str, int], int, list[str]]:
    project_dir = project_path.parent
    namespaces = set()
    patterns_found = set()
    file_counts = {"cs": 0, "razor": 0, "json": 0, "xml": 0}
    total_lines = 0

    for cs_file in project_dir.rglob("*.cs"):
        if "\\obj\\" in str(cs_file) or "/obj/" in str(cs_file):
            continue
        if "\\bin\\" in str(cs_file) or "/bin/" in str(cs_file):
            continue

        file_counts["cs"] += 1

        try:
            content = cs_file.read_text(encoding="utf-8", errors="ignore")
            total_lines += len(content.splitlines())

            ns_match = re.search(r"namespace\s+([\w.]+)", content)
            if ns_match:
                namespaces.add(ns_match.group(1))

            for pattern_name, signatures in PATTERN_SIGNATURES.items():
                for sig in signatures:
                    if re.search(sig, content):
                        patterns_found.add(pattern_name)
                        break
        except Exception as e:
            print(f"Warning: Could not read {cs_file}: {e}", file=sys.stderr)

    file_counts["razor"] = len(list(project_dir.rglob("*.razor")))
    file_counts["json"] = len(list(project_dir.rglob("*.json")))

    return list(namespaces), file_counts, total_lines, list(patterns_found)


def detect_frameworks(projects: list[ProjectInfo]) -> list[str]:
    frameworks = set()
    for project in projects:
        for pkg in project.package_references:
            pkg_name = pkg["name"]
            for framework, packages in FRAMEWORK_PACKAGES.items():
                if any(p.lower() in pkg_name.lower() for p in packages):
                    frameworks.add(framework)
    return sorted(list(frameworks))


def detect_architecture(projects: list[ProjectInfo]) -> str:
    project_names = [p.name.lower() for p in projects]

    clean_arch_layers = ["domain", "application", "infrastructure", "api", "webapi"]
    if sum(1 for layer in clean_arch_layers if any(layer in name for name in project_names)) >= 3:
        return "Clean Architecture"

    ntier_layers = ["data", "business", "presentation", "services", "dal", "bll"]
    if sum(1 for layer in ntier_layers if any(layer in name for name in project_names)) >= 2:
        return "N-Tier"

    return "Monolithic" if len(projects) == 1 else "Custom/Unknown"


def scan_codebase(root_path: str) -> SolutionInfo:
    root = Path(root_path).resolve()
    if not root.exists():
        raise ValueError(f"Path does not exist: {root_path}")

    solution = SolutionInfo(root_path=str(root))
    solution.solution_file = find_solution_file(root)

    for csproj in find_project_files(root):
        project = parse_csproj(csproj, root)
        namespaces, file_counts, lines, patterns = scan_cs_files(csproj)
        project.namespaces = namespaces
        project.file_counts = file_counts
        project.detected_patterns = patterns

        solution.total_cs_files += file_counts.get("cs", 0)
        solution.total_lines_of_code += lines
        solution.projects.append(project)

    all_patterns = set()
    for project in solution.projects:
        all_patterns.update(project.detected_patterns)
    solution.detected_patterns = sorted(list(all_patterns))

    solution.frameworks_used = detect_frameworks(solution.projects)
    solution.detected_architecture = detect_architecture(solution.projects)

    return solution


def main():
    parser = argparse.ArgumentParser(description="Scan a .NET codebase and output structured analysis.")
    parser.add_argument("path", help="Path to the .NET codebase root directory")
    parser.add_argument("--output", "-o", help="Output file path (default: stdout)", default=None)
    parser.add_argument("--pretty", "-p", help="Pretty print JSON output", action="store_true", default=True)

    args = parser.parse_args()

    try:
        solution = scan_codebase(args.path)
        result = asdict(solution)
        indent = 2 if args.pretty else None
        json_output = json.dumps(result, indent=indent)

        if args.output:
            Path(args.output).write_text(json_output)
            print(f"Analysis written to {args.output}", file=sys.stderr)
        else:
            print(json_output)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()

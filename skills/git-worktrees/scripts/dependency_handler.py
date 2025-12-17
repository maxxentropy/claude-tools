#!/usr/bin/env python3
"""
Smart dependency management for worktrees.

Detects dependency systems and handles installation/sharing appropriately.
"""

import argparse
import glob
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional


class DependencyHandler:
    """Handles dependency detection and installation."""

    def __init__(self, config_path: Optional[str] = None):
        self.config = self.load_config(config_path) if config_path else {}

    def load_config(self, config_path: str) -> Dict:
        """Load worktree configuration."""
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return json.load(f)
        return {}

    def detect_dependencies(self, worktree_path: str) -> Dict[str, str]:
        """Detect dependency systems in worktree."""
        deps: Dict[str, str] = {}
        path = Path(worktree_path)

        # Node.js
        if (path / "package.json").exists():
            if (path / "package-lock.json").exists():
                deps["nodejs"] = "npm"
            elif (path / "yarn.lock").exists():
                deps["nodejs"] = "yarn"
            elif (path / "pnpm-lock.yaml").exists():
                deps["nodejs"] = "pnpm"
            else:
                deps["nodejs"] = "npm"  # Default

        # Python
        if (path / "requirements.txt").exists():
            deps["python"] = "pip"
        elif (path / "pyproject.toml").exists():
            # Check if it's poetry or standard
            pyproject = (path / "pyproject.toml").read_text()
            if "[tool.poetry]" in pyproject:
                deps["python"] = "poetry"
            else:
                deps["python"] = "pip"
        elif (path / "Pipfile").exists():
            deps["python"] = "pipenv"

        # .NET
        csproj_files = list(path.glob("**/*.csproj"))
        sln_files = list(path.glob("*.sln"))
        if csproj_files or sln_files:
            deps["dotnet"] = "nuget"

        # Rust
        if (path / "Cargo.toml").exists():
            deps["rust"] = "cargo"

        # Go
        if (path / "go.mod").exists():
            deps["go"] = "go"

        # Ruby
        if (path / "Gemfile").exists():
            deps["ruby"] = "bundler"

        # Java/Kotlin
        if (path / "pom.xml").exists():
            deps["java"] = "maven"
        elif (path / "build.gradle").exists() or (path / "build.gradle.kts").exists():
            deps["java"] = "gradle"

        return deps

    def install_dependencies(self, worktree_path: str, verbose: bool = False) -> bool:
        """Install dependencies based on detected systems."""
        deps = self.detect_dependencies(worktree_path)

        if not deps:
            print("No dependencies detected")
            return True

        success = True

        for system, tool in deps.items():
            print(f"-> Installing {system} dependencies using {tool}...")

            try:
                if tool == "npm":
                    subprocess.run(
                        ["npm", "install"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "yarn":
                    subprocess.run(
                        ["yarn", "install"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "pnpm":
                    subprocess.run(
                        ["pnpm", "install"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "pip":
                    venv_path = Path(worktree_path) / ".venv"
                    if not venv_path.exists():
                        subprocess.run(
                            ["python3", "-m", "venv", ".venv"],
                            cwd=worktree_path,
                            check=True,
                            capture_output=not verbose,
                        )

                    # Determine requirements source
                    if (Path(worktree_path) / "requirements.txt").exists():
                        pip_cmd = [
                            str(venv_path / "bin" / "pip"),
                            "install",
                            "-r",
                            "requirements.txt",
                        ]
                    else:
                        pip_cmd = [
                            str(venv_path / "bin" / "pip"),
                            "install",
                            "-e",
                            ".",
                        ]

                    subprocess.run(
                        pip_cmd,
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "poetry":
                    subprocess.run(
                        ["poetry", "install"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "pipenv":
                    subprocess.run(
                        ["pipenv", "install"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "nuget":
                    subprocess.run(
                        ["dotnet", "restore"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "cargo":
                    subprocess.run(
                        ["cargo", "fetch"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "go":
                    subprocess.run(
                        ["go", "mod", "download"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "bundler":
                    subprocess.run(
                        ["bundle", "install"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "maven":
                    subprocess.run(
                        ["mvn", "dependency:resolve"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )
                elif tool == "gradle":
                    subprocess.run(
                        ["./gradlew", "dependencies"],
                        cwd=worktree_path,
                        check=True,
                        capture_output=not verbose,
                    )

                print(f"   {system} dependencies installed")

            except subprocess.CalledProcessError as e:
                print(f"   Warning: Failed to install {system} dependencies", file=sys.stderr)
                if verbose:
                    print(f"   Error: {e}", file=sys.stderr)
                success = False
            except FileNotFoundError:
                print(f"   Warning: {tool} not found, skipping {system}", file=sys.stderr)
                success = False

        return success


def main():
    parser = argparse.ArgumentParser(description="Handle worktree dependencies")
    parser.add_argument("command", choices=["install", "detect"])
    parser.add_argument("--path", required=True, help="Worktree path")
    parser.add_argument("--config", help="Config file path")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")

    args = parser.parse_args()

    handler = DependencyHandler(args.config)

    if args.command == "detect":
        deps = handler.detect_dependencies(args.path)
        print(json.dumps(deps, indent=2))

    elif args.command == "install":
        success = handler.install_dependencies(args.path, verbose=args.verbose)
        sys.exit(0 if success else 1)


if __name__ == "__main__":
    main()

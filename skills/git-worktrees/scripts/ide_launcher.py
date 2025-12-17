#!/usr/bin/env python3
"""
IDE launcher for worktrees.

Detects project type and launches appropriate IDE with support for:
- VS Code
- JetBrains Rider (for .NET projects)
- JetBrains IntelliJ IDEA
- JetBrains PyCharm
- JetBrains WebStorm
- JetBrains GoLand
"""

import argparse
import os
import subprocess
import sys
from pathlib import Path
from typing import Dict, List, Optional, Tuple


# IDE detection patterns and launch commands
IDE_CONFIG: Dict[str, Dict] = {
    "code": {
        "name": "Visual Studio Code",
        "command": ["code"],
        "mac_app": "/Applications/Visual Studio Code.app",
        "markers": [".vscode"],
        "project_types": ["*"],  # Universal
    },
    "rider": {
        "name": "JetBrains Rider",
        "command": ["rider"],
        "mac_app": "/Applications/Rider.app",
        "mac_cli": "/Applications/Rider.app/Contents/MacOS/rider",
        "markers": [".idea"],
        "project_types": ["dotnet"],
    },
    "idea": {
        "name": "IntelliJ IDEA",
        "command": ["idea"],
        "mac_app": "/Applications/IntelliJ IDEA.app",
        "mac_cli": "/Applications/IntelliJ IDEA.app/Contents/MacOS/idea",
        "markers": [".idea"],
        "project_types": ["java", "kotlin"],
    },
    "pycharm": {
        "name": "PyCharm",
        "command": ["pycharm"],
        "mac_app": "/Applications/PyCharm.app",
        "mac_cli": "/Applications/PyCharm.app/Contents/MacOS/pycharm",
        "markers": [".idea"],
        "project_types": ["python"],
    },
    "webstorm": {
        "name": "WebStorm",
        "command": ["webstorm"],
        "mac_app": "/Applications/WebStorm.app",
        "mac_cli": "/Applications/WebStorm.app/Contents/MacOS/webstorm",
        "markers": [".idea"],
        "project_types": ["nodejs"],
    },
    "goland": {
        "name": "GoLand",
        "command": ["goland"],
        "mac_app": "/Applications/GoLand.app",
        "mac_cli": "/Applications/GoLand.app/Contents/MacOS/goland",
        "markers": [".idea"],
        "project_types": ["go"],
    },
}


class IDELauncher:
    """Handles IDE detection and launching."""

    def __init__(self):
        self.is_mac = sys.platform == "darwin"

    def detect_project_type(self, path: str) -> str:
        """Detect the primary project type."""
        p = Path(path)

        # .NET projects (Rider)
        if list(p.glob("**/*.csproj")) or list(p.glob("**/*.sln")):
            return "dotnet"

        # Python projects
        if (p / "pyproject.toml").exists() or (p / "requirements.txt").exists():
            return "python"

        # Node.js projects
        if (p / "package.json").exists():
            return "nodejs"

        # Java/Kotlin projects
        if (p / "pom.xml").exists() or (p / "build.gradle").exists():
            return "java"

        # Go projects
        if (p / "go.mod").exists():
            return "go"

        # Rust projects
        if (p / "Cargo.toml").exists():
            return "rust"

        return "unknown"

    def detect_existing_ide_config(self, path: str) -> Optional[str]:
        """Detect IDE from existing configuration in project."""
        p = Path(path)

        # Check for VS Code
        if (p / ".vscode").exists():
            return "code"

        # Check for JetBrains IDEs
        if (p / ".idea").exists():
            # Try to determine which JetBrains IDE
            idea_dir = p / ".idea"

            # Check for .iml files that hint at the IDE
            for iml in idea_dir.glob("*.iml"):
                content = iml.read_text()
                if "RIDER_MODULE" in content:
                    return "rider"
                if "JAVA_MODULE" in content:
                    return "idea"
                if "WEB_MODULE" in content:
                    return "webstorm"
                if "PYTHON_MODULE" in content:
                    return "pycharm"

            # Fall back to project type detection
            project_type = self.detect_project_type(path)
            if project_type == "dotnet":
                return "rider"
            if project_type == "python":
                return "pycharm"
            if project_type == "nodejs":
                return "webstorm"
            if project_type in ["java", "kotlin"]:
                return "idea"
            if project_type == "go":
                return "goland"

        return None

    def get_best_ide(self, path: str) -> str:
        """Determine the best IDE for a project."""
        # First check for existing IDE config
        existing = self.detect_existing_ide_config(path)
        if existing and self.is_ide_available(existing):
            return existing

        # Detect project type and match to IDE
        project_type = self.detect_project_type(path)

        # Map project types to preferred IDEs
        type_to_ide = {
            "dotnet": ["rider", "code"],
            "python": ["pycharm", "code"],
            "nodejs": ["webstorm", "code"],
            "java": ["idea", "code"],
            "kotlin": ["idea", "code"],
            "go": ["goland", "code"],
            "rust": ["code"],  # No dedicated JetBrains IDE
            "unknown": ["code"],
        }

        candidates = type_to_ide.get(project_type, ["code"])

        for ide in candidates:
            if self.is_ide_available(ide):
                return ide

        # Final fallback
        return "code"

    def is_ide_available(self, ide: str) -> bool:
        """Check if an IDE is available on this system."""
        config = IDE_CONFIG.get(ide, {})

        if self.is_mac:
            # Check for macOS app
            mac_app = config.get("mac_app")
            if mac_app and os.path.exists(mac_app):
                return True

        # Check for command-line tool
        command = config.get("command", [])
        if command:
            try:
                subprocess.run(
                    ["which", command[0]],
                    capture_output=True,
                    check=True,
                )
                return True
            except subprocess.CalledProcessError:
                pass

        return False

    def get_launch_command(self, ide: str) -> List[str]:
        """Get the launch command for an IDE."""
        config = IDE_CONFIG.get(ide, {})

        if self.is_mac:
            # Prefer the CLI tool if available
            mac_cli = config.get("mac_cli")
            if mac_cli and os.path.exists(mac_cli):
                return [mac_cli]

            # Fall back to open command
            mac_app = config.get("mac_app")
            if mac_app and os.path.exists(mac_app):
                return ["open", "-a", mac_app]

        # Use command-line tool
        return config.get("command", ["code"])

    def launch(self, path: str, ide: str = "auto", new_window: bool = True) -> bool:
        """Launch an IDE for the given path."""
        # Resolve path
        path = os.path.abspath(path)

        # Determine IDE
        if ide == "auto":
            ide = self.get_best_ide(path)

        # Check availability
        if not self.is_ide_available(ide):
            print(f"Error: {ide} is not available", file=sys.stderr)
            return False

        # Get launch command
        cmd = self.get_launch_command(ide)
        config = IDE_CONFIG.get(ide, {})
        ide_name = config.get("name", ide)

        # Add new window flag if supported
        if new_window:
            if ide == "code":
                cmd.append("--new-window")
            # JetBrains IDEs open new windows by default

        # Add the path
        cmd.append(path)

        print(f"-> Opening in {ide_name}...")

        try:
            # Use Popen to avoid blocking
            subprocess.Popen(
                cmd,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            print(f"   Opened: {path}")
            return True
        except Exception as e:
            print(f"Error launching {ide_name}: {e}", file=sys.stderr)
            return False

    def list_available(self) -> List[Tuple[str, str]]:
        """List all available IDEs."""
        available = []
        for ide, config in IDE_CONFIG.items():
            if self.is_ide_available(ide):
                available.append((ide, config.get("name", ide)))
        return available


def main():
    parser = argparse.ArgumentParser(description="Launch IDE for worktree")
    subparsers = parser.add_subparsers(dest="command", required=True)

    # launch
    launch_cmd = subparsers.add_parser("launch", help="Launch IDE")
    launch_cmd.add_argument("--path", required=True, help="Path to open")
    launch_cmd.add_argument(
        "--ide",
        default="auto",
        choices=["auto", "code", "rider", "idea", "pycharm", "webstorm", "goland", "none"],
        help="IDE to use",
    )
    launch_cmd.add_argument(
        "--no-new-window", action="store_true", help="Don't force new window"
    )

    # detect
    detect_cmd = subparsers.add_parser("detect", help="Detect best IDE for project")
    detect_cmd.add_argument("--path", required=True, help="Path to analyze")

    # list
    list_cmd = subparsers.add_parser("list", help="List available IDEs")

    args = parser.parse_args()
    launcher = IDELauncher()

    if args.command == "launch":
        if args.ide == "none":
            print("IDE launch skipped")
            sys.exit(0)

        success = launcher.launch(
            args.path,
            ide=args.ide,
            new_window=not args.no_new_window,
        )
        sys.exit(0 if success else 1)

    elif args.command == "detect":
        best_ide = launcher.get_best_ide(args.path)
        project_type = launcher.detect_project_type(args.path)
        print(f"Project type: {project_type}")
        print(f"Recommended IDE: {best_ide}")

        config = IDE_CONFIG.get(best_ide, {})
        print(f"IDE name: {config.get('name', best_ide)}")

    elif args.command == "list":
        available = launcher.list_available()
        if available:
            print("Available IDEs:")
            for ide, name in available:
                print(f"  {ide}: {name}")
        else:
            print("No IDEs detected")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
TLA+ Project Store - Manages TLA+ project metadata and configuration.

This module provides the TLAStore class for managing:
- Project configuration (.tla-plus/project.json)
- Code-to-spec mappings (.tla-plus/mappings.json)
- Model registration and verification tracking
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional


@dataclass
class ModelConfig:
    """Configuration for a single TLA+ model."""

    name: str
    description: str
    spec_file: str
    configs: list[str] = field(default_factory=list)
    buggy_variant: Optional[str] = None
    verification_strategy: str = "tlc-simulation"
    last_verified: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "ModelConfig":
        return cls(
            name=data["name"],
            description=data.get("description", ""),
            spec_file=data["specFile"],
            configs=data.get("configs", []),
            buggy_variant=data.get("buggyVariant"),
            verification_strategy=data.get("verificationStrategy", "tlc-simulation"),
            last_verified=data.get("lastVerified"),
        )


@dataclass
class CIStrategy:
    """CI/CD verification strategy configuration."""

    default_mode: str = "simulation"
    simulation_depth: int = 100000
    full_verification_branches: list[str] = field(default_factory=lambda: ["main"])
    timeout_minutes: int = 30

    def to_dict(self) -> dict:
        return {
            "defaultMode": self.default_mode,
            "simulationDepth": self.simulation_depth,
            "fullVerificationBranches": self.full_verification_branches,
            "timeoutMinutes": self.timeout_minutes,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "CIStrategy":
        return cls(
            default_mode=data.get("defaultMode", "simulation"),
            simulation_depth=data.get("simulationDepth", 100000),
            full_verification_branches=data.get("fullVerificationBranches", ["main"]),
            timeout_minutes=data.get("timeoutMinutes", 30),
        )


@dataclass
class ActionMapping:
    """Mapping from TLA+ action to code location."""

    code_file: str
    method: str
    line: int

    def to_dict(self) -> dict:
        return {"codeFile": self.code_file, "method": self.method, "line": self.line}

    @classmethod
    def from_dict(cls, data: dict) -> "ActionMapping":
        return cls(
            code_file=data["codeFile"],
            method=data["method"],
            line=data["line"],
        )


@dataclass
class VariableMapping:
    """Mapping from TLA+ variable to data source."""

    table: Optional[str] = None
    column: Optional[str] = None
    derivation: Optional[str] = None

    def to_dict(self) -> dict:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, data: dict) -> "VariableMapping":
        return cls(
            table=data.get("table"),
            column=data.get("column"),
            derivation=data.get("derivation"),
        )


@dataclass
class InvariantMapping:
    """Mapping from TLA+ invariant to business rule."""

    description: str
    business_rule: Optional[str] = None

    def to_dict(self) -> dict:
        result = {"description": self.description}
        if self.business_rule:
            result["businessRule"] = self.business_rule
        return result

    @classmethod
    def from_dict(cls, data: dict) -> "InvariantMapping":
        return cls(
            description=data["description"],
            business_rule=data.get("businessRule"),
        )


@dataclass
class ModelMapping:
    """Complete mapping for a TLA+ model."""

    description: str
    actions: dict[str, ActionMapping] = field(default_factory=dict)
    variables: dict[str, VariableMapping] = field(default_factory=dict)
    constants: dict[str, str] = field(default_factory=dict)
    invariants: dict[str, InvariantMapping] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "description": self.description,
            "actions": {k: v.to_dict() for k, v in self.actions.items()},
            "variables": {k: v.to_dict() for k, v in self.variables.items()},
            "constants": self.constants,
            "invariants": {k: v.to_dict() for k, v in self.invariants.items()},
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModelMapping":
        return cls(
            description=data.get("description", ""),
            actions={k: ActionMapping.from_dict(v) for k, v in data.get("actions", {}).items()},
            variables={
                k: VariableMapping.from_dict(v) for k, v in data.get("variables", {}).items()
            },
            constants=data.get("constants", {}),
            invariants={
                k: InvariantMapping.from_dict(v) for k, v in data.get("invariants", {}).items()
            },
        )


class TLAStore:
    """Manages .tla-plus/ configuration and state."""

    VERSION = "1.0.0"
    DEFAULT_SPECS_DIR = "specs/tla+"
    DEFAULT_TOOLS_DIR = "specs/tla+/.tools"
    TLC_VERSION = "1.8.0"
    APALACHE_VERSION = "0.44.0"

    def __init__(self, project_root: Path | str):
        self.project_root = Path(project_root)
        self.config_dir = self.project_root / ".tla-plus"
        self.project_file = self.config_dir / "project.json"
        self.mappings_file = self.config_dir / "mappings.json"

    def is_initialized(self) -> bool:
        """Check if TLA+ project is initialized."""
        return self.project_file.exists()

    def init_project(self, specs_dir: str = DEFAULT_SPECS_DIR) -> None:
        """Initialize TLA+ project structure."""
        # Create directories
        self.config_dir.mkdir(parents=True, exist_ok=True)
        specs_path = self.project_root / specs_dir
        specs_path.mkdir(parents=True, exist_ok=True)
        (specs_path / ".tools").mkdir(exist_ok=True)
        (specs_path / "common").mkdir(exist_ok=True)

        # Create project.json
        project_config = {
            "version": self.VERSION,
            "specsDir": specs_dir,
            "toolsDir": f"{specs_dir}/.tools",
            "tlcVersion": self.TLC_VERSION,
            "apalacheVersion": self.APALACHE_VERSION,
            "models": [],
            "ciStrategy": CIStrategy().to_dict(),
        }
        self._write_json(self.project_file, project_config)

        # Create mappings.json
        mappings = {"models": {}}
        self._write_json(self.mappings_file, mappings)

        # Create .gitignore for tools
        gitignore = specs_path / ".tools" / ".gitignore"
        gitignore.write_text("tla2tools.jar\napalache/\nstates/\n*.states\n")

        # Create README
        readme = specs_path / "README.md"
        if not readme.exists():
            readme.write_text(self._get_readme_template())

    def get_project_config(self) -> dict:
        """Load project configuration."""
        if not self.project_file.exists():
            raise FileNotFoundError(
                f"TLA+ project not initialized. Run 'init_project()' first."
            )
        return self._read_json(self.project_file)

    def get_mappings(self) -> dict:
        """Load code-to-spec mappings."""
        if not self.mappings_file.exists():
            return {"models": {}}
        return self._read_json(self.mappings_file)

    def get_specs_dir(self) -> Path:
        """Get the specs directory path."""
        config = self.get_project_config()
        return self.project_root / config["specsDir"]

    def get_tools_dir(self) -> Path:
        """Get the tools directory path."""
        config = self.get_project_config()
        return self.project_root / config["toolsDir"]

    def list_models(self) -> list[ModelConfig]:
        """List all registered models."""
        config = self.get_project_config()
        return [ModelConfig.from_dict(m) for m in config.get("models", [])]

    def get_model(self, name: str) -> Optional[ModelConfig]:
        """Get a specific model by name."""
        for model in self.list_models():
            if model.name == name:
                return model
        return None

    def add_model(
        self,
        name: str,
        description: str,
        spec_file: str,
        configs: Optional[list[str]] = None,
        buggy_variant: Optional[str] = None,
    ) -> None:
        """Register a new model."""
        config = self.get_project_config()

        # Check if model already exists
        for model in config.get("models", []):
            if model["name"] == name:
                raise ValueError(f"Model '{name}' already exists")

        # Add new model
        model_config = {
            "name": name,
            "description": description,
            "specFile": spec_file,
            "configs": configs or [f"{name}.cfg"],
            "verificationStrategy": "tlc-simulation",
        }
        if buggy_variant:
            model_config["buggyVariant"] = buggy_variant

        config.setdefault("models", []).append(model_config)
        self._write_json(self.project_file, config)

        # Initialize mapping
        mappings = self.get_mappings()
        mappings["models"][name] = {"description": description, "actions": {}}
        self._write_json(self.mappings_file, mappings)

    def remove_model(self, name: str) -> bool:
        """Remove a model from the project."""
        config = self.get_project_config()
        original_count = len(config.get("models", []))
        config["models"] = [m for m in config.get("models", []) if m["name"] != name]

        if len(config["models"]) < original_count:
            self._write_json(self.project_file, config)

            # Remove from mappings
            mappings = self.get_mappings()
            mappings["models"].pop(name, None)
            self._write_json(self.mappings_file, mappings)
            return True
        return False

    def add_mapping(
        self,
        model: str,
        action: str,
        code_file: str,
        method: str,
        line: int,
    ) -> None:
        """Add code-to-spec mapping for an action."""
        mappings = self.get_mappings()

        if model not in mappings["models"]:
            mappings["models"][model] = {"description": "", "actions": {}}

        mappings["models"][model]["actions"][action] = {
            "codeFile": code_file,
            "method": method,
            "line": line,
        }
        self._write_json(self.mappings_file, mappings)

    def get_model_mapping(self, model: str) -> Optional[ModelMapping]:
        """Get complete mapping for a model."""
        mappings = self.get_mappings()
        if model not in mappings.get("models", {}):
            return None
        return ModelMapping.from_dict(mappings["models"][model])

    def get_trigger_paths(self, model: Optional[str] = None) -> list[str]:
        """Get CI trigger paths for a model (or all models)."""
        mappings = self.get_mappings()
        paths = set()

        # Always include specs directory
        config = self.get_project_config()
        paths.add(f"{config['specsDir']}/**")

        models_to_check = [model] if model else list(mappings.get("models", {}).keys())

        for m in models_to_check:
            model_data = mappings.get("models", {}).get(m, {})
            for action_data in model_data.get("actions", {}).values():
                if "codeFile" in action_data:
                    paths.add(action_data["codeFile"])

        return sorted(paths)

    def update_verification_timestamp(self, model: str) -> None:
        """Record successful verification timestamp."""
        config = self.get_project_config()
        timestamp = datetime.now(timezone.utc).isoformat()

        for m in config.get("models", []):
            if m["name"] == model:
                m["lastVerified"] = timestamp
                break

        self._write_json(self.project_file, config)

    def discover_models(self) -> list[dict]:
        """Auto-discover models from specs directory."""
        specs_dir = self.get_specs_dir()
        discovered = []

        for model_dir in specs_dir.iterdir():
            if not model_dir.is_dir() or model_dir.name.startswith("."):
                continue
            if model_dir.name == "common":
                continue

            # Look for main .tla file (not Race or Buggy variants)
            tla_files = list(model_dir.glob("*.tla"))
            main_files = [f for f in tla_files if not any(x in f.stem for x in ["Race", "Buggy"])]

            if main_files:
                main_file = main_files[0]
                cfg_files = list(model_dir.glob("*.cfg"))
                buggy_files = [f for f in tla_files if "Buggy" in f.stem]

                discovered.append({
                    "name": model_dir.name,
                    "spec_file": main_file.name,
                    "configs": [f.name for f in cfg_files],
                    "buggy_variant": buggy_files[0].name if buggy_files else None,
                    "path": str(model_dir.relative_to(self.project_root)),
                })

        return discovered

    def _read_json(self, path: Path) -> dict:
        """Read JSON file."""
        with open(path, "r") as f:
            return json.load(f)

    def _write_json(self, path: Path, data: dict) -> None:
        """Write JSON file with pretty formatting."""
        with open(path, "w") as f:
            json.dump(data, f, indent=2)
            f.write("\n")

    def _get_readme_template(self) -> str:
        """Get template for specs README."""
        return """# TLA+ Specifications

This directory contains TLA+ specifications for formal verification.

## Structure

```
specs/tla+/
├── .tools/           # TLC and other tools (gitignored)
├── common/           # Shared TLA+ modules
└── {model-name}/     # Individual specifications
    ├── {Model}.tla       # Main specification
    ├── {Model}.cfg       # Default configuration
    ├── {Model}_Large.cfg # Large configuration (thorough)
    └── {Model}Buggy.tla  # Negative test variant (optional)
```

## Running Verification

```bash
# Quick simulation (CI mode)
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py --all --mode quick

# Full verification
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py --model {name} --mode thorough
```

## Adding New Models

1. Create directory: `specs/tla+/{model-name}/`
2. Create specification: `{Model}.tla`
3. Create configuration: `{Model}.cfg`
4. Register with project (optional): Use `tla_store.add_model()`

## Configuration

Project configuration is stored in `.tla-plus/project.json`.
Code-to-spec mappings are in `.tla-plus/mappings.json`.
"""


def main():
    """CLI for TLA+ store operations."""
    import argparse

    parser = argparse.ArgumentParser(description="TLA+ Project Store")
    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    subparsers = parser.add_subparsers(dest="command", help="Commands")

    # init command
    init_parser = subparsers.add_parser("init", help="Initialize TLA+ project")
    init_parser.add_argument("--specs-dir", default="specs/tla+", help="Specs directory")

    # list command
    subparsers.add_parser("list", help="List models")

    # discover command
    subparsers.add_parser("discover", help="Discover models from specs directory")

    # add-model command
    add_parser = subparsers.add_parser("add-model", help="Add a model")
    add_parser.add_argument("name", help="Model name")
    add_parser.add_argument("--description", "-d", required=True, help="Description")
    add_parser.add_argument("--spec-file", "-s", required=True, help="Spec file name")

    # add-mapping command
    map_parser = subparsers.add_parser("add-mapping", help="Add code-to-spec mapping")
    map_parser.add_argument("--model", "-m", required=True, help="Model name")
    map_parser.add_argument("--action", "-a", required=True, help="TLA+ action name")
    map_parser.add_argument("--file", "-f", required=True, help="Code file path")
    map_parser.add_argument("--method", required=True, help="Method name")
    map_parser.add_argument("--line", "-l", type=int, required=True, help="Line number")

    # trigger-paths command
    paths_parser = subparsers.add_parser("trigger-paths", help="Get CI trigger paths")
    paths_parser.add_argument("--model", "-m", help="Specific model (optional)")

    args = parser.parse_args()
    store = TLAStore(args.project)

    if args.command == "init":
        store.init_project(args.specs_dir)
        print(f"Initialized TLA+ project in {store.config_dir}")

    elif args.command == "list":
        if not store.is_initialized():
            print("TLA+ project not initialized. Run 'init' first.")
            return

        models = store.list_models()
        if not models:
            print("No models registered.")
        else:
            for m in models:
                verified = f" (verified: {m.last_verified})" if m.last_verified else ""
                print(f"  {m.name}: {m.description}{verified}")

    elif args.command == "discover":
        if not store.is_initialized():
            print("TLA+ project not initialized. Run 'init' first.")
            return

        discovered = store.discover_models()
        if not discovered:
            print("No models found in specs directory.")
        else:
            print("Discovered models:")
            for d in discovered:
                print(f"  {d['name']}: {d['spec_file']} ({len(d['configs'])} configs)")

    elif args.command == "add-model":
        store.add_model(args.name, args.description, args.spec_file)
        print(f"Added model: {args.name}")

    elif args.command == "add-mapping":
        store.add_mapping(args.model, args.action, args.file, args.method, args.line)
        print(f"Added mapping: {args.action} -> {args.file}:{args.line}")

    elif args.command == "trigger-paths":
        paths = store.get_trigger_paths(args.model)
        for p in paths:
            print(p)

    else:
        parser.print_help()


if __name__ == "__main__":
    main()

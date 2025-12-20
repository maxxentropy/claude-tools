#!/usr/bin/env python3
"""
TLA+ CI Pipeline Generator - Generate CI/CD pipelines for TLA+ verification.

This module generates CI pipeline configurations for:
- Azure DevOps (YAML pipelines)
- GitHub Actions (workflow files)

Features:
- Automatic trigger path detection from TLAStore mappings
- Quick (simulation) and thorough (full BFS) verification modes
- Negative testing for buggy variants
- Configurable timeouts and worker counts
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional

from tla_store import TLAStore, CIStrategy


@dataclass
class PipelineConfig:
    """Configuration for pipeline generation."""

    platform: str  # "azure-devops" or "github"
    output_path: Path
    tlc_version: str = "1.8.0"
    java_version: str = "17"
    timeout_minutes: int = 30
    simulation_depth: int = 100000
    full_verification_branches: list[str] = field(default_factory=lambda: ["main"])
    include_negative_tests: bool = True
    include_thorough_verification: bool = True
    trigger_branches: list[str] = field(default_factory=lambda: ["main", "develop", "feature/*"])
    pr_branches: list[str] = field(default_factory=lambda: ["main", "develop"])


@dataclass
class GeneratedPipeline:
    """Result of pipeline generation."""

    output_path: Path
    platform: str
    success: bool
    message: str
    trigger_paths: list[str] = field(default_factory=list)


class PipelineGenerator:
    """Generates CI pipeline configurations for TLA+ verification."""

    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)
        self.store = TLAStore(self.project_root)

    def generate(self, config: PipelineConfig) -> GeneratedPipeline:
        """Generate a CI pipeline configuration."""
        # Get trigger paths from store if available
        trigger_paths = ["specs/tla+/**"]
        if self.store.is_initialized():
            trigger_paths = self.store.get_trigger_paths()

        # Get models info
        models = []
        buggy_models = []
        if self.store.is_initialized():
            for model in self.store.list_models():
                models.append(model.name)
                if model.buggy_variant:
                    buggy_models.append(model.name)
        else:
            # Discover from filesystem
            models = self._discover_models()
            buggy_models = self._discover_buggy_models()

        # Generate based on platform
        if config.platform == "azure-devops":
            content = self._generate_azure_devops(config, trigger_paths, models, buggy_models)
        elif config.platform == "github":
            content = self._generate_github_actions(config, trigger_paths, models, buggy_models)
        else:
            return GeneratedPipeline(
                output_path=config.output_path,
                platform=config.platform,
                success=False,
                message=f"Unsupported platform: {config.platform}",
            )

        # Write output
        config.output_path.parent.mkdir(parents=True, exist_ok=True)
        config.output_path.write_text(content)

        return GeneratedPipeline(
            output_path=config.output_path,
            platform=config.platform,
            success=True,
            message=f"Generated {config.platform} pipeline at {config.output_path}",
            trigger_paths=trigger_paths,
        )

    def _discover_models(self) -> list[str]:
        """Discover model names from specs directory."""
        specs_dir = self.project_root / "specs" / "tla+"
        if not specs_dir.exists():
            return []

        models = []
        for d in specs_dir.iterdir():
            if d.is_dir() and not d.name.startswith(".") and d.name != "common":
                if list(d.glob("*.tla")):
                    models.append(d.name)
        return sorted(models)

    def _discover_buggy_models(self) -> list[str]:
        """Discover models with buggy variants."""
        specs_dir = self.project_root / "specs" / "tla+"
        if not specs_dir.exists():
            return []

        buggy = []
        for d in specs_dir.iterdir():
            if d.is_dir() and not d.name.startswith("."):
                if list(d.glob("*Buggy.tla")):
                    buggy.append(d.name)
        return sorted(buggy)

    def _generate_azure_devops(
        self,
        config: PipelineConfig,
        trigger_paths: list[str],
        models: list[str],
        buggy_models: list[str],
    ) -> str:
        """Generate Azure DevOps YAML pipeline."""
        timestamp = datetime.now().strftime("%Y-%m-%d")

        # Format trigger paths
        trigger_paths_yaml = "\n".join(f"      - {p}" for p in trigger_paths)

        # Format branch triggers
        trigger_branches_yaml = "\n".join(f"      - {b}" for b in config.trigger_branches)
        pr_branches_yaml = "\n".join(f"      - {b}" for b in config.pr_branches)

        # Build full verification condition
        full_verification_condition = " || ".join(
            f"eq(variables['Build.SourceBranch'], 'refs/heads/{b}')"
            for b in config.full_verification_branches
        )

        # Negative test script
        negative_test_script = ""
        if config.include_negative_tests and buggy_models:
            negative_test_script = self._generate_azure_negative_test_job(
                buggy_models[0], config.tlc_version
            )

        # Thorough verification script
        thorough_script = ""
        if config.include_thorough_verification and models:
            thorough_script = f"""
          - script: |
              echo "Running thorough verification on protected branch..."
              python3 ${{HOME}}/.claude/skills/tla-plus/scripts/run_tlc.py \\
                --all --mode thorough --format markdown
            displayName: 'Thorough Verification (Full BFS)'
            condition: and(succeeded(), {full_verification_condition})"""

        return f'''# Azure DevOps Pipeline: TLA+ Formal Verification
#
# Generated: {timestamp}
# Generator: ~/.claude/skills/tla-plus/scripts/generate_pipeline.py
#
# Runs TLC model checker on TLA+ specifications to verify
# system invariants and detect concurrency bugs.

trigger:
  branches:
    include:
{trigger_branches_yaml}
  paths:
    include:
{trigger_paths_yaml}

pr:
  branches:
    include:
{pr_branches_yaml}
  paths:
    include:
{trigger_paths_yaml}

pool:
  vmImage: 'ubuntu-latest'

variables:
  TLA_VERSION: '{config.tlc_version}'
  JAVA_VERSION: '{config.java_version}'
  SIMULATION_DEPTH: '{config.simulation_depth}'

stages:
  - stage: TLAVerification
    displayName: 'TLA+ Formal Verification'
    jobs:
      - job: QuickVerification
        displayName: 'Quick Verification (Simulation)'
        timeoutInMinutes: {config.timeout_minutes}
        steps:
          - script: |
              echo "Installing Java ${{JAVA_VERSION}}..."
              sudo apt-get update
              sudo apt-get install -y openjdk-${{JAVA_VERSION}}-jdk
              java -version
            displayName: 'Install Java'

          - script: |
              echo "Downloading TLA+ tools v$(TLA_VERSION)..."
              mkdir -p specs/tla+/.tools
              curl -sL -o specs/tla+/.tools/tla2tools.jar \\
                "https://github.com/tlaplus/tlaplus/releases/download/v$(TLA_VERSION)/tla2tools.jar"
            displayName: 'Download TLA+ Tools'

          - script: |
              echo "Running TLA+ simulation verification..."
              python3 ${{HOME}}/.claude/skills/tla-plus/scripts/run_tlc.py \\
                --all --mode quick --depth $(SIMULATION_DEPTH) --format markdown
            displayName: 'Run TLC Simulation'
{thorough_script}

          - task: PublishBuildArtifacts@1
            displayName: 'Publish TLA+ Results'
            inputs:
              PathtoPublish: 'specs/tla+'
              ArtifactName: 'tla-verification'
            condition: always()
{negative_test_script}
'''

    def _generate_azure_negative_test_job(self, model: str, tlc_version: str) -> str:
        """Generate Azure DevOps negative test job."""
        return f'''
      - job: NegativeTest
        displayName: 'Verify Bug Detection'
        dependsOn: QuickVerification
        steps:
          - script: |
              sudo apt-get update
              sudo apt-get install -y openjdk-17-jdk
            displayName: 'Install Java'

          - script: |
              mkdir -p specs/tla+/.tools
              curl -sL -o specs/tla+/.tools/tla2tools.jar \\
                "https://github.com/tlaplus/tlaplus/releases/download/v{tlc_version}/tla2tools.jar"
            displayName: 'Download TLA+ Tools'

          - script: |
              echo "Verifying TLC detects bugs in intentionally buggy model..."
              cd specs/tla+/{model}

              # Run buggy model - it SHOULD fail
              if java -XX:+UseParallelGC -jar ../.tools/tla2tools.jar \\
                  -config *Buggy.cfg *Buggy.tla 2>&1; then
                echo "ERROR: Buggy model passed when it should have failed!"
                echo "This indicates the model checker is not detecting the bug."
                exit 1
              else
                echo "SUCCESS: TLC correctly detected the bug."
                echo "Model checker is working as expected."
                exit 0
              fi
            displayName: 'Verify Buggy Model Fails (Expected)'
'''

    def _generate_github_actions(
        self,
        config: PipelineConfig,
        trigger_paths: list[str],
        models: list[str],
        buggy_models: list[str],
    ) -> str:
        """Generate GitHub Actions workflow."""
        timestamp = datetime.now().strftime("%Y-%m-%d")

        # Format paths (GitHub uses slightly different syntax)
        paths_yaml = "\n".join(f"        - '{p}'" for p in trigger_paths)

        # Format branches
        push_branches = ", ".join(config.trigger_branches)
        pr_branches = ", ".join(config.pr_branches)

        # Full verification condition
        full_condition = " || ".join(
            f"github.ref == 'refs/heads/{b}'"
            for b in config.full_verification_branches
        )

        # Negative test job
        negative_test_job = ""
        if config.include_negative_tests and buggy_models:
            negative_test_job = self._generate_github_negative_test_job(
                buggy_models[0], config.tlc_version, config.java_version
            )

        # Thorough verification step
        thorough_step = ""
        if config.include_thorough_verification:
            thorough_step = f"""
      - name: Thorough Verification (Full BFS)
        if: {full_condition}
        run: |
          python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \\
            --all --mode thorough --format markdown"""

        return f'''# GitHub Actions: TLA+ Formal Verification
#
# Generated: {timestamp}
# Generator: ~/.claude/skills/tla-plus/scripts/generate_pipeline.py
#
# Runs TLC model checker on TLA+ specifications to verify
# system invariants and detect concurrency bugs.

name: TLA+ Verification

on:
  push:
    branches: [{push_branches}]
    paths:
{paths_yaml}
  pull_request:
    branches: [{pr_branches}]
    paths:
{paths_yaml}

jobs:
  verify:
    name: TLA+ Model Checking
    runs-on: ubuntu-latest
    timeout-minutes: {config.timeout_minutes}

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Java
        uses: actions/setup-java@v4
        with:
          distribution: 'temurin'
          java-version: '{config.java_version}'

      - name: Download TLA+ Tools
        run: |
          mkdir -p specs/tla+/.tools
          curl -sL -o specs/tla+/.tools/tla2tools.jar \\
            "https://github.com/tlaplus/tlaplus/releases/download/v{config.tlc_version}/tla2tools.jar"

      - name: Quick Verification (Simulation)
        run: |
          python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \\
            --all --mode quick --depth {config.simulation_depth} --format markdown
{thorough_step}

      - name: Upload Results
        uses: actions/upload-artifact@v4
        if: always()
        with:
          name: tla-verification
          path: specs/tla+/
{negative_test_job}
'''

    def _generate_github_negative_test_job(
        self, model: str, tlc_version: str, java_version: str
    ) -> str:
        """Generate GitHub Actions negative test job."""
        return f'''
  negative-test:
    name: Verify Bug Detection
    runs-on: ubuntu-latest
    needs: verify

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Setup Java
        uses: actions/setup-java@v4
        with:
          distribution: 'temurin'
          java-version: '{java_version}'

      - name: Download TLA+ Tools
        run: |
          mkdir -p specs/tla+/.tools
          curl -sL -o specs/tla+/.tools/tla2tools.jar \\
            "https://github.com/tlaplus/tlaplus/releases/download/v{tlc_version}/tla2tools.jar"

      - name: Verify Buggy Model Fails
        run: |
          echo "Verifying TLC detects bugs in intentionally buggy model..."
          cd specs/tla+/{model}

          # Run buggy model - it SHOULD fail
          if java -XX:+UseParallelGC -jar ../.tools/tla2tools.jar \\
              -config *Buggy.cfg *Buggy.tla 2>&1; then
            echo "ERROR: Buggy model passed when it should have failed!"
            exit 1
          else
            echo "SUCCESS: TLC correctly detected the bug."
            exit 0
          fi
'''

    def detect_platform(self) -> str:
        """Detect CI platform from project structure."""
        if (self.project_root / ".azure-pipelines").exists():
            return "azure-devops"
        if (self.project_root / "azure-pipelines.yml").exists():
            return "azure-devops"
        if (self.project_root / ".github" / "workflows").exists():
            return "github"
        # Default based on git remote
        try:
            import subprocess
            result = subprocess.run(
                ["git", "remote", "-v"],
                capture_output=True,
                text=True,
                cwd=self.project_root,
            )
            if "dev.azure.com" in result.stdout or "visualstudio.com" in result.stdout:
                return "azure-devops"
            if "github.com" in result.stdout:
                return "github"
        except Exception:
            pass
        return "azure-devops"  # Default

    def get_default_output_path(self, platform: str) -> Path:
        """Get default output path for platform."""
        if platform == "azure-devops":
            return self.project_root / ".azure-pipelines" / "tla-verification.yml"
        else:
            return self.project_root / ".github" / "workflows" / "tla-verification.yml"


def main():
    """CLI for TLA+ pipeline generation."""
    parser = argparse.ArgumentParser(
        description="Generate CI/CD pipelines for TLA+ verification",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Auto-detect platform and generate
  %(prog)s

  # Generate Azure DevOps pipeline
  %(prog)s --platform azure-devops

  # Generate GitHub Actions workflow
  %(prog)s --platform github --output .github/workflows/tla.yml

  # Custom configuration
  %(prog)s --platform azure-devops \\
      --timeout 45 \\
      --simulation-depth 200000 \\
      --full-branches main release/*
        """,
    )

    parser.add_argument(
        "--project", "-p",
        default=".",
        help="Project root directory (default: current directory)",
    )
    parser.add_argument(
        "--platform",
        choices=["azure-devops", "github", "auto"],
        default="auto",
        help="CI platform (default: auto-detect)",
    )
    parser.add_argument(
        "--output", "-o",
        help="Output file path (default: platform-specific)",
    )
    parser.add_argument(
        "--tlc-version",
        default="1.8.0",
        help="TLA+ tools version (default: 1.8.0)",
    )
    parser.add_argument(
        "--java-version",
        default="17",
        help="Java version (default: 17)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Job timeout in minutes (default: 30)",
    )
    parser.add_argument(
        "--simulation-depth",
        type=int,
        default=100000,
        help="Simulation depth for quick mode (default: 100000)",
    )
    parser.add_argument(
        "--full-branches",
        nargs="+",
        default=["main"],
        help="Branches for thorough verification (default: main)",
    )
    parser.add_argument(
        "--trigger-branches",
        nargs="+",
        default=["main", "develop", "feature/*"],
        help="Branches that trigger the pipeline",
    )
    parser.add_argument(
        "--no-negative-tests",
        action="store_true",
        help="Skip negative testing for buggy variants",
    )
    parser.add_argument(
        "--no-thorough",
        action="store_true",
        help="Skip thorough verification on protected branches",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output result as JSON",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print generated pipeline without writing file",
    )

    args = parser.parse_args()

    generator = PipelineGenerator(args.project)

    # Detect or use specified platform
    platform = args.platform
    if platform == "auto":
        platform = generator.detect_platform()
        if not args.json:
            print(f"Detected platform: {platform}")

    # Determine output path
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = generator.get_default_output_path(platform)

    # Build configuration
    config = PipelineConfig(
        platform=platform,
        output_path=output_path,
        tlc_version=args.tlc_version,
        java_version=args.java_version,
        timeout_minutes=args.timeout,
        simulation_depth=args.simulation_depth,
        full_verification_branches=args.full_branches,
        include_negative_tests=not args.no_negative_tests,
        include_thorough_verification=not args.no_thorough,
        trigger_branches=args.trigger_branches,
    )

    # Generate pipeline
    result = generator.generate(config)

    if args.dry_run:
        # Just print the content
        print(output_path.read_text())
        return

    if args.json:
        output = {
            "success": result.success,
            "message": result.message,
            "platform": result.platform,
            "output_path": str(result.output_path),
            "trigger_paths": result.trigger_paths,
        }
        print(json.dumps(output, indent=2))
    else:
        if result.success:
            print(f"\n✅ {result.message}")
            print(f"\nTrigger paths ({len(result.trigger_paths)}):")
            for p in result.trigger_paths[:10]:
                print(f"  - {p}")
            if len(result.trigger_paths) > 10:
                print(f"  ... and {len(result.trigger_paths) - 10} more")
            print(f"\nPipeline features:")
            print(f"  - Quick verification (simulation mode)")
            if not args.no_thorough:
                print(f"  - Thorough verification on: {', '.join(config.full_verification_branches)}")
            if not args.no_negative_tests:
                print(f"  - Negative testing for buggy variants")
            print(f"\nNext steps:")
            print(f"  1. Review the generated pipeline: {result.output_path}")
            print(f"  2. Commit and push to trigger verification")
        else:
            print(f"\n❌ {result.message}")
            sys.exit(1)


if __name__ == "__main__":
    main()

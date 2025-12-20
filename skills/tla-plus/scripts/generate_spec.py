#!/usr/bin/env python3
"""
TLA+ Specification Generator - Generate specs from pattern templates.

This module generates TLA+ specifications from pattern templates with:
- Placeholder substitution ({{PLACEHOLDER}} syntax)
- Configuration file generation (.cfg)
- Model directory structure creation
- Optional TLAStore registration
- Interactive mode for placeholder values
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from tla_store import TLAStore


@dataclass
class PlaceholderInfo:
    """Information about a placeholder in a template."""

    name: str
    description: str = ""
    default_value: str = ""
    example: str = ""
    placeholder_type: str = "constant"  # constant, set, value


@dataclass
class PatternTemplate:
    """A TLA+ pattern template."""

    name: str
    path: Path
    description: str = ""
    use_case: str = ""
    placeholders: list[PlaceholderInfo] = field(default_factory=list)
    content: str = ""

    def load(self) -> None:
        """Load template content and extract metadata."""
        self.content = self.path.read_text()
        self._parse_metadata()
        self._extract_placeholders()

    def _parse_metadata(self) -> None:
        """Extract description and use case from template header comment."""
        # Look for Pattern for: and Common in:
        pattern_match = re.search(r"\* Pattern for: (.+?)$", self.content, re.MULTILINE)
        if pattern_match:
            self.use_case = pattern_match.group(1).strip()

        desc_match = re.search(r"\* Template: (.+?)$", self.content, re.MULTILINE)
        if desc_match:
            self.description = desc_match.group(1).strip()

    def _extract_placeholders(self) -> None:
        """Extract all placeholders from template content."""
        # Find all {{NAME}} patterns
        placeholder_pattern = r"\{\{(\w+)\}\}"
        found = set(re.findall(placeholder_pattern, self.content))

        # Filter out generic placeholders that are just markers
        found = {p for p in found if p not in {"PLACEHOLDER", "Name", "DEFINE_TRANSITIONS"}}

        # Standard placeholders with known descriptions
        known_placeholders = {
            "ENTITIES": PlaceholderInfo(
                name="ENTITIES",
                description="Set of entity IDs",
                default_value="ENTITIES",
                example="{E1, E2, E3}",
                placeholder_type="set",
            ),
            "ACTORS": PlaceholderInfo(
                name="ACTORS",
                description="Set of concurrent actors",
                default_value="ACTORS",
                example="{A1, A2}",
                placeholder_type="set",
            ),
            "USERS": PlaceholderInfo(
                name="USERS",
                description="Set of user IDs",
                default_value="USERS",
                example="{U1, U2}",
                placeholder_type="set",
            ),
            "NODES": PlaceholderInfo(
                name="NODES",
                description="Set of node IDs",
                default_value="NODES",
                example="{N1, N2, N3}",
                placeholder_type="set",
            ),
            "SERVICES": PlaceholderInfo(
                name="SERVICES",
                description="Set of service IDs",
                default_value="SERVICES",
                example="{S1, S2}",
                placeholder_type="set",
            ),
            "CLIENTS": PlaceholderInfo(
                name="CLIENTS",
                description="Set of client IDs",
                default_value="CLIENTS",
                example="{C1, C2}",
                placeholder_type="set",
            ),
            "PARTICIPANTS": PlaceholderInfo(
                name="PARTICIPANTS",
                description="Set of participant IDs",
                default_value="PARTICIPANTS",
                example="{P1, P2, P3}",
                placeholder_type="set",
            ),
            "TRANSACTIONS": PlaceholderInfo(
                name="TRANSACTIONS",
                description="Set of transaction IDs",
                default_value="TRANSACTIONS",
                example="{T1}",
                placeholder_type="set",
            ),
            "SAGAS": PlaceholderInfo(
                name="SAGAS",
                description="Set of saga IDs",
                default_value="SAGAS",
                example="{S1}",
                placeholder_type="set",
            ),
            "STATES": PlaceholderInfo(
                name="STATES",
                description="Set of valid states",
                default_value="STATES",
                example='{"Draft", "Active", "Completed"}',
                placeholder_type="set",
            ),
            "STEPS": PlaceholderInfo(
                name="STEPS",
                description="Sequence of saga steps",
                default_value="STEPS",
                example='<<"Reserve", "Charge", "Ship">>',
                placeholder_type="value",
            ),
            "INITIAL_STATE": PlaceholderInfo(
                name="INITIAL_STATE",
                description="Initial state for entities",
                default_value='"Draft"',
                example='"Draft"',
                placeholder_type="value",
            ),
            "TERMINAL_STATES": PlaceholderInfo(
                name="TERMINAL_STATES",
                description="Set of terminal states",
                default_value="TERMINAL_STATES",
                example='{"Completed", "Cancelled"}',
                placeholder_type="set",
            ),
        }

        self.placeholders = []
        for name in sorted(found):
            if name in known_placeholders:
                self.placeholders.append(known_placeholders[name])
            else:
                # Unknown placeholder - create generic info
                self.placeholders.append(PlaceholderInfo(
                    name=name,
                    description=f"Value for {name}",
                    default_value=name,
                    placeholder_type="value",
                ))


@dataclass
class GenerationConfig:
    """Configuration for spec generation."""

    pattern: str
    name: str
    output_dir: Path
    placeholders: dict[str, str] = field(default_factory=dict)
    create_large_config: bool = True
    create_buggy_variant: bool = False
    register_with_store: bool = True
    description: str = ""


@dataclass
class GeneratedSpec:
    """Result of spec generation."""

    spec_file: Path
    config_files: list[Path]
    buggy_file: Optional[Path] = None
    model_name: str = ""
    success: bool = True
    message: str = ""


class SpecGenerator:
    """Generates TLA+ specifications from pattern templates."""

    def __init__(self, skill_dir: Optional[Path] = None):
        """
        Initialize the generator.

        Args:
            skill_dir: Path to tla-plus skill directory.
                       Defaults to ~/.claude/skills/tla-plus
        """
        if skill_dir:
            self.skill_dir = Path(skill_dir)
        else:
            self.skill_dir = Path.home() / ".claude" / "skills" / "tla-plus"

        self.templates_dir = self.skill_dir / "templates" / "patterns"

    def list_patterns(self) -> list[PatternTemplate]:
        """List available pattern templates."""
        patterns = []

        if not self.templates_dir.exists():
            return patterns

        for tla_file in sorted(self.templates_dir.glob("*.tla")):
            template = PatternTemplate(
                name=tla_file.stem,
                path=tla_file,
            )
            template.load()
            patterns.append(template)

        return patterns

    def get_pattern(self, name: str) -> Optional[PatternTemplate]:
        """Get a specific pattern template by name."""
        pattern_file = self.templates_dir / f"{name}.tla"
        if not pattern_file.exists():
            # Try with hyphens converted to underscores and vice versa
            alt_name = name.replace("-", "_")
            pattern_file = self.templates_dir / f"{alt_name}.tla"
            if not pattern_file.exists():
                alt_name = name.replace("_", "-")
                pattern_file = self.templates_dir / f"{alt_name}.tla"
                if not pattern_file.exists():
                    return None

        template = PatternTemplate(name=name, path=pattern_file)
        template.load()
        return template

    def generate(self, config: GenerationConfig) -> GeneratedSpec:
        """
        Generate a TLA+ specification from a pattern template.

        Args:
            config: Generation configuration

        Returns:
            GeneratedSpec with paths to created files
        """
        # Get pattern template
        pattern = self.get_pattern(config.pattern)
        if not pattern:
            return GeneratedSpec(
                spec_file=Path(),
                config_files=[],
                success=False,
                message=f"Pattern not found: {config.pattern}",
            )

        # Create output directory
        output_dir = Path(config.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        # Convert name to PascalCase for module name
        module_name = self._to_pascal_case(config.name)

        # Prepare substitutions
        substitutions = dict(config.placeholders)

        # Generate spec content
        spec_content = self._substitute_placeholders(
            pattern.content,
            substitutions,
            module_name,
            pattern.name,
        )

        # Write spec file
        spec_file = output_dir / f"{module_name}.tla"
        spec_file.write_text(spec_content)

        # Generate config files
        config_files = []

        # Standard config
        std_cfg = self._generate_config(
            module_name=module_name,
            placeholders=pattern.placeholders,
            substitutions=substitutions,
            size="standard",
            template_content=pattern.content,
        )
        std_cfg_file = output_dir / f"{module_name}.cfg"
        std_cfg_file.write_text(std_cfg)
        config_files.append(std_cfg_file)

        # Large config (optional)
        if config.create_large_config:
            large_cfg = self._generate_config(
                module_name=module_name,
                placeholders=pattern.placeholders,
                substitutions=substitutions,
                size="large",
                template_content=pattern.content,
            )
            large_cfg_file = output_dir / f"{module_name}_Large.cfg"
            large_cfg_file.write_text(large_cfg)
            config_files.append(large_cfg_file)

        # Buggy variant (optional)
        buggy_file = None
        if config.create_buggy_variant:
            buggy_content = self._generate_buggy_variant(spec_content, module_name)
            buggy_file = output_dir / f"{module_name}Buggy.tla"
            buggy_file.write_text(buggy_content)

        # Create README
        readme_content = self._generate_readme(
            module_name=module_name,
            pattern=pattern,
            config=config,
        )
        readme_file = output_dir / "README.md"
        readme_file.write_text(readme_content)

        # Register with store if requested
        model_name = self._to_kebab_case(config.name)
        if config.register_with_store:
            try:
                # Find project root (walk up to find .tla-plus directory)
                project_root = self._find_project_root(output_dir)
                if project_root:
                    store = TLAStore(project_root)
                    if store.is_initialized():
                        store.add_model(
                            name=model_name,
                            description=config.description or pattern.description,
                            spec_file=f"{module_name}.tla",
                            configs=[f.name for f in config_files],
                            buggy_variant=buggy_file.name if buggy_file else None,
                        )
            except Exception as e:
                # Non-fatal - just log warning
                print(f"Warning: Could not register with TLAStore: {e}", file=sys.stderr)

        return GeneratedSpec(
            spec_file=spec_file,
            config_files=config_files,
            buggy_file=buggy_file,
            model_name=model_name,
            success=True,
            message=f"Generated {module_name} from {pattern.name} pattern",
        )

    def _substitute_placeholders(
        self,
        content: str,
        substitutions: dict[str, str],
        module_name: str,
        pattern_name: str,
    ) -> str:
        """Substitute placeholders in template content."""
        result = content

        # Replace module name in header
        # Find the MODULE line and replace the module name
        old_module = self._to_pascal_case(pattern_name.replace("-", " "))
        result = re.sub(
            rf"MODULE {old_module}",
            f"MODULE {module_name}",
            result,
        )

        # Also try original module name patterns
        result = re.sub(
            r"MODULE (\w+)",
            f"MODULE {module_name}",
            result,
            count=1,  # Only replace first occurrence
        )

        # Replace user-specified placeholders
        for name, value in substitutions.items():
            # Replace {{NAME}} with value
            result = result.replace(f"{{{{{name}}}}}", value)

        # Replace remaining placeholders with their default (just remove braces)
        # This converts {{SERVICES}} to SERVICES
        result = re.sub(r"\{\{(\w+)\}\}", r"\1", result)

        return result

    def _generate_config(
        self,
        module_name: str,
        placeholders: list[PlaceholderInfo],
        substitutions: dict[str, str],
        size: str = "standard",
        template_content: str = "",
    ) -> str:
        """Generate a .cfg configuration file."""
        lines = [
            f"\\ Configuration for {module_name}",
            f"\\ Size: {size}",
            "",
            "SPECIFICATION Spec",
            "",
        ]

        # Add constants section
        lines.append("CONSTANTS")

        # First add placeholder-based constants (sets)
        for ph in placeholders:
            name = substitutions.get(ph.name, ph.default_value)
            if ph.placeholder_type == "set":
                # Generate appropriate set size based on config size
                if size == "large":
                    example_set = self._generate_set(name, 4)
                else:
                    example_set = self._generate_set(name, 2)
                lines.append(f"    {name} = {example_set}")
            elif ph.placeholder_type == "value" and ph.example:
                lines.append(f"    {name} = {ph.example}")

        # Extract non-placeholder constants from template content
        # Parse CONSTANTS section to find other constants
        extra_constants = self._extract_template_constants(template_content)

        # Add standard numeric constants with appropriate values
        for const_name in extra_constants:
            if const_name in [ph.name for ph in placeholders]:
                continue  # Already handled

            if "MAX_VERSION" in const_name or const_name == "MAX_VERSION":
                max_val = 10 if size == "large" else 5
                lines.append(f"    {const_name} = {max_val}")
            elif const_name == "MAX_TOKENS":
                max_val = 6 if size == "large" else 3
                lines.append(f"    {const_name} = {max_val}")
            elif const_name == "MAX_RETRIES":
                lines.append(f"    {const_name} = 2")
            elif const_name == "MAX_TICKS":
                max_val = 20 if size == "large" else 10
                lines.append(f"    {const_name} = {max_val}")
            elif const_name == "MAX_REQUESTS":
                max_val = 30 if size == "large" else 15
                lines.append(f"    {const_name} = {max_val}")
            elif const_name == "MAX_TERM":
                max_val = 5 if size == "large" else 3
                lines.append(f"    {const_name} = {max_val}")
            elif "THRESHOLD" in const_name:
                val = 5 if size == "large" else 3
                lines.append(f"    {const_name} = {val}")
            elif "DURATION" in const_name:
                lines.append(f"    {const_name} = 3")
            elif "RATE" in const_name:
                lines.append(f"    {const_name} = 1")
            elif "CAPACITY" in const_name:
                val = 10 if size == "large" else 5
                lines.append(f"    {const_name} = {val}")
            elif "TOKENS_PER" in const_name:
                lines.append(f"    {const_name} = 1")

        lines.extend([
            "",
            "INVARIANT Safety",
            "",
            "\\ Enable this for liveness checking with fairness:",
            "\\ PROPERTY EventuallyTerminal",
        ])

        return "\n".join(lines) + "\n"

    def _generate_set(self, name: str, count: int) -> str:
        """Generate a set constant with appropriate names."""
        # Determine prefix from name
        prefix = name[0] if name else "X"
        elements = [f"{prefix}{i}" for i in range(1, count + 1)]
        return "{" + ", ".join(elements) + "}"

    def _extract_template_constants(self, content: str) -> list[str]:
        """Extract constant names from template CONSTANTS section."""
        constants = []

        # Find CONSTANTS section (between CONSTANTS and VARIABLES)
        constants_match = re.search(
            r"CONSTANTS\s*\n(.*?)(?=VARIABLES|\n\\* -----)",
            content,
            re.DOTALL,
        )

        if constants_match:
            section = constants_match.group(1)
            # Find all constant names (words at start of line or after comma)
            for line in section.split("\n"):
                # Remove TLA+ comments (\*)
                line = re.sub(r"\\\\?\*.*$", "", line).strip()
                # Skip lines that are just placeholders or empty
                if not line or line.startswith("{{"):
                    continue
                # Match constant names (word characters)
                matches = re.findall(r"\b([A-Z][A-Z_0-9]*)\b", line)
                for m in matches:
                    # Skip placeholder markers and duplicates
                    if m not in constants and not m.startswith("{{"):
                        constants.append(m)

        return constants

    def _generate_buggy_variant(self, spec_content: str, module_name: str) -> str:
        """Generate a buggy variant that should fail verification."""
        buggy = spec_content

        # Change module name
        buggy = re.sub(
            rf"MODULE {module_name}",
            f"MODULE {module_name}Buggy",
            buggy,
        )

        # Add comment about bug
        header_comment = f"""(*
 * BUGGY VARIANT of {module_name}
 *
 * This specification intentionally contains a bug to verify
 * that TLC can detect the invariant violation.
 *
 * The bug: Removed version check in update operation,
 * allowing concurrent updates to succeed (lost update).
 *)

"""
        # Insert after MODULE line
        module_match = re.search(r"(MODULE \w+.*?\n)", buggy)
        if module_match:
            pos = module_match.end()
            buggy = buggy[:pos] + header_comment + buggy[pos:]

        # Remove or comment out version check (common pattern)
        # This is a simple heuristic - might need customization
        buggy = re.sub(
            r"IF VersionMatches\([^)]+\)[^T]+THEN",
            "IF TRUE THEN  \\ BUG: Version check removed",
            buggy,
        )

        # Alternative: remove re-check in CompleteRefresh pattern
        buggy = re.sub(
            r"IF currentToken\.isRevoked",
            "IF FALSE  \\ BUG: Revocation check removed",
            buggy,
        )

        return buggy

    def _generate_readme(
        self,
        module_name: str,
        pattern: PatternTemplate,
        config: GenerationConfig,
    ) -> str:
        """Generate README for the model directory."""
        kebab_name = self._to_kebab_case(config.name)
        return f"""# {module_name}

{config.description or pattern.description}

## Pattern

Based on: `{pattern.name}` template

{pattern.use_case}

## Files

- `{module_name}.tla` - Main specification
- `{module_name}.cfg` - Standard configuration
{f"- `{module_name}_Large.cfg` - Large configuration (thorough testing)" if config.create_large_config else ""}
{f"- `{module_name}Buggy.tla` - Intentionally buggy variant" if config.create_buggy_variant else ""}

## Running Verification

```bash
# Quick simulation
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \\
    --model {kebab_name} --mode quick

# Full verification
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \\
    --model {kebab_name} --mode standard

# Thorough verification with large config
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \\
    --model {kebab_name} --mode thorough
```

## Invariants

The specification verifies these safety properties:

- **Safety** - Combined invariant checking all properties
- **TypeInvariant** - All variables have correct types

## Customization

Placeholders replaced during generation:
{self._format_placeholder_list(pattern.placeholders, config.placeholders)}

---
*Generated with TLA+ Skill*
"""

    def _format_placeholder_list(
        self,
        placeholders: list[PlaceholderInfo],
        substitutions: dict[str, str],
    ) -> str:
        """Format placeholder list for README."""
        lines = []
        for ph in placeholders:
            value = substitutions.get(ph.name, ph.default_value)
            lines.append(f"- `{{{{{ph.name}}}}}` → `{value}`: {ph.description}")
        return "\n".join(lines)

    def _to_pascal_case(self, name: str) -> str:
        """Convert name to PascalCase for module name."""
        # Handle various separators
        words = re.split(r"[-_\s]+", name)
        return "".join(word.capitalize() for word in words)

    def _to_kebab_case(self, name: str) -> str:
        """Convert name to kebab-case for directory name."""
        # Insert hyphens before uppercase letters
        s1 = re.sub(r"(.)([A-Z][a-z]+)", r"\1-\2", name)
        s2 = re.sub(r"([a-z0-9])([A-Z])", r"\1-\2", s1)
        # Replace underscores and spaces with hyphens
        return re.sub(r"[_\s]+", "-", s2).lower()

    def _find_project_root(self, start_dir: Path) -> Optional[Path]:
        """Find project root by looking for .tla-plus directory."""
        current = start_dir.resolve()
        while current != current.parent:
            if (current / ".tla-plus").exists():
                return current
            current = current.parent
        return None


def interactive_generate(generator: SpecGenerator, pattern_name: str) -> Optional[GenerationConfig]:
    """Interactively gather generation configuration."""
    pattern = generator.get_pattern(pattern_name)
    if not pattern:
        print(f"Pattern not found: {pattern_name}")
        available = generator.list_patterns()
        if available:
            print("\nAvailable patterns:")
            for p in available:
                print(f"  {p.name}: {p.description}")
        return None

    print(f"\n=== Generate TLA+ Spec from '{pattern.name}' ===")
    print(f"Description: {pattern.description}")
    print(f"Use case: {pattern.use_case}")
    print()

    # Get spec name
    name = input("Spec name (e.g., OrderProcessing): ").strip()
    if not name:
        print("Name is required")
        return None

    # Get output directory
    default_output = f"specs/tla+/{generator._to_kebab_case(name)}"
    output = input(f"Output directory [{default_output}]: ").strip() or default_output

    # Get description
    description = input("Description (optional): ").strip()

    # Get placeholder values
    print("\n--- Placeholder Values ---")
    print("(Press Enter to use default value)\n")

    placeholders = {}
    for ph in pattern.placeholders:
        prompt = f"{ph.name}"
        if ph.description:
            prompt += f" ({ph.description})"
        prompt += f" [{ph.default_value}]: "

        value = input(prompt).strip()
        if value:
            placeholders[ph.name] = value

    # Options
    print("\n--- Options ---")
    create_large = input("Create large config? [Y/n]: ").strip().lower() != "n"
    create_buggy = input("Create buggy variant? [y/N]: ").strip().lower() == "y"

    return GenerationConfig(
        pattern=pattern_name,
        name=name,
        output_dir=Path(output),
        placeholders=placeholders,
        create_large_config=create_large,
        create_buggy_variant=create_buggy,
        description=description,
    )


def main():
    """CLI for TLA+ spec generation."""
    parser = argparse.ArgumentParser(
        description="Generate TLA+ specifications from pattern templates",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # List available patterns
  %(prog)s --list

  # Interactive generation
  %(prog)s --pattern optimistic-concurrency --interactive

  # Non-interactive generation
  %(prog)s --pattern token-rotation --name SessionRefresh \\
      --output specs/tla+/session-refresh \\
      --placeholder USERS=SESSIONS

  # Generate with all options
  %(prog)s --pattern state-machine --name OrderWorkflow \\
      --output specs/tla+/order-workflow \\
      --description "Order processing state machine" \\
      --large --buggy
        """,
    )

    parser.add_argument("--list", "-l", action="store_true", help="List available patterns")
    parser.add_argument("--pattern", "-p", help="Pattern template to use")
    parser.add_argument("--name", "-n", help="Name for the generated spec")
    parser.add_argument("--output", "-o", help="Output directory")
    parser.add_argument("--description", "-d", help="Spec description")
    parser.add_argument(
        "--placeholder", "-P",
        action="append",
        default=[],
        help="Placeholder value (NAME=VALUE), can be repeated",
    )
    parser.add_argument("--large", action="store_true", help="Create large config")
    parser.add_argument("--buggy", action="store_true", help="Create buggy variant")
    parser.add_argument("--no-register", action="store_true", help="Don't register with TLAStore")
    parser.add_argument("--interactive", "-i", action="store_true", help="Interactive mode")
    parser.add_argument(
        "--skill-dir",
        help="Path to tla-plus skill directory (default: ~/.claude/skills/tla-plus)",
    )
    parser.add_argument("--json", action="store_true", help="Output result as JSON")

    args = parser.parse_args()

    skill_dir = Path(args.skill_dir) if args.skill_dir else None
    generator = SpecGenerator(skill_dir)

    # List patterns
    if args.list:
        patterns = generator.list_patterns()
        if not patterns:
            print("No patterns found.")
            print(f"Check templates directory: {generator.templates_dir}")
            return

        if args.json:
            output = [{"name": p.name, "description": p.description, "use_case": p.use_case}
                      for p in patterns]
            print(json.dumps(output, indent=2))
        else:
            print("Available patterns:\n")
            for p in patterns:
                print(f"  {p.name}")
                print(f"    {p.description}")
                if p.use_case:
                    print(f"    Use case: {p.use_case}")
                if p.placeholders:
                    phs = ", ".join(ph.name for ph in p.placeholders[:5])
                    if len(p.placeholders) > 5:
                        phs += f", ... (+{len(p.placeholders) - 5} more)"
                    print(f"    Placeholders: {phs}")
                print()
        return

    # Interactive mode
    if args.interactive:
        if not args.pattern:
            # Show patterns and ask to select
            patterns = generator.list_patterns()
            if not patterns:
                print("No patterns found.")
                return

            print("Available patterns:")
            for i, p in enumerate(patterns, 1):
                print(f"  {i}. {p.name}: {p.description}")

            try:
                choice = int(input("\nSelect pattern (number): ")) - 1
                if 0 <= choice < len(patterns):
                    args.pattern = patterns[choice].name
                else:
                    print("Invalid selection")
                    return
            except ValueError:
                print("Invalid input")
                return

        config = interactive_generate(generator, args.pattern)
        if not config:
            return

    else:
        # Non-interactive mode - require all arguments
        if not args.pattern:
            parser.error("--pattern is required (use --interactive for guided mode)")

        if not args.name:
            parser.error("--name is required (use --interactive for guided mode)")

        if not args.output:
            # Default output based on name
            args.output = f"specs/tla+/{generator._to_kebab_case(args.name)}"

        # Parse placeholder arguments
        placeholders = {}
        for p in args.placeholder:
            if "=" in p:
                key, value = p.split("=", 1)
                placeholders[key] = value

        config = GenerationConfig(
            pattern=args.pattern,
            name=args.name,
            output_dir=Path(args.output),
            placeholders=placeholders,
            create_large_config=args.large,
            create_buggy_variant=args.buggy,
            register_with_store=not args.no_register,
            description=args.description or "",
        )

    # Generate spec
    result = generator.generate(config)

    if args.json:
        output = {
            "success": result.success,
            "message": result.message,
            "model_name": result.model_name,
            "spec_file": str(result.spec_file) if result.spec_file else None,
            "config_files": [str(f) for f in result.config_files],
            "buggy_file": str(result.buggy_file) if result.buggy_file else None,
        }
        print(json.dumps(output, indent=2))
    else:
        if result.success:
            print(f"\n✅ {result.message}")
            print(f"\nGenerated files:")
            print(f"  Spec: {result.spec_file}")
            for cfg in result.config_files:
                print(f"  Config: {cfg}")
            if result.buggy_file:
                print(f"  Buggy: {result.buggy_file}")
            print(f"\nModel name: {result.model_name}")
            print(f"\nRun verification:")
            print(f"  python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \\")
            print(f"      --model {result.model_name} --mode quick")
        else:
            print(f"\n❌ {result.message}")
            sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Generate Tests from TLA+ Specifications.

This module generates unit and integration tests from TLA+ specifications:
- Parse spec invariants and translate to test assertions
- Generate test scenarios from actions
- Map TLA+ variables to code entities
- Support multiple languages (C#, Java, Python, TypeScript)
- Integration with xUnit, NUnit, JUnit, pytest patterns
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional

from tla_store import TLAStore, ModelMapping


class Language(str, Enum):
    """Target test languages."""

    CSHARP = "csharp"
    JAVA = "java"
    PYTHON = "python"
    TYPESCRIPT = "typescript"


class TestFramework(str, Enum):
    """Test frameworks."""

    XUNIT = "xunit"
    NUNIT = "nunit"
    MSTEST = "mstest"
    JUNIT = "junit"
    PYTEST = "pytest"
    JEST = "jest"
    MOCHA = "mocha"


@dataclass
class ParsedInvariant:
    """A parsed TLA+ invariant."""

    name: str
    formula: str
    description: str
    variables: list[str]
    operators: list[str]
    is_type_invariant: bool = False


@dataclass
class ParsedAction:
    """A parsed TLA+ action."""

    name: str
    precondition: str
    effect: str
    parameters: list[str]
    primed_variables: list[str]
    description: str = ""


@dataclass
class TestCase:
    """A generated test case."""

    name: str
    description: str
    arrange: list[str]
    act: list[str]
    assertion: list[str]
    source_invariant: Optional[str] = None
    source_action: Optional[str] = None
    is_negative: bool = False


@dataclass
class GeneratedTestFile:
    """A generated test file."""

    file_name: str
    content: str
    test_count: int
    language: Language
    framework: TestFramework


class SpecParser:
    """Parses TLA+ specification files."""

    def __init__(self):
        self.variables: list[str] = []
        self.constants: list[str] = []
        self.invariants: list[ParsedInvariant] = []
        self.actions: list[ParsedAction] = []

    def parse(self, spec_file: Path) -> None:
        """Parse a TLA+ specification file."""
        content = spec_file.read_text()

        self._extract_variables(content)
        self._extract_constants(content)
        self._extract_invariants(content)
        self._extract_actions(content)

    def _extract_variables(self, content: str) -> None:
        """Extract VARIABLES declaration."""
        match = re.search(r"VARIABLES\s*\n\s*(.+?)(?=\n\n|\nvar)", content, re.DOTALL)
        if match:
            vars_text = match.group(1)
            # Handle both comma-separated and line-separated
            self.variables = [
                v.strip().rstrip(",")
                for v in re.split(r"[,\n]", vars_text)
                if v.strip() and not v.strip().startswith("\\*")
            ]

    def _extract_constants(self, content: str) -> None:
        """Extract CONSTANTS declaration."""
        match = re.search(r"CONSTANTS\s*\n(.+?)(?=\nVARIABLES|\n\\*)", content, re.DOTALL)
        if match:
            consts_text = match.group(1)
            self.constants = [
                c.strip().split()[0]  # Get just the name, not the comment
                for c in consts_text.strip().split("\n")
                if c.strip() and not c.strip().startswith("\\*")
            ]

    def _extract_invariants(self, content: str) -> None:
        """Extract invariant definitions."""
        # Match pattern: InvariantName == \n    formula
        inv_pattern = r"(\w+)\s*==\s*\n((?:\s+.+\n?)+)"

        # Find sections that look like invariants (after Safety Properties comment or contain Invariant in name)
        sections = re.split(r"\\* -----", content)

        for section in sections:
            if "Safety" in section or "Invariant" in section:
                for match in re.finditer(inv_pattern, section):
                    name = match.group(1)
                    formula = match.group(2).strip()

                    # Skip if it looks like an action (has primed variables)
                    if "'" in formula and "/\\" in formula:
                        continue

                    # Determine if it's a type invariant
                    is_type = "TypeInvariant" in name or "\\in" in formula

                    # Extract variables used
                    vars_used = [v for v in self.variables if v in formula]

                    # Extract operators
                    operators = re.findall(r"\\[A-Z]|~|=>|<=>|/\\\\|\\\\\/", formula)

                    # Get description from comment above
                    desc_match = re.search(rf"\\*\s*(.+?)\n\s*{name}\s*==", section)
                    description = desc_match.group(1).strip() if desc_match else ""

                    self.invariants.append(ParsedInvariant(
                        name=name,
                        formula=formula,
                        description=description,
                        variables=vars_used,
                        operators=operators,
                        is_type_invariant=is_type,
                    ))

    def _extract_actions(self, content: str) -> None:
        """Extract action definitions."""
        # Actions have primed variables (var')
        action_pattern = r"(\w+)(?:\([^)]*\))?\s*==\s*\n((?:\s+.+\n?)+)"

        for match in re.finditer(action_pattern, content):
            name = match.group(1)
            body = match.group(2).strip()

            # Skip if not an action (no primed variables)
            if "'" not in body:
                continue

            # Skip Next, Init, Spec
            if name in ["Next", "Init", "Spec", "Fairness", "vars"]:
                continue

            # Extract precondition (lines before any prime)
            lines = body.split("\n")
            pre_lines = []
            post_lines = []
            seen_prime = False

            for line in lines:
                line = line.strip()
                if not line or line.startswith("\\*"):
                    continue
                if "'" in line:
                    seen_prime = True
                if seen_prime:
                    post_lines.append(line)
                else:
                    pre_lines.append(line)

            precondition = " /\\ ".join(pre_lines) if pre_lines else "TRUE"
            effect = " /\\ ".join(post_lines) if post_lines else "UNCHANGED vars"

            # Extract primed variables
            primed = re.findall(r"(\w+)'", body)

            # Check for parameters
            params_match = re.search(rf"{name}\s*\(([^)]+)\)", content)
            parameters = []
            if params_match:
                parameters = [p.strip() for p in params_match.group(1).split(",")]

            # Get description
            desc_match = re.search(rf"\\*\s*(.+?)\n(?:\\*.*\n)*\s*{name}", content)
            description = desc_match.group(1).strip() if desc_match else ""

            self.actions.append(ParsedAction(
                name=name,
                precondition=precondition,
                effect=effect,
                parameters=parameters,
                primed_variables=list(set(primed)),
                description=description,
            ))


class TestGenerator:
    """Generates tests from parsed TLA+ specifications."""

    FRAMEWORK_DEFAULTS = {
        Language.CSHARP: TestFramework.XUNIT,
        Language.JAVA: TestFramework.JUNIT,
        Language.PYTHON: TestFramework.PYTEST,
        Language.TYPESCRIPT: TestFramework.JEST,
    }

    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)
        self.store = TLAStore(self.project_root)

    def generate(
        self,
        model: str,
        language: Language = Language.CSHARP,
        framework: Optional[TestFramework] = None,
        output_file: Optional[Path] = None,
        include_negative: bool = True,
    ) -> GeneratedTestFile:
        """
        Generate tests from a TLA+ model.

        Args:
            model: Model name
            language: Target language
            framework: Test framework (defaults based on language)
            output_file: Output file path
            include_negative: Include negative test cases

        Returns:
            GeneratedTestFile with generated content
        """
        # Find spec file
        specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"
        model_dir = specs_dir / model

        if not model_dir.exists():
            raise FileNotFoundError(f"Model directory not found: {model_dir}")

        # Find main spec file
        tla_files = [f for f in model_dir.glob("*.tla") if not any(x in f.stem for x in ["Race", "Buggy"])]
        if not tla_files:
            raise FileNotFoundError(f"No .tla file found in {model_dir}")

        spec_file = tla_files[0]

        # Parse spec
        parser = SpecParser()
        parser.parse(spec_file)

        # Get mappings
        mapping = self.store.get_model_mapping(model) if self.store.is_initialized() else None

        # Determine framework
        if framework is None:
            framework = self.FRAMEWORK_DEFAULTS[language]

        # Generate test cases
        test_cases = []

        # Generate invariant tests
        for inv in parser.invariants:
            if inv.is_type_invariant:
                continue  # Skip type invariants for now

            test_cases.extend(self._generate_invariant_tests(inv, mapping, include_negative))

        # Generate action tests
        for action in parser.actions:
            test_cases.extend(self._generate_action_tests(action, mapping))

        # Generate test file
        content = self._render_test_file(
            test_cases=test_cases,
            model=model,
            spec_file=spec_file,
            language=language,
            framework=framework,
            mapping=mapping,
        )

        # Determine output file name
        if output_file:
            file_name = output_file.name
        else:
            class_name = self._to_pascal_case(model)
            ext = self._get_extension(language)
            file_name = f"{class_name}.Invariants.Tests{ext}"

        return GeneratedTestFile(
            file_name=file_name,
            content=content,
            test_count=len(test_cases),
            language=language,
            framework=framework,
        )

    def _generate_invariant_tests(
        self,
        inv: ParsedInvariant,
        mapping: Optional[ModelMapping],
        include_negative: bool,
    ) -> list[TestCase]:
        """Generate test cases for an invariant."""
        tests = []

        # Positive test: invariant should hold
        test_name = f"Test_{inv.name}_Holds"
        description = f"Verify that {inv.name} holds: {inv.description}"

        # Generate arrange/act/assert based on formula
        arrange, act, assertion = self._translate_invariant(inv, mapping)

        tests.append(TestCase(
            name=test_name,
            description=description,
            arrange=arrange,
            act=act,
            assertion=assertion,
            source_invariant=inv.name,
        ))

        # Negative test: invariant violation should be detectable
        if include_negative:
            neg_name = f"Test_{inv.name}_DetectsViolation"
            neg_desc = f"Verify that {inv.name} violations are detectable"
            neg_arrange, neg_act, neg_assert = self._translate_invariant_negative(inv, mapping)

            tests.append(TestCase(
                name=neg_name,
                description=neg_desc,
                arrange=neg_arrange,
                act=neg_act,
                assertion=neg_assert,
                source_invariant=inv.name,
                is_negative=True,
            ))

        return tests

    def _generate_action_tests(
        self,
        action: ParsedAction,
        mapping: Optional[ModelMapping],
    ) -> list[TestCase]:
        """Generate test cases for an action."""
        tests = []

        # Test precondition
        pre_name = f"Test_{action.name}_RequiresPrecondition"
        pre_desc = f"Verify that {action.name} requires its precondition"

        pre_arrange = [f"// Setup state that violates precondition"]
        pre_act = [f"// Attempt to execute {action.name}"]
        pre_assert = [f"// Should throw or return error"]

        # Map to actual code if we have mappings
        if mapping and action.name in mapping.actions:
            action_map = mapping.actions[action.name]
            pre_act = [f"// Call {action_map.method} at {action_map.code_file}:{action_map.line}"]

        tests.append(TestCase(
            name=pre_name,
            description=pre_desc,
            arrange=pre_arrange,
            act=pre_act,
            assertion=pre_assert,
            source_action=action.name,
        ))

        # Test effect
        effect_name = f"Test_{action.name}_ProducesEffect"
        effect_desc = f"Verify that {action.name} produces expected state change"

        eff_arrange = [f"// Setup valid initial state"]
        eff_act = [f"// Execute {action.name}"]
        eff_assert = []

        for var in action.primed_variables:
            eff_assert.append(f"// Assert {var} changed correctly")

        tests.append(TestCase(
            name=effect_name,
            description=effect_desc,
            arrange=eff_arrange,
            act=eff_act,
            assertion=eff_assert,
            source_action=action.name,
        ))

        return tests

    def _translate_invariant(
        self,
        inv: ParsedInvariant,
        mapping: Optional[ModelMapping],
    ) -> tuple[list[str], list[str], list[str]]:
        """Translate invariant to test code."""
        arrange = ["// Arrange: Setup valid state"]
        act = ["// Act: Perform operations"]
        assertion = []

        formula = inv.formula

        # Translate common TLA+ patterns to assertions
        if "\\A" in formula:
            # Universal quantifier -> foreach assertion
            match = re.search(r"\\A\s+(\w+)\s+\\in\s+(\w+)\s*:\s*(.+)", formula)
            if match:
                var, collection, predicate = match.groups()
                assertion.append(f"// For all {var} in {collection}:")
                assertion.append(f"// Assert: {predicate.strip()}")

        elif "\\E" in formula:
            # Existential quantifier -> any assertion
            match = re.search(r"\\E\s+(\w+)\s+\\in\s+(\w+)\s*:\s*(.+)", formula)
            if match:
                var, collection, predicate = match.groups()
                assertion.append(f"// There exists {var} in {collection} such that:")
                assertion.append(f"// Assert: {predicate.strip()}")

        elif "=>" in formula:
            # Implication -> conditional assertion
            parts = formula.split("=>")
            if len(parts) == 2:
                condition, consequent = parts
                assertion.append(f"// If {condition.strip()}")
                assertion.append(f"// Then {consequent.strip()}")

        elif "Cardinality" in formula:
            # Cardinality constraint
            match = re.search(r"Cardinality\((\w+)\)\s*([<>=]+)\s*(\d+)", formula)
            if match:
                collection, op, value = match.groups()
                assertion.append(f"Assert.True({collection}.Count {op} {value});")

        else:
            # Default: translate formula as-is
            assertion.append(f"// Assert: {formula}")

        # Map to actual code
        if mapping:
            for var_name in inv.variables:
                if var_name in mapping.variables:
                    var_map = mapping.variables[var_name]
                    if var_map.table:
                        arrange.append(f"// Map: {var_name} -> {var_map.table}.{var_map.column}")

        return arrange, act, assertion

    def _translate_invariant_negative(
        self,
        inv: ParsedInvariant,
        mapping: Optional[ModelMapping],
    ) -> tuple[list[str], list[str], list[str]]:
        """Generate negative test for invariant."""
        arrange = ["// Arrange: Setup state that would violate invariant"]
        act = ["// Act: Attempt operation that should fail"]
        assertion = [
            "// Assert: Operation should fail with appropriate error",
            "// or validation should prevent the violation",
        ]

        return arrange, act, assertion

    def _render_test_file(
        self,
        test_cases: list[TestCase],
        model: str,
        spec_file: Path,
        language: Language,
        framework: TestFramework,
        mapping: Optional[ModelMapping],
    ) -> str:
        """Render the complete test file."""
        if language == Language.CSHARP:
            return self._render_csharp(test_cases, model, spec_file, framework, mapping)
        elif language == Language.JAVA:
            return self._render_java(test_cases, model, spec_file, framework, mapping)
        elif language == Language.PYTHON:
            return self._render_python(test_cases, model, spec_file, framework, mapping)
        elif language == Language.TYPESCRIPT:
            return self._render_typescript(test_cases, model, spec_file, framework, mapping)
        else:
            raise ValueError(f"Unsupported language: {language}")

    def _render_csharp(
        self,
        test_cases: list[TestCase],
        model: str,
        spec_file: Path,
        framework: TestFramework,
        mapping: Optional[ModelMapping],
    ) -> str:
        """Render C# test file."""
        class_name = f"{self._to_pascal_case(model)}InvariantTests"
        lines = []

        # Usings
        if framework == TestFramework.XUNIT:
            lines.append("using Xunit;")
        elif framework == TestFramework.NUNIT:
            lines.append("using NUnit.Framework;")
        elif framework == TestFramework.MSTEST:
            lines.append("using Microsoft.VisualStudio.TestTools.UnitTesting;")

        lines.append("using FluentAssertions;")
        lines.append("")

        # Namespace
        lines.append("namespace XTConnect.Tests.Invariants;")
        lines.append("")

        # Summary
        lines.append("/// <summary>")
        lines.append(f"/// Tests derived from TLA+ specification: {spec_file.name}")
        lines.append(f"/// Generated: {datetime.now().isoformat()}")
        lines.append("/// </summary>")

        # Class attributes
        if framework == TestFramework.NUNIT:
            lines.append("[TestFixture]")
        elif framework == TestFramework.MSTEST:
            lines.append("[TestClass]")

        lines.append(f"public class {class_name}")
        lines.append("{")

        # Test methods
        for tc in test_cases:
            lines.append("")
            lines.append(f"    /// <summary>")
            lines.append(f"    /// {tc.description}")
            if tc.source_invariant:
                lines.append(f"    /// Source: Invariant {tc.source_invariant}")
            if tc.source_action:
                lines.append(f"    /// Source: Action {tc.source_action}")
            lines.append(f"    /// </summary>")

            # Test attribute
            if framework == TestFramework.XUNIT:
                lines.append("    [Fact]")
            elif framework == TestFramework.NUNIT:
                lines.append("    [Test]")
            elif framework == TestFramework.MSTEST:
                lines.append("    [TestMethod]")

            lines.append(f"    public void {tc.name}()")
            lines.append("    {")

            # Arrange
            for line in tc.arrange:
                lines.append(f"        {line}")
            lines.append("")

            # Act
            for line in tc.act:
                lines.append(f"        {line}")
            lines.append("")

            # Assert
            for line in tc.assertion:
                lines.append(f"        {line}")

            lines.append("    }")

        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    def _render_java(
        self,
        test_cases: list[TestCase],
        model: str,
        spec_file: Path,
        framework: TestFramework,
        mapping: Optional[ModelMapping],
    ) -> str:
        """Render Java test file."""
        class_name = f"{self._to_pascal_case(model)}InvariantTests"
        lines = []

        # Package
        lines.append("package com.xtconnect.tests.invariants;")
        lines.append("")

        # Imports
        lines.append("import org.junit.jupiter.api.Test;")
        lines.append("import static org.junit.jupiter.api.Assertions.*;")
        lines.append("import static org.assertj.core.api.Assertions.*;")
        lines.append("")

        # Class
        lines.append("/**")
        lines.append(f" * Tests derived from TLA+ specification: {spec_file.name}")
        lines.append(f" * Generated: {datetime.now().isoformat()}")
        lines.append(" */")
        lines.append(f"public class {class_name} {{")

        for tc in test_cases:
            lines.append("")
            lines.append("    /**")
            lines.append(f"     * {tc.description}")
            lines.append("     */")
            lines.append("    @Test")
            lines.append(f"    void {self._to_camel_case(tc.name)}() {{")

            for line in tc.arrange:
                lines.append(f"        {line}")
            lines.append("")
            for line in tc.act:
                lines.append(f"        {line}")
            lines.append("")
            for line in tc.assertion:
                lines.append(f"        {line}")

            lines.append("    }")

        lines.append("}")
        lines.append("")

        return "\n".join(lines)

    def _render_python(
        self,
        test_cases: list[TestCase],
        model: str,
        spec_file: Path,
        framework: TestFramework,
        mapping: Optional[ModelMapping],
    ) -> str:
        """Render Python test file."""
        lines = []

        # Docstring
        lines.append('"""')
        lines.append(f"Tests derived from TLA+ specification: {spec_file.name}")
        lines.append(f"Generated: {datetime.now().isoformat()}")
        lines.append('"""')
        lines.append("")

        # Imports
        lines.append("import pytest")
        lines.append("")

        # Module docstring
        slug = model.replace("-", "_")
        lines.append(f"class Test{self._to_pascal_case(model)}Invariants:")
        lines.append(f'    """Invariant tests for {model}."""')
        lines.append("")

        for tc in test_cases:
            test_name = self._to_snake_case(tc.name)
            lines.append(f"    def {test_name}(self):")
            lines.append(f'        """')
            lines.append(f"        {tc.description}")
            if tc.source_invariant:
                lines.append(f"        Source: Invariant {tc.source_invariant}")
            lines.append(f'        """')

            for line in tc.arrange:
                lines.append(f"        {line.replace('//', '#')}")
            lines.append("")
            for line in tc.act:
                lines.append(f"        {line.replace('//', '#')}")
            lines.append("")
            for line in tc.assertion:
                lines.append(f"        {line.replace('//', '#')}")
            lines.append("        pass  # TODO: Implement")
            lines.append("")

        return "\n".join(lines)

    def _render_typescript(
        self,
        test_cases: list[TestCase],
        model: str,
        spec_file: Path,
        framework: TestFramework,
        mapping: Optional[ModelMapping],
    ) -> str:
        """Render TypeScript test file."""
        lines = []

        # Imports
        if framework == TestFramework.JEST:
            lines.append("import { describe, it, expect, beforeEach } from '@jest/globals';")
        else:  # Mocha
            lines.append("import { describe, it, beforeEach } from 'mocha';")
            lines.append("import { expect } from 'chai';")
        lines.append("")

        # Comment
        lines.append("/**")
        lines.append(f" * Tests derived from TLA+ specification: {spec_file.name}")
        lines.append(f" * Generated: {datetime.now().isoformat()}")
        lines.append(" */")
        lines.append("")

        # Describe block
        lines.append(f"describe('{self._to_pascal_case(model)} Invariants', () => {{")

        for tc in test_cases:
            lines.append("")
            lines.append(f"  /**")
            lines.append(f"   * {tc.description}")
            lines.append(f"   */")
            lines.append(f"  it('{tc.name}', () => {{")

            for line in tc.arrange:
                lines.append(f"    {line}")
            lines.append("")
            for line in tc.act:
                lines.append(f"    {line}")
            lines.append("")
            for line in tc.assertion:
                lines.append(f"    {line}")

            lines.append("  });")

        lines.append("});")
        lines.append("")

        return "\n".join(lines)

    def _to_pascal_case(self, name: str) -> str:
        """Convert to PascalCase."""
        words = re.split(r"[-_\s]", name)
        return "".join(word.capitalize() for word in words)

    def _to_camel_case(self, name: str) -> str:
        """Convert to camelCase."""
        pascal = self._to_pascal_case(name)
        return pascal[0].lower() + pascal[1:] if pascal else ""

    def _to_snake_case(self, name: str) -> str:
        """Convert to snake_case."""
        # Insert underscore before uppercase letters
        s1 = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1_\2", name)
        s2 = re.sub(r"([a-z\d])([A-Z])", r"\1_\2", s1)
        return s2.replace("-", "_").lower()

    def _get_extension(self, language: Language) -> str:
        """Get file extension for language."""
        extensions = {
            Language.CSHARP: ".cs",
            Language.JAVA: ".java",
            Language.PYTHON: ".py",
            Language.TYPESCRIPT: ".ts",
        }
        return extensions[language]


def main():
    """CLI for generating tests from TLA+ specs."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate Tests from TLA+ Specifications",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --model node-registration --language csharp
  %(prog)s --model token-refresh --language python --framework pytest
  %(prog)s --model order-locking --language java --output tests/OrderLockingTests.java
  %(prog)s --model all --language csharp
        """,
    )

    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    parser.add_argument("--model", "-m", help="Model name or 'all'")
    parser.add_argument(
        "--language", "-l",
        choices=["csharp", "java", "python", "typescript"],
        default="csharp",
        help="Target language (default: csharp)",
    )
    parser.add_argument(
        "--framework", "-f",
        choices=["xunit", "nunit", "mstest", "junit", "pytest", "jest", "mocha"],
        help="Test framework (default: based on language)",
    )
    parser.add_argument("--output", "-o", help="Output file path")
    parser.add_argument("--no-negative", action="store_true", help="Don't include negative tests")
    parser.add_argument("--dry-run", action="store_true", help="Print to stdout instead of writing")
    parser.add_argument("--list", action="store_true", help="List available models")

    args = parser.parse_args()

    generator = TestGenerator(args.project)

    if args.list:
        store = TLAStore(args.project)
        if store.is_initialized():
            models = store.list_models()
            if models:
                print("Available models:")
                for m in models:
                    print(f"  {m.name}: {m.description}")
            else:
                print("No models registered.")
        else:
            # Fallback: list from specs directory
            specs_dir = Path(args.project) / "specs" / "tla+"
            if specs_dir.exists():
                models = [d.name for d in specs_dir.iterdir()
                          if d.is_dir() and not d.name.startswith(".") and d.name != "common"]
                if models:
                    print("Available models:")
                    for m in sorted(models):
                        print(f"  {m}")
                else:
                    print("No models found.")
            else:
                print("No specs/tla+ directory found.")
        return

    if not args.model:
        parser.error("--model is required (use --list to see available models)")

    language = Language(args.language)
    framework = TestFramework(args.framework) if args.framework else None
    output_path = Path(args.output) if args.output else None

    # Generate tests
    try:
        result = generator.generate(
            model=args.model,
            language=language,
            framework=framework,
            output_file=output_path,
            include_negative=not args.no_negative,
        )

        if args.dry_run:
            print(result.content)
        else:
            # Write to file
            if output_path:
                output_path.write_text(result.content)
                print(f"Generated {result.test_count} tests -> {output_path}")
            else:
                # Default output path
                default_path = Path(result.file_name)
                default_path.write_text(result.content)
                print(f"Generated {result.test_count} tests -> {default_path}")

    except FileNotFoundError as e:
        print(f"Error: {e}")
        return 1


if __name__ == "__main__":
    main()

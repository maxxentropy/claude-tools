#!/usr/bin/env python3
"""
Generate TLA+ Specifications from Source Code - LLM-Assisted Extraction.

This module provides functions to generate TLA+ specifications from source code,
inspired by the Specula tool that won the TLAi+ Challenge 2025.

Key features:
- Control flow analysis to identify state transitions
- LLM-assisted extraction of state variables and invariants
- Interactive refinement mode
- Code-to-spec mapping generation
- Multiple language support (C#, Java, Python, TypeScript, Go)
"""

from __future__ import annotations

import json
import re
import sys
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional

from tla_store import TLAStore


class Language(str, Enum):
    """Supported programming languages."""

    CSHARP = "csharp"
    JAVA = "java"
    PYTHON = "python"
    TYPESCRIPT = "typescript"
    GO = "go"


class ConcernType(str, Enum):
    """Types of concurrency concerns to analyze."""

    RACE_CONDITION = "race-condition"
    DEADLOCK = "deadlock"
    LOST_UPDATE = "lost-update"
    STARVATION = "starvation"
    ATOMICITY = "atomicity"
    ORDERING = "ordering"
    GENERAL = "general"


@dataclass
class StateVariable:
    """A state variable extracted from code."""

    name: str
    tla_name: str
    type_hint: str
    initial_value: str
    source_location: str
    description: str = ""


@dataclass
class Action:
    """An action (state transition) extracted from code."""

    name: str
    tla_name: str
    precondition: str
    effect: str
    source_method: str
    source_file: str
    source_line: int
    description: str = ""
    parameters: list[str] = field(default_factory=list)


@dataclass
class Invariant:
    """An invariant (safety property) inferred from code."""

    name: str
    formula: str
    description: str
    source: str  # How it was inferred
    confidence: float = 1.0  # 0.0-1.0 confidence score


@dataclass
class TemporalProperty:
    """A temporal (liveness) property inferred from code."""

    name: str
    formula: str
    description: str
    property_type: str  # "eventually", "always_eventually", "leads_to"


@dataclass
class ExtractedSpec:
    """Complete specification extracted from code."""

    module_name: str
    description: str
    constants: dict[str, str]
    variables: list[StateVariable]
    actions: list[Action]
    invariants: list[Invariant]
    temporal_properties: list[TemporalProperty]
    source_files: list[str]
    concern: ConcernType
    warnings: list[str] = field(default_factory=list)

    def to_tla(self) -> str:
        """Generate TLA+ specification."""
        lines = []

        # Header
        separator = "-" * (26 + len(self.module_name))
        lines.append(f"{separator} MODULE {self.module_name} {separator}")
        lines.append("(*")
        lines.append(f" * {self.description}")
        lines.append(" *")
        lines.append(" * Generated from source code analysis.")
        lines.append(f" * Concern: {self.concern.value}")
        lines.append(" *")
        lines.append(" * Source files:")
        for f in self.source_files:
            lines.append(f" *   - {f}")
        lines.append(" *)")
        lines.append("")
        lines.append("EXTENDS Naturals, Sequences, FiniteSets, TLC")
        lines.append("")

        # Constants
        if self.constants:
            lines.append("CONSTANTS")
            for const_name, const_desc in self.constants.items():
                lines.append(f"    {const_name}  \\* {const_desc}")
            lines.append("")

        # Variables
        lines.append("VARIABLES")
        var_names = [v.tla_name for v in self.variables]
        lines.append(f"    {', '.join(var_names)}")
        lines.append("")

        lines.append("vars == <<" + ", ".join(var_names) + ">>")
        lines.append("")

        # Type invariant
        lines.append("\\* ----- Type Invariant -----")
        lines.append("TypeInvariant ==")
        for i, v in enumerate(self.variables):
            prefix = "    /\\ " if i == 0 else "    /\\ "
            lines.append(f"{prefix}{v.tla_name} \\in {v.type_hint}  \\* {v.description}")
        lines.append("")

        # Init
        lines.append("\\* ----- Initial State -----")
        lines.append("Init ==")
        for i, v in enumerate(self.variables):
            prefix = "    /\\ " if i == 0 else "    /\\ "
            lines.append(f"{prefix}{v.tla_name} = {v.initial_value}")
        lines.append("")

        # Actions
        lines.append("\\* ----- Actions -----")
        for action in self.actions:
            lines.append(f"\\* {action.description}")
            lines.append(f"\\* Source: {action.source_file}:{action.source_line} - {action.source_method}")
            params = f"({', '.join(action.parameters)})" if action.parameters else ""
            lines.append(f"{action.tla_name}{params} ==")
            lines.append(f"    /\\ {action.precondition}")
            lines.append(f"    /\\ {action.effect}")
            lines.append("")

        # Next state relation
        lines.append("\\* ----- Next State -----")
        lines.append("Next ==")
        action_names = []
        for a in self.actions:
            if a.parameters:
                action_names.append(f"\\E p \\in PARAMS: {a.tla_name}(p)")
            else:
                action_names.append(a.tla_name)
        lines.append("    \\/ " + "\n    \\/ ".join(action_names))
        lines.append("")

        # Fairness
        lines.append("\\* ----- Fairness -----")
        lines.append("Fairness ==")
        for a in self.actions:
            lines.append(f"    /\\ WF_vars({a.tla_name})")
        lines.append("")

        # Spec
        lines.append("\\* ----- Specification -----")
        lines.append("Spec == Init /\\ [][Next]_vars /\\ Fairness")
        lines.append("")

        # Invariants
        lines.append("\\* ----- Safety Properties (Invariants) -----")
        for inv in self.invariants:
            confidence_note = f" (confidence: {inv.confidence:.0%})" if inv.confidence < 1.0 else ""
            lines.append(f"\\* {inv.description}{confidence_note}")
            lines.append(f"\\* Inferred from: {inv.source}")
            lines.append(f"{inv.name} ==")
            lines.append(f"    {inv.formula}")
            lines.append("")

        # Temporal properties
        if self.temporal_properties:
            lines.append("\\* ----- Liveness Properties -----")
            for prop in self.temporal_properties:
                lines.append(f"\\* {prop.description}")
                lines.append(f"{prop.name} ==")
                lines.append(f"    {prop.formula}")
                lines.append("")

        # Footer
        lines.append("=" * 77)
        lines.append("")

        return "\n".join(lines)

    def to_cfg(self) -> str:
        """Generate TLC configuration file."""
        lines = []
        lines.append(f"\\* Configuration for {self.module_name}")
        lines.append("")

        if self.constants:
            lines.append("CONSTANTS")
            for const_name in self.constants:
                lines.append(f"    {const_name} = {const_name}")
            lines.append("")

        lines.append("INIT Init")
        lines.append("NEXT Next")
        lines.append("")

        lines.append("INVARIANTS")
        lines.append("    TypeInvariant")
        for inv in self.invariants:
            lines.append(f"    {inv.name}")
        lines.append("")

        if self.temporal_properties:
            lines.append("PROPERTIES")
            for prop in self.temporal_properties:
                lines.append(f"    {prop.name}")
            lines.append("")

        return "\n".join(lines)


class CodeAnalyzer:
    """Analyzes source code to extract specification elements."""

    LANGUAGE_EXTENSIONS = {
        ".cs": Language.CSHARP,
        ".java": Language.JAVA,
        ".py": Language.PYTHON,
        ".ts": Language.TYPESCRIPT,
        ".tsx": Language.TYPESCRIPT,
        ".go": Language.GO,
    }

    # Patterns for different concerns
    CONCERN_PATTERNS = {
        ConcernType.RACE_CONDITION: [
            r"lock\s*\(",
            r"synchronized",
            r"Interlocked\.",
            r"async\s+",
            r"await\s+",
            r"Task\.",
            r"Thread\.",
            r"mutex",
            r"semaphore",
        ],
        ConcernType.DEADLOCK: [
            r"lock\s*\(",
            r"Monitor\.",
            r"Mutex\.",
            r"Semaphore",
            r"Wait\(",
            r"WaitAll",
        ],
        ConcernType.LOST_UPDATE: [
            r"UPDATE\s+",
            r"SaveChanges",
            r"\.Update\(",
            r"version",
            r"etag",
            r"optimistic",
        ],
        ConcernType.ATOMICITY: [
            r"transaction",
            r"atomic",
            r"CompareExchange",
            r"CAS\(",
        ],
    }

    # State-indicating patterns
    STATE_PATTERNS = {
        "status": r"(status|state|phase)\s*[=:]",
        "counter": r"(count|counter|total|num)\s*[=:]",
        "flag": r"(is\w+|has\w+|can\w+)\s*[=:]",
        "collection": r"(list|set|dict|map|queue|stack)\s*[=:]",
        "id": r"(\w+Id|id)\s*[=:]",
    }

    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)

    def detect_language(self, file_path: Path) -> Language:
        """Detect programming language from file extension."""
        ext = file_path.suffix.lower()
        return self.LANGUAGE_EXTENSIONS.get(ext, Language.CSHARP)

    def analyze_file(
        self,
        file_path: Path,
        method: Optional[str] = None,
        concern: ConcernType = ConcernType.GENERAL,
    ) -> ExtractedSpec:
        """Analyze a source file and extract specification elements."""
        file_path = Path(file_path)
        if not file_path.is_absolute():
            file_path = self.project_root / file_path

        if not file_path.exists():
            raise FileNotFoundError(f"Source file not found: {file_path}")

        content = file_path.read_text()
        language = self.detect_language(file_path)

        # Extract module name from file
        module_name = self._derive_module_name(file_path, method)

        # Auto-detect concern if general
        if concern == ConcernType.GENERAL:
            concern = self._detect_concern(content)

        # Extract elements based on language
        variables = self._extract_variables(content, language, file_path)
        actions = self._extract_actions(content, language, file_path, method)
        invariants = self._infer_invariants(content, language, concern, variables)
        temporal = self._infer_temporal_properties(content, language, concern)
        constants = self._extract_constants(content, language)

        return ExtractedSpec(
            module_name=module_name,
            description=f"Specification for {file_path.name}" + (f".{method}" if method else ""),
            constants=constants,
            variables=variables,
            actions=actions,
            invariants=invariants,
            temporal_properties=temporal,
            source_files=[str(file_path.relative_to(self.project_root))],
            concern=concern,
            warnings=self._generate_warnings(variables, actions, invariants),
        )

    def _derive_module_name(self, file_path: Path, method: Optional[str]) -> str:
        """Derive TLA+ module name from file/method."""
        base = file_path.stem
        # Remove common suffixes
        for suffix in ["Handler", "Service", "Controller", "Manager", "Repository"]:
            if base.endswith(suffix):
                base = base[:-len(suffix)]
                break
        if method:
            base = f"{base}_{method}"
        # Convert to PascalCase
        return "".join(word.capitalize() for word in re.split(r"[-_\s]", base))

    def _detect_concern(self, content: str) -> ConcernType:
        """Auto-detect the type of concurrency concern."""
        concern_scores = {concern: 0 for concern in ConcernType}

        for concern, patterns in self.CONCERN_PATTERNS.items():
            for pattern in patterns:
                matches = len(re.findall(pattern, content, re.IGNORECASE))
                concern_scores[concern] += matches

        # Find highest scoring concern
        max_concern = max(concern_scores, key=concern_scores.get)
        if concern_scores[max_concern] > 0:
            return max_concern
        return ConcernType.GENERAL

    def _extract_variables(
        self,
        content: str,
        language: Language,
        file_path: Path,
    ) -> list[StateVariable]:
        """Extract state variables from code."""
        variables = []

        if language == Language.CSHARP:
            # Match fields and properties
            field_pattern = r"(?:private|public|protected|internal)?\s*(?:readonly|static)?\s*(\w+(?:<[\w,\s]+>)?)\s+(\w+)\s*[;=]"
            prop_pattern = r"(?:private|public|protected|internal)?\s*(\w+(?:<[\w,\s]+>)?)\s+(\w+)\s*\{\s*get"

            for pattern in [field_pattern, prop_pattern]:
                for match in re.finditer(pattern, content):
                    type_name, var_name = match.groups()
                    if self._is_state_variable(var_name, type_name):
                        variables.append(StateVariable(
                            name=var_name,
                            tla_name=self._to_tla_name(var_name),
                            type_hint=self._map_type_to_tla(type_name),
                            initial_value=self._default_initial_value(type_name),
                            source_location=f"{file_path.name}:{match.start()}",
                            description=f"Mapped from {type_name} {var_name}",
                        ))

        elif language == Language.PYTHON:
            # Match instance variables in __init__
            init_pattern = r"self\.(\w+)\s*=\s*(.+?)(?:\n|#)"
            for match in re.finditer(init_pattern, content):
                var_name, value = match.groups()
                if self._is_state_variable(var_name, ""):
                    variables.append(StateVariable(
                        name=var_name,
                        tla_name=self._to_tla_name(var_name),
                        type_hint=self._infer_tla_type(value.strip()),
                        initial_value=self._map_value_to_tla(value.strip()),
                        source_location=f"{file_path.name}:{match.start()}",
                        description=f"Mapped from self.{var_name}",
                    ))

        elif language in [Language.JAVA, Language.GO, Language.TYPESCRIPT]:
            # Simplified patterns for other languages
            field_pattern = r"(?:private|public|var|let|const)?\s*(\w+)\s*:\s*(\w+)" if language == Language.TYPESCRIPT else r"(?:private|public|var)?\s*(\w+)\s+(\w+)\s*[;=]"
            for match in re.finditer(field_pattern, content):
                groups = match.groups()
                if len(groups) >= 2:
                    type_name, var_name = groups[0], groups[1]
                    if self._is_state_variable(var_name, type_name):
                        variables.append(StateVariable(
                            name=var_name,
                            tla_name=self._to_tla_name(var_name),
                            type_hint=self._map_type_to_tla(type_name),
                            initial_value=self._default_initial_value(type_name),
                            source_location=f"{file_path.name}:{match.start()}",
                            description=f"Mapped from {type_name} {var_name}",
                        ))

        return variables

    def _extract_actions(
        self,
        content: str,
        language: Language,
        file_path: Path,
        target_method: Optional[str],
    ) -> list[Action]:
        """Extract actions (state transitions) from code."""
        actions = []

        if language == Language.CSHARP:
            # Match methods
            method_pattern = r"(?:public|private|protected|internal|async)?\s+(?:async\s+)?(?:Task<\w+>|Task|\w+)\s+(\w+)\s*\(([^)]*)\)\s*\{"
            for match in re.finditer(method_pattern, content):
                method_name = match.group(1)
                params = match.group(2)

                # Skip if target_method specified and doesn't match
                if target_method and method_name != target_method:
                    continue

                # Skip constructors, getters, etc.
                if method_name.startswith(("Get", "Is", "Has", "Can", "_")):
                    continue

                # Find line number
                line_num = content[:match.start()].count("\n") + 1

                # Extract method body
                body = self._extract_method_body(content, match.end() - 1)

                # Infer precondition and effect
                precondition, effect = self._infer_action_semantics(body, method_name)

                actions.append(Action(
                    name=method_name,
                    tla_name=method_name,
                    precondition=precondition,
                    effect=effect,
                    source_method=method_name,
                    source_file=str(file_path.relative_to(self.project_root)),
                    source_line=line_num,
                    description=f"Action derived from {method_name}",
                    parameters=self._parse_parameters(params),
                ))

        elif language == Language.PYTHON:
            # Match Python methods
            method_pattern = r"def\s+(\w+)\s*\(self(?:,\s*([^)]*))?\)\s*(?:->.*?)?:"
            for match in re.finditer(method_pattern, content):
                method_name = match.group(1)
                params = match.group(2) or ""

                if target_method and method_name != target_method:
                    continue

                if method_name.startswith("_") and not method_name.startswith("__"):
                    continue

                line_num = content[:match.start()].count("\n") + 1
                body = self._extract_python_method_body(content, match.end())
                precondition, effect = self._infer_action_semantics(body, method_name)

                actions.append(Action(
                    name=method_name,
                    tla_name=self._to_tla_name(method_name),
                    precondition=precondition,
                    effect=effect,
                    source_method=method_name,
                    source_file=str(file_path.relative_to(self.project_root)),
                    source_line=line_num,
                    description=f"Action derived from {method_name}",
                    parameters=self._parse_parameters(params),
                ))

        return actions

    def _extract_method_body(self, content: str, start: int) -> str:
        """Extract method body from curly braces."""
        brace_count = 0
        end = start

        for i, char in enumerate(content[start:], start):
            if char == "{":
                brace_count += 1
            elif char == "}":
                brace_count -= 1
                if brace_count == 0:
                    end = i
                    break

        return content[start:end]

    def _extract_python_method_body(self, content: str, start: int) -> str:
        """Extract Python method body (indentation-based)."""
        lines = content[start:].split("\n")
        if not lines:
            return ""

        # Find the base indentation
        body_lines = []
        base_indent = None

        for line in lines:
            if not line.strip():
                continue
            indent = len(line) - len(line.lstrip())
            if base_indent is None:
                base_indent = indent
            if indent < base_indent and line.strip():
                break
            body_lines.append(line)

        return "\n".join(body_lines)

    def _infer_action_semantics(self, body: str, method_name: str) -> tuple[str, str]:
        """Infer precondition and effect from method body."""
        preconditions = []
        effects = []

        # Look for null/validation checks (preconditions)
        if re.search(r"if\s*\(\s*\w+\s*==\s*null", body):
            preconditions.append("entity /= NULL")
        if re.search(r"if\s*\(\s*!\s*\w+", body):
            preconditions.append("condition = TRUE")

        # Look for state changes (effects)
        if re.search(r"\.Status\s*=|\.State\s*=", body):
            effects.append("state' = NEW_STATE")
        if re.search(r"_context\.SaveChanges|\.Commit\(|\.Save\(", body):
            effects.append("persisted' = TRUE")
        if re.search(r"\.Add\(|\.Insert\(", body):
            effects.append("items' = items \\union {newItem}")
        if re.search(r"\.Remove\(|\.Delete\(", body):
            effects.append("items' = items \\ {item}")

        # Default precondition and effect
        if not preconditions:
            preconditions.append("TRUE  \\* TODO: Add precondition")
        if not effects:
            effects.append("UNCHANGED vars  \\* TODO: Add effect")

        return " /\\ ".join(preconditions), " /\\ ".join(effects)

    def _infer_invariants(
        self,
        content: str,
        language: Language,
        concern: ConcernType,
        variables: list[StateVariable],
    ) -> list[Invariant]:
        """Infer invariants from code patterns."""
        invariants = []

        # Look for validation patterns
        if re.search(r"\.Count\s*>\s*0|\.Length\s*>\s*0|len\(\w+\)\s*>", content):
            invariants.append(Invariant(
                name="NonEmptyInvariant",
                formula="Cardinality(items) > 0",
                description="Collection is never empty when expected",
                source="Validation check in code",
                confidence=0.7,
            ))

        # Look for unique constraints
        if re.search(r"unique|distinct|\.Single\(|\.First\(", content, re.IGNORECASE):
            invariants.append(Invariant(
                name="UniqueKeyInvariant",
                formula="\\A x, y \\in items: x.id = y.id => x = y",
                description="Items have unique identifiers",
                source="Unique constraint pattern",
                confidence=0.8,
            ))

        # Concern-specific invariants
        if concern == ConcernType.RACE_CONDITION:
            invariants.append(Invariant(
                name="MutualExclusion",
                formula="\\A p1, p2 \\in Processes: p1 /= p2 => ~(inCritical[p1] /\\ inCritical[p2])",
                description="At most one process in critical section",
                source="Race condition concern",
                confidence=0.9,
            ))

        elif concern == ConcernType.LOST_UPDATE:
            invariants.append(Invariant(
                name="VersionConsistency",
                formula="\\A e \\in Entities: version[e] >= previousVersion[e]",
                description="Versions are monotonically increasing",
                source="Lost update concern",
                confidence=0.85,
            ))

        elif concern == ConcernType.DEADLOCK:
            invariants.append(Invariant(
                name="NoDeadlock",
                formula="\\E p \\in Processes: ~waiting[p]",
                description="At least one process can make progress",
                source="Deadlock concern",
                confidence=0.75,
            ))

        # Default invariant
        if not invariants:
            invariants.append(Invariant(
                name="SafetyInvariant",
                formula="TRUE  \\* TODO: Define safety property",
                description="Placeholder safety invariant",
                source="Auto-generated placeholder",
                confidence=0.5,
            ))

        return invariants

    def _infer_temporal_properties(
        self,
        content: str,
        language: Language,
        concern: ConcernType,
    ) -> list[TemporalProperty]:
        """Infer temporal (liveness) properties."""
        properties = []

        # Look for completion patterns
        if re.search(r"await|Task\.|async|Promise|then\(", content):
            properties.append(TemporalProperty(
                name="EventualCompletion",
                formula="<>(state = COMPLETED)",
                description="Operations eventually complete",
                property_type="eventually",
            ))

        # Look for retry patterns
        if re.search(r"retry|Retry|attempt|Attempt", content, re.IGNORECASE):
            properties.append(TemporalProperty(
                name="ProgressWithRetry",
                formula="[]<>(attempts < MAX_ATTEMPTS => eventually_succeeds)",
                description="Retries eventually succeed or exhaust",
                property_type="always_eventually",
            ))

        return properties

    def _extract_constants(self, content: str, language: Language) -> dict[str, str]:
        """Extract constants from code."""
        constants = {}

        # Match constant declarations
        const_patterns = [
            r"const\s+(\w+)\s*=\s*(\d+)",  # const X = 123
            r"static\s+readonly\s+\w+\s+(\w+)\s*=\s*(\d+)",  # static readonly int X = 123
            r"(\w+_MAX|\w+_MIN|\w+_LIMIT)\s*=\s*(\d+)",  # X_MAX = 123
        ]

        for pattern in const_patterns:
            for match in re.finditer(pattern, content):
                name, value = match.groups()
                if name.isupper() or "_" in name:
                    constants[name.upper()] = f"Numeric constant ({value})"

        return constants

    def _is_state_variable(self, name: str, type_name: str) -> bool:
        """Check if a variable likely represents state."""
        state_keywords = ["state", "status", "count", "flag", "is", "has", "items", "data", "result"]
        return any(kw in name.lower() for kw in state_keywords) or type_name.lower() in ["bool", "boolean", "int", "string"]

    def _to_tla_name(self, name: str) -> str:
        """Convert code name to TLA+ name."""
        # Remove prefixes
        if name.startswith("_"):
            name = name[1:]
        # Convert camelCase to TitleCase
        return name[0].upper() + name[1:] if name else name

    def _map_type_to_tla(self, type_name: str) -> str:
        """Map programming language type to TLA+ type."""
        type_map = {
            "int": "Int",
            "long": "Int",
            "string": "STRING",
            "bool": "BOOLEAN",
            "boolean": "BOOLEAN",
            "guid": "GUID",
            "datetime": "DATETIME",
            "list": "Seq(T)",
            "set": "SUBSET T",
            "dict": "[K -> V]",
            "dictionary": "[K -> V]",
        }

        type_lower = type_name.lower()
        for key, value in type_map.items():
            if key in type_lower:
                return value

        return f"{type_name}  \\* Custom type"

    def _default_initial_value(self, type_name: str) -> str:
        """Get default initial value for a type."""
        type_lower = type_name.lower()
        if "int" in type_lower or "long" in type_lower:
            return "0"
        elif "bool" in type_lower:
            return "FALSE"
        elif "list" in type_lower or "seq" in type_lower:
            return "<<>>"
        elif "set" in type_lower:
            return "{}"
        elif "dict" in type_lower or "map" in type_lower:
            return "[x \\in {} |-> NULL]"
        return "NULL"

    def _infer_tla_type(self, value: str) -> str:
        """Infer TLA+ type from Python value."""
        if value.isdigit() or (value.startswith("-") and value[1:].isdigit()):
            return "Int"
        elif value in ["True", "False", "true", "false"]:
            return "BOOLEAN"
        elif value.startswith("[") and value.endswith("]"):
            return "Seq(T)"
        elif value.startswith("{") and value.endswith("}"):
            return "SUBSET T"
        elif value.startswith('"') or value.startswith("'"):
            return "STRING"
        return "T"

    def _map_value_to_tla(self, value: str) -> str:
        """Map Python value to TLA+ value."""
        if value == "True":
            return "TRUE"
        elif value == "False":
            return "FALSE"
        elif value == "None":
            return "NULL"
        elif value == "[]":
            return "<<>>"
        elif value == "{}":
            return "{}"
        return value

    def _parse_parameters(self, params: str) -> list[str]:
        """Parse parameter list."""
        if not params.strip():
            return []
        return [p.strip().split()[-1] for p in params.split(",") if p.strip()]

    def _generate_warnings(
        self,
        variables: list[StateVariable],
        actions: list[Action],
        invariants: list[Invariant],
    ) -> list[str]:
        """Generate warnings about the extracted spec."""
        warnings = []

        if not variables:
            warnings.append("No state variables extracted. Manual refinement needed.")

        if not actions:
            warnings.append("No actions extracted. Check method patterns.")

        low_confidence = [inv for inv in invariants if inv.confidence < 0.7]
        if low_confidence:
            warnings.append(f"{len(low_confidence)} invariants have low confidence. Review carefully.")

        return warnings


class SpecGenerator:
    """High-level interface for generating specs from code."""

    def __init__(self, project_root: Path | str = "."):
        self.project_root = Path(project_root)
        self.analyzer = CodeAnalyzer(project_root)
        self.store = TLAStore(project_root)

    def generate(
        self,
        source_file: str | Path,
        output_dir: Optional[str | Path] = None,
        method: Optional[str] = None,
        concern: str = "general",
        interactive: bool = False,
        register: bool = True,
    ) -> tuple[Path, Path]:
        """
        Generate TLA+ specification from source code.

        Args:
            source_file: Path to source file
            output_dir: Output directory (default: specs/tla+/{model-name}/)
            method: Specific method to analyze
            concern: Type of concurrency concern
            interactive: Whether to run interactive refinement
            register: Whether to register with TLAStore

        Returns:
            Tuple of (spec_file, config_file) paths
        """
        source_path = Path(source_file)
        concern_type = ConcernType(concern) if concern else ConcernType.GENERAL

        # Analyze source file
        spec = self.analyzer.analyze_file(source_path, method, concern_type)

        # Interactive refinement
        if interactive:
            spec = self._interactive_refine(spec)

        # Determine output directory
        if output_dir:
            out_path = Path(output_dir)
        else:
            model_name = spec.module_name.lower().replace("_", "-")
            specs_dir = self.store.get_specs_dir() if self.store.is_initialized() else self.project_root / "specs" / "tla+"
            out_path = specs_dir / model_name

        out_path.mkdir(parents=True, exist_ok=True)

        # Write files
        spec_file = out_path / f"{spec.module_name}.tla"
        cfg_file = out_path / f"{spec.module_name}.cfg"

        spec_file.write_text(spec.to_tla())
        cfg_file.write_text(spec.to_cfg())

        # Register with store
        if register and self.store.is_initialized():
            try:
                self.store.add_model(
                    name=spec.module_name.lower().replace("_", "-"),
                    description=spec.description,
                    spec_file=spec_file.name,
                    configs=[cfg_file.name],
                )

                # Add action mappings
                for action in spec.actions:
                    self.store.add_mapping(
                        model=spec.module_name.lower().replace("_", "-"),
                        action=action.tla_name,
                        code_file=action.source_file,
                        method=action.source_method,
                        line=action.source_line,
                    )
            except ValueError:
                pass  # Model already exists

        return spec_file, cfg_file

    def _interactive_refine(self, spec: ExtractedSpec) -> ExtractedSpec:
        """Interactively refine the extracted specification."""
        print("\n=== Interactive Refinement Mode ===\n")

        # Show warnings first
        if spec.warnings:
            print("Warnings:")
            for w in spec.warnings:
                print(f"  ! {w}")
            print()

        # Review variables
        print("Extracted Variables:")
        for i, v in enumerate(spec.variables):
            print(f"  [{i}] {v.tla_name}: {v.type_hint} = {v.initial_value}")
        print()

        response = input("Add/remove variables? [y/N]: ").strip().lower()
        if response == "y":
            # Simple interactive editing
            to_remove = input("Indices to remove (comma-separated, or Enter to skip): ").strip()
            if to_remove:
                indices = [int(x.strip()) for x in to_remove.split(",")]
                spec.variables = [v for i, v in enumerate(spec.variables) if i not in indices]

        # Review actions
        print("\nExtracted Actions:")
        for i, a in enumerate(spec.actions):
            print(f"  [{i}] {a.tla_name}")
            print(f"      Pre:  {a.precondition}")
            print(f"      Post: {a.effect}")
        print()

        response = input("Refine actions? [y/N]: ").strip().lower()
        if response == "y":
            for a in spec.actions:
                print(f"\nAction: {a.tla_name}")
                new_pre = input(f"  Precondition [{a.precondition}]: ").strip()
                if new_pre:
                    a.precondition = new_pre
                new_eff = input(f"  Effect [{a.effect}]: ").strip()
                if new_eff:
                    a.effect = new_eff

        # Review invariants
        print("\nInferred Invariants:")
        for i, inv in enumerate(spec.invariants):
            conf = f" ({inv.confidence:.0%})" if inv.confidence < 1.0 else ""
            print(f"  [{i}] {inv.name}{conf}: {inv.formula}")
        print()

        response = input("Add custom invariant? [y/N]: ").strip().lower()
        if response == "y":
            name = input("  Name: ").strip()
            formula = input("  Formula: ").strip()
            desc = input("  Description: ").strip()
            if name and formula:
                spec.invariants.append(Invariant(
                    name=name,
                    formula=formula,
                    description=desc or "User-defined invariant",
                    source="Interactive refinement",
                    confidence=1.0,
                ))

        print("\n=== Refinement Complete ===\n")
        return spec


def main():
    """CLI for generating TLA+ specs from code."""
    import argparse

    parser = argparse.ArgumentParser(
        description="Generate TLA+ Specifications from Source Code",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s --source src/Services/OrderService.cs
  %(prog)s --source src/Services/OrderService.cs --method ProcessOrder
  %(prog)s --source src/Services/TokenService.cs --concern race-condition
  %(prog)s --source src/Services/LockManager.cs --interactive
        """,
    )

    parser.add_argument("--project", "-p", default=".", help="Project root directory")
    parser.add_argument("--source", "-s", required=True, help="Source file to analyze")
    parser.add_argument("--method", "-m", help="Specific method to focus on")
    parser.add_argument(
        "--concern", "-c",
        choices=["race-condition", "deadlock", "lost-update", "starvation", "atomicity", "ordering", "general"],
        default="general",
        help="Type of concurrency concern (default: general)",
    )
    parser.add_argument("--output", "-o", help="Output directory for generated spec")
    parser.add_argument("--interactive", "-i", action="store_true", help="Run interactive refinement")
    parser.add_argument("--no-register", action="store_true", help="Don't register with TLAStore")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be generated without writing")
    parser.add_argument("--format", "-f", choices=["tla", "json"], default="tla", help="Output format for dry-run")

    args = parser.parse_args()

    generator = SpecGenerator(args.project)

    if args.dry_run:
        # Just analyze and display
        analyzer = CodeAnalyzer(args.project)
        spec = analyzer.analyze_file(
            Path(args.source),
            args.method,
            ConcernType(args.concern),
        )

        if args.format == "json":
            output = {
                "module": spec.module_name,
                "description": spec.description,
                "concern": spec.concern.value,
                "variables": [{"name": v.name, "tla_name": v.tla_name, "type": v.type_hint} for v in spec.variables],
                "actions": [{"name": a.name, "tla_name": a.tla_name, "source": f"{a.source_file}:{a.source_line}"} for a in spec.actions],
                "invariants": [{"name": i.name, "formula": i.formula, "confidence": i.confidence} for i in spec.invariants],
                "warnings": spec.warnings,
            }
            print(json.dumps(output, indent=2))
        else:
            print(spec.to_tla())
            if spec.warnings:
                print("\n--- Warnings ---")
                for w in spec.warnings:
                    print(f"! {w}")
    else:
        spec_file, cfg_file = generator.generate(
            source_file=args.source,
            output_dir=args.output,
            method=args.method,
            concern=args.concern,
            interactive=args.interactive,
            register=not args.no_register,
        )

        print(f"Generated specification:")
        print(f"  Spec: {spec_file}")
        print(f"  Config: {cfg_file}")


if __name__ == "__main__":
    main()

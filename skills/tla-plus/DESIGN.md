# TLA+ Skill Design Document

## Executive Summary

This document describes the design for a best-in-class TLA+ skill for Claude Code that enables developers to:
1. Create and verify formal specifications
2. Integrate model checking into CI/CD pipelines
3. Generate specs from code patterns
4. Maintain synchronization between code and specifications
5. Learn TLA+ concepts in context

## Research Findings

### Industry Landscape

**TLA+ Foundation Tools:**
- **TLC** - The standard model checker (explicit state enumeration)
- **Apalache** - Symbolic model checker using Z3 (bounded model checking)
- **TLAPS** - Proof system for unbounded verification
- **VS Code Extension** - Active development, replacing the Eclipse-based Toolbox

**2025 Innovations:**
- **Specula** (TLAi+ Challenge Winner) - Automatic TLA+ spec extraction from source code using LLM + Control Flow Analysis
- **GenAI-assisted verification** - Growing area combining LLMs with formal methods

**CI/CD Integration:**
- No official GitHub Action exists (requested in issue #501)
- Projects use custom scripts with `java -jar tla2tools.jar`
- XTConnect's approach (simulation mode for CI, full verification locally) is a best practice

**Template Repositories:**
- [CRDT-TLA](https://github.com/JYwellin/CRDT-TLA) - Layered framework for CRDTs
- [tlaplus/Examples](https://github.com/tlaplus/Examples) - 80+ specifications across domains
- [Azure Cosmos TLA](https://github.com/Azure/azure-cosmos-tla) - Consistency level specifications

### Existing Skill Patterns (claude-tools)

Skills follow a consistent structure:
```
skills/{name}/
  SKILL.md         # Documentation with YAML frontmatter (triggers)
  scripts/         # Python scripts for operations
  references/      # Reference materials
  checklists/      # Review checklists
  schemas/         # JSON schemas for data
  tests/           # pytest tests
  pyproject.toml   # Dependencies
```

Key patterns:
- YAML frontmatter with trigger keywords
- Python scripts for CLI operations
- Integration with other skills (findings, azure-devops)
- Work item creation for findings
- Eval framework integration

---

## Skill Architecture

### Directory Structure

```
skills/tla-plus/
├── SKILL.md                      # Main documentation with triggers
├── scripts/
│   ├── pyproject.toml            # Dependencies
│   ├── tests/                    # pytest tests
│   │   └── test_*.py
│   ├── tla_store.py              # TLA+ project metadata management
│   ├── run_tlc.py                # TLC runner with structured output
│   ├── run_apalache.py           # Apalache runner
│   ├── generate_spec.py          # Spec generation from templates
│   ├── generate_from_code.py     # LLM-assisted spec extraction (Specula-inspired)
│   ├── check_drift.py            # Code-spec synchronization checker
│   ├── generate_pipeline.py      # CI pipeline generator
│   ├── explain_counterexample.py # Counterexample explanation
│   ├── validate_spec.py          # Syntax validation (SANY)
│   └── spec_to_tests.py          # Generate tests from invariants
├── templates/
│   ├── patterns/
│   │   ├── optimistic-concurrency.tla
│   │   ├── token-rotation.tla
│   │   ├── state-machine.tla
│   │   ├── leader-election.tla
│   │   ├── circuit-breaker.tla
│   │   ├── rate-limiter.tla
│   │   ├── saga-pattern.tla
│   │   ├── crdt-counter.tla
│   │   └── two-phase-commit.tla
│   ├── layers/
│   │   ├── network-reliable.tla
│   │   ├── network-lossy.tla
│   │   └── database-atomic.tla
│   └── configs/
│       ├── small.cfg.template
│       ├── large.cfg.template
│       └── ci.cfg.template
├── pipelines/
│   ├── azure-devops.yml.template
│   └── github-actions.yml.template
├── references/
│   ├── tlaplus-quickstart.md
│   ├── common-patterns.md
│   ├── tlc-optimization.md
│   ├── apalache-guide.md
│   └── code-spec-mapping.md
└── schemas/
    ├── tla-project.schema.json   # .tla-plus/project.json schema
    └── spec-mapping.schema.json  # Code-to-spec mapping schema
```

### Project Configuration

Projects using TLA+ create a `.tla-plus/` directory:

```
project/
├── .tla-plus/
│   ├── project.json              # TLA+ project configuration
│   └── mappings.json             # Code-to-spec traceability
└── specs/tla+/
    ├── README.md
    ├── common/
    │   └── ProjectCommon.tla
    └── {model-name}/
        ├── README.md
        ├── {Model}.tla
        ├── {Model}.cfg
        ├── {Model}_Large.cfg
        └── {Model}Buggy.tla      # Optional: negative test
```

**project.json:**
```json
{
  "version": "1.0.0",
  "specsDir": "specs/tla+",
  "toolsDir": "specs/tla+/.tools",
  "tlcVersion": "1.8.0",
  "apalacheVersion": "0.44.0",
  "models": [
    {
      "name": "node-registration",
      "description": "XTNode self-registration and mobile claiming",
      "specFile": "NodeRegistration.tla",
      "configs": ["NodeRegistration.cfg", "NodeRegistration_Large.cfg"],
      "buggyVariant": "NodeRegistrationBuggy.tla",
      "verificationStrategy": "tlc-simulation",
      "lastVerified": "2025-12-19T10:30:00Z"
    }
  ],
  "ciStrategy": {
    "defaultMode": "simulation",
    "simulationDepth": 100000,
    "fullVerificationBranches": ["main"],
    "timeoutMinutes": 30
  }
}
```

**mappings.json:**
```json
{
  "models": {
    "node-registration": {
      "description": "XTNode registration and claiming flow",
      "actions": {
        "NodeSelfRegister": {
          "codeFile": "src/Features/Registration/Commands/RegisterNode/RegisterNodeCommandHandler.cs",
          "method": "CreateNewNode",
          "line": 96
        },
        "UserClaimNode": {
          "codeFile": "src/Features/AccessPoint/Commands/RegisterAccessPoint/RegisterAccessPointCommandHandler.cs",
          "method": "ClaimSelfRegisteredNode",
          "line": 204
        }
      },
      "variables": {
        "nodeState": {
          "table": "access_points",
          "column": "OwnerId",
          "derivation": "Derived from OwnerId = SYSTEM vs user"
        },
        "nodeOwner": {
          "table": "access_points",
          "column": "OwnerId"
        }
      },
      "constants": {
        "SYSTEM": "SystemConstants.SystemNodeRegistrationOwnerId"
      },
      "invariants": {
        "SingleOwnership": {
          "description": "Every registered node has exactly one owner",
          "businessRule": "Node ownership is exclusive"
        }
      }
    }
  }
}
```

---

## Core Workflows

### 1. Create New Specification

**Trigger:** "Create a TLA+ spec for...", "Model this concurrency...", "Verify this algorithm..."

**Workflow:**
1. Understand the concurrency/safety concern
2. Select appropriate template from `templates/patterns/`
3. Customize template with domain-specific names/logic
4. Generate .cfg configurations (small, large)
5. Create mapping to code (if code exists)
6. Run initial verification
7. Create buggy variant for negative testing
8. Generate CI pipeline triggers

```bash
# Interactive generation
python3 ~/.claude/skills/tla-plus/scripts/generate_spec.py \
  --pattern optimistic-concurrency \
  --name "OrderLocking" \
  --output specs/tla+/order-locking/

# From code analysis (Specula-inspired)
python3 ~/.claude/skills/tla-plus/scripts/generate_from_code.py \
  --source src/Services/OrderService.cs \
  --method ProcessOrder \
  --concern "race condition" \
  --output specs/tla+/order-processing/
```

### 2. Run Verification

**Trigger:** "Verify TLA+ specs", "Run model checker", "Check invariants"

**Workflow:**
1. Check for Java/TLA+ tools installation
2. Select appropriate verification mode:
   - Quick (simulation, ~100k states)
   - Standard (full BFS, small config)
   - Thorough (full BFS, large config)
   - Symbolic (Apalache for larger state spaces)
3. Run verification
4. Parse results (states explored, time, errors)
5. If counterexample found, explain it
6. Capture findings if issues discovered

```bash
# Run TLC
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \
  --model node-registration \
  --mode quick \
  --format json

# Run Apalache (symbolic)
python3 ~/.claude/skills/tla-plus/scripts/run_apalache.py \
  --model token-refresh \
  --check-inductive \
  --length 20
```

### 3. Generate CI Pipeline

**Trigger:** "Set up TLA+ CI", "Add model checking to pipeline"

**Workflow:**
1. Detect platform (Azure DevOps vs GitHub Actions)
2. Analyze existing models and their code mappings
3. Generate trigger paths from mappings
4. Create pipeline YAML with:
   - Fast verification (simulation) on PRs
   - Full verification on main/develop
   - Negative testing (buggy variants)
5. Add to existing CI or create new pipeline

```bash
# Generate Azure DevOps pipeline
python3 ~/.claude/skills/tla-plus/scripts/generate_pipeline.py \
  --platform azure-devops \
  --output .azure-pipelines/tla-verification.yml

# Generate GitHub Actions
python3 ~/.claude/skills/tla-plus/scripts/generate_pipeline.py \
  --platform github \
  --output .github/workflows/tla-verification.yml
```

### 4. Check Code-Spec Drift

**Trigger:** "Is my spec up to date?", "Check TLA+ drift", "Sync specs"

**Workflow:**
1. Load mappings.json
2. For each mapping:
   - Check if source file exists
   - Check if mapped line/method still exists
   - Parse code to extract current logic
   - Compare with spec actions (LLM-assisted)
3. Report drift with severity:
   - **Critical:** Mapped code deleted/renamed
   - **High:** Logic changed significantly
   - **Medium:** Code moved (line numbers off)
   - **Low:** Style changes, comments

```bash
python3 ~/.claude/skills/tla-plus/scripts/check_drift.py \
  --model node-registration \
  --format table
```

### 5. Explain Counterexample

**Trigger:** "Why did TLC fail?", "Explain this counterexample"

**Workflow:**
1. Parse TLC output for counterexample trace
2. Map each state to:
   - TLA+ action that led to it
   - Corresponding code method
   - Variable values
3. Identify the violating state
4. Explain in plain English:
   - What happened step by step
   - Why the invariant was violated
   - What race condition or bug this represents
5. Suggest fix (based on pattern library)

```bash
python3 ~/.claude/skills/tla-plus/scripts/explain_counterexample.py \
  --tlc-output specs/tla+/node-registration/states/tlc-output.txt \
  --mapping .tla-plus/mappings.json
```

### 6. Generate Tests from Invariants

**Trigger:** "Generate tests from TLA+", "Test invariants in code"

**Workflow:**
1. Parse spec invariants
2. For each invariant:
   - Identify testable conditions
   - Map to code entities via mappings
   - Generate test scaffolding
3. Output test file with:
   - Setup matching initial state
   - Actions corresponding to TLA+ actions
   - Assertions matching invariants

```bash
python3 ~/.claude/skills/tla-plus/scripts/spec_to_tests.py \
  --model node-registration \
  --language csharp \
  --output tests/NodeRegistration.Invariants.Tests.cs
```

---

## Python Scripts Specification

### tla_store.py

Manages TLA+ project metadata (similar to findings_store.py pattern).

```python
class TLAStore:
    """Manages .tla-plus/ configuration and state."""

    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.config_dir = project_root / ".tla-plus"
        self.project_file = self.config_dir / "project.json"
        self.mappings_file = self.config_dir / "mappings.json"

    def init_project(self, specs_dir: str = "specs/tla+") -> None:
        """Initialize TLA+ project structure."""

    def add_model(self, name: str, description: str, spec_file: Path) -> None:
        """Register a new model."""

    def add_mapping(self, model: str, action: str, code_file: Path,
                    method: str, line: int) -> None:
        """Add code-to-spec mapping."""

    def get_trigger_paths(self, model: str) -> List[str]:
        """Get CI trigger paths for a model."""

    def update_verification_timestamp(self, model: str) -> None:
        """Record successful verification."""
```

### run_tlc.py

TLC runner with structured output and CI integration.

```python
def run_tlc(
    model: str,
    mode: Literal["quick", "standard", "thorough"] = "quick",
    config: Optional[str] = None,
    workers: int = -1,  # auto
    simulation_depth: int = 100000,
    timeout_minutes: int = 30,
    format: Literal["text", "json", "markdown"] = "text"
) -> TLCResult:
    """
    Run TLC model checker.

    Modes:
    - quick: Simulation mode, fast feedback
    - standard: Full BFS with default config
    - thorough: Full BFS with large config
    """

@dataclass
class TLCResult:
    success: bool
    model: str
    mode: str
    states_generated: int
    distinct_states: int
    depth: int
    duration_seconds: float
    error: Optional[str]
    counterexample: Optional[List[State]]
    warnings: List[str]
```

### generate_from_code.py (Specula-inspired)

LLM-assisted specification extraction.

```python
def generate_from_code(
    source_file: Path,
    method: Optional[str] = None,
    concern: str = "concurrency",
    output_dir: Path = None,
    interactive: bool = True
) -> GeneratedSpec:
    """
    Generate TLA+ specification from source code.

    Uses LLM to:
    1. Identify state variables
    2. Extract actions (state transitions)
    3. Infer invariants from business rules
    4. Create code-to-spec mappings

    Interactive mode asks clarifying questions.
    """
```

### check_drift.py

Detect synchronization issues between code and specs.

```python
def check_drift(
    model: Optional[str] = None,
    all_models: bool = False,
    format: Literal["table", "json", "markdown"] = "table"
) -> DriftReport:
    """
    Check for drift between code and TLA+ specifications.

    Checks:
    - File existence
    - Method/line existence
    - Logic similarity (LLM-assisted)
    """

@dataclass
class DriftIssue:
    model: str
    mapping_type: str  # action, variable, constant
    mapping_name: str
    severity: Literal["critical", "high", "medium", "low"]
    description: str
    spec_location: str
    code_location: str
    suggestion: str
```

### explain_counterexample.py

Human-readable counterexample explanation.

```python
def explain_counterexample(
    tlc_output: Optional[Path] = None,
    model: Optional[str] = None,
    format: Literal["text", "markdown", "json"] = "markdown"
) -> Explanation:
    """
    Parse and explain TLC counterexample.

    Output includes:
    - Step-by-step trace in plain English
    - Code locations for each step
    - Root cause analysis
    - Suggested fix patterns
    """
```

---

## Integration Points

### With findings skill

```python
# After discovering issues via TLA+ verification
from findings_store import FindingsStore

findings = FindingsStore(project_root)
findings.capture(
    title="Race condition in ClaimSelfRegisteredNode",
    finding_type="discovery",
    severity="critical",
    category="thread-safety",
    evidence={
        "file": "src/Features/AccessPoint/RegisterAccessPointCommandHandler.cs",
        "line": 204,
        "tla_model": "node-registration",
        "counterexample": "trace.json"
    },
    during="tla-verification"
)
```

### With azure-devops skill

```python
# Promote TLA+ finding to work item
from promote_to_ado import promote_finding

work_item = promote_finding(
    finding_id="f-abc123",
    work_item_type="Bug",
    additional_fields={
        "System.Tags": "TLA+;RaceCondition;Formal-Verification"
    }
)
```

### With code-review skill

The code-review skill should recognize TLA+ related changes:

```yaml
# In code-review checklist
tla_review:
  - "If modifying code mapped to a TLA+ spec, run verification"
  - "If adding concurrency, consider adding TLA+ model"
  - "Check code-spec drift after changes"
```

### With architecture-review skill

Architecture assessments should include formal verification coverage:

```yaml
# In architecture-review checklist
formal_verification:
  - rating: [None | Partial | Good | Comprehensive]
  - observations:
    - "TLA+ specs exist for: X, Y, Z"
    - "Missing specs for: A, B, C (high-risk areas)"
  - recommendations:
    - "P2: Add TLA+ model for token refresh flow"
```

---

## Template Library

### Pattern Templates

Each pattern template includes:
- Base specification (.tla)
- Customization points (marked with {{PLACEHOLDER}})
- Common invariants for the pattern
- Example buggy variant
- CI configuration

#### optimistic-concurrency.tla

```tla
--------------------------- MODULE OptimisticConcurrency ---------------------------
(*
 * Template: Optimistic Concurrency Control with Version Check
 *
 * Pattern for: Database updates with version-based conflict detection
 * Common in: Entity updates, document stores, distributed caches
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

CONSTANTS
    {{ENTITIES}},     \* Set of entity IDs
    {{ACTORS}},       \* Set of concurrent actors
    MAX_VERSION       \* Upper bound for version numbers

VARIABLES
    entityVersion,    \* entityVersion[e] = current version number
    entityState,      \* entityState[e] = current entity state
    pendingUpdates    \* In-flight update operations

\* Template invariants
VersionMonotonicity ==
    \* Versions only increase
    \A e \in {{ENTITIES}} : entityVersion'[e] >= entityVersion[e]

NoLostUpdates ==
    \* Concurrent updates are detected, not silently lost
    \* (Customized based on business rules)
    TRUE

=============================================================================
```

#### token-rotation.tla

For JWT/token refresh with rotation semantics.

#### state-machine.tla

Generic state machine with guards and transitions.

#### circuit-breaker.tla

Circuit breaker pattern with open/closed/half-open states.

#### rate-limiter.tla

Token bucket or sliding window rate limiting.

---

## CI Pipeline Templates

### Azure DevOps Template

```yaml
# .azure-pipelines/tla-verification.yml
# Generated by: python3 ~/.claude/skills/tla-plus/scripts/generate_pipeline.py

trigger:
  branches:
    include:
      - main
      - develop
      - feature/*
  paths:
    include:
      - specs/tla+/**
      {{MAPPED_SOURCE_PATHS}}

pr:
  branches:
    include:
      - main
      - develop
  paths:
    include:
      - specs/tla+/**
      {{MAPPED_SOURCE_PATHS}}

pool:
  vmImage: 'ubuntu-latest'

variables:
  TLA_VERSION: '{{TLC_VERSION}}'
  JAVA_VERSION: '17'

stages:
  - stage: TLAVerification
    displayName: 'TLA+ Formal Verification'
    jobs:
      - job: SimulationCheck
        displayName: 'Quick Verification (Simulation)'
        steps:
          - task: JavaToolInstaller@0
            inputs:
              versionSpec: '17'
              jdkArchitectureOption: 'x64'

          - script: |
              curl -sL -o tla2tools.jar \
                "https://github.com/tlaplus/tlaplus/releases/download/v$(TLA_VERSION)/tla2tools.jar"
            displayName: 'Download TLA+ Tools'

          - script: |
              python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \
                --all --mode quick --format markdown
            displayName: 'Run TLC Simulation'

      - job: FullVerification
        displayName: 'Thorough Verification'
        dependsOn: SimulationCheck
        condition: and(succeeded(), eq(variables['Build.SourceBranch'], 'refs/heads/main'))
        steps:
          # ... full verification steps

      - job: NegativeTests
        displayName: 'Verify Bug Detection'
        dependsOn: SimulationCheck
        steps:
          # ... buggy variant verification
```

### GitHub Actions Template

```yaml
# .github/workflows/tla-verification.yml
name: TLA+ Verification

on:
  push:
    branches: [main, develop]
    paths:
      - 'specs/tla+/**'
      {{MAPPED_SOURCE_PATHS}}
  pull_request:
    branches: [main, develop]
    paths:
      - 'specs/tla+/**'
      {{MAPPED_SOURCE_PATHS}}

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: 'temurin'
          java-version: '17'

      - name: Download TLA+ Tools
        run: |
          curl -sL -o tla2tools.jar \
            "https://github.com/tlaplus/tlaplus/releases/download/v{{TLC_VERSION}}/tla2tools.jar"

      - name: Run TLC Verification
        run: |
          python3 scripts/run_tlc.py --all --mode quick
```

---

## ADR: Key Design Decisions

### ADR-001: Multi-Tool Support (TLC + Apalache)

**Context:** TLC and Apalache have complementary strengths.

**Decision:** Support both tools with unified interface.

**Rationale:**
- TLC: Fast for small state spaces, mature, well-documented
- Apalache: Handles larger/infinite state spaces, symbolic approach
- Users can choose based on model characteristics

**Consequences:**
- Need abstraction layer for tool invocation
- Result parsing differs between tools
- Documentation must cover both

### ADR-002: Simulation Mode for CI

**Context:** Full TLC verification can take minutes to hours.

**Decision:** Default to simulation mode in CI, full verification locally.

**Rationale:**
- Simulation catches most bugs quickly (~100k random behaviors)
- Fast CI feedback (seconds vs minutes)
- Full verification runs on protected branches only

**Consequences:**
- Some bugs may escape simulation (low probability for well-designed specs)
- Clear documentation about verification levels
- Option to force full verification when needed

### ADR-003: Code-Spec Mapping with JSON

**Context:** Need to track relationships between code and specs.

**Decision:** Use `.tla-plus/mappings.json` for bidirectional traceability.

**Rationale:**
- Machine-readable for drift detection
- Human-readable for documentation
- Git-tracked for history
- Similar pattern to findings skill

**Consequences:**
- Manual maintenance burden (mitigated by generators)
- Risk of stale mappings (drift checker addresses this)

### ADR-004: Template-Based Spec Generation

**Context:** Writing TLA+ specs from scratch is hard for beginners.

**Decision:** Provide pattern templates with customization points.

**Rationale:**
- Lower barrier to entry
- Encode best practices
- Consistent structure across projects

**Consequences:**
- Templates may not fit all use cases
- Need to maintain template library
- Clear escape hatch to raw TLA+

### ADR-005: LLM-Assisted Spec Extraction (Specula-Inspired)

**Context:** Manual spec writing is tedious and error-prone.

**Decision:** Implement Claude-assisted spec generation from code.

**Rationale:**
- Inspired by Specula's success in TLAi+ Challenge
- Claude can identify state variables, actions, invariants
- Interactive refinement catches LLM errors
- Validation via TLC catches semantic errors

**Consequences:**
- Output requires human review
- Interactive mode for refinement
- Clear warnings about AI-generated specs

---

## SKILL.md Frontmatter

```yaml
---
name: tla-plus
description: |
  TLA+ formal verification for modeling and verifying concurrent algorithms.
  Use when asked about: TLA+, formal verification, model checking, verify algorithm,
  check invariants, race condition analysis, concurrency model, TLC, Apalache,
  formal spec, temporal logic, prove correctness, state machine verification.
  Capabilities: Create specs from templates, run TLC/Apalache, generate CI pipelines,
  check code-spec drift, explain counterexamples, generate tests from invariants.
---
```

---

## Implementation Roadmap

### Phase 1: Foundation (Week 1)
- [ ] Create skill directory structure
- [ ] Implement tla_store.py
- [ ] Implement run_tlc.py with JSON output
- [ ] Create basic SKILL.md documentation
- [ ] Port XTConnect run-tlc.sh patterns

### Phase 2: Templates (Week 2)
- [ ] Create 5 core pattern templates
- [ ] Implement generate_spec.py
- [ ] Create CI pipeline templates
- [ ] Implement generate_pipeline.py

### Phase 3: Intelligence (Week 3)
- [ ] Implement check_drift.py
- [ ] Implement explain_counterexample.py
- [ ] Implement generate_from_code.py (Specula-inspired)
- [ ] Add LLM prompts for interactive refinement

### Phase 4: Integration (Week 4)
- [ ] Integrate with findings skill
- [ ] Integrate with azure-devops skill
- [ ] Update code-review checklist
- [ ] Update architecture-review checklist
- [ ] Write comprehensive tests

### Phase 5: Polish (Week 5)
- [ ] Add Apalache support (run_apalache.py)
- [ ] Implement spec_to_tests.py
- [ ] Create reference documentation
- [ ] Add more pattern templates
- [ ] Performance optimization

---

## References

**TLA+ Resources:**
- [TLA+ Foundation](https://foundation.tlapl.us/)
- [TLA+ VS Code Extension](https://marketplace.visualstudio.com/items?itemName=tlaplus.vscode-ide)
- [Learn TLA+](https://learntla.com/)
- [Apalache Model Checker](https://apalache-mc.org/)

**Inspiration:**
- [Specula](https://foundation.tlapl.us/challenge/index.html) - 2025 TLAi+ Challenge Winner
- [CRDT-TLA](https://github.com/JYwellin/CRDT-TLA) - Layered framework pattern
- [Azure Cosmos TLA](https://github.com/Azure/azure-cosmos-tla) - Production specs

**Claude-tools Patterns:**
- findings skill - Storage pattern, CLI pattern
- azure-devops skill - CI integration, work item creation
- architecture-review skill - Assessment pattern, findings capture

---

*Document Version: 1.0.0*
*Created: 2025-12-19*
*Author: Claude (claude-opus-4-5-20251101)*

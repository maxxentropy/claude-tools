# Claude Code Global Configuration

Global instructions for Claude Code across all projects.

## Skills

Skills extend Claude Code with specialized workflows. Each skill has YAML frontmatter with `name` and `description` that determine when it triggers.

**Before using a skill**: Read its `SKILL.md` file completely and follow the defined workflow.

### Installed Skills

| Skill | Purpose | Location |
|-------|---------|----------|
| code-review | Per-change code review (C#, Python) - correctness, safety, patterns | `~/.claude/skills/code-review/` |
| architecture-review | System-level architectural assessment - resilience, observability, design | `~/.claude/skills/architecture-review/` |
| eval-framework | Capture, store, compare evaluations for consistency measurement | `~/.claude/skills/eval-framework/` |
| docgen | Generate .NET documentation (architecture, API, domain models) | `~/.claude/skills/docgen/` |
| azure-devops | Work items, pipelines, repositories via Azure CLI | `~/.claude/skills/azure-devops/` |
| github | Issues, pull requests, repositories via GitHub CLI | `~/.claude/skills/github/` |
| wsr-generator | Weekly status reports from git and ADO activity | `~/.claude/skills/wsr-generator/` |
| ui-design-team | Cross-platform UI design and implementation | `~/.claude/skills/ui-design-team/` |
| xtconnect-pi | Debug/manage XTConnect Raspberry Pi nodes - SSH, serial port, deployment | `~/.claude/skills/xtconnect-pi/` |
| findings | **Persistent memory** - Cross-session discoveries, tech debt, handoff notes | `~/.claude/skills/findings/` |

## Installed Agents

Agents provide expert personas for complex reasoning tasks. Located in `~/.claude/agents/`.

| Agent | Purpose | Specialty |
|-------|---------|-----------|
| software-architect | System design, ADRs, technology decisions | Forward-looking design |
| database-architect | Schema design, EF Core, query optimization | Data modeling |
| senior-code-reviewer | Deep code analysis, subtle bugs, teaching | Expert judgment |
| unit-test-architect | Test strategy, testability, coverage | Test-driven quality |
| devops-engineer | CI/CD, infrastructure, deployment | Automation & operations |
| security-engineer | Threat modeling, vulnerability analysis | Security & compliance |

## Development Lifecycle Integration

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         FULL DEVELOPMENT LIFECYCLE                          │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  ┌─────────────┐   ┌─────────────┐   ┌─────────────┐   ┌─────────────┐    │
│  │   DESIGN    │   │  IMPLEMENT  │   │    TEST     │   │   DEPLOY    │    │
│  ├─────────────┤   ├─────────────┤   ├─────────────┤   ├─────────────┤    │
│  │ software-   │   │ code-review │   │ unit-test-  │   │ devops-     │    │
│  │ architect   │──►│ skill       │──►│ architect   │──►│ engineer    │    │
│  │             │   │      │      │   │             │   │      │      │    │
│  │ architecture│   │      ▼      │   │             │   │      ▼      │    │
│  │ -review     │   │ senior-code │   │             │   │ security-   │    │
│  │ skill       │   │ -reviewer   │   │             │   │ engineer    │    │
│  └─────────────┘   └─────────────┘   └─────────────┘   └─────────────┘    │
│                                                                             │
│  ◄──────────────────── Continuous Feedback Loop ────────────────────────►  │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘
```

## Tool Selection Matrix

| User Request | Tool | Type |
|--------------|------|------|
| "Review this PR" / "Review my changes" | `code-review` | Skill |
| "This code feels wrong" / "Deep review" | `senior-code-reviewer` | Agent |
| "Review the architecture" / "Assess tech debt" | `architecture-review` | Skill |
| "How should I design X?" / "Should we use Y?" | `software-architect` | Agent |
| "Does this follow Clean Architecture?" | `architecture-review` | Skill |
| "Create an ADR for this decision" | `software-architect` | Agent |
| "Design the database schema" | `database-architect` | Agent |
| "Map my domain model to EF Core" | `database-architect` | Agent |
| "My queries are slow / N+1 issues" | `database-architect` | Agent |
| "Plan a database migration" | `database-architect` | Agent |
| "Add tests for this code" | `unit-test-architect` | Agent |
| "This code is hard to test" | `unit-test-architect` | Agent |
| "Set up CI/CD pipeline" | `devops-engineer` | Agent |
| "Create deployment checklist" | `devops-engineer` | Agent |
| "Review for security issues" | `security-engineer` | Agent |
| "Create a threat model" | `security-engineer` | Agent |
| "Generate documentation" | `docgen` | Skill |
| "Create work items" | `azure-devops` / `github` | Skill |
| "Connect to Pi" / "Debug Pi node" | `xtconnect-pi` | Skill |
| "Check serial port" / "Monitor RS-485" | `xtconnect-pi` | Skill |
| "Verify master image" / "Check deployment" | `xtconnect-pi` | Skill |
| "Remember this" / "Capture finding" | `findings` | Skill |
| "What did I find" / "Load context" | `findings` | Skill |
| "Session handoff" / "Save session" | `findings` | Skill |

## Skills vs Agents

| Aspect | Skills | Agents |
|--------|--------|--------|
| **Purpose** | Structured workflows with reference materials | Expert personas with reasoning approaches |
| **Context** | Load checklists, patterns, best practices | Apply expert judgment, deep analysis |
| **Best for** | Systematic, repeatable processes | Complex problems requiring expertise |
| **Location** | `~/.claude/skills/` | `~/.claude/agents/` |
| **Examples** | code-review, architecture-review | software-architect, security-engineer |

## Common Workflows

**Assessing a new codebase:**
1. `architecture-review` skill → Full assessment
2. `software-architect` agent → ADRs for findings
3. `azure-devops` skill → Create work items

**Reviewing a complex PR:**
1. `code-review` skill → Systematic checklist
2. `senior-code-reviewer` agent → Deep analysis (if needed)
3. `unit-test-architect` agent → Test coverage

**Designing a new feature:**
1. `software-architect` agent → Design & ADR
2. (implement)
3. `code-review` skill → Review implementation

**Setting up a new service:**
1. `software-architect` agent → Architecture design
2. `devops-engineer` agent → CI/CD pipeline
3. `security-engineer` agent → Threat model
4. (implement)
5. `code-review` skill → Review code

**Security assessment:**
1. `architecture-review` skill → Identify security gaps
2. `security-engineer` agent → Threat model & assessment
3. `azure-devops` skill → Create security work items

**Improving test coverage:**
1. `unit-test-architect` agent → Testability assessment
2. (refactor if needed)
3. `unit-test-architect` agent → Write tests
4. `devops-engineer` agent → CI integration

**Designing a new data model:**
1. `software-architect` agent → Domain model design
2. `database-architect` agent → Schema design & EF Core mapping
3. `database-architect` agent → Migration strategy
4. `devops-engineer` agent → Migration deployment

**Optimizing database performance:**
1. `database-architect` agent → Query analysis & optimization
2. `database-architect` agent → Index strategy
3. `devops-engineer` agent → Apply changes to production

### Skill Invocation

Skills trigger automatically based on their `description` in YAML frontmatter. You can also invoke explicitly:
- "Use the docgen skill to document this project"
- "Read ~/.claude/skills/azure-devops/SKILL.md and query my work items"

### Work Item Platform Selection

When asked to create/query work items, bugs, tasks, or issues, detect the platform:

```bash
python3 ~/.claude/skills/detect-platform.py
```

**Rules (in priority order):**
1. If `.ado/config.json` exists → **Azure DevOps** (always wins)
2. If Azure DevOps remote exists → **Azure DevOps**
3. If GitHub remote exists → **GitHub**

Many repos have both GitHub and Azure DevOps remotes. GitHub is for code sharing only; Azure DevOps is the primary work item tracker.

## Global Preferences

### Code Style
- Primary language: C#/.NET
- Architecture: Clean Architecture, Domain-Driven Design
- Patterns: SOLID, dependency injection, composition
- Features: Modern C# (pattern matching, nullable reference types)

### Communication
- Technical accuracy over simplicity
- Explain design decisions and tradeoffs
- Include usage examples for APIs
- Proactive risk identification

### Output
- Create files for anything >20 lines
- Use meaningful commit-style descriptions
- Include work item references (AB#1234) when applicable

## Project Overrides

Project-level `CLAUDE.md` files override these global settings.

## Troubleshooting

### Skill not triggering
1. Check skill's YAML frontmatter has correct `description` with triggers
2. Verify skill folder exists with SKILL.md
3. Invoke explicitly: "Read ~/.claude/skills/{name}/SKILL.md and..."

### Azure CLI issues
```bash
az --version                    # Check installed
az extension list               # Check devops extension
az login                        # Re-authenticate
```

### GitHub CLI issues
```bash
gh --version                    # Check installed
gh auth status                  # Check authentication
gh auth login                   # Re-authenticate
```

## Python Testing Workflow

When running Python tests for skills or projects, use the universal test runner to handle virtual environment setup automatically.

### Running Tests

```bash
# Run tests for a skill/project directory
./scripts/run_python_tests.sh skills/azure-devops/scripts

# Run with additional pytest arguments
./scripts/run_python_tests.sh skills/azure-devops/scripts -v --tb=long
./scripts/run_python_tests.sh skills/azure-devops/scripts -k "test_parse"
./scripts/run_python_tests.sh skills/azure-devops/scripts --cov=.
```

### What the Test Runner Does

1. **Detects dependency file** (`pyproject.toml` or `requirements.txt`)
2. **Creates `.venv`** if it doesn't exist
3. **Installs dependencies** (cached based on file checksum)
4. **Runs pytest** with the project directory in PYTHONPATH

### Adding Tests to a Skill

1. Create `pyproject.toml` with test dependencies:
```toml
[project]
name = "my-skill-scripts"
version = "1.0.0"
dependencies = []

[project.optional-dependencies]
test = ["pytest>=7.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

2. Create `tests/` directory with `test_*.py` files
3. Run: `./scripts/run_python_tests.sh skills/my-skill/scripts`

### Key Points for Agents

- **Always use the test runner** - Don't manually create venvs or run pytest directly
- **Tests are isolated** - Each skill has its own `.venv` directory
- **Dependencies are cached** - Subsequent runs skip install if deps haven't changed
- **PYTHONPATH is set** - Local imports work automatically

## Feature Branch Workflow

Use the `feature` command for streamlined branch management with Azure DevOps integration.

### Setup

Add to your shell profile (`~/.zshrc` or `~/.bashrc`):

```bash
# Feature branch workflow
alias feature="$HOME/source/tools/claude-tools/scripts/feature.sh"
```

Then reload: `source ~/.zshrc`

### Quick Reference

```bash
feature start 1234              # Create branch from work item (auto-fetches title)
feature start 1234 'add-login'  # Create with custom description
feature pr                      # Push and create PR
feature pr --draft              # Create draft PR
feature status                  # Show branch/PR status
feature finish                  # Merge PR and cleanup
feature cleanup                 # Delete merged branches
feature list                    # List feature branches and PRs
```

### Typical Workflow

```bash
# 1. Start work on a task
feature start 1234
# Creates: feature/AB#1234-task-title-from-ado

# 2. Make changes, commit normally
git add . && git commit -m "Add the feature"
# Pre-commit hook auto-appends AB#1234

# 3. Create PR when ready
feature pr

# 4. After review/approval, merge and cleanup
feature finish
```

### Branch Naming

The `feature start` command:
1. Fetches work item title from Azure DevOps
2. Slugifies it (lowercase, hyphens, truncated)
3. Creates branch: `{prefix}/AB#{id}-{slug}`

Prefixes by work item type:
- `feature/` - User Stories, Features (default)
- `fix/` - Bugs
- `task/` - Tasks

### Pre-commit Integration

The workflow integrates with pre-commit hooks:
- **Branch protection**: Prevents accidental commits to main
- **Work item linking**: Auto-appends `AB#1234` to commit messages
- **Secret detection**: Scans for leaked credentials

Bypass when needed: `git commit --no-verify -m "message"`

### For Agents

When helping users with git workflows:
1. **Use `feature start`** when beginning work on a work item
2. **Use `feature pr`** when code is ready for review
3. **Use `feature status`** to check current state
4. **Remember**: Pre-commit hooks auto-link work items

## Session Continuity (Persistent Memory)

The `findings` skill provides cross-session memory. **Use this to remember discoveries between conversations.**

### How It Works

```
┌─────────────────────────────────────────────────────────────────┐
│                    THREE-TIER MEMORY MODEL                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  TodoWrite (Session)     Findings (Persistent)    ADO (Official) │
│  ─────────────────────   ────────────────────    ─────────────── │
│  • Task tracking         • Discoveries           • Work items    │
│  • This conversation     • Tech debt             • Sprint work   │
│  • Ephemeral             • Cross-session         • Team-visible  │
│                          • Git-tracked           • Managed       │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

### When to Use Each

| Tool | When to Use |
|------|-------------|
| **TodoWrite** | Tracking tasks within THIS conversation (still use this!) |
| **Findings** | Discoveries that should persist to next session |
| **ADO Work Items** | Official work that needs team tracking |

### Session Start Protocol

At the beginning of significant work sessions, consider loading context:

```bash
# Load previous session context
python3 ~/.claude/skills/findings/scripts/session_context.py --load

# See what's ready to work on
python3 ~/.claude/skills/findings/scripts/query_findings.py --ready
```

### During Session: Capture Discoveries

When you discover something worth remembering:

```bash
python3 ~/.claude/skills/findings/scripts/query_findings.py --capture \
  --title "N+1 query in OrderService.GetAllWithDetails" \
  --severity medium \
  --type discovery \
  --category performance \
  --file "src/Services/OrderService.cs" \
  --line 145
```

**Capture when you find:**
- Performance issues (N+1 queries, inefficient algorithms)
- Security concerns
- Code smells or tech debt
- Bugs that aren't immediate fixes
- Architecture observations
- Questions to investigate later

### Session End Protocol

Before ending a significant session, save context:

```bash
python3 ~/.claude/skills/findings/scripts/session_context.py --save \
  --notes "Fixed the N+1 in GetAll, still need to address GetHistory" \
  --questions "Should we use Include() or explicit loading?"
```

### Findings → ADO Promotion

When a finding should become official work:

```bash
# 1. Create ADO work item
az boards work-item create --type "Task" --title "Fix N+1 query"

# 2. Link finding to it
python3 ~/.claude/skills/findings/scripts/query_findings.py \
  --promote f-abc123 --promote-to AB#5678
```

### Key Commands

```bash
# Query
python3 ~/.claude/skills/findings/scripts/query_findings.py --open      # Open findings
python3 ~/.claude/skills/findings/scripts/query_findings.py --ready     # Ready to work
python3 ~/.claude/skills/findings/scripts/query_findings.py --search X  # Search
python3 ~/.claude/skills/findings/scripts/query_findings.py --stats     # Statistics

# Capture
python3 ~/.claude/skills/findings/scripts/query_findings.py --capture --title "..." --severity medium

# Update
python3 ~/.claude/skills/findings/scripts/query_findings.py --resolve f-abc123
python3 ~/.claude/skills/findings/scripts/query_findings.py --promote f-abc123 --promote-to AB#1234

# Session
python3 ~/.claude/skills/findings/scripts/session_context.py --load     # Start session
python3 ~/.claude/skills/findings/scripts/session_context.py --save     # End session
python3 ~/.claude/skills/findings/scripts/session_context.py --onboard  # Full context dump
```

### Integration with Reviews

After architecture or code reviews, capture findings:

```bash
# During review, capture each significant finding
python3 ~/.claude/skills/findings/scripts/query_findings.py --capture \
  --title "Thread safety issue in StateManager" \
  --severity critical \
  --type discovery \
  --category thread-safety \
  --during "architecture-review"
```

This ensures discoveries from reviews don't get lost between sessions.

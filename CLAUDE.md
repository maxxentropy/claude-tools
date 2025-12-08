# Claude Code Global Configuration

This file configures Claude Code behavior across all projects on this machine.

---

## Critical Instructions

**BEFORE executing any task that matches a skill trigger below, you MUST:**
1. Read the skill's SKILL.md file completely
2. Follow the workflow defined in that file
3. Use the scripts and templates provided

Do not improvise or use general knowledge when a skill exists for the task.

---

## Skills Registry

Skills extend Claude Code with specialized workflows, scripts, and templates.

| Skill | Triggers | Location |
|-------|----------|----------|
| [Documentation Generator](#documentation-generator) | `generate docs`, `document this`, `create documentation` | `~/.claude/skills/docgen/` |
| [Azure DevOps](#azure-devops) | `ado`, `azure devops`, `work item`, `pipeline` | `~/.claude/skills/azure-devops/` |
| [WSR Generator](#wsr-generator) | `wsr`, `dostatus`, `weekly report`, `status entry` | `~/.claude/skills/wsr-generator/` |

---

### Documentation Generator

**Location:** `~/.claude/skills/docgen/SKILL.md`

**Triggers:** `generate docs`, `document this`, `create documentation`, `write docs for`

**Purpose:** Generate comprehensive documentation for .NET codebases including architecture diagrams, API references, domain models, and getting started guides.

**Prerequisites:** Must be in a .NET solution directory

**Key Scripts:**
- `scan_dotnet.py` - Analyze project structure and patterns
- `find_endpoints.py` - Extract API endpoints

---

### Azure DevOps

**Location:** `~/.claude/skills/azure-devops/SKILL.md`

**Triggers:** `ado`, `azure devops`, `work item`, `create task`, `create bug`, `query work items`, `pipeline`, `set up ado`

**Purpose:** Integrate with Azure DevOps for work item management, queries, and pipeline operations.

**Prerequisites:** 
- Azure CLI installed with devops extension
- Authenticated via `az login`
- Project configured (`.ado/config.json`) or will run configuration wizard

**Key Scripts:**
- `check-prerequisites.py` - Verify CLI and authentication
- `discover-project.py` - Scan project structure (areas, iterations, teams)
- `query-work-items.py` - Query with presets or custom WIQL

**Configuration:** Per-repo config stored in `.ado/config.json` (gitignored)

---

### WSR Generator

**Location:** `~/.claude/skills/wsr-generator/SKILL.md`

**Triggers:** `wsr`, `dostatus`, `weekly report`, `status entry`, `what did I complete`

**Purpose:** Generate weekly status report entries from git history and Azure DevOps activity.

**Prerequisites:**
- Azure DevOps skill must be configured for current repo
- Must be in a git repository with commit history

**Key Scripts:**
- `gather-git-activity.py` - Extract commits with work item references
- `gather-ado-activity.py` - Query ADO for work items and pipelines

**Depends On:** Azure DevOps skill

---

## Adding New Skills

When installing a new skill:

1. Copy skill folder to `~/.claude/skills/{skill-name}/`
2. Add entry to the Skills Registry table above
3. Add a detail section following this template:

```markdown
### {Skill Name}

**Location:** `~/.claude/skills/{skill-name}/SKILL.md`

**Triggers:** `trigger1`, `trigger2`, `trigger3`

**Purpose:** {One sentence description}

**Prerequisites:** {What must be true before using}

**Key Scripts:** {If any}
- `script1.py` - Description
- `script2.py` - Description

**Depends On:** {Other skills required, if any}
```

---

## Global Preferences

### Code Style
- Primary language: C#/.NET
- Follow Clean Architecture and DDD principles
- Prefer dependency injection and composition
- Use modern C# features (pattern matching, nullable reference types)

### Communication
- Technical accuracy over simplicity
- Explain design decisions and tradeoffs
- Include usage examples for APIs
- Proactive risk identification

### Output
- Create files rather than just showing code (for anything >20 lines)
- Use meaningful commit-style messages when describing changes
- Include work item references (AB#1234) in commit messages when applicable

---

## Project-Specific Overrides

Individual repositories can have their own `CLAUDE.md` in the repo root that:
- Adds project-specific context
- Overrides global preferences
- Defines project-specific conventions

Project-level settings take precedence over this global file.

---

## Installed Skills Checklist

Use this to track what's installed:

- [x] docgen - Documentation Generator
- [x] azure-devops - Azure DevOps Integration  
- [x] wsr-generator - Weekly Status Reports

---

## Troubleshooting

### Skill not being used
1. Check triggers match what you said
2. Verify skill folder exists: `ls ~/.claude/skills/{skill-name}/`
3. Verify SKILL.md exists: `cat ~/.claude/skills/{skill-name}/SKILL.md`
4. Be explicit: "Read ~/.claude/skills/{skill-name}/SKILL.md and then..."

### Azure CLI issues
```bash
az --version                    # Check installed
az extension list               # Check devops extension
az login                        # Re-authenticate
az account show                 # Verify logged in
```

### Git activity not found
```bash
git config user.email           # Check author email
git log --oneline -5            # Verify commits exist
```

# Claude Code Global Configuration

Global instructions for Claude Code across all projects.

## Skills

Skills extend Claude Code with specialized workflows. Each skill has YAML frontmatter with `name` and `description` that determine when it triggers.

**Before using a skill**: Read its `SKILL.md` file completely and follow the defined workflow.

### Installed Skills

| Skill | Purpose | Location |
|-------|---------|----------|
| docgen | Generate .NET documentation (architecture, API, domain models) | `skills/docgen/` |
| azure-devops | Work items, pipelines, repositories via Azure CLI | `skills/azure-devops/` |
| wsr-generator | Weekly status reports from git and ADO activity | `skills/wsr-generator/` |
| ui-design-team | Cross-platform UI design and implementation | `skills/ui-design-team/` |

### Skill Invocation

Skills trigger automatically based on their `description` in YAML frontmatter. You can also invoke explicitly:
- "Use the docgen skill to document this project"
- "Read skills/azure-devops/SKILL.md and query my work items"

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
3. Invoke explicitly: "Read skills/{name}/SKILL.md and..."

### Azure CLI issues
```bash
az --version                    # Check installed
az extension list               # Check devops extension
az login                        # Re-authenticate
```

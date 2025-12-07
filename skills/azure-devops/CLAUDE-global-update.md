# Global Claude Configuration

This file provides global instructions inherited by all projects under the home directory.

## Shared Skills Library

A library of reusable skills is available at `~/.claude/skills/`.

When a task matches one of these skills, read the SKILL.md file and follow its instructions.

### Available Skills

| Skill | Location | Use When |
|-------|----------|----------|
| docgen | `~/.claude/skills/docgen/SKILL.md` | Generating documentation for codebases |
| azure-devops | `~/.claude/skills/azure-devops/SKILL.md` | Interacting with Azure DevOps (work items, pipelines, repos) |

### How to Use Skills

1. Check if a skill applies to the current task
2. Read the skill's SKILL.md file with `cat ~/.claude/skills/{skill-name}/SKILL.md`
3. Follow the instructions in the skill file
4. Use any scripts/templates provided by the skill

### Azure DevOps Configuration Check

Before any Azure DevOps operation:
1. Check if `.ado/config.json` exists in the current repo
2. If not, run the configuration wizard from the azure-devops skill
3. Check if `.ado/project-metadata.json` exists; if not or if stale, run discovery

## Global Development Preferences

### Primary Stack
- Language: C# / .NET 8+
- Architecture: Clean Architecture, Domain-Driven Design
- Principles: SOLID, dependency injection, composition over inheritance

### Code Style
- Follow Microsoft's .NET coding conventions
- Use nullable reference types
- Prefer async/await for I/O operations
- Include XML documentation for public APIs

### Project Structure Expectations
Typical .NET projects follow Clean Architecture:
```
ProjectName/
├── src/
│   ├── ProjectName.Domain/         # Entities, value objects, domain events
│   ├── ProjectName.Application/    # Use cases, interfaces, DTOs
│   ├── ProjectName.Infrastructure/ # EF Core, external services
│   └── ProjectName.Api/            # Controllers, middleware
└── tests/
```

## Notes

- Project-specific CLAUDE.md files override these global settings
- Skills can be invoked explicitly ("use the docgen skill") or implicitly when the task matches
- Azure DevOps configuration is per-repo (stored in .ado/ which should be gitignored)

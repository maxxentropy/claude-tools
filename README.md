# Claude Tools

Reusable skills and utilities for Claude Code.

## Structure

```
claude-tools/
├── CLAUDE.md                    # Global config (symlink to ~/CLAUDE.md)
├── bin/
│   └── claude-skills            # Skill management helper
└── skills/
    ├── docgen/                  # Documentation generator
    ├── azure-devops/            # Azure DevOps integration
    └── wsr-generator/           # Weekly status reports
```

## Installation

```bash
# Symlink skills directory (if not already done)
ln -sf ~/source/claude-tools/skills ~/.claude/skills

# Symlink global CLAUDE.md
ln -sf ~/source/claude-tools/CLAUDE.md ~/CLAUDE.md

# Add helper to PATH (optional)
mkdir -p ~/bin
ln -sf ~/source/claude-tools/bin/claude-skills ~/bin/claude-skills
```

### Verify

```bash
claude-skills check
```

## Skills

| Skill | Triggers | Purpose |
|-------|----------|---------|
| docgen | `generate docs`, `document this` | Generate .NET documentation |
| azure-devops | `ado`, `work item`, `pipeline` | Azure DevOps integration |
| wsr-generator | `wsr`, `dostatus`, `weekly report` | Weekly status reports |

### Documentation Generator (`docgen`)
Generate comprehensive documentation for .NET codebases including architecture diagrams, API references, domain models, and getting started guides.

### Azure DevOps (`azure-devops`)
Integrate with Azure DevOps for work item management, queries, and pipeline operations. Requires Azure CLI with devops extension.

### WSR Generator (`wsr-generator`)
Generate weekly status report entries from git history and ADO activity. Correlates commits to work items and formats output per your WSR template. Depends on azure-devops skill.

## Helper Commands

```bash
claude-skills list              # List installed skills
claude-skills check             # Verify installations  
claude-skills info <skill>      # Show skill details
claude-skills triggers          # List all trigger words
```

## Adding New Skills

1. Create folder: `skills/{skill-name}/`
2. Add `SKILL.md` with workflow instructions
3. Add `scripts/`, `templates/` as needed
4. Update `CLAUDE.md` Skills Registry table
5. Run `claude-skills check`

## Design Principles

- **Skills provide infrastructure, Claude does reasoning** - Scripts output JSON, Claude interprets
- **No API costs** - Uses Claude Pro subscription via Claude Code  
- **Per-repo configuration** - Skills adapt to different projects
- **Read SKILL.md first** - Claude must read instructions before acting

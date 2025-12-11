# Claude Tools

Reusable skills for Claude Code.

## Quick Start

```bash
# Clone repo
git clone https://github.com/YOUR_USERNAME/claude-tools.git ~/source/claude-tools

# Create symlinks
ln -s ~/source/claude-tools/skills ~/.claude/skills
ln -s ~/source/claude-tools/CLAUDE.md ~/CLAUDE.md
```

## Structure

```
claude-tools/
├── CLAUDE.md                    # Global configuration
├── README.md
└── skills/
    ├── docgen/                  # .NET documentation generator
    │   ├── SKILL.md
    │   ├── scripts/
    │   └── references/
    ├── azure-devops/            # Azure DevOps integration
    │   ├── SKILL.md
    │   └── scripts/
    ├── wsr-generator/           # Weekly status reports
    │   ├── SKILL.md
    │   ├── scripts/
    │   └── assets/
    └── ui-design-team/          # Cross-platform UI design
        ├── SKILL.md
        ├── references/
        └── assets/
```

## Skills

### docgen
Generate documentation for .NET codebases: architecture diagrams, API references, domain models.

**Triggers**: `generate docs`, `document this`, `create documentation`

### azure-devops
Work item management, pipeline monitoring, repository operations via Azure CLI.

**Triggers**: `ado`, `azure devops`, `work item`, `pipeline`

**Requires**: Azure CLI with devops extension, `az login`

### wsr-generator
Generate weekly status reports from git history and Azure DevOps activity.

**Triggers**: `wsr`, `dostatus`, `weekly report`, `status entry`

**Requires**: azure-devops skill configured, git repository

### ui-design-team
Cross-platform UI design and implementation specialists for Web (HTML/CSS), XAML (WPF/WinUI/MAUI), Blazor, and Python GUI.

**Triggers**: `UI design`, `color scheme`, `layout`, `component styling`, `XAML`, `Blazor components`

## Skill Anatomy

Each skill follows the standard structure:

```
skill-name/
├── SKILL.md          # Required: Instructions with YAML frontmatter
├── scripts/          # Optional: Executable Python/Bash scripts
├── references/       # Optional: Documentation loaded on-demand
└── assets/           # Optional: Templates, files for output
```

### YAML Frontmatter (Required)

```yaml
---
name: skill-name
description: |
  What the skill does and WHEN to use it.
  Include trigger words - this is what Claude reads to decide activation.
---
```

## Adding Skills

1. Create `skills/{name}/SKILL.md` with frontmatter
2. Add scripts, references, assets as needed
3. Skills auto-register via frontmatter description

## Design Principles

- **Skills provide infrastructure, Claude does reasoning**: Scripts output JSON, Claude interprets
- **Progressive disclosure**: SKILL.md loads always, references load on-demand
- **Concise is key**: Only include what Claude doesn't already know

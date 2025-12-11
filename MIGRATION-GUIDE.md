# Migration Guide: claude-tools v1 → v2

This document details the changes made to modernize the claude-tools repository to follow skill-creator best practices.

## Summary of Changes

### 1. Added YAML Frontmatter (Critical)

All SKILL.md files now have required YAML frontmatter:

```yaml
---
name: skill-name
description: |
  What the skill does and WHEN to use it.
  Trigger words go here - Claude reads this to decide when to activate.
---
```

**Why**: The frontmatter `description` is the primary mechanism for skill triggering. Without it, Claude cannot automatically determine when to use a skill.

### 2. Removed Redundant Files

| Removed | Reason |
|---------|--------|
| `README.md` (in each skill) | Per skill-creator: "Do NOT create README.md" |
| `CLAUDE-global-update.md` | Redundant - frontmatter description handles triggering |
| `profiles/.gitkeep` | Empty directory removed |

### 3. Standardized Directory Names

| Old | New | Reason |
|-----|-----|--------|
| `prompts/` | `references/` | Matches skill-creator standard |
| `templates/` | `assets/` | Matches skill-creator standard |

### 4. Simplified Global CLAUDE.md

**Before**: Detailed Skills Registry table with triggers duplicating skill descriptions.

**After**: Simple table referencing skills. Triggers are in each skill's frontmatter.

### 5. Added ui-design-team Skill

New skill with:
- UX/Visual Design specialist (design authority)
- Web Platform specialist (HTML/CSS)
- XAML Platform specialist (WPF/WinUI/MAUI)
- Blazor Platform specialist
- Python Platform specialist (PyQt, Tkinter, etc.)

## File Structure Comparison

### Before (v1)
```
claude-tools/
├── CLAUDE.md                    # Large with duplicate trigger info
├── INSTALL.md
├── README.md
├── bin/
│   └── claude-skills
└── skills/
    ├── docgen/
    │   ├── SKILL.md             # No YAML frontmatter
    │   ├── scripts/
    │   └── prompts/             # Non-standard name
    ├── azure-devops/
    │   ├── SKILL.md             # No YAML frontmatter
    │   ├── README.md            # Unnecessary
    │   ├── CLAUDE-global-update.md  # Redundant
    │   ├── scripts/
    │   └── profiles/
    └── wsr-generator/
        ├── SKILL.md             # No YAML frontmatter
        ├── README.md            # Unnecessary
        ├── CLAUDE-global-update.md  # Redundant
        ├── scripts/
        └── templates/           # Non-standard name
```

### After (v2)
```
claude-tools/
├── CLAUDE.md                    # Simplified
├── INSTALL.md                   # Simplified
├── README.md                    # Simplified
└── skills/
    ├── docgen/
    │   ├── SKILL.md             # With YAML frontmatter
    │   ├── scripts/
    │   └── references/          # Standard name
    ├── azure-devops/
    │   ├── SKILL.md             # With YAML frontmatter
    │   └── scripts/
    ├── wsr-generator/
    │   ├── SKILL.md             # With YAML frontmatter
    │   ├── scripts/
    │   └── assets/              # Standard name
    └── ui-design-team/          # NEW
        ├── SKILL.md
        ├── references/
        └── assets/
```

## Migration Steps

### Option A: Start Fresh (Recommended)

1. Backup your current repo
2. Replace contents with v2 structure
3. Commit: "Modernize to skill-creator v2 standards"

### Option B: Incremental Migration

1. Add YAML frontmatter to each SKILL.md:
   ```bash
   # For each skill, prepend:
   ---
   name: skill-name
   description: |
     Description with trigger words...
   ---
   ```

2. Rename directories:
   ```bash
   mv skills/docgen/prompts skills/docgen/references
   mv skills/wsr-generator/templates skills/wsr-generator/assets
   ```

3. Remove redundant files:
   ```bash
   rm skills/*/README.md
   rm skills/*/CLAUDE-global-update.md
   rm -rf skills/azure-devops/profiles
   ```

4. Add ui-design-team skill:
   ```bash
   cp -r path/to/ui-design-team skills/
   ```

5. Update global CLAUDE.md with simplified version

## Breaking Changes

### Trigger Behavior

**Before**: Triggers defined in global CLAUDE.md table.

**After**: Triggers defined in each skill's YAML frontmatter description.

If you have workflows that depend on the old trigger table, update them to reference the skill's description field instead.

### bin/claude-skills Script

The helper script referenced the old structure. If you use it, update or remove it. The skill-creator provides `package_skill.py` for packaging.

## Verification

After migration, verify:

1. Each skill has YAML frontmatter with `name` and `description`
2. No README.md files in skill directories
3. Directory names are `references/` and `assets/` (not `prompts/` or `templates/`)
4. Global CLAUDE.md is simplified

Test by asking Claude Code: "What skills do you have access to?"

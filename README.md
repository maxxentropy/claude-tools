# Claude Tools

A shared library of skills and utilities for Claude Code and Claude.ai.

## What's Here

```
claude-tools/
├── CLAUDE.md              # Global instructions (install to ~/)
├── skills/
│   └── docgen/            # Documentation generator skill
│       ├── SKILL.md       # Main skill instructions
│       ├── scripts/       # Helper scripts (Python/Bash)
│       ├── templates/     # Document templates
│       └── prompts/       # Analysis prompts
└── INSTALL.md             # Setup instructions
```

## Skills

| Skill | Description | Status |
|-------|-------------|--------|
| docgen | Generate comprehensive documentation for .NET codebases | In Development |

## Quick Start

See [INSTALL.md](INSTALL.md) for setup instructions.

## Usage

Once installed, Claude Code will automatically have access to these skills from any project directory. Just ask:

- "Generate documentation for this project"
- "Use the docgen skill to document this codebase"

Claude will read the appropriate SKILL.md and follow its instructions.

## Adding New Skills

1. Create a new folder under `skills/`
2. Add a `SKILL.md` with instructions
3. Add any supporting scripts, templates, or prompts
4. Update the global `CLAUDE.md` to reference the new skill

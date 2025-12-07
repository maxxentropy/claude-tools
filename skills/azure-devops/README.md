# Azure DevOps Skill

Integration with Azure DevOps for work item management, pipeline monitoring, and repository operations.

## Features

- **Configuration Wizard**: Interactive setup that guides you through connecting to your organization
- **Project Discovery**: Automatically scans and caches area paths, iterations, teams, work item types, pipelines, and repositories
- **Work Item Queries**: Preset queries for common scenarios (my active items, changed this week, etc.)
- **Multi-Project Support**: Configure each repository independently

## Installation

1. Copy the `azure-devops` folder to your skills directory:
   ```bash
   cp -r azure-devops ~/.claude/skills/
   ```

2. Make scripts executable:
   ```bash
   chmod +x ~/.claude/skills/azure-devops/scripts/*.py
   ```

3. Update your global `~/CLAUDE.md` to include the skill (see `CLAUDE-global-update.md`)

## Prerequisites

- Azure CLI: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli
- Azure DevOps extension: `az extension add --name azure-devops`
- Authentication: `az login`

## Quick Start

1. Navigate to any git repository
2. Ask Claude: "Set up Azure DevOps for this project"
3. Follow the wizard prompts
4. Once configured, ask: "Show me my active work items"

## Files

| File | Purpose |
|------|---------|
| `SKILL.md` | Main skill instructions with CLI reference |
| `scripts/check-prerequisites.py` | Verify Azure CLI and auth |
| `scripts/discover-project.py` | Scan project structure |
| `scripts/query-work-items.py` | Query work items with presets |
| `profiles/` | Global organization profiles (optional) |

## Configuration Files Created

In each repository that uses this skill:

```
your-repo/
├── .ado/
│   ├── config.json            # Connection settings
│   └── project-metadata.json  # Discovered project structure
└── .gitignore                 # .ado/ added automatically
```

## Usage Examples

```
"Set up Azure DevOps for this project"
"Show my active work items"
"What did I complete this week?"
"Show work items in the NodeService area"
"Rescan DevOps project structure"
"What pipelines are available?"
"Show recent pipeline runs"
```

## Query Presets

| Preset | Description |
|--------|-------------|
| my-active | My work items not closed/done |
| my-all | All my work items |
| changed-today | Items I changed today |
| changed-this-week | Items I changed in last 7 days |
| completed-this-week | Items I completed in last 7 days |
| recent-bugs | Bugs changed in last 14 days |
| sprint-items | Current sprint items |
| blocked | Items tagged as blocked |

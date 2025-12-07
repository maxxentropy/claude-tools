# WSR Generator Skill

Generate professional weekly status report entries from git history and Azure DevOps activity.

## Quick Start

In any git repository with Azure DevOps configured:

```
"wsr"
"dostatus"  
"weekly report"
"status entry"
```

## Prerequisites

1. **Azure DevOps skill configured** - `.ado/config.json` must exist
2. **Git repository** - Must be inside a git repo with commit history
3. **Azure CLI authenticated** - `az login` completed

## What It Does

1. **Gathers git commits** in the time range, extracting work item references (AB#1234)
2. **Queries Azure DevOps** for work items changed/completed and pipeline runs
3. **Correlates** commits to work items, building a hierarchy
4. **Generates** WSR entries in your preferred format

## Scripts

| Script | Purpose |
|--------|---------|
| `gather-git-activity.py` | Extract git commits with work item references |
| `gather-ado-activity.py` | Query ADO for work items and pipelines |

## Output Format

Generates entries matching the Weekly Status Report format:
- Title, Status, Domain, Priority, Timeline
- Objective/Background
- Solution/Approach  
- Business/Technical Impact
- Risk Assessment
- Next Steps
- Work item and commit references

## Installation

```bash
# Copy to skills directory
cp -r wsr-generator ~/.claude/skills/

# Add to global CLAUDE.md
cat >> ~/CLAUDE.md << 'EOF'

## WSR Generator Skill
Location: `~/.claude/skills/wsr-generator/SKILL.md`
Triggers: `wsr`, `dostatus`, `weekly report`, `status entry`
Requires: Azure DevOps skill configured in current repo
EOF
```

## Usage Examples

```
"Generate WSR for this week"
"What did I complete since Monday?"
"Status report for December 1-7"
"WSR covering the serial port work"
```

## Dependencies

- Python 3.8+
- Azure CLI with devops extension
- Git
- Azure DevOps skill (`.ado/config.json`)

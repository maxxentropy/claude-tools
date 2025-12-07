# Add to ~/CLAUDE.md

## WSR Generator Skill

**Location:** `~/.claude/skills/wsr-generator/SKILL.md`
**Triggers:** `wsr`, `dostatus`, `weekly report`, `status entry`

Generates weekly status report entries from git history and Azure DevOps activity.

**Prerequisites:**
- Azure DevOps skill must be configured (`.ado/config.json` exists)
- Must be in a git repository

**Capabilities:**
- Gathers git commits with work item references (AB#1234)
- Queries ADO for changed/completed work items
- Includes pipeline run statistics
- Correlates commits to work items
- Generates formatted WSR entries

**IMPORTANT:** Read `~/.claude/skills/wsr-generator/SKILL.md` before generating any status reports.

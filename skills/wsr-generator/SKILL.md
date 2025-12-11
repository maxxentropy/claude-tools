---
name: wsr-generator
description: |
  Generate professional weekly status report entries from git history and Azure DevOps activity.
  Use when asked for: wsr, dostatus, weekly report, status entry, what did I complete, 
  status update, generate report, weekly summary.
  Requires: azure-devops skill configured (.ado/config.json), git repository.
---

# Weekly Status Report Generator

Generate professional WSR entries from git history and Azure DevOps activity.

## Prerequisites

1. **Azure DevOps configured**: `.ado/config.json` must exist
2. **Git repository**: Must be inside a git repo with commit history

If not configured, run azure-devops configuration wizard first.

## Workflow

### Phase 1: Gather Data

#### 1.1 Determine Time Range

- "This week" → Last 7 days
- "Last week" → 7-14 days ago
- "Since [date]" → Custom range
- Default: Last 7 days

#### 1.2 Gather Git Activity

```bash
python3 scripts/gather-git-activity.py --since "7 days ago" --output /tmp/git-activity.json
```

Extracts commits with work item references (AB#1234, #1234, Fixes #1234).

#### 1.3 Gather ADO Activity

```bash
python3 scripts/gather-ado-activity.py --config .ado/config.json --since "7 days ago" --output /tmp/ado-activity.json
```

Queries: changed work items, completed items, pipeline runs.

#### 1.4 Correlate Data

1. Match commits to work items via AB#1234 references
2. Group tasks under parent User Stories/Features
3. Identify orphan commits (no linked work item)

### Phase 2: Analyze & Categorize

#### Domain Mapping

| Area Path Pattern | Domain |
|------------------|--------|
| **/Infrastructure/** | Infrastructure |
| **/Security/** | Security |
| **/Documentation/** | Documentation |
| **/Support/**, Bug | Support |
| Default | Development |

#### Status Determination

- All tasks Done → **Completed**
- Some Active → **In Progress**
- Has "Blocked" tag → **Blocked**

#### Priority

- Priority 1 → **High**
- Priority 2 → **Medium**
- Priority 3+ → **Low**

### Phase 3: Generate Report

Use the WSR entry template in `assets/wsr-entry-template.md`.

## WSR Entry Format

```markdown
## [Title - max 80 chars]

**Status:** [Completed | In Progress | Blocked]
**Domain:** [Development | Architecture | Infrastructure | Security | Documentation | Support]
**Priority:** [High | Medium | Low]
**Timeline:** [Date range]

### Objective/Background
[Why this work was undertaken]

### Solution/Approach
[Technical approach, key decisions]

### Business Impact
[Value delivered, improvements]

### Technical Impact
[Code quality, performance, maintainability]

### Risk Assessment & Mitigation
[Risks identified, mitigation strategies]

### Next Steps
[Follow-up actions, future phases]

**Work Items:** AB#1234, AB#1235
**Key Commits:** `abc1234` - Description
**Pipeline Status:** X runs, Y% success rate
```

## Scripts

| Script | Purpose |
|--------|---------|
| `scripts/gather-git-activity.py` | Extract commits with work item refs |
| `scripts/gather-ado-activity.py` | Query ADO for work items and pipelines |

## Quick Git Commands

```bash
# Commits in last 7 days by me
git log --since="7 days ago" --author="$(git config user.email)" --oneline

# Extract work item references
git log --since="7 days ago" --pretty=format:"%s" | grep -oE "AB#[0-9]+"
```

## Customization

**Brief summary:**
> "Generate a brief WSR for this week"

**Detailed entries:**
> "Generate comprehensive WSR with all technical details"

**Specific time ranges:**
> "WSR for last Monday through Friday"
> "Status report since January 1st"

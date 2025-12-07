# Weekly Status Report Generator Skill

Generate professional weekly status report entries from git history and Azure DevOps activity.

## Trigger Words

Activate this skill when the user says any of:
- `wsr`
- `dostatus`
- `weekly report`
- `status entry`

## Prerequisites

1. **Azure DevOps skill must be configured** for the current repository
   - Check: `.ado/config.json` exists
   - If not: Run azure-devops configuration wizard first

2. **Git repository** with commit history
   - Must be inside a git repository

## Workflow

### Phase 1: Gather Data

#### Step 1.1: Determine Time Range

Ask user or infer from context:
- "This week" → Last 7 days
- "Last week" → 7-14 days ago
- "Since [date]" → Custom range
- "Since last report" → Check for `.wsr/last-report.json`

Default: Last 7 days if not specified.

#### Step 1.2: Gather Git Activity

Run the git activity script:
```bash
python3 ~/.claude/skills/wsr-generator/scripts/gather-git-activity.py \
  --since "7 days ago" \
  --author "$(git config user.email)" \
  --output /tmp/git-activity.json
```

Or manually with git:
```bash
git log --since="7 days ago" --author="$(git config user.email)" \
  --pretty=format:'{"hash":"%h","date":"%ai","subject":"%s","body":"%b"}' \
  --no-merges
```

Extract work item references from commit messages:
- Pattern: `AB#1234` or `#1234`
- Also look for: `Fixes #1234`, `Closes AB#1234`, `Related to AB#1234`

#### Step 1.3: Gather Azure DevOps Activity

Run the ADO activity script:
```bash
python3 ~/.claude/skills/wsr-generator/scripts/gather-ado-activity.py \
  --config .ado/config.json \
  --since "7 days ago" \
  --output /tmp/ado-activity.json
```

This queries:
- Work items changed by me in the time range
- Work items completed/closed by me
- Pipeline runs (success/failure counts)

#### Step 1.4: Correlate Data

Match git commits to work items:
1. Extract work item IDs from commit messages
2. Fetch work item details for each referenced ID
3. Group commits by work item
4. Identify orphan commits (no linked work item)

Build hierarchy:
1. Group Tasks under their parent User Stories
2. Group User Stories under their parent Features/Epics
3. Create a tree of completed work

### Phase 2: Analyze & Categorize

#### Step 2.1: Categorize Work by Domain

Map work to domains based on area paths and work item tags:

| Area Path Pattern | Domain |
|------------------|--------|
| **/Infrastructure/** | Infrastructure |
| **/DevOps/**, **/Pipeline/** | Infrastructure |
| **/Security/** | Security |
| **/Documentation/**, **/Docs/** | Documentation |
| **/Architecture/** | Architecture |
| **/Support/**, **/Bug/** | Support |
| Default | Development |

Also check work item tags for domain hints.

#### Step 2.2: Determine Status

For each work item or group:
- All tasks Done/Closed → **Completed**
- Some tasks Done, some Active → **In Progress**
- Has "Blocked" tag or state → **Blocked**
- No changes this period but previously active → **On Hold**

#### Step 2.3: Assess Priority

Based on work item priority field:
- Priority 1 → **High**
- Priority 2 → **Medium**
- Priority 3-4 → **Low**

Or infer from parent item type:
- Epic/Feature work → **High**
- Bug fixes → **Medium** (unless critical)
- Tech debt/chores → **Low**

### Phase 3: Generate Report

#### Step 3.1: Choose Grouping Strategy

Options:
1. **By Work Item** - One WSR entry per significant work item
2. **By Feature/Epic** - Roll up to parent items
3. **Single Summary** - One entry covering all work

Default: Group by parent User Story or Feature, with significant items getting their own entry.

#### Step 3.2: Generate WSR Entry

For each entry, use this format:

```markdown
## [Title - max 80 chars]

**Status:** [Completed | In Progress | Blocked | On Hold]
**Domain:** [Development | Architecture | Infrastructure | Security | Documentation | Support]
**Priority:** [High | Medium | Low]
**Timeline:** [Date range or duration]

### Objective/Background
[Why this work was undertaken, context, alignment with goals]

### Solution/Approach
[Technical approach, key decisions, tools/patterns used]

### Business Impact
[Value delivered, user experience improvements, capabilities added]

### Technical Impact
[Code quality, performance, maintainability improvements]

### Risk Assessment & Mitigation
[Risks identified, how they were addressed]

### Next Steps
[Follow-up work, future phases, monitoring needs]
```

#### Step 3.3: Include Evidence

Reference specific commits:
```markdown
**Key Commits:**
- `abc1234` - Implemented retry logic for controller communication
- `def5678` - Added unit tests for parsing module
```

Reference work items:
```markdown
**Work Items:** AB#1234, AB#1235, AB#1236
```

Include pipeline stats if relevant:
```markdown
**Pipeline Status:** 15 runs, 14 successful (93% pass rate)
```

### Phase 4: Output

#### Step 4.1: Present to User

Display the generated WSR entry(ies) in chat.

#### Step 4.2: Save Report Marker (Optional)

Save a marker for "since last report" functionality:
```bash
mkdir -p .wsr
cat > .wsr/last-report.json << EOF
{
  "generatedAt": "2024-01-15T10:30:00Z",
  "periodStart": "2024-01-08",
  "periodEnd": "2024-01-15",
  "workItemsCovered": [1234, 1235, 1236]
}
EOF
```

Add to .gitignore if not present:
```bash
echo ".wsr/" >> .gitignore
```

---

## Quick Reference: Git Commands

```bash
# Commits in last 7 days by me
git log --since="7 days ago" --author="$(git config user.email)" --oneline

# Commits with stats
git log --since="7 days ago" --author="$(git config user.email)" --stat

# Extract work item references
git log --since="7 days ago" --author="$(git config user.email)" --pretty=format:"%s" | grep -oE "AB#[0-9]+"

# Count commits by day
git log --since="7 days ago" --author="$(git config user.email)" --format="%ad" --date=short | sort | uniq -c
```

## Quick Reference: ADO Queries

```bash
# My items changed this week (using azure-devops skill)
python3 ~/.claude/skills/azure-devops/scripts/query-work-items.py \
  --config .ado/config.json \
  --preset changed-this-week

# My completed items
python3 ~/.claude/skills/azure-devops/scripts/query-work-items.py \
  --config .ado/config.json \
  --preset completed-this-week
```

---

## Example Output

### Example 1: Feature Completion

```markdown
## XTConnect Serial Port Resilience Implementation

**Status:** Completed
**Domain:** Development
**Priority:** High
**Timeline:** January 8-15, 2024

### Objective/Background
Implemented robust retry and reconnection logic for serial port communication to handle intermittent connection issues reported in field deployments. This addresses reliability concerns from the agricultural monitoring use case where environmental factors can disrupt connections.

### Solution/Approach
- Implemented Polly-based retry policies with exponential backoff
- Added connection health monitoring with automatic reconnection
- Created comprehensive unit tests using mock serial ports
- Applied circuit breaker pattern to prevent cascade failures

### Business Impact
- Reduced field support calls related to connection issues
- Improved data collection reliability from 94% to 99.5%
- Enabled deployment in more challenging environments

### Technical Impact
- Added `Polly` package for resilience patterns
- Refactored `SerialPortTransport` to support async reconnection
- Increased test coverage in communication module to 87%

### Risk Assessment & Mitigation
- Risk: Retry storms during extended outages
  - Mitigation: Circuit breaker opens after 5 consecutive failures
- Risk: Data loss during reconnection
  - Mitigation: Buffer up to 1000 readings during reconnection attempts

### Next Steps
- Monitor field deployment metrics for 2 weeks
- Document operational runbook for connection troubleshooting
- Consider adding telemetry for connection health dashboard

**Work Items:** AB#1234, AB#1235, AB#1240
**Key Commits:** `a1b2c3d`, `e4f5g6h`, `i7j8k9l`
**Pipeline Status:** 8 runs, 8 successful (100% pass rate)
```

### Example 2: Multiple Small Items

```markdown
## XTConnect Maintenance & Bug Fixes

**Status:** Completed
**Domain:** Support
**Priority:** Medium
**Timeline:** January 8-15, 2024

### Objective/Background
Addressed several maintenance items and bug fixes reported during the previous sprint, focusing on parsing edge cases and configuration validation.

### Solution/Approach
- Fixed zone parser handling of empty sensor arrays (AB#1250)
- Corrected temperature unit conversion for Celsius displays (AB#1251)
- Added validation for configuration file schema (AB#1252)

### Business Impact
- Resolved 3 customer-reported issues
- Improved configuration error messages for easier troubleshooting

### Technical Impact
- Added 12 new unit tests covering edge cases
- Refactored validation to use FluentValidation consistently

### Next Steps
- Continue monitoring for related issues
- Consider adding integration tests for configuration loading

**Work Items:** AB#1250, AB#1251, AB#1252
```

---

## Customization

### Adjusting Detail Level

For quick summaries, ask:
> "Generate a brief WSR for this week"

For detailed entries, ask:
> "Generate a comprehensive WSR with all technical details"

### Specific Time Ranges

> "WSR for last Monday through Friday"
> "Status report since January 1st"
> "What did I complete yesterday?"

### Multiple Repositories

To aggregate across repos:
> "Generate WSR covering XTConnect.NodeService and XTConnect.ControllersLib"

---

## Troubleshooting

### "No Azure DevOps configuration found"
Run the azure-devops skill configuration wizard first:
```
"Set up Azure DevOps for this project"
```

### "No commits found"
- Check the author email matches: `git config user.email`
- Verify the time range includes your work
- Check you're in the right branch

### "Cannot correlate commits to work items"
- Ensure commits include `AB#1234` references
- Work items must exist in the configured ADO project

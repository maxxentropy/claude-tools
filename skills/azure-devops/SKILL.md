# Azure DevOps Integration Skill


**STOP** - If you haven't read this entire file, read it now before proceeding.
 Do NOT use general knowledge about Azure DevOps CLI. Follow these specific instructions.

Integrate with Azure DevOps for work item management, repository operations, and pipeline monitoring using the Azure CLI.

## When to Use

Use this skill when asked to:
- Query or update work items
- Check pipeline status
- List or manage repositories
- Generate reports from ADO data
- Set up Azure DevOps integration for a project

## Prerequisites Check

Before any ADO operation, verify prerequisites are met:

### Step 1: Check Azure CLI Installation

```bash
az --version
```

If not installed, direct user to: https://docs.microsoft.com/en-us/cli/azure/install-azure-cli

### Step 2: Check Azure DevOps Extension

```bash
az extension show --name azure-devops
```

If not installed:
```bash
az extension add --name azure-devops
```

### Step 3: Check Authentication

```bash
az account show
```

If not logged in:
```bash
az login
```

### Step 4: Check Project Configuration

Look for `.ado/config.json` in the current repository root.

```bash
cat .ado/config.json 2>/dev/null || echo "NOT_CONFIGURED"
```

**If NOT_CONFIGURED → Run Configuration Wizard (see below)**

---

## Configuration Wizard

Run this wizard when `.ado/config.json` does not exist or user requests reconfiguration.

### Wizard Step 1: Gather Organization Information

Ask the user:
> "What is your Azure DevOps organization URL?"
> 
> Example: `https://dev.azure.com/val-controls`

Validate the organization is accessible:
```bash
az devops project list --organization "https://dev.azure.com/ORGNAME" --output table
```

### Wizard Step 2: Select Project

If validation succeeded, list available projects:
```bash
az devops project list --organization "URL" --query "[].name" --output tsv
```

Ask the user:
> "Which project would you like to connect to?"
> 
> Available projects: [list from above]

### Wizard Step 3: Create Configuration Directory

```bash
mkdir -p .ado
echo ".ado/" >> .gitignore  # Add to gitignore if not present
```

### Wizard Step 4: Save Initial Configuration

Create `.ado/config.json`:
```json
{
  "organization": "https://dev.azure.com/val-controls",
  "project": "XTConnect",
  "configuredAt": "2024-01-15T10:30:00Z",
  "configuredBy": "user"
}
```

### Wizard Step 5: Run Discovery

After saving config, immediately run the discovery process (see below).

### Wizard Complete

Inform user:
> "Azure DevOps configuration complete. Project metadata has been discovered and saved."
> 
> Configuration: `.ado/config.json`
> Project metadata: `.ado/project-metadata.json`
>
> You can now use Azure DevOps commands. Try: "Show me my work items"

---

## Project Discovery

Discovers and caches project structure (areas, iterations, teams, work item types).

### When to Run Discovery

- After initial configuration
- When user requests: "rescan devops", "refresh ado metadata", "update devops config"
- If project-metadata.json is missing
- If metadata is older than 7 days (optional refresh prompt)

### Discovery Process

Run the discovery script:
```bash
python3 ~/.claude/skills/azure-devops/scripts/discover-project.py \
  --config .ado/config.json \
  --output .ado/project-metadata.json
```

Or manually with Azure CLI:

#### Discover Areas
```bash
az boards area project list \
  --organization "ORG_URL" \
  --project "PROJECT" \
  --output json > /tmp/areas.json
```

#### Discover Iterations
```bash
az boards iteration project list \
  --organization "ORG_URL" \
  --project "PROJECT" \
  --output json > /tmp/iterations.json
```

#### Discover Teams
```bash
az devops team list \
  --organization "ORG_URL" \
  --project "PROJECT" \
  --output json > /tmp/teams.json
```

#### Discover Work Item Types
```bash
az boards work-item type list \
  --organization "ORG_URL" \
  --project "PROJECT" \
  --output json > /tmp/wit.json
```

### Save Discovery Results

Create `.ado/project-metadata.json`:
```json
{
  "discoveredAt": "2024-01-15T10:35:00Z",
  "organization": "https://dev.azure.com/val-controls",
  "project": "XTConnect",
  "areas": [
    {
      "id": 123,
      "name": "XTConnect",
      "path": "\\XTConnect\\Area",
      "children": [
        {"id": 124, "name": "NodeService", "path": "\\XTConnect\\NodeService"},
        {"id": 125, "name": "ControllersLib", "path": "\\XTConnect\\ControllersLib"}
      ]
    }
  ],
  "iterations": [
    {
      "id": 200,
      "name": "Sprint 42",
      "path": "\\XTConnect\\Sprint 42",
      "startDate": "2024-01-08",
      "finishDate": "2024-01-21"
    }
  ],
  "teams": [
    {"id": "team-guid", "name": "XTConnect Team"}
  ],
  "workItemTypes": [
    {"name": "Epic", "icon": "icon_crown"},
    {"name": "Feature", "icon": "icon_trophy"},
    {"name": "User Story", "icon": "icon_book"},
    {"name": "Task", "icon": "icon_clipboard"},
    {"name": "Bug", "icon": "icon_bug"}
  ]
}
```

---

## Common Operations

### Load Configuration

Before any operation, load config:
```bash
CONFIG=$(cat .ado/config.json)
ORG=$(echo $CONFIG | jq -r '.organization')
PROJECT=$(echo $CONFIG | jq -r '.project')
```

Or set as defaults for session:
```bash
az devops configure --defaults \
  organization="https://dev.azure.com/val-controls" \
  project="XTConnect"
```

---

### Work Items

#### Query My Work Items
```bash
az boards query \
  --organization "$ORG" \
  --project "$PROJECT" \
  --wiql "SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType] FROM workitems WHERE [System.AssignedTo] = @Me AND [System.State] <> 'Closed' ORDER BY [System.ChangedDate] DESC" \
  --output table
```

#### Query Items Changed This Week
```bash
az boards query \
  --organization "$ORG" \
  --project "$PROJECT" \
  --wiql "SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType] FROM workitems WHERE [System.AssignedTo] = @Me AND [System.ChangedDate] >= @Today - 7 ORDER BY [System.ChangedDate] DESC" \
  --output json
```

#### Get Work Item Details
```bash
az boards work-item show \
  --organization "$ORG" \
  --id WORK_ITEM_ID \
  --output json
```

#### Query by Area Path
```bash
az boards query \
  --organization "$ORG" \
  --project "$PROJECT" \
  --wiql "SELECT [System.Id], [System.Title] FROM workitems WHERE [System.AreaPath] UNDER 'XTConnect\\NodeService'" \
  --output table
```

#### Create Work Item
```bash
az boards work-item create \
  --organization "$ORG" \
  --project "$PROJECT" \
  --type "Task" \
  --title "Task title" \
  --assigned-to "user@email.com" \
  --area "XTConnect\\NodeService" \
  --iteration "XTConnect\\Sprint 42" \
  --output json
```

#### Update Work Item
```bash
az boards work-item update \
  --organization "$ORG" \
  --id WORK_ITEM_ID \
  --state "Active" \
  --output json
```

#### Add Comment to Work Item
```bash
az boards work-item update \
  --organization "$ORG" \
  --id WORK_ITEM_ID \
  --discussion "Comment text here" \
  --output json
```

---

### Pipelines

#### List Pipelines
```bash
az pipelines list \
  --organization "$ORG" \
  --project "$PROJECT" \
  --output table
```

#### List Recent Pipeline Runs
```bash
az pipelines runs list \
  --organization "$ORG" \
  --project "$PROJECT" \
  --pipeline-ids PIPELINE_ID \
  --top 10 \
  --output table
```

#### Get Pipeline Run Details
```bash
az pipelines runs show \
  --organization "$ORG" \
  --project "$PROJECT" \
  --id RUN_ID \
  --output json
```

#### Trigger Pipeline
```bash
az pipelines run \
  --organization "$ORG" \
  --project "$PROJECT" \
  --name "PipelineName" \
  --branch "main" \
  --output json
```

---

### Repositories

#### List Repositories
```bash
az repos list \
  --organization "$ORG" \
  --project "$PROJECT" \
  --output table
```

#### Get Repository Details
```bash
az repos show \
  --organization "$ORG" \
  --project "$PROJECT" \
  --repository "RepoName" \
  --output json
```

---

### Boards & Sprints

#### Get Current Iteration
```bash
az boards iteration team list \
  --organization "$ORG" \
  --project "$PROJECT" \
  --team "TeamName" \
  --timeframe "current" \
  --output json
```

#### List Team Iterations
```bash
az boards iteration team list \
  --organization "$ORG" \
  --project "$PROJECT" \
  --team "TeamName" \
  --output table
```

---

## WIQL Query Reference

Work Item Query Language (WIQL) examples:

### Basic Queries
```sql
-- My active items
SELECT [System.Id], [System.Title], [System.State]
FROM workitems
WHERE [System.AssignedTo] = @Me
  AND [System.State] <> 'Closed'

-- Items changed today
SELECT [System.Id], [System.Title], [System.ChangedDate]
FROM workitems
WHERE [System.ChangedDate] >= @Today

-- Items in specific area
SELECT [System.Id], [System.Title]
FROM workitems
WHERE [System.AreaPath] UNDER 'Project\Area'

-- Items by type
SELECT [System.Id], [System.Title]
FROM workitems
WHERE [System.WorkItemType] = 'User Story'
```

### Date Macros
- `@Today` - Current date
- `@Today - 7` - 7 days ago
- `@StartOfWeek` - Beginning of current week
- `@StartOfMonth` - Beginning of current month

### Operators
- `=` - Equals
- `<>` - Not equals
- `>`, `>=`, `<`, `<=` - Comparisons
- `IN ('A', 'B')` - In list
- `UNDER 'Path'` - Under path (hierarchical)
- `CONTAINS 'text'` - Contains text

---

## Troubleshooting

### "You are not authorized"
```bash
# Re-authenticate
az logout
az login

# Verify correct account
az account show
```

### "Project not found"
```bash
# List available projects
az devops project list --organization "ORG_URL" --output table

# Check spelling/case sensitivity
```

### "az devops: command not found"
```bash
# Install extension
az extension add --name azure-devops
```

### Slow Queries
- Limit results with `--top N`
- Use more specific WIQL filters
- Query specific fields only

---

## Configuration Files Reference

### .ado/config.json
```json
{
  "organization": "https://dev.azure.com/val-controls",
  "project": "XTConnect",
  "defaultTeam": "XTConnect Team",
  "defaultAreaPath": "XTConnect",
  "defaultIterationPath": "XTConnect\\Sprint 42",
  "configuredAt": "2024-01-15T10:30:00Z"
}
```

### .ado/project-metadata.json
```json
{
  "discoveredAt": "2024-01-15T10:35:00Z",
  "areas": [...],
  "iterations": [...],
  "teams": [...],
  "workItemTypes": [...],
  "pipelines": [...]
}
```

### .gitignore Entry
```
# Azure DevOps local config
.ado/
```

---

## Quick Reference

| Task | Command |
|------|---------|
| My work items | `az boards query --wiql "...@Me..."` |
| Item details | `az boards work-item show --id ID` |
| Create task | `az boards work-item create --type Task --title "..."` |
| Update state | `az boards work-item update --id ID --state Active` |
| Pipeline runs | `az pipelines runs list --top 10` |
| Current sprint | `az boards iteration team list --timeframe current` |
| Rescan project | Run discovery process |

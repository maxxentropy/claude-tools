---
name: azure-devops
description: |
  Integrate with Azure DevOps for work item management, pipeline monitoring, and repository operations.
  Use when asked about: ado, azure devops, work item, create task, create bug, query work items,
  pipeline, set up ado, my work items, sprint items, what did I complete.
  Requires: Azure CLI with devops extension, authentication via az login.
---

# Azure DevOps Integration

Integrate with Azure DevOps for work items, pipelines, and repositories using Azure CLI and REST API.

## Quick Start

```bash
# Check prerequisites
python3 skills/azure-devops/scripts/check-prerequisites.py

# If not configured, run configuration wizard (see below)

# Query your active work items
python3 skills/azure-devops/scripts/query-work-items.py --preset my-active

# Query items you changed this week
python3 skills/azure-devops/scripts/query-work-items.py --preset changed-this-week --format table
```

## Prerequisites Check

Before any ADO operation, verify prerequisites:

```bash
python3 skills/azure-devops/scripts/check-prerequisites.py
```

Or manually:

```bash
# 1. Check Azure CLI installation
az --version

# 2. Check DevOps extension
az extension show --name azure-devops
# If missing: az extension add --name azure-devops

# 3. Check authentication
az account show
# If not logged in: az login

# 4. Check project configuration
cat .ado/config.json 2>/dev/null || echo "NOT_CONFIGURED"
```

**If NOT_CONFIGURED, run Configuration Wizard below**

## Configuration Wizard

Run when `.ado/config.json` doesn't exist:

### Step 1: Get Organization URL
Ask user for Azure DevOps organization URL (e.g., `https://dev.azure.com/org-name`)

Validate access:
```bash
az devops project list --organization "URL" --output table
```

### Step 2: Select Project
```bash
az devops project list --organization "URL" --query "[].name" --output tsv
```

### Step 3: Save Configuration
```bash
mkdir -p .ado
echo ".ado/" >> .gitignore
```

Create `.ado/config.json`:
```json
{
  "organization": "https://dev.azure.com/org-name",
  "project": "ProjectName",
  "configuredAt": "2024-01-15T10:30:00Z"
}
```

### Step 4: Run Discovery (REQUIRED for work item creation)
```bash
python3 skills/azure-devops/scripts/discover-project.py --config .ado/config.json --output .ado/project-metadata.json
```

**This step is critical!** It discovers the complete field schema for all work item types, including:
- Required fields for each type (Bug, Task, User Story, etc.)
- Allowed values for picklist fields (State, Priority, Severity)
- Default values
- Custom fields specific to your organization

## Query Presets

Use presets for optimized, commonly-needed queries:

```bash
python3 skills/azure-devops/scripts/query-work-items.py --preset PRESET_NAME [--format table]
```

| Preset | Description |
|--------|-------------|
| `my-active` | Active work items assigned to me |
| `my-all` | All work items assigned to me |
| `changed-today` | Items I changed today |
| `changed-this-week` | Items I changed in past 7 days |
| `completed-this-week` | Items I completed in past 7 days |
| `recent-bugs` | Bugs changed in past 14 days |
| `sprint-items` | Items in current sprint/iteration |
| `blocked` | Blocked work items |
| `created-by-me` | Items I created in past 30 days |
| `high-priority` | High priority (P1/P2) active items |

List all presets:
```bash
python3 skills/azure-devops/scripts/query-work-items.py --list-presets
```

## Best Practices

### Avoiding Rate Limits

Azure DevOps enforces rate limits of **200 TSTUs per 5-minute sliding window**. Follow these practices:

1. **Use Batch Operations**: The scripts use batch API (200 items per request) instead of N+1 queries
2. **Use Presets**: Optimized queries with date/range limiting
3. **Limit Results**: Use `--max-results` to cap returned items
4. **Honor Retry-After**: Scripts automatically handle rate limiting with exponential backoff

Reference: [Azure DevOps Rate Limits](https://learn.microsoft.com/en-us/azure/devops/integrate/concepts/rate-limits)

### Query Optimization

Follow WIQL best practices:
- Place date/range-limiting clauses early in WHERE
- Avoid `Contains` operator (use `Contains Words` instead)
- Minimize `Or` operators
- Avoid sorting on non-core fields
- Specify project scope instead of querying across projects
- Keep query execution under 30 seconds

Reference: [WIQL Syntax](https://learn.microsoft.com/en-us/azure/devops/boards/queries/wiql-syntax)

### Error Handling

The client module (`ado_client.py`) provides structured error types:

| Error Type | Meaning | Action |
|------------|---------|--------|
| `TRANSIENT` | Temporary failure | Auto-retry with backoff |
| `RATE_LIMITED` | Hit rate limit | Wait and retry (auto-handled) |
| `AUTH_FAILED` | Authentication issue | Run `az login` |
| `NOT_FOUND` | Resource doesn't exist | Check IDs/paths |
| `VALIDATION` | Bad request | Fix query/parameters |
| `PERMISSION` | Access denied | Check permissions |

## Common Operations

### Load Configuration
```bash
CONFIG=$(cat .ado/config.json)
ORG=$(echo $CONFIG | jq -r '.organization')
PROJECT=$(echo $CONFIG | jq -r '.project')
```

### Work Items

**Query with presets (recommended):**
```bash
python3 skills/azure-devops/scripts/query-work-items.py --preset my-active --format table
```

**Get specific work items by ID:**
```bash
python3 skills/azure-devops/scripts/query-work-items.py --id 1234 1235 1236
```

**Custom WIQL query:**
```bash
python3 skills/azure-devops/scripts/query-work-items.py --wiql "SELECT [System.Id], [System.Title] FROM workitems WHERE [System.AssignedTo] = @Me"
```

**Get work item details (CLI):**
```bash
az boards work-item show --org "$ORG" --id ITEM_ID --output json
```

**Create work item (ALWAYS check schema first!):**
```bash
# BEFORE creating, check .ado/project-metadata.json for:
# 1. Valid work item types (work_item_types[].name)
# 2. Required fields (work_item_types[].requiredFields)
# 3. Allowed values (work_item_types[].picklistFields)

az boards work-item create --org "$ORG" --project "$PROJECT" \
  --type "Task" --title "Title" --assigned-to "user@email.com" \
  --output json
```

**Update work item:**
```bash
# Check fieldSummary.statesByType for valid state transitions
az boards work-item update --org "$ORG" --id ITEM_ID --state "Active" --output json
```

### Work Item Description Formatting (CRITICAL)

**Azure DevOps uses HTML for descriptions, NOT markdown!**

When creating or updating work items with descriptions, ALWAYS use HTML formatting:

**Setting description via CLI:**
```bash
az boards work-item create --org "$ORG" --project "$PROJECT" \
  --type "Task" --title "Title" \
  --description "<h2>Problem</h2><p>Description of the issue.</p><h2>Solution</h2><p>How it was fixed.</p>" \
  --output json
```

**Or use --fields for the description:**
```bash
az boards work-item update --org "$ORG" --id ITEM_ID \
  --fields "System.Description=<h2>Summary</h2><p>Text here</p>"
```

#### HTML Formatting Reference

| Element | HTML | Result |
|---------|------|--------|
| Heading | `<h2>Title</h2>` | **Title** (large) |
| Paragraph | `<p>Text</p>` | Paragraph with spacing |
| Bold | `<strong>text</strong>` | **text** |
| Italic | `<em>text</em>` | *text* |
| Line break | `<br>` | New line |
| Bullet list | `<ul><li>Item</li></ul>` | • Item |
| Numbered list | `<ol><li>Item</li></ol>` | 1. Item |
| Code | `<code>text</code>` | `text` |
| Code block | `<pre>code</pre>` | Code block |
| Link | `<a href="url">text</a>` | Clickable link |

#### Example: Well-Formatted Description

**DO NOT write this (markdown - won't render):**
```
## Problem
- Serial port config didn't persist
- Baud rate reverted after restart

## Solution
1. Added config volume
2. Updated Program.cs
```

**WRITE THIS (HTML - renders correctly):**
```html
<h2>Problem</h2>
<ul>
  <li>Serial port config didn't persist</li>
  <li>Baud rate reverted after restart</li>
</ul>

<h2>Solution</h2>
<ol>
  <li>Added config volume</li>
  <li>Updated Program.cs</li>
</ol>
```

#### Complete Work Item Example

```bash
DESCRIPTION=$(cat <<'EOF'
<h2>Problem</h2>
<p>Serial port configuration changes made via dashboard didn't persist after container restart.</p>
<ul>
  <li>Baud rate would revert to 9600</li>
  <li>Config was being saved to ephemeral storage</li>
</ul>

<h2>Solution</h2>
<ol>
  <li>Added <code>XTCONNECT_CONFIG_DIR</code> environment variable</li>
  <li>Updated Program.cs to load config from external directory</li>
  <li>Fixed default baud rate to 19200</li>
</ol>

<h2>Files Changed</h2>
<ul>
  <li>docker-compose.prod.yml</li>
  <li>src/XTConnect.Node/Program.cs</li>
  <li>src/XTConnect.Node/Configuration/SerialPortSettings.cs</li>
</ul>
EOF
)

az boards work-item update --org "$ORG" --id ITEM_ID \
  --fields "System.Description=$DESCRIPTION"
```

### Pipelines

**List pipelines:**
```bash
az pipelines list --org "$ORG" --project "$PROJECT" --output table
```

**Recent runs:**
```bash
az pipelines runs list --org "$ORG" --project "$PROJECT" --pipeline-ids ID --top 10 --output table
```

**Trigger pipeline:**
```bash
az pipelines run --org "$ORG" --project "$PROJECT" --name "PipelineName" --branch "main"
```

### Repositories

**List repos:**
```bash
az repos list --org "$ORG" --project "$PROJECT" --output table
```

## Scripts Reference

| Script | Purpose | Key Features |
|--------|---------|--------------|
| `ado_client.py` | REST API client | Batch operations, rate limiting, retry logic |
| `query-work-items.py` | Query work items | Presets, batch fetch, table output |
| `check-prerequisites.py` | Verify setup | CLI, extension, auth validation |
| `discover-project.py` | Scan project | Areas, iterations, teams, pipelines |

### ado_client.py Features

The core client module provides:

- **Batch API**: Fetches up to 200 work items per request (vs N+1 with CLI)
- **Rate Limit Handling**: Monitors `X-RateLimit-*` headers, honors `Retry-After`
- **Exponential Backoff**: Automatic retry with jitter for transient failures
- **Token Refresh**: Automatic Azure AD token management
- **Error Classification**: Structured errors for appropriate handling

```python
from ado_client import ADOClient, ADOConfig, ADOError

config = ADOConfig.from_file(".ado/config.json")
client = ADOClient(config, verbose=True)

# Batch fetch (efficient!)
items = client.get_work_items_batch([1, 2, 3, 4, 5])

# Query with auto-batch fetch
items = client.query_work_items(
    "SELECT [System.Id] FROM workitems WHERE [System.AssignedTo] = @Me"
)
```

## Work Item Field Schema

**CRITICAL: Before creating or updating work items, ALWAYS read `.ado/project-metadata.json`**

The metadata file contains the complete field schema for your project:

### Structure
```json
{
  "work_item_types": [
    {
      "name": "Bug",
      "requiredFields": ["System.Title", "System.State", ...],
      "picklistFields": {
        "System.State": ["New", "Active", "Resolved", "Closed"],
        "Microsoft.VSTS.Common.Priority": ["1", "2", "3", "4"],
        "Microsoft.VSTS.Common.Severity": ["1 - Critical", "2 - High", "3 - Medium", "4 - Low"]
      },
      "fields": [
        {
          "referenceName": "System.Title",
          "name": "Title",
          "alwaysRequired": true,
          "defaultValue": null
        },
        {
          "referenceName": "System.State",
          "name": "State",
          "alwaysRequired": true,
          "defaultValue": "New",
          "allowedValues": ["New", "Active", "Resolved", "Closed"]
        }
      ]
    }
  ],
  "fieldSummary": {
    "statesByType": {
      "Bug": ["New", "Active", "Resolved", "Closed"],
      "Task": ["New", "Active", "Closed"],
      "User Story": ["New", "Active", "Resolved", "Closed"]
    },
    "priorityValues": ["1", "2", "3", "4"],
    "severityValues": ["1 - Critical", "2 - High", "3 - Medium", "4 - Low"]
  }
}
```

### How to Use

1. **Before creating a work item:**
   ```bash
   # Check what fields are required for a Bug
   cat .ado/project-metadata.json | jq '.work_item_types[] | select(.name=="Bug") | .requiredFields'
   ```

2. **Get valid state values:**
   ```bash
   cat .ado/project-metadata.json | jq '.fieldSummary.statesByType'
   ```

3. **Get allowed priority values:**
   ```bash
   cat .ado/project-metadata.json | jq '.fieldSummary.priorityValues'
   ```

### Refresh Schema
If fields change (new custom fields, process template updates), re-run discovery:
```bash
python3 skills/azure-devops/scripts/discover-project.py --config .ado/config.json --output .ado/project-metadata.json
```

## WIQL Quick Reference

```sql
-- My active items (optimized)
SELECT [System.Id], [System.Title] FROM workitems
WHERE [System.AssignedTo] = @Me
  AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
ORDER BY [Microsoft.VSTS.Common.Priority] ASC

-- Items changed this week (date-limited)
SELECT [System.Id], [System.Title] FROM workitems
WHERE [System.ChangedDate] >= @Today - 7
  AND [System.AssignedTo] = @Me
ORDER BY [System.ChangedDate] DESC

-- Items in area path
SELECT [System.Id], [System.Title] FROM workitems
WHERE [System.AreaPath] UNDER 'Project\Area'
  AND [System.State] <> 'Removed'
```

**Date macros:** `@Today`, `@Today - 7`, `@StartOfWeek`, `@StartOfMonth`, `@CurrentIteration`

**Important constraints:**
- Max 32,000 characters per WIQL query
- CLI query returns max 1,000 items (use REST API for more)
- Query timeout is 30 seconds

## Configuration Files

### .ado/config.json
```json
{
  "organization": "https://dev.azure.com/org-name",
  "project": "ProjectName",
  "configuredAt": "2024-01-15T10:30:00Z"
}
```

### .ado/project-metadata.json
Generated by `discover-project.py` with:
- Areas (hierarchy)
- Iterations (with dates)
- Teams
- Work item types
- Pipelines
- Repositories

## Troubleshooting

### Authentication Errors

```bash
# Re-authenticate
az login

# Check current account
az account show

# If using service principal, ensure it has Azure DevOps permissions
```

### Rate Limiting (HTTP 429)

If you see `TF400733: Request was blocked`:

1. Wait 5 minutes for the sliding window to reset
2. Use presets with date limiting instead of broad queries
3. Reduce `--max-results` parameter
4. Use batch operations (default in scripts)

### Query Timeout (VS402335)

If query times out after 30 seconds:

1. Add date range limits to narrow results
2. Remove expensive operators (`Contains`, `Ever`, `Or`)
3. Specify project scope
4. Sort by `System.Id` instead of custom fields

### Extension Missing

```bash
az extension add --name azure-devops
az extension update --name azure-devops  # Update if outdated
```

## References

- [Azure DevOps REST API](https://learn.microsoft.com/en-us/rest/api/azure/devops/)
- [Rate Limits](https://learn.microsoft.com/en-us/azure/devops/integrate/concepts/rate-limits)
- [Integration Best Practices](https://learn.microsoft.com/en-us/azure/devops/integrate/concepts/integration-bestpractices)
- [WIQL Syntax](https://learn.microsoft.com/en-us/azure/devops/boards/queries/wiql-syntax)
- [Azure CLI DevOps Extension](https://learn.microsoft.com/en-us/cli/azure/devops)

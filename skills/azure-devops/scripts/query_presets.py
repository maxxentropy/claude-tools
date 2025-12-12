#!/usr/bin/env python3
"""
Query Presets for Azure DevOps Work Items

Organized, optimized WIQL queries for common daily tasks.
All queries follow Microsoft best practices:
- Date/range limiting clauses near the top
- Avoid expensive operators (Contains -> Contains Words)
- Minimize Or operators
- Specify fields explicitly to reduce payload

Categories:
- my-*       : Personal work management
- sprint-*   : Sprint/iteration focused
- completed-*: Completion tracking
- changed-*  : Activity tracking
- bugs-*     : Bug management
- backlog-*  : Backlog and planning
- blocked-*  : Impediment tracking
- priority-* : Priority-based views
- created-*  : Creation tracking
- team-*     : Team awareness
"""

from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class QueryPreset:
    """A canned query preset."""
    name: str
    description: str
    category: str
    wiql: str
    fields: List[str]
    use_case: Optional[str] = None


# Standard field sets for reuse
STANDARD_FIELDS = [
    "System.Id", "System.Title", "System.State", "System.WorkItemType",
    "System.AssignedTo", "System.ChangedDate"
]

DETAIL_FIELDS = STANDARD_FIELDS + [
    "System.AreaPath", "System.IterationPath", "Microsoft.VSTS.Common.Priority",
    "System.Tags", "System.Parent"
]

BUG_FIELDS = STANDARD_FIELDS + [
    "Microsoft.VSTS.Common.Priority", "Microsoft.VSTS.Common.Severity",
    "System.AreaPath"
]

SPRINT_FIELDS = STANDARD_FIELDS + [
    "System.IterationPath", "Microsoft.VSTS.Common.Priority",
    "Microsoft.VSTS.Scheduling.StoryPoints"
]


# =============================================================================
# PRESET DEFINITIONS BY CATEGORY
# =============================================================================

PRESETS: Dict[str, QueryPreset] = {}


def _register(preset: QueryPreset) -> QueryPreset:
    """Register a preset in the global dictionary."""
    PRESETS[preset.name] = preset
    return preset


# -----------------------------------------------------------------------------
# Personal Work (my-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="my-active",
    description="Active work items assigned to me",
    category="Personal",
    use_case="Daily work list, standup prep",
    fields=DETAIL_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType],
               [System.AreaPath], [System.IterationPath], [Microsoft.VSTS.Common.Priority]
        FROM workitems
        WHERE [System.AssignedTo] = @Me
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="my-in-progress",
    description="Items I'm actively working on",
    category="Personal",
    use_case="Current focus, standup 'working on'",
    fields=DETAIL_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.AssignedTo] = @Me
          AND [System.State] IN ('Active', 'In Progress', 'Committed', 'Doing')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="my-new",
    description="New items assigned to me (not started)",
    category="Personal",
    use_case="Items to pick up next",
    fields=DETAIL_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.AssignedTo] = @Me
          AND [System.State] IN ('New', 'To Do', 'Proposed')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.CreatedDate] DESC
    """
))

_register(QueryPreset(
    name="my-blocked",
    description="My blocked items",
    category="Personal",
    use_case="Standup blockers, escalation",
    fields=DETAIL_FIELDS + ["System.Tags"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.Tags]
        FROM workitems
        WHERE [System.AssignedTo] = @Me
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
          AND ([System.Tags] CONTAINS 'Blocked' OR [System.State] = 'Blocked')
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="my-recent",
    description="Items I touched in last 3 days",
    category="Personal",
    use_case="Recent context, memory refresh",
    fields=STANDARD_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today - 3
          AND [System.ChangedBy] = @Me
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="my-all",
    description="All work items assigned to me",
    category="Personal",
    use_case="Full personal inventory",
    fields=STANDARD_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.AssignedTo] = @Me
        ORDER BY [System.ChangedDate] DESC
    """
))

# -----------------------------------------------------------------------------
# Sprint/Iteration (sprint-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="sprint-items",
    description="All items in current sprint",
    category="Sprint",
    use_case="Sprint overview, planning",
    fields=SPRINT_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.IterationPath] = @CurrentIteration
          AND [System.State] NOT IN ('Removed')
        ORDER BY [System.WorkItemType], [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="sprint-mine",
    description="My items in current sprint",
    category="Sprint",
    use_case="Personal sprint focus",
    fields=SPRINT_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.IterationPath] = @CurrentIteration
          AND [System.AssignedTo] = @Me
          AND [System.State] NOT IN ('Removed')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="sprint-not-started",
    description="Sprint items not yet started",
    category="Sprint",
    use_case="Sprint risk, capacity check",
    fields=SPRINT_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.IterationPath] = @CurrentIteration
          AND [System.State] IN ('New', 'To Do', 'Proposed')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="sprint-in-progress",
    description="Sprint items being worked",
    category="Sprint",
    use_case="Active sprint work",
    fields=SPRINT_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.IterationPath] = @CurrentIteration
          AND [System.State] IN ('Active', 'In Progress', 'Committed', 'Doing')
        ORDER BY [System.AssignedTo], [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="sprint-done",
    description="Completed sprint items",
    category="Sprint",
    use_case="Sprint progress, demo prep",
    fields=SPRINT_FIELDS + ["Microsoft.VSTS.Common.ClosedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.IterationPath] = @CurrentIteration
          AND [System.State] IN ('Closed', 'Done')
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="sprint-at-risk",
    description="High priority items not started in sprint",
    category="Sprint",
    use_case="Sprint health, risk identification",
    fields=SPRINT_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Priority]
        FROM workitems
        WHERE [System.IterationPath] = @CurrentIteration
          AND [Microsoft.VSTS.Common.Priority] <= 2
          AND [System.State] IN ('New', 'To Do', 'Proposed')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="sprint-unassigned",
    description="Unassigned items in current sprint",
    category="Sprint",
    use_case="Capacity planning, assignment",
    fields=SPRINT_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.IterationPath] = @CurrentIteration
          AND [System.AssignedTo] = ''
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC
    """
))

# -----------------------------------------------------------------------------
# Completed (completed-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="completed-today",
    description="Items completed today",
    category="Completed",
    use_case="End of day summary",
    fields=STANDARD_FIELDS + ["Microsoft.VSTS.Common.ClosedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.ClosedDate]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today
          AND [System.State] IN ('Closed', 'Done')
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="completed-this-week",
    description="Items completed in past 7 days",
    category="Completed",
    use_case="Weekly summary, WSR",
    fields=STANDARD_FIELDS + ["Microsoft.VSTS.Common.ClosedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.ClosedDate]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today - 7
          AND [System.State] IN ('Closed', 'Done')
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="completed-by-me-today",
    description="Items I completed today",
    category="Completed",
    use_case="Daily standup, personal tracking",
    fields=STANDARD_FIELDS + ["Microsoft.VSTS.Common.ClosedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.ClosedDate]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today
          AND [System.AssignedTo] = @Me
          AND [System.State] IN ('Closed', 'Done')
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="completed-by-me-this-week",
    description="Items I completed in past 7 days",
    category="Completed",
    use_case="Weekly status report (WSR)",
    fields=STANDARD_FIELDS + ["Microsoft.VSTS.Common.ClosedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.ClosedDate]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today - 7
          AND [System.AssignedTo] = @Me
          AND [System.State] IN ('Closed', 'Done')
        ORDER BY [System.ChangedDate] DESC
    """
))

# -----------------------------------------------------------------------------
# Changed/Activity (changed-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="changed-today",
    description="Items changed today (by me)",
    category="Activity",
    use_case="Daily activity tracking",
    fields=STANDARD_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today
          AND [System.ChangedBy] = @Me
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="changed-this-week",
    description="Items changed in past 7 days (by me)",
    category="Activity",
    use_case="Weekly activity review",
    fields=STANDARD_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today - 7
          AND [System.ChangedBy] = @Me
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="recent-activity",
    description="All items changed in past 24 hours",
    category="Activity",
    use_case="Team pulse, daily activity",
    fields=STANDARD_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today - 1
        ORDER BY [System.ChangedDate] DESC
    """
))

# -----------------------------------------------------------------------------
# Bugs (bugs-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="bugs-mine",
    description="Active bugs assigned to me",
    category="Bugs",
    use_case="Bug fixing focus",
    fields=BUG_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Severity]
        FROM workitems
        WHERE [System.WorkItemType] = 'Bug'
          AND [System.AssignedTo] = @Me
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [Microsoft.VSTS.Common.Severity] ASC, [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="bugs-critical",
    description="Critical/high severity active bugs",
    category="Bugs",
    use_case="Critical issues, escalation",
    fields=BUG_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Severity]
        FROM workitems
        WHERE [System.WorkItemType] = 'Bug'
          AND [Microsoft.VSTS.Common.Severity] IN ('1 - Critical', '2 - High')
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [Microsoft.VSTS.Common.Severity] ASC, [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="bugs-new",
    description="Bugs created in past 14 days",
    category="Bugs",
    use_case="New issues trend",
    fields=BUG_FIELDS + ["System.CreatedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.CreatedDate]
        FROM workitems
        WHERE [System.WorkItemType] = 'Bug'
          AND [System.CreatedDate] >= @Today - 14
        ORDER BY [System.CreatedDate] DESC
    """
))

_register(QueryPreset(
    name="bugs-triage",
    description="New bugs needing triage (unassigned)",
    category="Bugs",
    use_case="Triage meeting, assignment",
    fields=BUG_FIELDS + ["System.CreatedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.CreatedDate]
        FROM workitems
        WHERE [System.WorkItemType] = 'Bug'
          AND [System.State] IN ('New', 'To Do', 'Proposed')
          AND [System.AssignedTo] = ''
        ORDER BY [Microsoft.VSTS.Common.Severity] ASC, [System.CreatedDate] ASC
    """
))

_register(QueryPreset(
    name="bugs-recent",
    description="Bugs changed in past 14 days",
    category="Bugs",
    use_case="Bug activity overview",
    fields=BUG_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Priority]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today - 14
          AND [System.WorkItemType] = 'Bug'
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
    """
))

# -----------------------------------------------------------------------------
# Backlog & Planning (backlog-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="backlog-ready",
    description="Backlog items ready for sprint (estimated)",
    category="Backlog",
    use_case="Sprint planning, refinement",
    fields=SPRINT_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Scheduling.StoryPoints]
        FROM workitems
        WHERE [System.State] IN ('New', 'Approved', 'Ready')
          AND [Microsoft.VSTS.Scheduling.StoryPoints] > 0
          AND [System.WorkItemType] IN ('User Story', 'Product Backlog Item', 'Bug')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="backlog-unestimated",
    description="Backlog items without estimates",
    category="Backlog",
    use_case="Refinement needed",
    fields=SPRINT_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.WorkItemType]
        FROM workitems
        WHERE [System.State] IN ('New', 'Approved', 'Ready', 'To Do')
          AND ([Microsoft.VSTS.Scheduling.StoryPoints] = ''
               OR [Microsoft.VSTS.Scheduling.StoryPoints] = 0)
          AND [System.WorkItemType] IN ('User Story', 'Product Backlog Item', 'Bug')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="backlog-stale",
    description="Backlog items not updated in 90+ days",
    category="Backlog",
    use_case="Backlog grooming, cleanup",
    fields=STANDARD_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
        FROM workitems
        WHERE [System.ChangedDate] < @Today - 90
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [System.ChangedDate] ASC
    """
))

# -----------------------------------------------------------------------------
# Blocked (blocked-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="blocked-all",
    description="All blocked work items",
    category="Blocked",
    use_case="Impediment tracking, standup",
    fields=DETAIL_FIELDS + ["System.Tags"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.Tags]
        FROM workitems
        WHERE [System.State] NOT IN ('Closed', 'Done', 'Removed')
          AND ([System.Tags] CONTAINS 'Blocked' OR [System.State] = 'Blocked')
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="blocked-long",
    description="Items blocked for more than 3 days",
    category="Blocked",
    use_case="Escalation candidates",
    fields=DETAIL_FIELDS + ["System.Tags"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.ChangedDate]
        FROM workitems
        WHERE [System.ChangedDate] < @Today - 3
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
          AND ([System.Tags] CONTAINS 'Blocked' OR [System.State] = 'Blocked')
        ORDER BY [System.ChangedDate] ASC
    """
))

# -----------------------------------------------------------------------------
# Priority (priority-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="priority-critical",
    description="P1 critical active items",
    category="Priority",
    use_case="Executive focus, urgent work",
    fields=DETAIL_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Priority]
        FROM workitems
        WHERE [Microsoft.VSTS.Common.Priority] = 1
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="priority-high",
    description="P1-P2 high priority active items",
    category="Priority",
    use_case="Priority focus, planning",
    fields=DETAIL_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Priority]
        FROM workitems
        WHERE [Microsoft.VSTS.Common.Priority] <= 2
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC, [System.ChangedDate] DESC
    """
))

_register(QueryPreset(
    name="priority-mine",
    description="My high priority items (P1-P2)",
    category="Priority",
    use_case="Personal priority focus",
    fields=DETAIL_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [Microsoft.VSTS.Common.Priority]
        FROM workitems
        WHERE [System.AssignedTo] = @Me
          AND [Microsoft.VSTS.Common.Priority] <= 2
          AND [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [Microsoft.VSTS.Common.Priority] ASC
    """
))

# -----------------------------------------------------------------------------
# Created (created-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="created-today",
    description="Items created today",
    category="Created",
    use_case="New work intake",
    fields=STANDARD_FIELDS + ["System.CreatedDate", "System.CreatedBy"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.CreatedDate]
        FROM workitems
        WHERE [System.CreatedDate] >= @Today
        ORDER BY [System.CreatedDate] DESC
    """
))

_register(QueryPreset(
    name="created-this-week",
    description="Items created in past 7 days",
    category="Created",
    use_case="Weekly intake review",
    fields=STANDARD_FIELDS + ["System.CreatedDate", "System.CreatedBy"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.CreatedDate]
        FROM workitems
        WHERE [System.CreatedDate] >= @Today - 7
        ORDER BY [System.CreatedDate] DESC
    """
))

_register(QueryPreset(
    name="created-by-me",
    description="Items I created in past 30 days",
    category="Created",
    use_case="My contributions, follow-up",
    fields=STANDARD_FIELDS + ["System.CreatedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.CreatedDate]
        FROM workitems
        WHERE [System.CreatedDate] >= @Today - 30
          AND [System.CreatedBy] = @Me
        ORDER BY [System.CreatedDate] DESC
    """
))

# -----------------------------------------------------------------------------
# Team (team-*)
# -----------------------------------------------------------------------------

_register(QueryPreset(
    name="team-active",
    description="All active items (team-wide)",
    category="Team",
    use_case="Team workload overview",
    fields=DETAIL_FIELDS,
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.AssignedTo]
        FROM workitems
        WHERE [System.State] NOT IN ('Closed', 'Done', 'Removed')
        ORDER BY [System.AssignedTo], [Microsoft.VSTS.Common.Priority] ASC
    """
))

_register(QueryPreset(
    name="team-completed-this-week",
    description="Items completed by team this week",
    category="Team",
    use_case="Team progress, demo prep",
    fields=STANDARD_FIELDS + ["Microsoft.VSTS.Common.ClosedDate"],
    wiql="""
        SELECT [System.Id], [System.Title], [System.State], [System.AssignedTo]
        FROM workitems
        WHERE [System.ChangedDate] >= @Today - 7
          AND [System.State] IN ('Closed', 'Done')
        ORDER BY [System.AssignedTo], [System.ChangedDate] DESC
    """
))


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_preset(name: str) -> Optional[QueryPreset]:
    """Get a preset by name."""
    return PRESETS.get(name)


def get_presets_by_category(category: str) -> List[QueryPreset]:
    """Get all presets in a category."""
    return [p for p in PRESETS.values() if p.category.lower() == category.lower()]


def get_categories() -> List[str]:
    """Get list of unique categories."""
    return sorted(set(p.category for p in PRESETS.values()))


def list_presets(verbose: bool = False) -> str:
    """
    Format all presets for display.

    Args:
        verbose: Include use cases and more detail
    """
    lines = []

    for category in get_categories():
        lines.append(f"\n{category}:")
        lines.append("-" * (len(category) + 1))

        for preset in get_presets_by_category(category):
            if verbose:
                lines.append(f"  {preset.name:30} {preset.description}")
                if preset.use_case:
                    lines.append(f"  {' ':30} Use: {preset.use_case}")
            else:
                lines.append(f"  {preset.name:25} {preset.description}")

    return "\n".join(lines)


def to_legacy_format() -> Dict[str, dict]:
    """
    Convert presets to legacy format for backwards compatibility.

    Returns dict in the format expected by query-work-items.py:
    {
        "preset-name": {
            "description": "...",
            "wiql": "...",
            "fields": [...]
        }
    }
    """
    return {
        name: {
            "description": preset.description,
            "wiql": preset.wiql,
            "fields": preset.fields,
            "category": preset.category,
            "use_case": preset.use_case
        }
        for name, preset in PRESETS.items()
    }


# For backwards compatibility - expose as QUERY_PRESETS
QUERY_PRESETS = to_legacy_format()


if __name__ == "__main__":
    # When run directly, list all presets
    import argparse

    parser = argparse.ArgumentParser(description="List Azure DevOps query presets")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show use cases")
    parser.add_argument("-c", "--category", help="Filter by category")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    args = parser.parse_args()

    if args.json:
        import json
        print(json.dumps(QUERY_PRESETS, indent=2))
    elif args.category:
        presets = get_presets_by_category(args.category)
        if not presets:
            print(f"No presets in category: {args.category}")
            print(f"Available categories: {', '.join(get_categories())}")
        else:
            for p in presets:
                print(f"  {p.name:25} {p.description}")
    else:
        print("Azure DevOps Query Presets")
        print("=" * 60)
        print(list_presets(verbose=args.verbose))
        print(f"\nTotal: {len(PRESETS)} presets in {len(get_categories())} categories")

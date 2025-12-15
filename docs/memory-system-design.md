# Memory System Design: Long-Term Persistence for Claude Code

**Status:** Proposed
**Date:** 2025-12-15
**Author:** software-architect agent

---

## Executive Summary

This document analyzes options for integrating long-term memory and cross-session persistence into the claude-tools repository. The goal is to enable Claude Code sessions to remember discoveries, findings, and unfinished work across sessions, while sharing this knowledge with other developers working in the same codebase.

### Key Recommendation

**Build a lightweight "findings" skill** that complements the existing Azure DevOps integration rather than replacing it. Use a similar architecture to beads (JSONL + git) but tailored to claude-tools' existing patterns and ADO workflow.

---

## 1. Architecture Analysis

### 1.1 Key Patterns in Beads That Make It Effective

Beads succeeds as an agent memory system because of several deliberate architectural choices:

```
┌─────────────────────────────────────────────────────────────────┐
│                    BEADS ARCHITECTURE                           │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌─────────────────┐    ┌─────────────────┐                   │
│   │  .beads/        │    │   .beads/       │                   │
│   │  issues.jsonl   │◄──►│   beads.db      │                   │
│   │  (Git-tracked)  │    │   (Git-ignored) │                   │
│   │  SOURCE OF      │    │   QUERY CACHE   │                   │
│   │  TRUTH          │    │                 │                   │
│   └────────┬────────┘    └────────┬────────┘                   │
│            │                      │                            │
│            └──────────┬───────────┘                            │
│                       │                                        │
│                       ▼                                        │
│            ┌─────────────────────┐                             │
│            │   bd CLI            │                             │
│            │   - bd ready        │  ◄── Agent bootstrap        │
│            │   - bd onboard      │  ◄── Context loading        │
│            │   - bd compact      │  ◄── Memory decay           │
│            └─────────────────────┘                             │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Pattern 1: Git as the Persistence Layer**
- JSONL file is committed to git = automatically shared with team
- Works with branching and merging
- No external database or service dependency
- Survives across machines, clones, and time

**Pattern 2: Append-Only Log with Cache**
- JSONL is append-friendly (no merge conflicts on concurrent edits)
- SQLite cache provides fast queries without parsing JSONL every time
- Debounced sync prevents cache thrash

**Pattern 3: Hash-Based IDs**
- Content-addressable IDs prevent collisions in multi-agent scenarios
- No central coordination needed for ID generation
- Enables deduplication

**Pattern 4: Dependency Tracking**
- `blocks`, `related`, `parent-child`, `discovered-from` relationships
- `bd ready` command answers "what can I work on now?"
- Helps agents prioritize work

**Pattern 5: Agent Bootstrap Commands**
- `bd onboard` provides context dump for new sessions
- `bd ready` shows actionable items
- Designed for prompt injection at session start

### 1.2 Comparison: Beads vs. Existing Azure DevOps Caching

| Aspect | Beads | ADO Work Item Cache |
|--------|-------|---------------------|
| **Purpose** | Agent-local memory | Team work tracking |
| **Storage** | `.beads/issues.jsonl` (git-tracked) | `.ado/work-items.json` (git-ignored) |
| **Scope** | Local discoveries, notes, TODOs | Official work items from ADO |
| **Sharing** | Committed to repo, shared via git | Each developer has own cache |
| **ID Source** | Hash-generated locally | ADO server-assigned |
| **Dependencies** | Built-in (blocks, related) | Via ADO parent/child |
| **Sync** | N/A (git-native) | Pull from ADO API |
| **Best For** | Quick captures, agent memory | Tracking planned work |

**Key Insight:** These serve different purposes and can coexist. ADO is for "official" team work; beads-style memory is for "discovered" findings and agent context.

### 1.3 What We Lose/Gain by Adopting Beads vs Building Our Own

**Adopting Beads As-Is:**

| Gains | Losses |
|-------|--------|
| Mature implementation | No ADO integration |
| MCP server included | Separate CLI to learn |
| Proven patterns | Duplicate dependency tracking (vs ADO) |
| Active development | Less control over schema |
| Python-native | Another tool to maintain |

**Building Our Own:**

| Gains | Losses |
|-------|--------|
| Tight ADO integration | Development time |
| Consistent with existing skills | Need to implement core patterns |
| Custom schema for our needs | Risk of reinventing wheels |
| Single toolchain | No MCP server (unless we build it) |
| Skill-based activation | |

---

## 2. Integration Options

### Option A: Use Beads As-Is

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPTION A: PARALLEL TOOLS                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌───────────────────┐        ┌───────────────────┐           │
│   │   claude-tools    │        │      beads        │           │
│   │   skills/         │        │   .beads/         │           │
│   ├───────────────────┤        ├───────────────────┤           │
│   │ azure-devops      │        │ issues.jsonl      │           │
│   │ - Official work   │        │ - Agent memory    │           │
│   │ - Team tracking   │        │ - Local findings  │           │
│   │ - Sprint items    │        │ - Quick captures  │           │
│   └────────┬──────────┘        └────────┬──────────┘           │
│            │                            │                       │
│            └────────────┬───────────────┘                       │
│                         │                                       │
│                         ▼                                       │
│              ┌─────────────────────┐                           │
│              │ Manual Promotion    │                           │
│              │ (User decides when  │                           │
│              │  to create ADO item │                           │
│              │  from bead)         │                           │
│              └─────────────────────┘                           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
1. `pip install beads-mcp` (or clone repo)
2. Add to Claude Desktop MCP config
3. Document usage alongside existing skills
4. Manual workflow to promote beads to ADO items

**Pros:**
- Zero development time
- Battle-tested implementation
- MCP integration works out of the box
- Community support and updates

**Cons:**
- Two separate systems, no integration
- Different ID schemes (hash vs AB#)
- No automatic ADO linking
- Users must learn two tools
- No sharing between eval-framework results and memory

**Complexity:** Low
**Time to implement:** 1 day (documentation only)

---

### Option B: Bridge Beads to ADO

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPTION B: BRIDGE PATTERN                     │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   ┌───────────────────┐                                        │
│   │      beads        │                                        │
│   │   .beads/         │                                        │
│   │   issues.jsonl    │                                        │
│   └────────┬──────────┘                                        │
│            │                                                    │
│            ▼                                                    │
│   ┌───────────────────────────────────────┐                    │
│   │         beads-ado-bridge.py           │                    │
│   │                                       │                    │
│   │  - Watch for promotion_requested tag  │                    │
│   │  - Create ADO work item               │                    │
│   │  - Update bead with AB#1234 link      │                    │
│   │  - Sync status back to bead           │                    │
│   └────────┬──────────────────────────────┘                    │
│            │                                                    │
│            ▼                                                    │
│   ┌───────────────────┐                                        │
│   │   azure-devops    │                                        │
│   │   .ado/           │                                        │
│   │   ADO REST API    │                                        │
│   └───────────────────┘                                        │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Implementation:**
1. Install beads as dependency
2. Create `skills/beads-ado-bridge/` skill
3. Bridge script watches for specific tags/states
4. Auto-creates ADO items, backlinks

**Data Flow:**
```
1. Agent creates bead: "bd create 'Found N+1 query in OrderService'"
2. User tags for promotion: "bd tag abc123 promote-to-ado"
3. Bridge detects tag, creates ADO Task:
   - Title: "Found N+1 query in OrderService"
   - Description: Bead details + source link
   - Area: Auto-detected from bead context
4. Bridge updates bead:
   - Adds "AB#1234" to bead metadata
   - Changes state to "promoted"
5. Status syncs bidirectionally
```

**Pros:**
- Best of both worlds
- Gradual adoption path
- Keeps beads for quick capture
- ADO for official tracking
- Findings don't get lost

**Cons:**
- Complexity of sync logic
- Two sources of truth during transition
- Bridge can get out of sync
- More moving parts

**Complexity:** Medium-High
**Time to implement:** 1-2 weeks

---

### Option C: Build a "Findings" Skill

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPTION C: NATIVE SKILL                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│   skills/findings/                                              │
│   ├── SKILL.md                                                  │
│   ├── schemas/                                                  │
│   │   └── finding.schema.yaml                                   │
│   └── scripts/                                                  │
│       ├── findings_store.py      # JSONL + index management     │
│       ├── query_findings.py      # CLI for querying             │
│       ├── promote_to_ado.py      # Create ADO item from finding │
│       └── session_context.py     # Bootstrap for new sessions   │
│                                                                 │
│   Storage:                                                      │
│   .findings/                                                    │
│   ├── findings.jsonl             # Git-tracked (shared)         │
│   ├── findings.db                # Git-ignored (local cache)    │
│   └── session-context.json       # Last session state           │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘

Integration Points:

┌──────────────────┐     ┌──────────────────┐     ┌──────────────────┐
│  architecture-   │     │   findings       │     │   azure-devops   │
│  review skill    │────►│   skill          │────►│   skill          │
│                  │     │                  │     │                  │
│  Discovers       │     │  Captures &      │     │  Promotes to     │
│  issues          │     │  persists        │     │  official work   │
└──────────────────┘     └──────────────────┘     └──────────────────┘
        │                        │                        │
        └────────────────────────┼────────────────────────┘
                                 │
                                 ▼
                    ┌────────────────────────┐
                    │    eval-framework      │
                    │    skill               │
                    │                        │
                    │  Links findings to     │
                    │  evaluation results    │
                    └────────────────────────┘
```

**Implementation:**
1. New `skills/findings/` directory
2. Reuse patterns from `work_item_index.py`
3. JSONL storage (beads-inspired)
4. Direct integration with existing skills
5. `promote_to_ado.py` creates work items

**Key Features:**
- Session context loading (like `bd onboard`)
- Ready queue (like `bd ready`)
- Direct ADO promotion
- Links to eval-framework results
- Same CLI patterns as other skills

**Pros:**
- Fully integrated with existing tooling
- Consistent patterns (same as ADO cache)
- Custom schema for our needs
- No external dependencies
- Can reference ADO items natively

**Cons:**
- Development effort
- Need to implement core patterns
- No MCP server (initially)
- Less mature than beads

**Complexity:** Medium
**Time to implement:** 1-2 weeks

---

### Option D: Hybrid Approach

```
┌─────────────────────────────────────────────────────────────────┐
│                    OPTION D: HYBRID                             │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  Different tools for different purposes:                        │
│                                                                 │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   QUICK CAPTURE                          │   │
│  │                   (Session-local)                        │   │
│  │                                                          │   │
│  │  .claude/session-notes.md                                │   │
│  │  - Markdown scratchpad                                   │   │
│  │  - Git-ignored                                           │   │
│  │  - Auto-loaded at session start                          │   │
│  │  - Low friction capture                                  │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         │                                       │
│                         │ Promote if valuable                   │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   SHARED FINDINGS                        │   │
│  │                   (Team-visible)                         │   │
│  │                                                          │   │
│  │  .findings/findings.jsonl                                │   │
│  │  - Structured findings                                   │   │
│  │  - Git-tracked                                           │   │
│  │  - Queryable index                                       │   │
│  │  - Links to eval results                                 │   │
│  └──────────────────────┬──────────────────────────────────┘   │
│                         │                                       │
│                         │ Promote to official work              │
│                         ▼                                       │
│  ┌─────────────────────────────────────────────────────────┐   │
│  │                   OFFICIAL WORK                          │   │
│  │                   (ADO/GitHub)                           │   │
│  │                                                          │   │
│  │  Azure DevOps / GitHub Issues                            │   │
│  │  - Sprint planning                                       │   │
│  │  - Team assignment                                       │   │
│  │  - Status tracking                                       │   │
│  │  - Release management                                    │   │
│  └─────────────────────────────────────────────────────────┘   │
│                                                                 │
└─────────────────────────────────────────────────────────────────┘
```

**Three-Tier Memory Model:**

| Tier | Storage | Visibility | Lifecycle | Use Case |
|------|---------|------------|-----------|----------|
| **Scratchpad** | `.claude/notes.md` | Local only | Session | Quick thoughts, WIP |
| **Findings** | `.findings/` JSONL | Team (git) | Persistent | Discoveries, tech debt |
| **Official** | ADO/GitHub | Team | Managed | Planned work, sprints |

**Pros:**
- Clear separation of concerns
- Appropriate friction for each level
- Progressive formalization
- Nothing gets lost

**Cons:**
- Three places to check
- More complex mental model
- Migration between tiers

**Complexity:** Medium-High
**Time to implement:** 2-3 weeks

---

## 3. Data Model

### 3.1 Core Finding Schema

```yaml
# .findings/findings.jsonl - One JSON object per line

{
  # Identity
  "id": "f-a1b2c3d4",           # Hash-based ID (first 8 chars of content hash)
  "version": 2,                  # Increments on update

  # Classification
  "type": "discovery",           # discovery, todo, question, note, tech-debt
  "category": "performance",     # Maps to eval-framework categories
  "severity": "medium",          # critical, high, medium, low, info

  # Content
  "title": "N+1 query in OrderService.GetAllWithDetails",
  "description": "Found N+1 query pattern when loading orders with line items...",
  "evidence": {
    "file": "src/Services/OrderService.cs",
    "line": 145,
    "snippet": "foreach (var order in orders) { order.LineItems = await _repo.GetLineItems(order.Id); }"
  },

  # Context
  "discovered_at": "2025-12-15T10:30:00Z",
  "discovered_by": "claude-opus-4-5",
  "discovered_during": "architecture-review",
  "session_id": "sess-xyz789",
  "branch": "feature/AB#1234-order-optimization",
  "commit": "abc123def",

  # Relationships
  "related_to": ["f-e5f6g7h8"],          # Other findings
  "blocks": [],                           # Findings this blocks
  "blocked_by": [],                       # Findings blocking this
  "parent": null,                         # Parent finding (for sub-issues)
  "ado_work_item": null,                  # AB#1234 if promoted
  "eval_result": "arch-review-2025-12-15-eval-abc123",  # Link to eval

  # Status
  "status": "open",              # open, in_progress, resolved, wont_fix, promoted
  "resolution": null,            # How it was resolved
  "resolved_at": null,
  "resolved_by": null,

  # Metadata
  "tags": ["performance", "database", "n+1"],
  "priority": 2,                 # 1-4 (like ADO)
  "effort": "small",             # small, medium, large, unknown
  "confidence": 0.9,             # How confident is the finding (0-1)

  # Updates
  "created_at": "2025-12-15T10:30:00Z",
  "updated_at": "2025-12-15T10:30:00Z",
  "history": [
    {
      "timestamp": "2025-12-15T10:30:00Z",
      "action": "created",
      "by": "claude-opus-4-5",
      "details": null
    }
  ]
}
```

### 3.2 Session Context Schema

```yaml
# .findings/session-context.json - Loaded at session start

{
  "last_session": {
    "id": "sess-xyz789",
    "started_at": "2025-12-15T09:00:00Z",
    "ended_at": "2025-12-15T12:30:00Z",
    "branch": "feature/AB#1234-order-optimization",
    "work_item": "AB#1234",

    # What was worked on
    "files_modified": [
      "src/Services/OrderService.cs",
      "tests/Services/OrderServiceTests.cs"
    ],
    "commits": ["abc123", "def456"],

    # What was discovered
    "findings_created": ["f-a1b2c3d4", "f-e5f6g7h8"],
    "findings_resolved": ["f-i9j0k1l2"],

    # What's still open
    "open_findings": ["f-a1b2c3d4"],
    "blocked_findings": [],

    # Summary for next session
    "handoff_notes": "Optimized GetAllWithDetails but still need to address the N+1 in GetOrderHistory"
  },

  "active_context": {
    "work_item": "AB#1234",
    "focus_area": "src/Services/",
    "open_questions": [
      "Should we use Include() or explicit loading for order line items?"
    ]
  },

  "statistics": {
    "total_sessions": 45,
    "total_findings": 127,
    "findings_promoted_to_ado": 23,
    "findings_resolved": 89
  }
}
```

### 3.3 Schema Comparison

| Field | Beads | ADO Work Item | Proposed Finding |
|-------|-------|---------------|------------------|
| ID | Hash (collision-resistant) | Server-assigned int | Hash (8-char) |
| Title | Yes | Yes | Yes |
| Description | Yes | Yes (HTML) | Yes (Markdown) |
| Status | open/closed/etc | New/Active/etc | open/in_progress/resolved/promoted |
| Priority | Yes | 1-4 | 1-4 (same as ADO) |
| Dependencies | blocks, related, parent | Parent/child | blocks, blocked_by, related_to, parent |
| Location | No | No | file, line, snippet |
| Source | No | No | discovered_during, session_id |
| Confidence | No | No | 0-1 score |
| ADO Link | No | N/A | ado_work_item field |

---

## 4. Recommendation

### My Recommendation: Option C (Native Findings Skill) with Elements of D

**Build a "findings" skill** that is native to claude-tools, follows existing patterns, and integrates tightly with ADO and eval-framework.

**Rationale:**

1. **Consistency with existing architecture**
   - Same patterns as `work_item_index.py`
   - Same skill structure as other skills
   - Users don't need to learn a new tool

2. **ADO integration is already our strength**
   - Existing work item cache, context detection, and hooks
   - Promotion to ADO should be seamless, not bridged
   - Single source of truth for "official" work

3. **Eval-framework integration**
   - Findings should link to evaluation results
   - `discovered_during` field ties memory to assessments
   - Enables "what did we find last time?" queries

4. **Appropriate level of formality**
   - Quick capture for session memory
   - Git-tracked for team sharing
   - Promotion path for official work

5. **Beads patterns are good, but we don't need the whole system**
   - JSONL storage: Yes, adopt this
   - Hash IDs: Yes, adopt this
   - SQLite cache: Maybe later (start with JSON index)
   - MCP server: Not needed (we have CLI skill pattern)

### Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                    RECOMMENDED ARCHITECTURE                         │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  SESSION START                                                      │
│  ─────────────────────────────────────────────────────────────────  │
│  1. Load .findings/session-context.json                             │
│  2. Show open findings for current branch/area                      │
│  3. Show handoff notes from last session                            │
│                                                                     │
│  DURING SESSION                                                     │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  ┌─────────────────┐   ┌─────────────────┐   ┌─────────────────┐   │
│  │ architecture-   │   │ code-review     │   │ security-       │   │
│  │ review skill    │   │ skill           │   │ engineer agent  │   │
│  └────────┬────────┘   └────────┬────────┘   └────────┬────────┘   │
│           │                     │                     │             │
│           └─────────────────────┼─────────────────────┘             │
│                                 │                                   │
│                                 ▼                                   │
│                    ┌────────────────────────┐                       │
│                    │    findings skill      │                       │
│                    │                        │                       │
│                    │  capture_finding()     │                       │
│                    │  query_findings()      │                       │
│                    │  update_finding()      │                       │
│                    │  promote_to_ado()      │                       │
│                    │  get_session_context() │                       │
│                    └────────────┬───────────┘                       │
│                                 │                                   │
│                                 ▼                                   │
│                    ┌────────────────────────┐                       │
│                    │  .findings/            │                       │
│                    │  ├── findings.jsonl    │ ◄── Git-tracked       │
│                    │  ├── index.json        │ ◄── Git-ignored       │
│                    │  └── session-ctx.json  │ ◄── Git-ignored       │
│                    └────────────────────────┘                       │
│                                                                     │
│  PROMOTION PATH                                                     │
│  ─────────────────────────────────────────────────────────────────  │
│                                                                     │
│  findings skill                    azure-devops skill               │
│  ┌─────────────────┐              ┌─────────────────┐               │
│  │ Finding f-abc123│   ────────►  │ Work Item       │               │
│  │ status: open    │   promote()  │ AB#5678         │               │
│  │ ado_work_item:  │              │                 │               │
│  │   null          │              │ Description:    │               │
│  └─────────────────┘              │ From finding    │               │
│                                   │ f-abc123        │               │
│  After promotion:                 └─────────────────┘               │
│  ┌─────────────────┐                                                │
│  │ Finding f-abc123│                                                │
│  │ status: promoted│                                                │
│  │ ado_work_item:  │                                                │
│  │   AB#5678       │                                                │
│  └─────────────────┘                                                │
│                                                                     │
│  SESSION END                                                        │
│  ─────────────────────────────────────────────────────────────────  │
│  1. Auto-save session context                                       │
│  2. Summarize changes for next session                              │
│  3. git commit .findings/findings.jsonl (if changed)                │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 5. Implementation Roadmap

### Phase 1: MVP (1 week)

**Goal:** Basic capture and retrieval of findings with session context.

**Deliverables:**

```
skills/findings/
├── SKILL.md                      # Skill documentation
├── schemas/
│   └── finding.schema.yaml       # Finding schema definition
└── scripts/
    ├── findings_store.py         # Core storage (JSONL + index)
    ├── query_findings.py         # Query CLI
    └── session_context.py        # Session bootstrap/save
```

**Key Features:**
- [x] JSONL append-only storage
- [x] JSON index (simpler than SQLite initially)
- [x] Basic CRUD for findings
- [x] Session context load/save
- [x] CLI: `--capture`, `--query`, `--context`

**Commands:**

```bash
# Capture a finding
python3 skills/findings/scripts/query_findings.py --capture \
  --title "N+1 query in OrderService" \
  --type discovery \
  --severity medium \
  --file "src/Services/OrderService.cs" \
  --line 145

# Query findings
python3 skills/findings/scripts/query_findings.py --open
python3 skills/findings/scripts/query_findings.py --search "N+1"
python3 skills/findings/scripts/query_findings.py --branch feature/AB#1234

# Session context
python3 skills/findings/scripts/session_context.py --load  # At session start
python3 skills/findings/scripts/session_context.py --save  # At session end
```

### Phase 2: Integration (1 week)

**Goal:** Integrate with ADO and eval-framework.

**Deliverables:**

```
skills/findings/scripts/
├── promote_to_ado.py            # Create ADO item from finding
├── link_eval_results.py         # Link findings to evaluations
└── findings_from_eval.py        # Extract findings from eval results
```

**Key Features:**
- [x] Promote finding to ADO work item
- [x] Backlink ADO item to finding
- [x] Auto-extract findings from eval-framework results
- [x] Status sync (finding resolved when ADO item closed)

**Commands:**

```bash
# Promote to ADO
python3 skills/findings/scripts/promote_to_ado.py f-abc123

# Link to eval
python3 skills/findings/scripts/link_eval_results.py \
  --finding f-abc123 \
  --eval arch-review-2025-12-15-eval-xyz

# Extract findings from eval result
python3 skills/findings/scripts/findings_from_eval.py \
  --eval-file .eval-results/arch-review-2025-12-15.yaml
```

### Phase 3: Advanced Features (1-2 weeks)

**Goal:** Dependencies, ready queue, and agent bootstrap.

**Deliverables:**

```
skills/findings/scripts/
├── dependencies.py              # blocks, related, parent management
├── ready_queue.py               # What can be worked on now
├── compact.py                   # Memory decay / summarization
└── onboard.py                   # Full context dump for new sessions
```

**Key Features:**
- [x] Dependency tracking (blocks, blocked_by)
- [x] Ready queue: findings with no blockers
- [x] Onboard command: context for new sessions
- [x] Compact: summarize old findings (memory decay)

**Commands:**

```bash
# Dependencies
python3 skills/findings/scripts/dependencies.py add f-abc123 blocks f-def456
python3 skills/findings/scripts/dependencies.py show f-abc123

# Ready queue
python3 skills/findings/scripts/ready_queue.py  # Like bd ready

# Onboard
python3 skills/findings/scripts/onboard.py  # Like bd onboard

# Compact old findings
python3 skills/findings/scripts/compact.py --older-than 90d
```

### Phase 4: Polish (Optional)

**Goal:** Enhanced UX and optional MCP server.

**Deliverables:**
- SQLite cache for faster queries (if JSONL gets large)
- MCP server for Claude Desktop integration
- VS Code extension for finding visualization
- Dashboard for finding metrics

---

## 6. ADR: Memory System Selection

```markdown
# ADR-001: Agent Memory System for Claude-Tools

## Status
Proposed

## Context
Claude Code sessions lack persistent memory between invocations. When a session
ends, all discoveries, notes, and context are lost. This leads to:
- Repeated rediscovery of the same issues
- No team visibility into AI findings
- Lost context when switching between tasks
- No connection between discoveries and official work tracking

Steve Yegge's "beads" project provides a proven pattern for agent-local memory
using git-tracked JSONL storage. We need to decide whether to adopt beads,
bridge to it, or build our own solution.

## Decision Drivers
- Integration with existing Azure DevOps workflow is critical
- Must share findings across team (git-tracked)
- Should link to eval-framework results
- Consistent patterns with existing skills
- Minimal new tooling for users to learn

## Considered Options
1. **Use beads as-is**: Install alongside claude-tools, manual workflow
2. **Bridge beads to ADO**: Sync layer between beads and ADO
3. **Build native findings skill**: Our own implementation following existing patterns
4. **Hybrid**: Beads for quick capture, ADO for official work

## Decision
We will build a **native findings skill** (Option C) that:
- Uses JSONL storage pattern from beads
- Integrates directly with azure-devops skill
- Links to eval-framework results
- Follows existing claude-tools patterns

## Consequences

### Positive
- Consistent with existing architecture
- Seamless ADO promotion
- Direct eval-framework integration
- Single toolchain for users
- Full control over schema and features

### Negative
- Development effort required (2-3 weeks)
- Less mature than beads initially
- No MCP server (initially)

### Risks
- Reinventing patterns beads already solved: Mitigate by adopting proven patterns
- Scope creep: Mitigate with phased implementation

## Implementation Notes
See Section 5 (Implementation Roadmap) in memory-system-design.md
```

---

## 7. Open Questions

1. **Git tracking granularity**: Should we commit every finding immediately, or batch commits?
   - Recommendation: Batch at session end, or when explicitly requested

2. **ID collision handling**: What if two developers create findings with same content hash?
   - Recommendation: Include timestamp in hash input, or use longer hashes

3. **Finding lifecycle**: When should findings be auto-resolved?
   - Recommendation: When linked ADO item is closed, or manually

4. **Privacy**: Should some findings be local-only (not git-tracked)?
   - Recommendation: Add `private: true` flag, store in separate `.findings/local.jsonl`

5. **Cross-repo findings**: Should findings be global or per-repo?
   - Recommendation: Per-repo initially, with option to reference cross-repo

---

## 8. Success Metrics

| Metric | Target | Measurement |
|--------|--------|-------------|
| Session continuity | 80% of sessions load relevant context | Session context load success rate |
| Finding capture rate | 5+ findings per architecture review | Findings created per eval |
| ADO promotion rate | 30% of findings promoted to work items | Promoted / total findings |
| Rediscovery reduction | 50% fewer duplicate findings | Findings with similar titles |
| Team adoption | 3+ developers using findings | Unique git committers to .findings/ |

---

## 9. References

- [Beads Project](https://github.com/steveyegge/beads) - Git-based issue tracker for AI agents
- [Existing ADO Skill](/Users/sean/source/tools/claude-tools/skills/azure-devops/SKILL.md)
- [Eval Framework](/Users/sean/source/tools/claude-tools/skills/eval-framework/SKILL.md)
- [Work Item Index Pattern](/Users/sean/source/tools/claude-tools/skills/azure-devops/scripts/work_item_index.py)

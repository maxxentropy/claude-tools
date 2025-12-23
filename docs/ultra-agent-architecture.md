# Ultra Agent Architecture

## Executive Summary

The Ultra Agent system extends your existing Claude Code infrastructure with continuous learning,
sophisticated memory, and reasoning capabilities. Unlike the GODAGENT approach which requires a
complex daemon and custom databases, Ultra Agent takes a **pragmatic, incremental approach** that
builds on what already works.

**Philosophy**: "The best architecture is the simplest one that will still work in 2 years."

---

## Architecture Comparison

### GODAGENT vs Ultra Agent

```
GODAGENT (Complex)                          ULTRA AGENT (Pragmatic)
==============================              ==============================

Daemon Process (Unix Socket)                Session-Based (Stateless Hooks)
- Background process required               - No daemon needed
- IPC complexity                            - File-based persistence
- Process management overhead               - Simpler debugging

Custom Vector DB                            SQLite + sqlite-vec
- Requires embeddings server                - Single file, portable
- Complex deployment                        - Built-in to Python
- Operational overhead                      - Zero ops burden

Hypergraph Database                         Findings + Relationships
- N-node graph structures                   - Your existing findings.jsonl
- Complex querying                          - blocks/blocked_by/related_to
- Learning curve                            - Already implemented

SOMA Trainer                                Episode Store
- Trajectory learning                       - Successful task patterns
- Pattern extraction                        - Simple JSON episodes
- Force learning                            - Template matching

DRR 3-Layer Context                         Enhanced Context Manager
- Reasoning bank                            - Session context (existing)
- Memory DB                                 - Episode retrieval
- Graph traversal                           - Pattern suggestions
```

### Why Ultra Agent is Better for You

1. **You already have 80% of the infrastructure** - Findings, hooks, session context
2. **No operational burden** - No daemon to monitor, restart, debug
3. **Git-trackable** - Everything stays in your repo or ~/.claude
4. **Incrementally adoptable** - Each phase adds value independently
5. **Uses boring technology** - SQLite, JSON, Python - no exotic dependencies

---

## System Architecture

```
                        ULTRA AGENT SYSTEM ARCHITECTURE
                       "Practical Continuous Learning"

+-----------------------------------------------------------------------------+
|                           CLAUDE CODE CLI                                    |
|                          (Main Agent Loop)                                   |
|                                 |                                            |
|          +----------------------+----------------------+                     |
|          |                      |                      |                     |
|    SESSION START          TOOL EXECUTION          SESSION END                |
|       HOOK                    HOOKS                  HOOK                    |
|    ~~~~~~~~~~~~           ~~~~~~~~~~~~            ~~~~~~~~~~~~               |
|    session_start_         [PostToolUse]           session_end_               |
|    findings.py            episode_capture.py      learning.py                |
|    + context_prime.py     [SubagentStop]          + episode_commit.py        |
|                           learning_capture.py                                |
|                                 |                                            |
|          +----------------------+----------------------+                     |
|          |                      |                      |                     |
|   CONTEXT MANAGER         EPISODE STORE          PATTERN ENGINE              |
|   ~~~~~~~~~~~~~~~         ~~~~~~~~~~~~~          ~~~~~~~~~~~~~~              |
|   • Recent findings       • Task episodes        • Match patterns            |
|   • Session handoff       • Success/fail         • Suggest approaches        |
|   • Work item links       • Reasoning chains     • Learn from outcomes       |
|   • Branch context        • Tool sequences                                   |
|                                 |                                            |
|                    +------------+------------+                               |
|                    |                         |                               |
|              MEMORY STORE              PATTERN STORE                         |
|              ~~~~~~~~~~~~              ~~~~~~~~~~~~~                         |
|              SQLite + vec              JSON patterns                         |
|              • Embeddings              • Task templates                      |
|              • Semantic search         • Successful sequences                |
|              • Similar tasks           • Error recovery                      |
|                                                                              |
+-----------------------------------------------------------------------------+
                                   |
              EXISTING INFRASTRUCTURE (No Changes Required)
              ~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
              • Skills (code-review, architecture-review, etc.)
              • Agents (software-architect, database-architect, etc.)
              • Findings (local + global store)
              • Hooks (session_start_findings.py, prompt_submit_findings.py)
```

---

## Component Design

### 1. Episode Store

An "episode" is a complete unit of work: task description, reasoning, actions taken, and outcome.

```
~/.claude/ultra-agent/
├── episodes/
│   ├── episodes.jsonl          # Append-only episode log
│   ├── episodes.db             # SQLite with embeddings (sqlite-vec)
│   └── index.json              # Fast lookup cache
├── patterns/
│   ├── task-patterns.json      # Learned task templates
│   ├── error-recovery.json     # Known error->fix mappings
│   └── tool-sequences.json     # Common tool patterns
└── config.json                 # Ultra Agent settings
```

**Episode Schema**:

```json
{
  "id": "ep-a1b2c3d4",
  "timestamp": "2025-12-23T10:30:00Z",
  "task": {
    "description": "Add retry logic to API client",
    "type": "feature",
    "complexity": "medium",
    "repo": "my-service",
    "branch": "feature/AB#1234-retry-logic"
  },
  "reasoning": [
    {"step": 1, "thought": "Need to identify all API calls", "action": "grep"},
    {"step": 2, "thought": "Use Polly library for .NET", "action": "read"},
    {"step": 3, "thought": "Add exponential backoff", "action": "edit"}
  ],
  "tools_used": ["Grep", "Read", "Edit", "Bash"],
  "files_modified": ["src/ApiClient.cs", "src/RetryPolicy.cs"],
  "outcome": {
    "success": true,
    "tests_passed": true,
    "build_passed": true,
    "error": null
  },
  "duration_seconds": 180,
  "tokens_used": 25000,
  "linked_findings": ["f-abc123"],
  "linked_work_item": "AB#1234"
}
```

### 2. Enhanced Context Manager

Extends your existing `session_context.py` to include episode-based priming.

**Responsibilities**:
- Load findings context (existing)
- Load relevant past episodes for similar tasks
- Inject successful patterns as suggestions
- Track current session for episode capture

**Enhancement to session_start_findings.py**:

```python
# After loading findings context, also load relevant episodes
episodes = episode_store.find_similar(
    task_description=prompt,
    repo=current_repo,
    limit=3
)

if episodes:
    print("## Relevant Past Episodes")
    for ep in episodes:
        print(f"- {ep.task.description} ({ep.outcome.success})")
        if ep.outcome.success:
            print(f"  Approach: {summarize_reasoning(ep.reasoning)}")
```

### 3. Pattern Engine

Extracts and matches patterns from successful episodes.

**Pattern Types**:

| Type | Example | Trigger |
|------|---------|---------|
| Task Template | "Add X to Y" | Similar task description |
| Tool Sequence | Grep -> Read -> Edit | Beginning of task |
| Error Recovery | "ModuleNotFoundError" -> pip install | Error encountered |
| Refactor Pattern | Extract method with tests | Refactor request |

**Pattern Schema**:

```json
{
  "id": "pat-xyz789",
  "name": "dotnet-retry-pattern",
  "type": "task_template",
  "triggers": ["retry", "resilience", "polly", "exponential backoff"],
  "template": {
    "steps": [
      "1. Identify existing HTTP client usage",
      "2. Add Polly NuGet package",
      "3. Create retry policy with exponential backoff",
      "4. Wrap HTTP calls with policy",
      "5. Add unit tests for retry behavior"
    ],
    "common_files": ["**/HttpClient*.cs", "**/ApiClient.cs"],
    "typical_tools": ["Grep", "Read", "Edit", "Bash"]
  },
  "success_rate": 0.87,
  "usage_count": 15,
  "last_used": "2025-12-20T14:00:00Z"
}
```

### 4. Learning Hooks

New hooks that capture learning opportunities.

**PostToolUse: episode_capture.py**

```python
# Captures tool usage as part of current episode
# Runs after every tool execution
# Appends to ~/.claude/ultra-agent/current-episode.json
```

**SubagentStop: learning_capture.py**

```python
# Captures outcome when subagent completes
# Records success/failure + reasoning chain
# Updates pattern statistics
```

**SessionEnd: episode_commit.py**

```python
# Finalizes current episode
# Computes embeddings for semantic search
# Updates pattern store if successful
# Links to findings/work items
```

### 5. Memory Store (SQLite + sqlite-vec)

SQLite database with vector embeddings for semantic search.

**Why SQLite + sqlite-vec**:
- Single file, zero configuration
- Works offline
- Fast enough for thousands of episodes
- sqlite-vec extension adds vector similarity search
- No external embedding service required (use local sentence-transformers)

**Schema**:

```sql
CREATE TABLE episodes (
    id TEXT PRIMARY KEY,
    timestamp TEXT,
    task_description TEXT,
    task_type TEXT,
    repo TEXT,
    branch TEXT,
    outcome_success BOOLEAN,
    duration_seconds INTEGER,
    data_json TEXT,  -- Full episode JSON
    embedding BLOB   -- Vector for semantic search (sqlite-vec)
);

CREATE VIRTUAL TABLE episodes_vec USING vec0(
    id TEXT,
    embedding float[384]  -- all-MiniLM-L6-v2 dimension
);

CREATE TABLE patterns (
    id TEXT PRIMARY KEY,
    name TEXT,
    type TEXT,
    triggers TEXT,  -- JSON array
    template_json TEXT,
    success_rate REAL,
    usage_count INTEGER,
    last_used TEXT
);
```

---

## Integration Points

### With Existing Findings System

```
                    FINDINGS <---> EPISODES

Finding discovered ──────────────► Episode records finding
during task                        (linked_findings)

Episode outcome ──────────────────► Finding updated
(success/fail)                      (status, resolution)

Similar finding ──────────────────► Episode suggested
in new session                      (pattern from past success)
```

### With Existing Agents

Agents continue to work unchanged. Ultra Agent adds:

1. **Before agent runs**: Inject relevant episodes as context
2. **While agent runs**: Capture tool usage
3. **After agent completes**: Record outcome as episode

```python
# In software-architect agent prompt (optional enhancement)
"""
## Relevant Past Decisions

The following past episodes are relevant to this task:
{inject_similar_episodes()}

Consider these approaches but evaluate if they apply.
"""
```

### With Existing Skills

Skills continue to work unchanged. Ultra Agent adds:

1. **code-review**: Capture review outcomes as episodes
2. **architecture-review**: Link findings to episodes
3. **azure-devops**: Auto-link work items to episodes

### Hook Integration

**Current hooks (unchanged)**:
- `SessionStart`: `session_start_findings.py`
- `UserPromptSubmit`: `slash_command_validator.py`, `prompt_submit_findings.py`
- `PreToolUse`: Bash echo
- `PostToolUse`: dotnet format

**New hooks (additive)**:
- `SessionStart`: `+ context_prime.py` (after findings)
- `PostToolUse`: `+ episode_capture.py`
- `SubagentStop`: `+ learning_capture.py` (new)
- `SessionEnd`: `+ episode_commit.py` (new)

**Updated settings.json**:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {"type": "command", "command": "python3 ~/.claude/hooks/session_start_findings.py"},
          {"type": "command", "command": "python3 ~/.claude/ultra-agent/hooks/context_prime.py"}
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {"type": "command", "command": "dotnet format --verify-no-changes || true"}
        ]
      },
      {
        "matcher": ".*",
        "hooks": [
          {"type": "command", "command": "python3 ~/.claude/ultra-agent/hooks/episode_capture.py"}
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {"type": "command", "command": "python3 ~/.claude/ultra-agent/hooks/learning_capture.py"}
        ]
      }
    ]
  }
}
```

---

## Data Flow

### Session Start

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. User starts Claude Code session                                       │
│    ↓                                                                     │
│ 2. session_start_findings.py loads findings context                      │
│    ↓                                                                     │
│ 3. context_prime.py:                                                     │
│    • Get current repo, branch, recent git history                        │
│    • Query episode store for similar tasks                               │
│    • Query pattern store for applicable patterns                         │
│    • Inject as context suggestions (not commands)                        │
│    ↓                                                                     │
│ 4. Claude receives primed context + finds relevant past work             │
└─────────────────────────────────────────────────────────────────────────┘
```

### During Task Execution

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. User gives task: "Add retry logic to the API client"                  │
│    ↓                                                                     │
│ 2. Claude reasons + uses tools (Grep, Read, Edit, Bash)                  │
│    ↓                                                                     │
│ 3. episode_capture.py (PostToolUse):                                     │
│    • Appends tool usage to current-episode.json                          │
│    • Records tool name, parameters, duration                             │
│    • Captures any errors                                                 │
│    ↓                                                                     │
│ 4. Repeat for each tool use                                              │
└─────────────────────────────────────────────────────────────────────────┘
```

### Task Completion

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. Task completes (success or failure)                                   │
│    ↓                                                                     │
│ 2. learning_capture.py (SubagentStop):                                   │
│    • Captures final outcome (build pass, tests pass)                     │
│    • Records reasoning chain (if available)                              │
│    • Links to findings created/resolved                                  │
│    ↓                                                                     │
│ 3. If successful:                                                        │
│    • Pattern engine analyzes for new patterns                            │
│    • Updates existing pattern success rates                              │
│    • Adds tool sequence to common patterns                               │
│    ↓                                                                     │
│ 4. If failed:                                                            │
│    • Records error for future avoidance                                  │
│    • Updates pattern failure rates                                       │
│    • Captures what went wrong for learning                               │
└─────────────────────────────────────────────────────────────────────────┘
```

### Session End

```
┌─────────────────────────────────────────────────────────────────────────┐
│ 1. User ends session or session times out                                │
│    ↓                                                                     │
│ 2. episode_commit.py:                                                    │
│    • Finalizes current-episode.json                                      │
│    • Computes embedding for semantic search                              │
│    • Appends to episodes.jsonl (source of truth)                         │
│    • Updates episodes.db (SQLite cache)                                  │
│    • Clears current-episode.json                                         │
│    ↓                                                                     │
│ 3. Ready for next session with learned context                           │
└─────────────────────────────────────────────────────────────────────────┘
```

---

## Semantic Search Implementation

### Local Embeddings (No API Required)

```python
# Using sentence-transformers (local, offline)
from sentence_transformers import SentenceTransformer

model = SentenceTransformer('all-MiniLM-L6-v2')  # 384 dimensions, fast

def embed_task(task_description: str) -> list[float]:
    return model.encode(task_description).tolist()

def find_similar_episodes(query: str, limit: int = 5) -> list[Episode]:
    query_embedding = embed_task(query)

    # Using sqlite-vec for similarity search
    cursor = db.execute("""
        SELECT e.*, distance
        FROM episodes e
        JOIN episodes_vec v ON e.id = v.id
        WHERE v.embedding MATCH ?
        ORDER BY distance
        LIMIT ?
    """, (query_embedding, limit))

    return [Episode.from_row(row) for row in cursor]
```

### Fallback: TF-IDF (Zero Dependencies)

```python
# If sentence-transformers not available, use TF-IDF
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity

# Pre-compute TF-IDF matrix for existing episodes
vectorizer = TfidfVectorizer(max_features=1000)
episode_vectors = vectorizer.fit_transform(episode_descriptions)

def find_similar_tfidf(query: str, limit: int = 5) -> list[Episode]:
    query_vec = vectorizer.transform([query])
    similarities = cosine_similarity(query_vec, episode_vectors)[0]
    top_indices = similarities.argsort()[-limit:][::-1]
    return [episodes[i] for i in top_indices]
```

---

## What Ultra Agent Does NOT Include (By Design)

| GODAGENT Feature | Ultra Agent Alternative | Rationale |
|------------------|------------------------|-----------|
| Daemon process | Stateless hooks | No ops burden, easier debugging |
| Unix socket IPC | File-based state | Portable, git-friendly |
| Custom hypergraph DB | findings relationships | Already have blocks/related_to |
| Vector DB server | SQLite + sqlite-vec | Single file, zero config |
| External embedding API | Local sentence-transformers | Offline, fast, private |
| Real-time learning | End-of-session commit | Simpler, more reliable |
| SOMA trainer | Pattern extraction | Simpler pattern matching |
| Force learning | Manual pattern curation | User control over learning |

---

## Success Metrics

How to know if Ultra Agent is working:

| Metric | Measurement | Target |
|--------|-------------|--------|
| Episode capture rate | Episodes / session | >80% of meaningful sessions |
| Pattern match rate | Suggestions used / offered | >30% acceptance |
| Task completion time | Average time per task type | 10% reduction |
| Error recovery | Auto-suggested fixes used | >50% when offered |
| Context relevance | User skips primed context | <20% skip rate |

---

## Security Considerations

1. **All data stays local** - No cloud services, no API calls for embeddings
2. **Episode sanitization** - Strip secrets before storing
3. **Private patterns** - Can mark patterns as repo-specific
4. **No code execution** - Hooks only capture, never execute learned code

---

## Next: Implementation Phases

See [implementation-phases.md](./ultra-agent-implementation-phases.md) for the P0-P3 rollout plan.

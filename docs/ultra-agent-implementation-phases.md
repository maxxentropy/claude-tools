# Ultra Agent Implementation Phases

## Overview

Ultra Agent is implemented in four phases, each delivering independent value.
You can stop at any phase and still have a useful system.

```
Phase 0 (P0)           Phase 1 (P1)           Phase 2 (P2)           Phase 3 (P3)
"Foundation"           "Episodes"             "Learning"             "Intelligence"
~~~~~~~~~~~~~~         ~~~~~~~~~~~            ~~~~~~~~~~~            ~~~~~~~~~~~~~~
• Episode schema       • Capture hooks        • Pattern engine       • Semantic search
• Current session      • Episode store        • Pattern matching     • Auto-suggestions
• Manual capture       • Basic queries        • Success tracking     • Cross-repo learning
                       • SQLite storage       • Error recovery       • Refinement UI

TIME: 1-2 days         TIME: 2-3 days         TIME: 3-5 days         TIME: 5-7 days
VALUE: Tracking        VALUE: Persistence     VALUE: Suggestions     VALUE: Intelligence
```

---

## Phase 0: Foundation (1-2 days)

### Goal
Establish the episode format and manual capture capability without any hooks.
Validate the data model before automating.

### Deliverables

**1. Directory Structure**

```
~/.claude/ultra-agent/
├── episodes/
│   ├── current-episode.json    # In-progress episode
│   └── episodes.jsonl          # Completed episodes
├── patterns/
│   └── .gitkeep
├── config.json                 # Configuration
└── README.md                   # Usage instructions
```

**2. Episode Schema** (`episode_schema.py`)

```python
@dataclass
class Episode:
    id: str
    timestamp: str
    task: TaskDescription
    reasoning: list[ReasoningStep]
    tools_used: list[str]
    files_modified: list[str]
    outcome: Outcome
    duration_seconds: int
    tokens_used: Optional[int]
    linked_findings: list[str]
    linked_work_item: Optional[str]
```

**3. Manual Capture Script** (`capture_episode.py`)

```bash
# Start tracking an episode
python3 ~/.claude/ultra-agent/scripts/capture_episode.py start \
  --task "Add retry logic to API client" \
  --type feature

# Add a reasoning step
python3 ~/.claude/ultra-agent/scripts/capture_episode.py step \
  --thought "Need to identify all API calls" \
  --action "grep"

# Complete the episode
python3 ~/.claude/ultra-agent/scripts/capture_episode.py complete \
  --success \
  --tests-passed \
  --build-passed
```

**4. Query Script** (`query_episodes.py`)

```bash
# List recent episodes
python3 ~/.claude/ultra-agent/scripts/query_episodes.py --recent 10

# Search by task type
python3 ~/.claude/ultra-agent/scripts/query_episodes.py --type feature

# Show episode details
python3 ~/.claude/ultra-agent/scripts/query_episodes.py --show ep-abc123
```

### Success Criteria

- [ ] Can manually capture an episode
- [ ] Episode persists in JSONL file
- [ ] Can query and view past episodes
- [ ] Schema supports all needed fields

### Files to Create

| File | Purpose |
|------|---------|
| `~/.claude/ultra-agent/scripts/episode_store.py` | Core storage logic |
| `~/.claude/ultra-agent/scripts/capture_episode.py` | CLI for manual capture |
| `~/.claude/ultra-agent/scripts/query_episodes.py` | CLI for queries |
| `~/.claude/ultra-agent/config.json` | Configuration |

---

## Phase 1: Episodes (2-3 days)

### Goal
Automatic episode capture via hooks. Every meaningful session becomes an episode.

### Deliverables

**1. PostToolUse Hook** (`episode_capture.py`)

Captures tool usage in real-time:

```python
#!/usr/bin/env python3
"""
PostToolUse hook that captures tool usage for current episode.
Runs after every tool execution.
"""
import json
import sys
from pathlib import Path

# Load hook input from stdin
hook_input = json.load(sys.stdin)
tool_name = hook_input.get("tool_name")
tool_params = hook_input.get("tool_params", {})
tool_result = hook_input.get("tool_result", {})

# Append to current episode
current_episode = Path.home() / ".claude/ultra-agent/episodes/current-episode.json"
# ... append logic
```

**2. Session End Hook** (`episode_commit.py`)

Finalizes episode when session ends:

```python
#!/usr/bin/env python3
"""
SessionEnd hook that commits the current episode.
Computes statistics and appends to episodes.jsonl.
"""
# Finalize current episode
# Calculate duration, token usage
# Append to episodes.jsonl
# Clear current-episode.json
```

**3. Context Prime Hook** (`context_prime.py`)

Loads relevant context at session start:

```python
#!/usr/bin/env python3
"""
SessionStart hook that primes context with relevant episodes.
Runs after session_start_findings.py.
"""
# Get current repo and recent git activity
# Query for similar past episodes
# Output relevant context for Claude
```

**4. SQLite Storage**

Add SQLite for faster queries:

```python
# episode_store.py additions
class EpisodeStore:
    def __init__(self, use_sqlite: bool = True):
        self.sqlite_path = self.episodes_dir / "episodes.db"
        if use_sqlite:
            self._init_sqlite()

    def _init_sqlite(self):
        # Create tables, indexes
        pass

    def query_by_repo(self, repo: str) -> list[Episode]:
        # Fast SQLite query
        pass

    def query_by_task_type(self, task_type: str) -> list[Episode]:
        # Fast SQLite query
        pass
```

### Settings.json Updates

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
        "matcher": ".*",
        "hooks": [
          {"type": "command", "command": "python3 ~/.claude/ultra-agent/hooks/episode_capture.py", "timeout": 5}
        ]
      }
    ]
  }
}
```

### Success Criteria

- [ ] Episodes automatically captured during sessions
- [ ] Tool usage tracked in real-time
- [ ] Episodes committed on session end
- [ ] Can query episodes by repo, type, date
- [ ] Context primed with relevant episodes

### Files to Create

| File | Purpose |
|------|---------|
| `~/.claude/ultra-agent/hooks/context_prime.py` | SessionStart hook |
| `~/.claude/ultra-agent/hooks/episode_capture.py` | PostToolUse hook |
| `~/.claude/ultra-agent/hooks/episode_commit.py` | SessionEnd hook |
| `~/.claude/ultra-agent/scripts/episode_store.py` | Updated with SQLite |

---

## Phase 2: Learning (3-5 days)

### Goal
Extract patterns from successful episodes and suggest them for similar tasks.

### Deliverables

**1. Pattern Schema** (`pattern_schema.py`)

```python
@dataclass
class Pattern:
    id: str
    name: str
    type: str  # task_template, tool_sequence, error_recovery
    triggers: list[str]  # Keywords that trigger this pattern
    template: dict  # Steps, common files, typical tools
    success_rate: float
    usage_count: int
    last_used: str
    source_episodes: list[str]  # Episodes this was learned from
```

**2. Pattern Engine** (`pattern_engine.py`)

```python
class PatternEngine:
    def __init__(self, episode_store: EpisodeStore):
        self.episode_store = episode_store
        self.patterns = self._load_patterns()

    def extract_patterns(self, episode: Episode) -> list[Pattern]:
        """Extract patterns from a successful episode."""
        patterns = []

        # Extract task template pattern
        if episode.outcome.success:
            template = self._extract_task_template(episode)
            if template:
                patterns.append(template)

            # Extract tool sequence pattern
            tool_seq = self._extract_tool_sequence(episode)
            if tool_seq:
                patterns.append(tool_seq)

        return patterns

    def match_patterns(self, task_description: str) -> list[Pattern]:
        """Find patterns relevant to a task."""
        matched = []
        for pattern in self.patterns:
            if self._matches_triggers(task_description, pattern.triggers):
                matched.append(pattern)
        return sorted(matched, key=lambda p: p.success_rate, reverse=True)

    def update_statistics(self, pattern_id: str, used: bool, success: bool):
        """Update pattern usage statistics."""
        pattern = self._get_pattern(pattern_id)
        pattern.usage_count += 1
        if used:
            # Update success rate with exponential moving average
            alpha = 0.1
            pattern.success_rate = (alpha * (1.0 if success else 0.0) +
                                   (1 - alpha) * pattern.success_rate)
        pattern.last_used = datetime.now(timezone.utc).isoformat()
```

**3. Error Recovery Patterns**

Special patterns for common errors:

```python
# error_patterns.json
{
  "patterns": [
    {
      "id": "err-module-not-found",
      "type": "error_recovery",
      "triggers": ["ModuleNotFoundError", "No module named"],
      "recovery": {
        "diagnosis": "Python module not installed",
        "fix": "pip install {module_name}",
        "verification": "python -c 'import {module_name}'"
      },
      "success_rate": 0.95
    },
    {
      "id": "err-dotnet-restore",
      "type": "error_recovery",
      "triggers": ["NU1101", "Unable to find package"],
      "recovery": {
        "diagnosis": "NuGet package not restored",
        "fix": "dotnet restore",
        "verification": "dotnet build"
      },
      "success_rate": 0.92
    }
  ]
}
```

**4. Pattern Suggestions in Context**

Update `context_prime.py` to include pattern suggestions:

```python
# In context_prime.py
patterns = pattern_engine.match_patterns(task_description)
if patterns:
    print("\n## Suggested Approaches\n")
    for i, pattern in enumerate(patterns[:3], 1):
        print(f"{i}. **{pattern.name}** (success rate: {pattern.success_rate:.0%})")
        print(f"   Based on: {len(pattern.source_episodes)} similar tasks")
        if pattern.template.get("steps"):
            print("   Steps:")
            for step in pattern.template["steps"][:3]:
                print(f"     - {step}")
```

### Success Criteria

- [ ] Patterns extracted from successful episodes
- [ ] Pattern matching by task description
- [ ] Error recovery patterns working
- [ ] Suggestions shown at session start
- [ ] Pattern success rates updated based on usage

### Files to Create

| File | Purpose |
|------|---------|
| `~/.claude/ultra-agent/scripts/pattern_engine.py` | Pattern extraction and matching |
| `~/.claude/ultra-agent/patterns/task-patterns.json` | Task template patterns |
| `~/.claude/ultra-agent/patterns/tool-sequences.json` | Common tool patterns |
| `~/.claude/ultra-agent/patterns/error-recovery.json` | Error fix patterns |
| `~/.claude/ultra-agent/hooks/context_prime.py` | Updated with patterns |

---

## Phase 3: Intelligence (5-7 days)

### Goal
Semantic search for similar tasks and intelligent auto-suggestions.

### Deliverables

**1. Local Embeddings**

Using sentence-transformers for offline embeddings:

```python
# embedding_service.py
from sentence_transformers import SentenceTransformer
import sqlite3
import numpy as np

class EmbeddingService:
    def __init__(self, model_name: str = "all-MiniLM-L6-v2"):
        self.model = SentenceTransformer(model_name)
        self.dimension = 384  # Model output dimension

    def embed(self, text: str) -> list[float]:
        """Generate embedding for text."""
        return self.model.encode(text).tolist()

    def embed_batch(self, texts: list[str]) -> list[list[float]]:
        """Generate embeddings for multiple texts."""
        return self.model.encode(texts).tolist()
```

**2. SQLite-vec Integration**

Vector similarity search in SQLite:

```python
# episode_store.py additions
import sqlite_vec

class EpisodeStore:
    def _init_sqlite_vec(self):
        """Initialize sqlite-vec for vector search."""
        self.conn.enable_load_extension(True)
        sqlite_vec.load(self.conn)

        self.conn.executescript("""
            CREATE VIRTUAL TABLE IF NOT EXISTS episode_embeddings
            USING vec0(
                id TEXT PRIMARY KEY,
                embedding float[384]
            );
        """)

    def add_embedding(self, episode_id: str, embedding: list[float]):
        """Store episode embedding."""
        self.conn.execute(
            "INSERT INTO episode_embeddings (id, embedding) VALUES (?, ?)",
            (episode_id, embedding)
        )

    def find_similar(self, query_embedding: list[float], limit: int = 5) -> list[Episode]:
        """Find similar episodes by embedding."""
        cursor = self.conn.execute("""
            SELECT e.*, vec_distance_L2(v.embedding, ?) as distance
            FROM episodes e
            JOIN episode_embeddings v ON e.id = v.id
            ORDER BY distance
            LIMIT ?
        """, (query_embedding, limit))

        return [Episode.from_row(row) for row in cursor]
```

**3. Smart Context Injection**

Semantic search for relevant context:

```python
# context_prime.py (enhanced)
def prime_context(task_description: str):
    """Prime context with semantically similar episodes."""

    # Generate embedding for current task
    query_embedding = embedding_service.embed(task_description)

    # Find similar episodes
    similar_episodes = episode_store.find_similar(query_embedding, limit=5)

    # Filter to successful ones
    successful = [ep for ep in similar_episodes if ep.outcome.success]

    if successful:
        print("\n## Similar Past Tasks (Successful)\n")
        for ep in successful[:3]:
            similarity = 1 - ep.distance  # Convert distance to similarity
            print(f"- [{similarity:.0%}] {ep.task.description}")
            print(f"  Approach: {summarize_reasoning(ep.reasoning)}")
            if ep.files_modified:
                print(f"  Files: {', '.join(ep.files_modified[:3])}")
```

**4. Cross-Repo Learning**

Learn from episodes across all repositories:

```python
# Global episode store at ~/.claude/ultra-agent/global/
class GlobalEpisodeStore:
    def __init__(self):
        self.global_dir = Path.home() / ".claude/ultra-agent/global"
        self.global_db = self.global_dir / "global-episodes.db"

    def sync_from_local(self, local_store: EpisodeStore, repo_name: str):
        """Sync episodes from local repo to global store."""
        for episode in local_store.get_all():
            if not episode.tags or "private" not in episode.tags:
                global_episode = episode.copy()
                global_episode.source_repo = repo_name
                self.add(global_episode)

    def find_cross_repo_patterns(self, task_type: str) -> list[Pattern]:
        """Find patterns across all repositories."""
        episodes = self.query_by_task_type(task_type)
        return self.pattern_engine.extract_common_patterns(episodes)
```

**5. Refinement Commands**

Commands for curating learned patterns:

```bash
# View learned patterns
python3 ~/.claude/ultra-agent/scripts/manage_patterns.py list

# Boost a pattern (increase priority)
python3 ~/.claude/ultra-agent/scripts/manage_patterns.py boost pat-abc123

# Suppress a pattern (won't suggest)
python3 ~/.claude/ultra-agent/scripts/manage_patterns.py suppress pat-abc123

# Delete a pattern
python3 ~/.claude/ultra-agent/scripts/manage_patterns.py delete pat-abc123

# Export patterns (for sharing)
python3 ~/.claude/ultra-agent/scripts/manage_patterns.py export > my-patterns.json

# Import patterns
python3 ~/.claude/ultra-agent/scripts/manage_patterns.py import team-patterns.json
```

### Success Criteria

- [ ] Local embeddings working (offline)
- [ ] Semantic search finding similar episodes
- [ ] Cross-repo learning syncing
- [ ] Pattern refinement commands working
- [ ] Suggestions relevance >30% acceptance

### Files to Create

| File | Purpose |
|------|---------|
| `~/.claude/ultra-agent/scripts/embedding_service.py` | Local embedding generation |
| `~/.claude/ultra-agent/scripts/global_store.py` | Cross-repo episode store |
| `~/.claude/ultra-agent/scripts/manage_patterns.py` | Pattern curation CLI |
| `~/.claude/ultra-agent/global/global-episodes.db` | Global episode database |

---

## Dependencies by Phase

### P0: Foundation

```
# No new dependencies (uses standard library)
python >= 3.10
```

### P1: Episodes

```
# pyproject.toml
[project.optional-dependencies]
episodes = []  # Still no new deps
```

### P2: Learning

```
# pyproject.toml
[project.optional-dependencies]
learning = []  # Pattern matching uses standard library
```

### P3: Intelligence

```
# pyproject.toml
[project.optional-dependencies]
intelligence = [
    "sentence-transformers>=2.2.0",
    "sqlite-vec>=0.1.0",
    "torch>=2.0.0",  # Required by sentence-transformers
]
```

**Note**: P3 has heavier dependencies. Consider:
- Installing in a dedicated venv: `~/.claude/ultra-agent/.venv`
- Using lazy loading (only import when needed)
- Providing TF-IDF fallback (no heavy deps)

---

## Rollback Plan

Each phase can be rolled back independently:

| Phase | Rollback Action |
|-------|-----------------|
| P0 | Delete `~/.claude/ultra-agent/` |
| P1 | Remove hooks from settings.json |
| P2 | Delete patterns/ directory |
| P3 | Remove global/ directory, uninstall deps |

---

## Validation Checklist

### After P0

- [ ] `python3 ~/.claude/ultra-agent/scripts/capture_episode.py --help` works
- [ ] Can manually create an episode
- [ ] Episode appears in `episodes.jsonl`

### After P1

- [ ] Sessions automatically create episodes
- [ ] Context shows relevant past work
- [ ] `query_episodes.py --recent` shows recent episodes

### After P2

- [ ] Patterns extracted from successful episodes
- [ ] Pattern suggestions shown at session start
- [ ] `manage_patterns.py list` shows learned patterns

### After P3

- [ ] Semantic search returns relevant results
- [ ] Cross-repo patterns available
- [ ] Pattern refinement commands work

---

## Next: ADR

See [ADR-001-ultra-agent.md](./adr/ADR-001-ultra-agent.md) for the formal decision record.

# Ultra Agent File Structure

## Complete Directory Layout

```
~/.claude/
├── ultra-agent/                          # <-- NEW: Ultra Agent System
│   │
│   ├── episodes/                         # Episode storage
│   │   ├── current-episode.json          # In-progress episode (reset each session)
│   │   ├── episodes.jsonl                # Append-only episode log (source of truth)
│   │   ├── episodes.db                   # SQLite cache with embeddings
│   │   └── index.json                    # Fast lookup cache
│   │
│   ├── patterns/                         # Learned patterns
│   │   ├── task-patterns.json            # Task template patterns
│   │   ├── tool-sequences.json           # Common tool sequences
│   │   ├── error-recovery.json           # Error -> fix mappings
│   │   └── custom/                       # User-defined patterns
│   │       └── *.json
│   │
│   ├── global/                           # Cross-repo learning (P3)
│   │   ├── global-episodes.db            # Aggregated episodes
│   │   ├── global-patterns.json          # Cross-repo patterns
│   │   └── repositories.json             # Known repos
│   │
│   ├── hooks/                            # Ultra Agent hooks
│   │   ├── context_prime.py              # SessionStart: prime context
│   │   ├── episode_capture.py            # PostToolUse: capture tools
│   │   ├── learning_capture.py           # SubagentStop: capture outcome
│   │   └── episode_commit.py             # SessionEnd: finalize episode
│   │
│   ├── scripts/                          # CLI tools
│   │   ├── episode_store.py              # Core episode storage
│   │   ├── pattern_engine.py             # Pattern extraction/matching
│   │   ├── embedding_service.py          # Local embeddings (P3)
│   │   ├── global_store.py               # Cross-repo store (P3)
│   │   ├── capture_episode.py            # Manual episode capture
│   │   ├── query_episodes.py             # Episode queries
│   │   └── manage_patterns.py            # Pattern curation
│   │
│   ├── models/                           # Downloaded models (P3)
│   │   └── all-MiniLM-L6-v2/             # Sentence transformer model
│   │
│   ├── .venv/                            # Python virtual environment
│   │
│   ├── config.json                       # Ultra Agent configuration
│   ├── pyproject.toml                    # Python dependencies
│   └── README.md                         # Usage documentation
│
├── hooks/                                # EXISTING: Your current hooks
│   ├── session_start_findings.py         # Load findings (keep as-is)
│   ├── prompt_submit_findings.py         # Show status (keep as-is)
│   └── slash_command_validator.py        # Validate commands (keep as-is)
│
├── skills/                               # EXISTING: Your skills
│   └── findings/                         # Already integrated
│
├── agents/                               # EXISTING: Your agents
│   └── *.md                              # Continue working as-is
│
├── findings/                             # EXISTING: Global findings
│   └── ...
│
└── settings.json                         # UPDATED: Add Ultra Agent hooks
```

## Integration with Existing Structure

### settings.json Updates

Current settings.json already has hooks. Ultra Agent adds to them:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/session_start_findings.py",
            "timeout": 15
          },
          {
            "type": "command",
            "command": "python3 ~/.claude/ultra-agent/hooks/context_prime.py",
            "timeout": 10
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          {
            "type": "command",
            "command": "echo 'Executing bash command...'",
            "timeout": 5
          }
        ]
      }
    ],
    "PostToolUse": [
      {
        "matcher": "Edit|Write|MultiEdit",
        "hooks": [
          {
            "type": "command",
            "command": "dotnet format --verify-no-changes || true",
            "timeout": 30
          }
        ]
      },
      {
        "matcher": ".*",
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/ultra-agent/hooks/episode_capture.py",
            "timeout": 5
          }
        ]
      }
    ],
    "SubagentStop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/ultra-agent/hooks/learning_capture.py",
            "timeout": 10
          }
        ]
      }
    ],
    "UserPromptSubmit": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/slash_command_validator.py"
          },
          {
            "type": "command",
            "command": "python3 ~/.claude/hooks/prompt_submit_findings.py",
            "timeout": 5
          }
        ]
      }
    ]
  }
}
```

## File Details

### Core Files (P0-P1)

| File | Phase | Purpose |
|------|-------|---------|
| `episodes/current-episode.json` | P0 | Tracks current session's episode |
| `episodes/episodes.jsonl` | P0 | Append-only episode log |
| `scripts/episode_store.py` | P0 | Episode CRUD operations |
| `scripts/capture_episode.py` | P0 | Manual CLI for episode capture |
| `scripts/query_episodes.py` | P0 | CLI for querying episodes |
| `config.json` | P0 | Configuration settings |
| `hooks/context_prime.py` | P1 | Loads context at session start |
| `hooks/episode_capture.py` | P1 | Captures tool usage |
| `hooks/episode_commit.py` | P1 | Finalizes episode |
| `episodes/episodes.db` | P1 | SQLite cache for fast queries |

### Learning Files (P2)

| File | Phase | Purpose |
|------|-------|---------|
| `patterns/task-patterns.json` | P2 | Task template patterns |
| `patterns/tool-sequences.json` | P2 | Common tool sequences |
| `patterns/error-recovery.json` | P2 | Error -> fix patterns |
| `scripts/pattern_engine.py` | P2 | Pattern extraction/matching |
| `hooks/learning_capture.py` | P2 | Captures outcomes for learning |

### Intelligence Files (P3)

| File | Phase | Purpose |
|------|-------|---------|
| `scripts/embedding_service.py` | P3 | Local embedding generation |
| `scripts/global_store.py` | P3 | Cross-repo episode store |
| `scripts/manage_patterns.py` | P3 | Pattern curation |
| `global/global-episodes.db` | P3 | Aggregated cross-repo data |
| `models/all-MiniLM-L6-v2/` | P3 | Downloaded sentence transformer |

## config.json Schema

```json
{
  "version": "1.0.0",
  "enabled": true,

  "episodes": {
    "auto_capture": true,
    "min_duration_seconds": 30,
    "max_tools_before_commit": 100,
    "include_token_counts": true
  },

  "patterns": {
    "auto_extract": true,
    "min_success_rate": 0.5,
    "min_usage_count": 3,
    "max_patterns": 500
  },

  "embeddings": {
    "enabled": true,
    "model": "all-MiniLM-L6-v2",
    "fallback": "tfidf"
  },

  "global": {
    "enabled": true,
    "sync_on_commit": true,
    "exclude_private": true
  },

  "context": {
    "max_episodes": 5,
    "max_patterns": 3,
    "show_reasoning": true
  },

  "privacy": {
    "exclude_repos": [],
    "exclude_tags": ["private", "sensitive"]
  }
}
```

## pyproject.toml

```toml
[project]
name = "ultra-agent"
version = "0.1.0"
description = "Continuous learning system for Claude Code"
requires-python = ">=3.10"
dependencies = []  # No deps for P0-P2

[project.optional-dependencies]
full = [
    "sentence-transformers>=2.2.0",
    "sqlite-vec>=0.1.0",
]
dev = [
    "pytest>=7.0",
    "pytest-cov",
]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["."]
```

## Data Flow by File

```
User Task
    │
    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ SESSION START                                                         │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  session_start_findings.py ──► findings context                       │
│            │                                                          │
│            ▼                                                          │
│  context_prime.py                                                     │
│            │                                                          │
│            ├── Read: episodes.db ──► similar episodes                 │
│            ├── Read: task-patterns.json ──► matching patterns         │
│            └── Output: primed context to Claude                       │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ TOOL EXECUTION (repeated)                                             │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  Claude uses tool (Grep, Read, Edit, etc.)                           │
│            │                                                          │
│            ▼                                                          │
│  episode_capture.py                                                   │
│            │                                                          │
│            └── Write: current-episode.json                            │
│                (append tool usage)                                    │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ SUBAGENT COMPLETE (if using agents)                                   │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  learning_capture.py                                                  │
│            │                                                          │
│            ├── Read: current-episode.json                             │
│            ├── Analyze: outcome, reasoning                            │
│            ├── Update: pattern success rates                          │
│            └── Write: task-patterns.json (if new pattern)             │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
                    │
                    ▼
┌──────────────────────────────────────────────────────────────────────┐
│ SESSION END                                                           │
├──────────────────────────────────────────────────────────────────────┤
│                                                                       │
│  episode_commit.py                                                    │
│            │                                                          │
│            ├── Read: current-episode.json                             │
│            ├── Compute: embeddings (P3)                               │
│            ├── Write: episodes.jsonl (append)                         │
│            ├── Write: episodes.db (upsert)                            │
│            ├── Write: global-episodes.db (sync) (P3)                  │
│            └── Clear: current-episode.json                            │
│                                                                       │
└──────────────────────────────────────────────────────────────────────┘
```

## Relationship to Existing Files

| Existing File | Ultra Agent Integration |
|---------------|------------------------|
| `~/.claude/hooks/session_start_findings.py` | Runs first, then context_prime.py |
| `~/.claude/hooks/prompt_submit_findings.py` | Unchanged |
| `~/.claude/skills/findings/` | Episodes can link to findings |
| `~/.claude/findings/` | Global findings separate from episodes |
| `~/.claude/agents/` | Agents work unchanged, episodes capture their work |
| `~/.claude/settings.json` | Add Ultra Agent hooks |
| `~/source/tools/claude-tools/` | Symlink scripts or import |

## Git Tracking

### Git-Tracked Files

```
episodes/
└── episodes.jsonl      # Source of truth, trackable history

patterns/
├── task-patterns.json  # Learned patterns
├── tool-sequences.json
├── error-recovery.json
└── custom/*.json       # User patterns

config.json             # Configuration
```

### Git-Ignored Files

```
episodes/
├── current-episode.json  # Session state
├── episodes.db           # Cache (rebuildable)
└── index.json            # Cache (rebuildable)

global/                   # Personal aggregation
.venv/                    # Dependencies
models/                   # Downloaded models
```

### Suggested .gitignore

```gitignore
# Ultra Agent
episodes/current-episode.json
episodes/episodes.db
episodes/index.json
global/
.venv/
models/
*.pyc
__pycache__/
```

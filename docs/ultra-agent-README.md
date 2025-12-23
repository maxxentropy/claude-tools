# Ultra Agent - Continuous Learning for Claude Code

A pragmatic continuous learning system that makes Claude Code smarter over time.

## What is Ultra Agent?

Ultra Agent extends your existing Claude Code setup with:

1. **Episode Memory**: Remember what worked (and what did not) across sessions
2. **Pattern Learning**: Extract and suggest successful approaches
3. **Semantic Search**: Find similar past tasks to inform new ones
4. **Cross-Repo Learning**: Share patterns across your projects

```
Before Ultra Agent:        After Ultra Agent:
==================        =================

Session 1: Fix N+1         Session 1: Fix N+1
Session 2: (no memory)     Session 2: "You fixed a similar N+1
Session 3: (no memory)              query last week. Here's
                                    what worked..."
```

## Philosophy

**"The best architecture is the simplest one that will still work in 2 years."**

Ultra Agent is NOT:
- A complex daemon process
- A cloud service
- Dependent on external APIs
- Difficult to debug

Ultra Agent IS:
- File-based and portable
- Incrementally adoptable
- Built on SQLite and JSON
- Privacy-preserving (all local)

## Quick Comparison: GODAGENT vs Ultra Agent

| Feature | GODAGENT | Ultra Agent |
|---------|----------|-------------|
| Background Process | Daemon required | Stateless hooks |
| Storage | Custom hypergraph DB | SQLite + JSONL |
| Embeddings | External API | Local sentence-transformers |
| Complexity | High | Low |
| Operational Burden | Significant | None |
| Incremental Adoption | No | Yes |
| Works Offline | Maybe | Yes |

## Documentation

| Document | Purpose |
|----------|---------|
| [Architecture](./ultra-agent-architecture.md) | System design, component interactions |
| [Implementation Phases](./ultra-agent-implementation-phases.md) | P0-P3 rollout plan |
| [File Structure](./ultra-agent-file-structure.md) | Directory layout, integration points |
| [ADR-001](./adr/ADR-001-ultra-agent.md) | Architectural decision record |

## Quick Start

### Prerequisites

- Your existing Claude Code setup (skills, findings, hooks)
- Python 3.10+
- 10 minutes

### P0: Foundation (Start Here)

```bash
# Create the directory structure
mkdir -p ~/.claude/ultra-agent/{episodes,patterns,hooks,scripts}

# Copy the P0 files (when implemented)
cp ultra-agent/scripts/episode_store.py ~/.claude/ultra-agent/scripts/
cp ultra-agent/scripts/capture_episode.py ~/.claude/ultra-agent/scripts/
cp ultra-agent/scripts/query_episodes.py ~/.claude/ultra-agent/scripts/

# Initialize config
cat > ~/.claude/ultra-agent/config.json << 'EOF'
{
  "version": "1.0.0",
  "enabled": true,
  "episodes": {
    "auto_capture": false
  }
}
EOF

# Test manual episode capture
python3 ~/.claude/ultra-agent/scripts/capture_episode.py start \
  --task "Test Ultra Agent setup" \
  --type feature

python3 ~/.claude/ultra-agent/scripts/capture_episode.py complete \
  --success

# Verify
python3 ~/.claude/ultra-agent/scripts/query_episodes.py --recent
```

### P1: Auto-Capture (After P0 Works)

```bash
# Copy hook files
cp ultra-agent/hooks/*.py ~/.claude/ultra-agent/hooks/

# Update settings.json (add to existing hooks)
# See ultra-agent-file-structure.md for exact config

# Verify hooks work
claude --help  # Hooks should execute on session start
```

## How It Works

### Episode Capture Flow

```
1. You start a Claude Code session
   │
   ▼
2. context_prime.py runs (after findings)
   - Finds similar past episodes
   - Suggests relevant patterns
   │
   ▼
3. You work on a task
   - Claude uses tools (Grep, Edit, etc.)
   - episode_capture.py records each tool use
   │
   ▼
4. Task completes
   - learning_capture.py records outcome
   - Updates pattern success rates
   │
   ▼
5. Session ends
   - episode_commit.py finalizes episode
   - Computes embeddings for search
   - Ready for next session
```

### Pattern Learning Flow

```
Successful Episode
        │
        ▼
┌─────────────────────────────┐
│ Pattern Engine extracts:    │
│ • Task template             │
│ • Tool sequence             │
│ • Common files modified     │
└─────────────────────────────┘
        │
        ▼
   Pattern Store
        │
        ▼
┌─────────────────────────────┐
│ Next similar task:          │
│ "Based on 5 past successes, │
│  try this approach..."      │
└─────────────────────────────┘
```

## Integration with Existing Setup

Ultra Agent integrates with your existing infrastructure:

| Component | Integration |
|-----------|-------------|
| **Findings** | Episodes link to findings created/resolved |
| **Agents** | Capture agent outputs as episodes |
| **Skills** | Skills work unchanged; patterns may reference them |
| **Hooks** | Add Ultra Agent hooks alongside existing ones |
| **Work Items** | Episodes link to ADO/GitHub items |

## Data Privacy

All data stays local:
- Episodes stored in `~/.claude/ultra-agent/episodes/`
- Embeddings computed locally with sentence-transformers
- No cloud services required
- Can exclude repos/tags from sync

## Phases Overview

| Phase | Time | What You Get |
|-------|------|--------------|
| **P0** | 1-2 days | Manual episode capture, basic queries |
| **P1** | 2-3 days | Auto-capture, session context priming |
| **P2** | 3-5 days | Pattern learning, suggestions |
| **P3** | 5-7 days | Semantic search, cross-repo learning |

**You can stop at any phase** - each delivers value independently.

## Next Steps

1. Read [Architecture](./ultra-agent-architecture.md) for the full design
2. Review [Implementation Phases](./ultra-agent-implementation-phases.md) for the rollout plan
3. Start with P0 when ready

## Future Enhancements

Not in scope for initial implementation, but possible later:

- Team pattern sharing (git-tracked patterns)
- Pattern templates (pre-built patterns for common tasks)
- Learning analytics (what's being learned, success trends)
- Integration with evaluation framework
- Claude MCP server for richer integration

---

*Ultra Agent: Because Claude Code should learn from experience, not just follow instructions.*

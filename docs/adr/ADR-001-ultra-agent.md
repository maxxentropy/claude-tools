# ADR-001: Ultra Agent - Continuous Learning System for Claude Code

## Status

**Proposed** (2025-12-23)

## Context

The user has observed sophisticated "GODAGENT" architectures that provide continuous learning,
persistent memory, and reasoning capabilities for AI coding assistants. They want to implement
similar capabilities for their Claude Code setup, which already includes:

- **Skills**: code-review, architecture-review, findings, azure-devops, tla-plus, etc.
- **Agents**: software-architect, database-architect, security-engineer, etc.
- **Findings System**: Per-repo + global store with session context and handoff notes
- **Hooks**: SessionStart (findings context), UserPromptSubmit (status display)

The GODAGENT approach uses:
- Daemon process with Unix socket IPC
- Custom vector database with hypergraph storage
- SOMA trainer for trajectory learning
- DRR 3-layer context system
- Complex operational infrastructure

The user's goals are:
1. Produce production-quality code using industry best practices
2. Learn and improve as it does more work (continuous learning)
3. Enable taking on and completing more complex tasks
4. Have Claude guide them through larger projects

## Decision Drivers

1. **Operational Simplicity**: No daemon processes to manage, restart, or debug
2. **Build on Existing Infrastructure**: 80% of needed capabilities already exist
3. **Incremental Adoption**: Each phase delivers value independently
4. **Portable and Git-Friendly**: File-based storage that works across machines
5. **Zero External Dependencies for Core**: No cloud services required for basic operation
6. **Offline-First**: Work without internet connectivity
7. **Privacy**: All data stays local unless explicitly shared

## Considered Options

### Option 1: GODAGENT-Style Full Implementation

Implement the full GODAGENT architecture:
- Background daemon process
- Custom hypergraph database
- External vector embedding service
- Complex IPC via Unix sockets

**Pros**:
- Real-time learning
- Sophisticated graph relationships
- Maximum feature parity

**Cons**:
- Significant operational complexity
- Process management overhead
- Debugging difficulty
- Heavy dependencies
- Non-portable (daemon state)

### Option 2: Ultra Agent - Pragmatic Incremental Approach

Build on existing infrastructure with stateless hooks:
- Session-based capture (no daemon)
- SQLite + sqlite-vec for storage
- Local sentence-transformers for embeddings
- File-based persistence
- Incremental phases

**Pros**:
- No operational burden
- Builds on existing infrastructure
- Incrementally adoptable
- Git-trackable
- Works offline
- Simpler debugging

**Cons**:
- No real-time learning (end-of-session commit)
- Less sophisticated than hypergraph
- Limited cross-session state

### Option 3: Cloud-Based Learning

Use cloud services for storage and embeddings:
- Cloud vector database (Pinecone, Weaviate)
- OpenAI/Anthropic embeddings API
- Cloud-synced patterns

**Pros**:
- No local compute for embeddings
- Cross-machine sync
- Team sharing built-in

**Cons**:
- Requires internet connection
- Ongoing cloud costs
- Privacy concerns (code in cloud)
- Vendor lock-in
- Latency for searches

## Decision

We will implement **Option 2: Ultra Agent - Pragmatic Incremental Approach** because:

1. **80% Infrastructure Already Exists**: The findings system, hooks, and session context
   provide most of the foundation. We only need to add episode capture and pattern learning.

2. **No Operational Burden**: A daemon process requires monitoring, restart logic, logging,
   and debugging infrastructure. Stateless hooks are simpler and more reliable.

3. **Incremental Value**: Each phase (P0-P3) delivers independent value. The user can stop
   at any phase and still benefit. This matches their practical, ship-real-code approach.

4. **Git-Trackable**: Episodes and patterns in JSONL/JSON files can be version controlled,
   reviewed, and shared. This aligns with their existing findings system design.

5. **Local-First Privacy**: All data stays on the user's machine. Embeddings are computed
   locally with sentence-transformers. No code or task descriptions leave the machine.

6. **Technology Choices Are Boring**: SQLite, JSON, Python - well-understood, debuggable,
   and will still work in 2 years. No exotic dependencies for core functionality.

## Consequences

### Positive

1. **Quick Time to Value**: P0 can be implemented in 1-2 days with manual episode capture
2. **No Process Management**: No daemon to monitor, restart, or debug
3. **Portable**: Works identically across machines with file copy
4. **Debuggable**: All state in readable JSON/JSONL files
5. **Rollback Simple**: Each phase can be rolled back independently
6. **Builds Team Knowledge**: Can share patterns via git

### Negative

1. **No Real-Time Learning**: Learning happens at session end, not during
2. **Simpler Relationships**: No hypergraph; uses simpler linked lists
3. **Embedding Compute**: Local sentence-transformers uses CPU/GPU resources
4. **Session Boundary**: Must define what constitutes a "session"

### Risks

1. **Hook Timing Issues**: PostToolUse hooks run after tools; timing may vary
   - Mitigation: Use timeouts, handle missing captures gracefully

2. **Episode Bloat**: Long sessions could create very large episodes
   - Mitigation: Episode summarization, max tools limit

3. **Pattern Quality**: Auto-extracted patterns may be low quality
   - Mitigation: Success rate tracking, manual curation commands

4. **Embedding Model Size**: sentence-transformers models can be 100MB+
   - Mitigation: Use smallest effective model (all-MiniLM-L6-v2 at 80MB)

## Implementation Notes

### Phase Boundaries

| Phase | Time | Focus | Dependencies |
|-------|------|-------|--------------|
| P0 | 1-2 days | Schema, manual capture | Standard library only |
| P1 | 2-3 days | Hooks, automatic capture | Standard library only |
| P2 | 3-5 days | Pattern engine, suggestions | Standard library only |
| P3 | 5-7 days | Embeddings, semantic search | sentence-transformers, sqlite-vec |

### Key Technical Decisions

1. **SQLite over custom DB**: Single file, portable, well-understood, fast enough
2. **JSONL for episodes**: Append-only, git-friendly, human-readable
3. **Local embeddings**: Privacy, offline support, no API costs
4. **all-MiniLM-L6-v2**: Best balance of size (80MB) and quality (384 dim)
5. **Stateless hooks**: Simpler than daemon, each hook is independent

### Integration with Existing Systems

- **Findings**: Episodes can link to findings via `linked_findings` field
- **Agents**: Continue working unchanged; episodes capture their output
- **Skills**: Continue working unchanged; patterns may reference skills
- **Work Items**: Episodes link to ADO items via `linked_work_item` field

### Configuration

All configuration in `~/.claude/ultra-agent/config.json`:
- Enable/disable features
- Tune thresholds (min duration, max patterns)
- Privacy controls (exclude repos, tags)

## Related Decisions

- Findings system design (existing)
- Hook architecture (existing)
- Session context format (existing)

## References

- [GODAGENT Architecture](https://github.com/godagent) - Inspiration for features
- [sqlite-vec](https://github.com/asg017/sqlite-vec) - SQLite vector extension
- [sentence-transformers](https://www.sbert.net/) - Local embedding models
- [beads](https://github.com/steveyegge/beads) - Git-based issue tracking inspiration

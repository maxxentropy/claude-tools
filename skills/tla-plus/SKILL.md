---
name: tla-plus
description: |
  TLA+ formal verification for modeling and verifying concurrent algorithms and distributed systems.
  Use when asked about: TLA+, formal verification, model checking, verify algorithm, verify spec,
  check invariants, race condition analysis, concurrency model, TLC, Apalache, formal spec,
  temporal logic, prove correctness, state machine verification, model concurrent, TOCTOU,
  double-check locking, create TLA spec, run TLC, explain counterexample, verify safety,
  liveness property, deadlock detection, formal methods.
  Capabilities: Create specs from templates, run TLC/Apalache, generate CI pipelines,
  check code-spec drift, explain counterexamples, generate tests from invariants.
---

# TLA+ Formal Verification Skill

Model and verify concurrent algorithms, race conditions, and distributed protocols using TLA+ formal methods.

## Role in Quality Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ software-       │     │ tla-plus        │     │ code-review     │
│ architect       │ ──► │ skill           │ ──► │ skill           │
│ (Design)        │     │ (Verify)        │     │ (Implement)     │
└─────────────────┘     └─────────────────┘     └─────────────────┘
      DESIGN              FORMAL VERIFY           CODE CHECK
        │                       │                       │
        └───────────────────────┴───────────────────────┘
                    Continuous Verification
```

This skill is the **FORMAL VERIFY** phase. It mathematically proves properties about algorithms before or during implementation.

## When to Use TLA+

| Situation | Use TLA+ | Why |
|-----------|----------|-----|
| Concurrent operations | Yes | TLA+ explores all interleavings |
| Race condition suspected | Yes | Find bugs impossible to test empirically |
| Token/session management | Yes | Verify rotation, expiry, refresh logic |
| Distributed consensus | Yes | TLA+'s sweet spot |
| State machine design | Yes | Verify all transitions are safe |
| CRUD operations | No | Overkill for simple operations |
| UI rendering | No | Not the right tool |

**Prime candidates:**
- Database operations with optimistic concurrency
- Token refresh/rotation flows
- Leader election, distributed locks
- Saga patterns, two-phase commits
- Rate limiters, circuit breakers

## Quick Start

### Run Existing Specs

```bash
# Run all models (quick simulation)
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py --all --mode quick

# Run specific model with full verification
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py --model node-registration --mode thorough

# Get JSON output for CI
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py --model token-refresh --format json
```

### Create New Specification

```bash
# From pattern template
python3 ~/.claude/skills/tla-plus/scripts/generate_spec.py \
  --pattern optimistic-concurrency \
  --name "OrderLocking" \
  --output specs/tla+/order-locking/

# From code (LLM-assisted)
python3 ~/.claude/skills/tla-plus/scripts/generate_from_code.py \
  --source src/Services/OrderService.cs \
  --method ProcessOrder \
  --concern "race condition"
```

### Generate CI Pipeline

```bash
# Azure DevOps
python3 ~/.claude/skills/tla-plus/scripts/generate_pipeline.py \
  --platform azure-devops \
  --output .azure-pipelines/tla-verification.yml

# GitHub Actions
python3 ~/.claude/skills/tla-plus/scripts/generate_pipeline.py \
  --platform github \
  --output .github/workflows/tla-verification.yml
```

## Core Workflows

### 1. Creating a New Specification

**Step 1: Identify the Concern**

What concurrent/distributed behavior needs verification?
- Race conditions in shared state
- Ordering of operations
- Safety invariants (bad things never happen)
- Liveness properties (good things eventually happen)

**Step 2: Choose a Pattern**

| Pattern | Use Case | Template |
|---------|----------|----------|
| Optimistic Concurrency | DB updates with version check | `optimistic-concurrency.tla` |
| Token Rotation | JWT refresh, session management | `token-rotation.tla` |
| State Machine | Workflow, lifecycle management | `state-machine.tla` |
| Leader Election | Distributed coordination | `leader-election.tla` |
| Circuit Breaker | Resilience patterns | `circuit-breaker.tla` |
| Rate Limiter | Token bucket, sliding window | `rate-limiter.tla` |
| Saga Pattern | Distributed transactions | `saga-pattern.tla` |
| Two-Phase Commit | Atomic distributed operations | `two-phase-commit.tla` |

**Step 3: Generate and Customize**

```bash
python3 ~/.claude/skills/tla-plus/scripts/generate_spec.py \
  --pattern optimistic-concurrency \
  --name "NodeClaiming" \
  --entities "NODES" \
  --actors "USERS" \
  --output specs/tla+/node-claiming/
```

**Step 4: Add Code Mappings**

Document the relationship between TLA+ and code:

```bash
python3 ~/.claude/skills/tla-plus/scripts/add_mapping.py \
  --model node-claiming \
  --action "UserClaimNode" \
  --file "src/Features/AccessPoint/RegisterAccessPointCommandHandler.cs" \
  --method "ClaimSelfRegisteredNode" \
  --line 204
```

**Step 5: Verify**

```bash
# Quick check during development
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py --model node-claiming --mode quick

# Full verification before merge
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py --model node-claiming --mode thorough
```

**Step 6: Create Buggy Variant (Recommended)**

Create a version that intentionally lacks safety measures to verify TLC catches bugs:

```bash
python3 ~/.claude/skills/tla-plus/scripts/generate_buggy.py \
  --model node-claiming \
  --remove-guard "version check" \
  --expected-violation "SingleOwnership"
```

### 2. Understanding Counterexamples

When TLC finds an invariant violation, it produces a counterexample trace.

```bash
# Explain the counterexample in plain English
python3 ~/.claude/skills/tla-plus/scripts/explain_counterexample.py \
  --model node-registration \
  --format markdown
```

**Example Output:**

```markdown
## Counterexample Analysis: NodeRegistrationBuggy

### Invariant Violated: `NoDoubleClaimSuccess`

### Trace (5 states):

**State 1** (Initial):
- Node N1 is unregistered
- No claims in progress

**State 2** (Action: `NodeSelfRegister(N1)`):
- Node N1 becomes self-registered (owner = SYSTEM)
- Code: `RegisterNodeCommandHandler.CreateNewNode()` at line 96

**State 3** (Action: `UserReadForClaim(U1, N1)`):
- User U1 reads N1, sees it's claimable (self_registered)
- Code: Start of `ClaimSelfRegisteredNode()` at line 204

**State 4** (Action: `UserReadForClaim(U2, N1)`) *RACE CONDITION*:
- User U2 also reads N1, sees it's claimable
- Both U1 and U2 now believe they can claim N1

**State 5** (Action: `UserCompleteClaim(U1, N1)`, then `UserCompleteClaim(U2, N1)`):
- Both complete their claims
- **INVARIANT VIOLATED**: Two users successfully claimed the same node

### Root Cause
Time-of-check to time-of-use (TOCTOU) vulnerability. The check for claimability
and the claim operation are not atomic.

### Recommended Fix
Implement optimistic concurrency control:
1. Add version column to the entity
2. Check version at write time
3. Retry on conflict

See template: `optimistic-concurrency.tla`
```

### 3. Checking Code-Spec Drift

After code changes, verify specs are still accurate:

```bash
python3 ~/.claude/skills/tla-plus/scripts/check_drift.py --all --format table
```

**Example Output:**

```
┌─────────────────────┬──────────────────────────┬──────────┬────────────────────────────────┐
│ Model               │ Mapping                  │ Severity │ Issue                          │
├─────────────────────┼──────────────────────────┼──────────┼────────────────────────────────┤
│ node-registration   │ UserClaimNode → line 204 │ Medium   │ Method moved to line 245       │
│ token-refresh       │ TokenRevoke → file       │ Critical │ File renamed to TokenService   │
│ order-locking       │ All mappings             │ Low      │ OK - no drift detected         │
└─────────────────────┴──────────────────────────┴──────────┴────────────────────────────────┘
```

### 4. CI/CD Integration

**Verification Strategy:**

| Branch | Mode | Timeout | Purpose |
|--------|------|---------|---------|
| PR (any) | simulation | 5 min | Fast feedback, catch most bugs |
| develop | standard | 15 min | Thorough check before integration |
| main | thorough | 30 min | Complete verification |

**Smart Triggers:**

The generated pipeline only runs when relevant files change:
- Any `.tla` or `.cfg` file in `specs/tla+/`
- Source files mapped to specifications (from `mappings.json`)

**Negative Testing:**

Pipeline includes verification that buggy variants fail:
- Confirms TLC can catch the bugs we're protecting against
- Guards against regressions in the spec itself

### 5. Generating Tests from Specs

Extract testable properties from TLA+ invariants:

```bash
python3 ~/.claude/skills/tla-plus/scripts/spec_to_tests.py \
  --model node-registration \
  --language csharp \
  --output tests/NodeRegistration.Invariants.Tests.cs
```

**Generated Test Example:**

```csharp
/// <summary>
/// Tests derived from TLA+ invariant: SingleOwnership
/// Spec: Every registered node has exactly one owner
/// </summary>
[Fact]
public async Task SingleOwnership_NodeCannotHaveMultipleOwners()
{
    // Arrange: Create self-registered node
    var node = await CreateSelfRegisteredNode();

    // Act: Two users attempt to claim simultaneously
    var claim1 = ClaimNodeAsync(node.Id, user1);
    var claim2 = ClaimNodeAsync(node.Id, user2);
    await Task.WhenAll(claim1, claim2);

    // Assert: Exactly one claim succeeded
    var owner = await GetNodeOwner(node.Id);
    Assert.NotEqual(SystemConstants.SystemNodeRegistrationOwnerId, owner);
    Assert.True(
        (claim1.Result.IsSuccess && !claim2.Result.IsSuccess) ||
        (!claim1.Result.IsSuccess && claim2.Result.IsSuccess),
        "Exactly one claim should succeed (TLA+ invariant: SingleOwnership)"
    );
}
```

## Verification Modes

### TLC (Default)

Explicit state model checker. Explores all reachable states.

| Mode | States | Time | Use Case |
|------|--------|------|----------|
| `quick` | ~100k (simulation) | Seconds | Development, CI |
| `standard` | All (small config) | Minutes | Pre-merge |
| `thorough` | All (large config) | 10-30 min | Release verification |

### Apalache (Symbolic)

Symbolic model checker using Z3. Better for:
- Large/infinite state spaces
- Integer arithmetic
- Inductive invariant checking

```bash
python3 ~/.claude/skills/tla-plus/scripts/run_apalache.py \
  --model token-refresh \
  --check-inductive \
  --length 20
```

### When to Use Which

| Situation | Tool | Why |
|-----------|------|-----|
| Small state space (<1M states) | TLC | Fast, complete |
| Large integers/unbounded | Apalache | Symbolic handling |
| Inductive invariant proof | Apalache | Built-in support |
| Liveness properties | TLC | Better temporal support |
| Quick feedback | TLC simulation | Fastest |

## Project Structure

```
project/
├── .tla-plus/
│   ├── project.json      # TLA+ project configuration
│   └── mappings.json     # Code-to-spec traceability
└── specs/tla+/
    ├── README.md
    ├── .tools/
    │   ├── run-tlc.sh    # Shell runner (legacy)
    │   └── tla2tools.jar # TLC (downloaded)
    ├── common/
    │   └── ProjectCommon.tla
    └── {model-name}/
        ├── README.md
        ├── {Model}.tla       # Main specification
        ├── {Model}.cfg       # Small configuration
        ├── {Model}_Large.cfg # Large configuration
        └── {Model}Buggy.tla  # Negative test variant
```

## Pattern Templates

### Optimistic Concurrency

For database updates with version-based conflict detection.

**Use when:**
- Multiple actors can update the same entity
- Updates should not silently overwrite each other
- Conflicts should be detected and handled

**Key invariants:**
- Version monotonicity (versions only increase)
- No lost updates (conflicts detected)
- Single writer wins (exactly one concurrent update succeeds)

### Token Rotation

For JWT refresh, session management, API key rotation.

**Use when:**
- Old token must be invalidated when new one is issued
- Concurrent refresh requests possible
- Token chain must be maintained

**Key invariants:**
- Single active token per user
- Replacement chain integrity
- No double refresh (same token refreshed twice)

### State Machine

For lifecycle management, workflow engines, order processing.

**Use when:**
- Entity has defined states
- Transitions have guards/preconditions
- Some transitions should be impossible

**Key invariants:**
- Only valid transitions occur
- Guards are respected
- Terminal states are reachable (liveness)

## Integration with Other Skills

### With findings Skill

Discoveries from TLA+ verification are captured as persistent findings:

```bash
# After TLC finds a bug
python3 ~/.claude/skills/findings/scripts/query_findings.py --capture \
  --title "Race condition in ClaimSelfRegisteredNode" \
  --severity critical \
  --type discovery \
  --category thread-safety \
  --file "src/Features/AccessPoint/RegisterAccessPointCommandHandler.cs" \
  --line 204 \
  --during "tla-verification"
```

### With azure-devops Skill

Promote TLA+ findings to work items:

```bash
# Create bug for race condition
python3 ~/.claude/skills/findings/scripts/promote_to_ado.py f-abc123 --type Bug
```

### With code-review Skill

Code review checklist includes TLA+ considerations:

- If modifying code mapped to a TLA+ spec, run verification
- If adding concurrency, consider adding TLA+ model
- Check code-spec drift after changes

### With architecture-review Skill

Architecture assessments include formal verification coverage:

```markdown
### Formal Verification
**Rating**: Partial

**Observations**:
- TLA+ specs exist for: node-registration, token-refresh
- Missing specs for: order processing, payment flow

**Recommendations**:
- P2: Add TLA+ model for payment saga pattern
- P3: Add TLA+ model for rate limiting
```

## Learning Resources

### In-Skill References

| File | Content |
|------|---------|
| `references/tlaplus-quickstart.md` | TLA+ syntax and concepts |
| `references/common-patterns.md` | Pattern catalog with examples |
| `references/tlc-optimization.md` | TLC performance tuning |
| `references/apalache-guide.md` | Symbolic model checking |
| `references/code-spec-mapping.md` | Mapping TLA+ to code |

### External Resources

- [Specifying Systems](https://lamport.azurewebsites.net/tla/book.html) - Lamport's TLA+ book (free)
- [Learn TLA+](https://learntla.com/) - Practical tutorial
- [TLA+ Video Course](https://lamport.azurewebsites.net/video/videos.html) - By Leslie Lamport
- [AWS and TLA+](https://cacm.acm.org/magazines/2015/4/184701-how-amazon-web-services-uses-formal-methods/fulltext) - Industry case study

## Example: Complete Workflow

**Scenario:** Verify a new "order claiming" feature has no race conditions.

```bash
# 1. Generate spec from template
python3 ~/.claude/skills/tla-plus/scripts/generate_spec.py \
  --pattern optimistic-concurrency \
  --name "OrderClaiming" \
  --output specs/tla+/order-claiming/

# 2. Customize the generated spec (edit in VS Code with TLA+ extension)

# 3. Add code mappings
python3 ~/.claude/skills/tla-plus/scripts/add_mapping.py \
  --model order-claiming \
  --action "ClaimOrder" \
  --file "src/Features/Orders/ClaimOrderHandler.cs" \
  --method "Handle" \
  --line 45

# 4. Run verification
python3 ~/.claude/skills/tla-plus/scripts/run_tlc.py \
  --model order-claiming \
  --mode thorough

# 5. If counterexample found, understand it
python3 ~/.claude/skills/tla-plus/scripts/explain_counterexample.py \
  --model order-claiming

# 6. Fix the bug (add version check), re-verify

# 7. Create buggy variant for negative testing
python3 ~/.claude/skills/tla-plus/scripts/generate_buggy.py \
  --model order-claiming \
  --remove-guard "version check"

# 8. Generate CI pipeline
python3 ~/.claude/skills/tla-plus/scripts/generate_pipeline.py \
  --platform azure-devops \
  --output .azure-pipelines/tla-verification.yml

# 9. Capture as finding for documentation
python3 ~/.claude/skills/findings/scripts/query_findings.py --capture \
  --title "Order claiming verified with TLA+" \
  --type note \
  --category architecture
```

## Troubleshooting

### TLC hangs or runs forever

**Cause:** State space too large.

**Solutions:**
1. Use simulation mode: `--mode quick`
2. Reduce constants (fewer nodes, users)
3. Add state constraints
4. Use Apalache for symbolic checking

### Counterexample is confusing

**Solution:** Use explain_counterexample.py for plain English explanation.

### Spec doesn't match code

**Solution:**
1. Run drift check: `check_drift.py --model X`
2. Update mappings
3. Re-verify

### Java not found

**Solution:**
```bash
# macOS
brew install openjdk@17

# Ubuntu
sudo apt install openjdk-17-jdk

# Verify
java -version
```

### TLA+ tools not downloaded

**Solution:**
```bash
# Auto-download on first run, or manually:
curl -sL -o specs/tla+/.tools/tla2tools.jar \
  "https://github.com/tlaplus/tlaplus/releases/download/v1.8.0/tla2tools.jar"
```

## Files Reference

| File | Purpose |
|------|---------|
| `SKILL.md` | This documentation |
| `DESIGN.md` | Detailed design document |
| `scripts/run_tlc.py` | TLC model checker runner |
| `scripts/run_apalache.py` | Apalache symbolic checker |
| `scripts/generate_spec.py` | Generate spec from template |
| `scripts/generate_from_code.py` | LLM-assisted spec extraction |
| `scripts/check_drift.py` | Code-spec synchronization |
| `scripts/explain_counterexample.py` | Counterexample explanation |
| `scripts/generate_pipeline.py` | CI pipeline generator |
| `scripts/spec_to_tests.py` | Test generation from invariants |
| `templates/patterns/*.tla` | Pattern templates |
| `templates/pipelines/*.yml` | CI templates |
| `references/*.md` | Learning materials |

---

*See DESIGN.md for implementation details and ADRs.*

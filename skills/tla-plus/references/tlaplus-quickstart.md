# TLA+ Quickstart Guide

A practical introduction to TLA+ for developers who want to verify concurrent algorithms.

## What is TLA+?

TLA+ (Temporal Logic of Actions) is a formal specification language for describing and verifying concurrent and distributed systems. It was developed by Leslie Lamport (inventor of LaTeX and many distributed algorithms).

**Key insight:** TLA+ describes systems as state machines. You specify:
1. **Initial state** - How the system starts
2. **Actions** - How states can change
3. **Invariants** - Properties that must always hold
4. **Temporal properties** - How the system evolves over time

## Core Concepts

### 1. Variables and State

State is defined by variables. Each variable maps to a value.

```tla
VARIABLES
    counter,      \* A simple integer
    messages,     \* A sequence of messages
    nodeState     \* A function from nodes to states
```

### 2. Initial State (Init)

Defines how variables start.

```tla
Init ==
    /\ counter = 0
    /\ messages = <<>>
    /\ nodeState = [n \in Nodes |-> "idle"]
```

### 3. Actions

Actions describe state transitions. An action is TRUE if it's a valid transition.

```tla
Increment ==
    /\ counter < 10           \* Guard (precondition)
    /\ counter' = counter + 1 \* Next state
    /\ UNCHANGED messages     \* Other variables don't change
```

**Key operators:**
- `'` (prime) - refers to the next state value
- `/\` - logical AND
- `\/` - logical OR
- `UNCHANGED` - variable stays the same

### 4. Next State Relation

Combines all possible actions.

```tla
Next ==
    \/ Increment
    \/ Decrement
    \/ Reset
```

### 5. Specification

Complete system behavior.

```tla
Spec == Init /\ [][Next]_vars
\* "Start in Init, and every step is either Next or a stutter step"
```

### 6. Invariants

Properties that must hold in every reachable state.

```tla
\* Counter is always non-negative
CounterNonNegative == counter >= 0

\* Every node in "claimed" state has an owner
ClaimedHasOwner ==
    \A n \in Nodes :
        nodeState[n] = "claimed" => owner[n] # NULL
```

## Common Patterns

### Pattern 1: Modeling Concurrent Operations

```tla
\* Two processes can modify shared state
Process1Update ==
    /\ sharedValue' = sharedValue + 1
    /\ UNCHANGED otherVars

Process2Update ==
    /\ sharedValue' = sharedValue * 2
    /\ UNCHANGED otherVars

Next ==
    \/ Process1Update
    \/ Process2Update
```

TLC will explore ALL possible interleavings.

### Pattern 2: Read-Modify-Write with Race Condition

**Buggy version (shows the race):**

```tla
\* Phase 1: Read current value
StartOperation(p) ==
    /\ localCopy[p]' = sharedValue
    /\ phase[p]' = "read"
    /\ UNCHANGED sharedValue

\* Phase 2: Write based on local copy (RACE!)
CompleteOperation(p) ==
    /\ phase[p] = "read"
    /\ sharedValue' = localCopy[p] + 1
    /\ phase[p]' = "done"
```

**Fixed version (with optimistic concurrency):**

```tla
CompleteOperation(p) ==
    /\ phase[p] = "read"
    /\ IF sharedValue = localCopy[p]  \* Version check
       THEN /\ sharedValue' = localCopy[p] + 1
            /\ phase[p]' = "done"
       ELSE /\ phase[p]' = "retry"   \* Conflict detected
            /\ UNCHANGED sharedValue
```

### Pattern 3: Functions (Maps)

```tla
\* Function from nodes to owners
owner == [n \in Nodes |-> "nobody"]

\* Update one element
ClaimNode(n, u) ==
    owner' = [owner EXCEPT ![n] = u]

\* Check ownership
IsOwnedBy(n, u) == owner[n] = u
```

### Pattern 4: Sequences

```tla
\* Empty sequence
messages == <<>>

\* Append to sequence
SendMessage(m) ==
    messages' = Append(messages, m)

\* Process first message
ProcessMessage ==
    /\ Len(messages) > 0
    /\ messages' = Tail(messages)
```

### Pattern 5: Sets

```tla
\* Set of active users
activeUsers == {}

\* Add to set
Login(u) ==
    activeUsers' = activeUsers \cup {u}

\* Remove from set
Logout(u) ==
    activeUsers' = activeUsers \ {u}

\* Check membership
IsActive(u) == u \in activeUsers
```

## Running TLC

### Command Line

```bash
# Basic run
java -jar tla2tools.jar MySpec.tla

# With config file
java -jar tla2tools.jar -config MySpec.cfg MySpec.tla

# Simulation mode (faster, samples behaviors)
java -jar tla2tools.jar -simulate num=100000 MySpec.tla

# Multiple workers
java -jar tla2tools.jar -workers auto MySpec.tla
```

### Configuration File (.cfg)

```tla
\* MySpec.cfg

\* Define constants
CONSTANTS
    Nodes = {N1, N2, N3}
    Users = {U1, U2}
    MAX_VALUE = 10

\* Specify initial state and next relation
INIT Init
NEXT Next

\* Properties to check
INVARIANTS
    TypeInvariant
    SafetyProperty

\* Temporal properties (optional)
PROPERTIES
    EventuallyComplete
```

## Understanding Counterexamples

When TLC finds a violation, it outputs a trace showing how to reach the bad state.

```
Error: Invariant SingleOwner is violated.

1: Initial state
   counter = 0
   owner = [N1 |-> "nobody"]

2: StartClaim(N1, U1)
   counter = 0
   owner = [N1 |-> "nobody"]
   phase = [U1 |-> "read"]

3: StartClaim(N1, U2)      <-- RACE: U2 also reads
   counter = 0
   owner = [N1 |-> "nobody"]
   phase = [U1 |-> "read", U2 |-> "read"]

4: CompleteClaim(U1)
   owner = [N1 |-> U1]

5: CompleteClaim(U2)       <-- BUG: U2 overwrites U1
   owner = [N1 |-> U2]
   \* Both think they own N1!
```

## Common Operators Reference

| Operator | Meaning | Example |
|----------|---------|---------|
| `=` | Equals | `x = 5` |
| `#` | Not equals | `x # 0` |
| `/\` | AND | `x > 0 /\ x < 10` |
| `\/` | OR | `x = 0 \/ x = 1` |
| `~` | NOT | `~isEmpty` |
| `=>` | Implies | `x > 0 => y > 0` |
| `<=>` | If and only if | `isEmpty <=> Len(s) = 0` |
| `'` | Next state | `x' = x + 1` |
| `[]` | Always (temporal) | `[]Invariant` |
| `<>` | Eventually (temporal) | `<>Done` |
| `~>` | Leads to (temporal) | `Start ~> End` |

## Data Structures

### Sets

```tla
{1, 2, 3}           \* Literal set
{x \in S : P(x)}    \* Set comprehension (filter)
{f(x) : x \in S}    \* Set map
S \cup T            \* Union
S \cap T            \* Intersection
S \ T               \* Difference
x \in S             \* Membership
S \subseteq T       \* Subset
Cardinality(S)      \* Size
SUBSET S            \* Power set
```

### Sequences

```tla
<<1, 2, 3>>         \* Literal sequence
Head(s)             \* First element
Tail(s)             \* All but first
Append(s, x)        \* Add to end
Len(s)              \* Length
s[i]                \* i-th element (1-indexed)
SubSeq(s, m, n)     \* Subsequence
s \o t              \* Concatenation
```

### Functions (Maps)

```tla
[x \in S |-> e]     \* Function definition
f[x]                \* Function application
DOMAIN f            \* Domain of function
[f EXCEPT ![x] = v] \* Update one value
```

## Best Practices

1. **Start simple** - Begin with 2-3 entities, add complexity gradually
2. **Name actions clearly** - `UserClaimNode` not `Action3`
3. **Document invariants** - Explain WHY each property matters
4. **Create buggy variants** - Verify TLC catches known bugs
5. **Map to code** - Document which code implements each action
6. **Use symmetry** - Reduce state space with symmetry sets

## VS Code Setup

1. Install TLA+ extension: `tlaplus.vscode-ide`
2. Open any `.tla` file
3. Use Command Palette:
   - "TLA+: Check Model with TLC" - Run verification
   - "TLA+: Parse Module" - Syntax check

## Resources

- [Specifying Systems](https://lamport.azurewebsites.net/tla/book.html) - Free book
- [Learn TLA+](https://learntla.com/) - Interactive tutorial
- [TLA+ Examples](https://github.com/tlaplus/Examples) - Real-world specs
- [Hillel Wayne's blog](https://www.hillelwayne.com/) - Practical TLA+

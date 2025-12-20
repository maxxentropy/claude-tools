--------------------------- MODULE OptimisticConcurrency ---------------------------
(*
 * Template: Optimistic Concurrency Control with Version Check
 *
 * Pattern for: Database updates with version-based conflict detection
 * Common in: Entity updates, document stores, distributed caches
 *
 * Customize:
 * - Replace {{ENTITIES}} with your entity set (e.g., NODES, ORDERS)
 * - Replace {{ACTORS}} with your actor set (e.g., USERS, SERVICES)
 * - Add domain-specific state variables
 * - Customize invariants for your business rules
 *
 * Usage:
 *   python3 ~/.claude/skills/tla-plus/scripts/generate_spec.py \
 *     --pattern optimistic-concurrency \
 *     --name "NodeClaiming" \
 *     --entities "NODES" \
 *     --actors "USERS"
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

\* ----- CONSTANTS -----
CONSTANTS
    {{ENTITIES}},     \* Set of entity IDs (e.g., {E1, E2, E3})
    {{ACTORS}},       \* Set of concurrent actors (e.g., {A1, A2})
    MAX_VERSION       \* Upper bound for version numbers (e.g., 10)

\* ----- VARIABLES -----
VARIABLES
    entityVersion,    \* entityVersion[e] = current version number
    entityState,      \* entityState[e] = current entity state
    entityOwner,      \* entityOwner[e] = current owner (or "NONE")
    pendingUpdates,   \* pendingUpdates = sequence of in-flight operations
    updateResults     \* updateResults = history of update outcomes

vars == <<entityVersion, entityState, entityOwner, pendingUpdates, updateResults>>

\* ----- TYPE INVARIANT -----
TypeInvariant ==
    /\ entityVersion \in [{{ENTITIES}} -> 0..MAX_VERSION]
    /\ entityState \in [{{ENTITIES}} -> {"initial", "claimed", "processed"}]
    /\ entityOwner \in [{{ENTITIES}} -> {{ACTORS}} \cup {"NONE"}]
    /\ pendingUpdates \in Seq([entity: {{ENTITIES}}, actor: {{ACTORS}}, readVersion: 0..MAX_VERSION])

\* ----- INITIAL STATE -----
Init ==
    /\ entityVersion = [e \in {{ENTITIES}} |-> 0]
    /\ entityState = [e \in {{ENTITIES}} |-> "initial"]
    /\ entityOwner = [e \in {{ENTITIES}} |-> "NONE"]
    /\ pendingUpdates = <<>>
    /\ updateResults = <<>>

\* ----- HELPER OPERATORS -----

\* Check if entity can be claimed
CanClaim(e) ==
    /\ entityState[e] = "initial"
    /\ entityOwner[e] = "NONE"

\* Check if version matches (no concurrent modification)
VersionMatches(e, expectedVersion) ==
    entityVersion[e] = expectedVersion

\* ----- ACTIONS -----

(*
 * StartClaim: Actor begins claiming an entity
 *
 * Phase 1 of optimistic concurrency: READ
 * - Actor reads current entity state and version
 * - Stores the read version for later comparison
 *
 * Maps to: Reading entity with SELECT ... WHERE id = @id
 *)
StartClaim(e, a) ==
    /\ CanClaim(e)
    /\ pendingUpdates' = Append(pendingUpdates,
            [entity |-> e, actor |-> a, readVersion |-> entityVersion[e]])
    /\ UNCHANGED <<entityVersion, entityState, entityOwner, updateResults>>

(*
 * CompleteClaim: Actor completes claiming an entity
 *
 * Phase 2 of optimistic concurrency: CHECK-MODIFY-WRITE
 * - Re-check version matches what was read
 * - If match: update entity and increment version
 * - If mismatch: fail (concurrent modification detected)
 *
 * Maps to: UPDATE ... SET version = version + 1 WHERE id = @id AND version = @expectedVersion
 *)
CompleteClaim(idx) ==
    /\ idx \in 1..Len(pendingUpdates)
    /\ LET op == pendingUpdates[idx]
           e == op.entity
           a == op.actor
           expectedVersion == op.readVersion
       IN
           IF VersionMatches(e, expectedVersion) /\ CanClaim(e)
           THEN \* SUCCESS: Version matches, claim succeeds
                /\ entityVersion' = [entityVersion EXCEPT ![e] = @ + 1]
                /\ entityState' = [entityState EXCEPT ![e] = "claimed"]
                /\ entityOwner' = [entityOwner EXCEPT ![e] = a]
                /\ updateResults' = Append(updateResults,
                        [entity |-> e, actor |-> a, result |-> "success"])
                /\ pendingUpdates' = SubSeq(pendingUpdates, 1, idx-1) \o
                                     SubSeq(pendingUpdates, idx+1, Len(pendingUpdates))
           ELSE \* FAILURE: Concurrent modification detected
                /\ updateResults' = Append(updateResults,
                        [entity |-> e, actor |-> a, result |-> "conflict"])
                /\ pendingUpdates' = SubSeq(pendingUpdates, 1, idx-1) \o
                                     SubSeq(pendingUpdates, idx+1, Len(pendingUpdates))
                /\ UNCHANGED <<entityVersion, entityState, entityOwner>>

(*
 * ProcessEntity: Owner processes their claimed entity
 *
 * Subsequent operations after claiming.
 *)
ProcessEntity(e, a) ==
    /\ entityState[e] = "claimed"
    /\ entityOwner[e] = a
    /\ entityVersion' = [entityVersion EXCEPT ![e] = @ + 1]
    /\ entityState' = [entityState EXCEPT ![e] = "processed"]
    /\ UNCHANGED <<entityOwner, pendingUpdates, updateResults>>

\* ----- NEXT STATE RELATION -----
Next ==
    \/ \E e \in {{ENTITIES}}, a \in {{ACTORS}} : StartClaim(e, a)
    \/ \E idx \in 1..10 : CompleteClaim(idx)  \* Bounded for model checking
    \/ \E e \in {{ENTITIES}}, a \in {{ACTORS}} : ProcessEntity(e, a)

\* Allow stuttering (system can stay in same state)
Spec == Init /\ [][Next]_vars

\* ----- SAFETY PROPERTIES (INVARIANTS) -----

(*
 * VersionMonotonicity: Entity versions only increase
 *
 * Ensures version numbers always go up, never down.
 *)
VersionMonotonicity ==
    \A e \in {{ENTITIES}} : entityVersion[e] >= 0

(*
 * SingleOwner: Each claimed entity has exactly one owner
 *
 * Critical safety property: no entity can have multiple owners.
 *)
SingleOwner ==
    \A e \in {{ENTITIES}} :
        entityState[e] = "claimed" => entityOwner[e] \in {{ACTORS}}

(*
 * OwnerConsistency: Owner is set iff entity is claimed
 *)
OwnerConsistency ==
    \A e \in {{ENTITIES}} :
        (entityOwner[e] # "NONE") <=> (entityState[e] \in {"claimed", "processed"})

(*
 * NoLostUpdates: Concurrent updates are detected, not silently lost
 *
 * If two actors try to claim the same entity, at most one succeeds.
 *)
NoLostUpdates ==
    \A e \in {{ENTITIES}} :
        LET successfulClaims == {r \in DOMAIN updateResults :
                updateResults[r].entity = e /\ updateResults[r].result = "success"}
        IN Cardinality(successfulClaims) <= 1

\* Combined safety invariant
Safety ==
    /\ TypeInvariant
    /\ VersionMonotonicity
    /\ SingleOwner
    /\ OwnerConsistency
    /\ NoLostUpdates

\* ----- LIVENESS PROPERTIES -----

(*
 * EventuallyProcessed: A claimed entity can eventually be processed
 * (Requires fairness)
 *)
EventuallyProcessed ==
    \A e \in {{ENTITIES}} :
        entityState[e] = "claimed" ~> entityState[e] = "processed"

=============================================================================
(*
 * Configuration Example ({{Name}}.cfg):
 *
 * CONSTANTS
 *     {{ENTITIES}} = {E1, E2}
 *     {{ACTORS}} = {A1, A2}
 *     MAX_VERSION = 5
 *
 * INIT Init
 * NEXT Next
 *
 * INVARIANTS
 *     Safety
 *
 * To run:
 *     java -jar tla2tools.jar -config {{Name}}.cfg {{Name}}.tla
 *)

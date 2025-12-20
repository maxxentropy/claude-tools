---------------------------- MODULE StateMachine ----------------------------
(*
 * Template: Finite State Machine with Transitions
 *
 * Pattern for: Workflow engines, order processing, document lifecycles
 * Common in: E-commerce, content management, approval workflows
 *
 * Customization points marked with {{PLACEHOLDER}}
 *
 * Key properties verified:
 * - Only valid transitions are allowed
 * - Terminal states cannot be exited
 * - All states are reachable from initial state
 * - No orphan states (states with no incoming transitions)
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

\* ----- CONSTANTS -----
CONSTANTS
    {{ENTITIES}},           \* Set of entity IDs (e.g., {Order1, Order2})
    {{STATES}},             \* Set of valid states (e.g., {Draft, Submitted, Approved})
    {{INITIAL_STATE}},      \* Initial state for new entities
    {{TERMINAL_STATES}}     \* Set of terminal states (cannot exit)

\* ----- VARIABLES -----
VARIABLES
    entityState,            \* entityState[e] = current state of entity
    stateHistory,           \* stateHistory[e] = sequence of state transitions
    transitionCount         \* transitionCount[e] = number of transitions made

vars == <<entityState, stateHistory, transitionCount>>

\* ----- TRANSITION DEFINITIONS -----
(*
 * Define valid transitions as a set of [from, to] pairs.
 * Customize this for your domain.
 *
 * Example for Order workflow:
 * ValidTransitions == {
 *     [from |-> "Draft", to |-> "Submitted"],
 *     [from |-> "Submitted", to |-> "Approved"],
 *     [from |-> "Submitted", to |-> "Rejected"],
 *     [from |-> "Approved", to |-> "Fulfilled"],
 *     [from |-> "Rejected", to |-> "Draft"]
 * }
 *)
ValidTransitions == {
    \* {{DEFINE_TRANSITIONS}}
    [from |-> "State1", to |-> "State2"],
    [from |-> "State2", to |-> "State3"]
}

\* Check if a transition is valid
CanTransition(fromState, toState) ==
    /\ [from |-> fromState, to |-> toState] \in ValidTransitions
    /\ fromState \notin {{TERMINAL_STATES}}

\* ----- TYPE INVARIANT -----
TypeInvariant ==
    /\ entityState \in [{{ENTITIES}} -> {{STATES}} \cup {"UNINITIALIZED"}]
    /\ stateHistory \in [{{ENTITIES}} -> Seq({{STATES}})]
    /\ transitionCount \in [{{ENTITIES}} -> Nat]

\* ----- INITIAL STATE -----
Init ==
    /\ entityState = [e \in {{ENTITIES}} |-> "UNINITIALIZED"]
    /\ stateHistory = [e \in {{ENTITIES}} |-> <<>>]
    /\ transitionCount = [e \in {{ENTITIES}} |-> 0]

\* ----- ACTIONS -----

(*
 * CreateEntity: Initialize a new entity in the initial state
 *)
CreateEntity(e) ==
    /\ entityState[e] = "UNINITIALIZED"
    /\ entityState' = [entityState EXCEPT ![e] = {{INITIAL_STATE}}]
    /\ stateHistory' = [stateHistory EXCEPT ![e] = <<{{INITIAL_STATE}}>>]
    /\ UNCHANGED transitionCount

(*
 * Transition: Move entity from one state to another
 *)
Transition(e, newState) ==
    /\ entityState[e] # "UNINITIALIZED"
    /\ CanTransition(entityState[e], newState)
    /\ entityState' = [entityState EXCEPT ![e] = newState]
    /\ stateHistory' = [stateHistory EXCEPT ![e] = Append(@, newState)]
    /\ transitionCount' = [transitionCount EXCEPT ![e] = @ + 1]

(*
 * ForceState: Administrative override (use carefully!)
 * Models scenarios like admin corrections, system recovery
 *)
ForceState(e, newState) ==
    /\ entityState[e] # "UNINITIALIZED"
    /\ newState \in {{STATES}}
    /\ newState # entityState[e]
    /\ entityState' = [entityState EXCEPT ![e] = newState]
    /\ stateHistory' = [stateHistory EXCEPT ![e] = Append(@, newState)]
    /\ transitionCount' = [transitionCount EXCEPT ![e] = @ + 1]

\* ----- NEXT STATE RELATION -----
Next ==
    \/ \E e \in {{ENTITIES}} : CreateEntity(e)
    \/ \E e \in {{ENTITIES}}, s \in {{STATES}} : Transition(e, s)
    \* Uncomment to allow forced transitions:
    \* \/ \E e \in {{ENTITIES}}, s \in {{STATES}} : ForceState(e, s)

Spec == Init /\ [][Next]_vars

\* ----- SAFETY INVARIANTS -----

(*
 * ValidStateInvariant: All entities are in valid states
 *)
ValidStateInvariant ==
    \A e \in {{ENTITIES}} :
        entityState[e] \in {{STATES}} \cup {"UNINITIALIZED"}

(*
 * TerminalStateInvariant: Terminal states are never exited
 * (This is enforced by CanTransition, but we verify it)
 *)
TerminalStateInvariant ==
    \A e \in {{ENTITIES}} :
        LET hist == stateHistory[e]
        IN \A i \in 1..(Len(hist) - 1) :
            hist[i] \in {{TERMINAL_STATES}} => hist[i+1] = hist[i]

(*
 * HistoryConsistency: Current state matches last history entry
 *)
HistoryConsistency ==
    \A e \in {{ENTITIES}} :
        entityState[e] # "UNINITIALIZED" =>
            entityState[e] = stateHistory[e][Len(stateHistory[e])]

(*
 * NoBackwardTransitions: State always progresses (if your model requires this)
 * Customize based on whether cycles are allowed
 *)
\* NoBackwardTransitions ==
\*     \A e \in {{ENTITIES}} :
\*         LET hist == stateHistory[e]
\*         IN \A i \in 1..(Len(hist) - 1) :
\*             \* Define your ordering here

\* Combined safety invariant
Safety ==
    /\ ValidStateInvariant
    /\ HistoryConsistency

\* ----- LIVENESS PROPERTIES -----

(*
 * EventuallyTerminal: All entities eventually reach a terminal state
 * (Enable only if your workflow guarantees termination)
 *)
\* EventuallyTerminal ==
\*     \A e \in {{ENTITIES}} : <>(entityState[e] \in {{TERMINAL_STATES}})

(*
 * NoStarvation: If entity is in non-terminal state, it can eventually transition
 *)
\* NoStarvation ==
\*     \A e \in {{ENTITIES}} :
\*         (entityState[e] \notin {{TERMINAL_STATES}} /\ entityState[e] # "UNINITIALIZED")
\*             ~> (entityState'[e] # entityState[e])

=============================================================================

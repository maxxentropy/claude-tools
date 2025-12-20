---------------------------- MODULE TwoPhaseCommit ----------------------------
(*
 * Template: Two-Phase Commit Protocol
 *
 * Pattern for: Distributed transaction coordination, atomic commits
 * Common in: Database replication, distributed databases, transaction managers
 *
 * Implements: Classic 2PC with coordinator and participants
 *
 * Customization points marked with {{PLACEHOLDER}}
 *
 * Key properties verified:
 * - All participants reach same decision
 * - No commit if any participant voted abort
 * - Commit only after all participants voted commit
 * - Blocking on coordinator failure (known limitation)
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

\* ----- CONSTANTS -----
CONSTANTS
    {{PARTICIPANTS}},           \* Set of participant IDs (e.g., {DB1, DB2, DB3})
    {{TRANSACTIONS}}            \* Set of transaction IDs (e.g., {T1, T2})

\* Coordinator states
C_INIT == "C_INIT"
C_WAITING == "C_WAITING"
C_COMMITTED == "C_COMMITTED"
C_ABORTED == "C_ABORTED"

\* Participant states
P_WORKING == "P_WORKING"
P_PREPARED == "P_PREPARED"
P_COMMITTED == "P_COMMITTED"
P_ABORTED == "P_ABORTED"

\* Vote values
VOTE_COMMIT == "COMMIT"
VOTE_ABORT == "ABORT"
NO_VOTE == "NONE"

\* ----- VARIABLES -----
VARIABLES
    \* Coordinator state
    coordState,             \* coordState[t] = coordinator state for transaction
    votes,                  \* votes[t][p] = vote from participant p

    \* Participant state
    partState,              \* partState[t][p] = participant state

    \* Message channels (modeled as sets for simplicity)
    prepareMessages,        \* Set of {tx, participant} prepare requests
    commitMessages,         \* Set of {tx, participant} commit decisions
    abortMessages           \* Set of {tx, participant} abort decisions

vars == <<coordState, votes, partState, prepareMessages, commitMessages, abortMessages>>

\* ----- TYPE INVARIANT -----
TypeInvariant ==
    /\ coordState \in [{{TRANSACTIONS}} -> {C_INIT, C_WAITING, C_COMMITTED, C_ABORTED}]
    /\ votes \in [{{TRANSACTIONS}} -> [{{PARTICIPANTS}} -> {VOTE_COMMIT, VOTE_ABORT, NO_VOTE}]]
    /\ partState \in [{{TRANSACTIONS}} -> [{{PARTICIPANTS}} -> {P_WORKING, P_PREPARED, P_COMMITTED, P_ABORTED}]]

\* ----- INITIAL STATE -----
Init ==
    /\ coordState = [t \in {{TRANSACTIONS}} |-> C_INIT]
    /\ votes = [t \in {{TRANSACTIONS}} |-> [p \in {{PARTICIPANTS}} |-> NO_VOTE]]
    /\ partState = [t \in {{TRANSACTIONS}} |-> [p \in {{PARTICIPANTS}} |-> P_WORKING]]
    /\ prepareMessages = {}
    /\ commitMessages = {}
    /\ abortMessages = {}

\* ----- HELPER OPERATORS -----

\* All participants have voted
AllVoted(t) ==
    \A p \in {{PARTICIPANTS}} : votes[t][p] # NO_VOTE

\* All participants voted commit
AllVotedCommit(t) ==
    \A p \in {{PARTICIPANTS}} : votes[t][p] = VOTE_COMMIT

\* Any participant voted abort
AnyVotedAbort(t) ==
    \E p \in {{PARTICIPANTS}} : votes[t][p] = VOTE_ABORT

\* ----- PHASE 1: PREPARE -----

(*
 * CoordinatorStartsPrepare: Coordinator initiates transaction
 *)
CoordinatorStartsPrepare(t) ==
    /\ coordState[t] = C_INIT
    /\ coordState' = [coordState EXCEPT ![t] = C_WAITING]
    /\ prepareMessages' = prepareMessages \cup
                          {[tx |-> t, participant |-> p] : p \in {{PARTICIPANTS}}}
    /\ UNCHANGED <<votes, partState, commitMessages, abortMessages>>

(*
 * ParticipantReceivesPrepare: Participant receives prepare, votes commit
 *)
ParticipantVotesCommit(t, p) ==
    /\ partState[t][p] = P_WORKING
    /\ [tx |-> t, participant |-> p] \in prepareMessages
    /\ partState' = [partState EXCEPT ![t][p] = P_PREPARED]
    /\ votes' = [votes EXCEPT ![t][p] = VOTE_COMMIT]
    /\ prepareMessages' = prepareMessages \ {[tx |-> t, participant |-> p]}
    /\ UNCHANGED <<coordState, commitMessages, abortMessages>>

(*
 * ParticipantVotesAbort: Participant cannot prepare, votes abort
 *)
ParticipantVotesAbort(t, p) ==
    /\ partState[t][p] = P_WORKING
    /\ [tx |-> t, participant |-> p] \in prepareMessages
    /\ partState' = [partState EXCEPT ![t][p] = P_ABORTED]
    /\ votes' = [votes EXCEPT ![t][p] = VOTE_ABORT]
    /\ prepareMessages' = prepareMessages \ {[tx |-> t, participant |-> p]}
    /\ UNCHANGED <<coordState, commitMessages, abortMessages>>

\* ----- PHASE 2: COMMIT/ABORT -----

(*
 * CoordinatorDecideCommit: All voted commit, coordinator commits
 *)
CoordinatorDecideCommit(t) ==
    /\ coordState[t] = C_WAITING
    /\ AllVoted(t)
    /\ AllVotedCommit(t)
    /\ coordState' = [coordState EXCEPT ![t] = C_COMMITTED]
    /\ commitMessages' = commitMessages \cup
                         {[tx |-> t, participant |-> p] : p \in {{PARTICIPANTS}}}
    /\ UNCHANGED <<votes, partState, prepareMessages, abortMessages>>

(*
 * CoordinatorDecideAbort: Any voted abort, coordinator aborts
 *)
CoordinatorDecideAbort(t) ==
    /\ coordState[t] = C_WAITING
    /\ AnyVotedAbort(t)
    /\ coordState' = [coordState EXCEPT ![t] = C_ABORTED]
    /\ abortMessages' = abortMessages \cup
                        {[tx |-> t, participant |-> p] : p \in {{PARTICIPANTS}}}
    /\ UNCHANGED <<votes, partState, prepareMessages, commitMessages>>

(*
 * ParticipantReceivesCommit: Participant commits
 *)
ParticipantCommits(t, p) ==
    /\ partState[t][p] = P_PREPARED
    /\ [tx |-> t, participant |-> p] \in commitMessages
    /\ partState' = [partState EXCEPT ![t][p] = P_COMMITTED]
    /\ commitMessages' = commitMessages \ {[tx |-> t, participant |-> p]}
    /\ UNCHANGED <<coordState, votes, prepareMessages, abortMessages>>

(*
 * ParticipantReceivesAbort: Participant aborts
 *)
ParticipantAborts(t, p) ==
    /\ partState[t][p] \in {P_PREPARED, P_WORKING}
    /\ [tx |-> t, participant |-> p] \in abortMessages
    /\ partState' = [partState EXCEPT ![t][p] = P_ABORTED]
    /\ abortMessages' = abortMessages \ {[tx |-> t, participant |-> p]}
    /\ UNCHANGED <<coordState, votes, prepareMessages, commitMessages>>

\* ----- FAILURE ACTIONS -----

(*
 * CoordinatorTimeout: Coordinator times out waiting for votes, aborts
 *)
CoordinatorTimeout(t) ==
    /\ coordState[t] = C_WAITING
    /\ ~AllVoted(t)  \* Still waiting for some votes
    /\ coordState' = [coordState EXCEPT ![t] = C_ABORTED]
    /\ abortMessages' = abortMessages \cup
                        {[tx |-> t, participant |-> p] : p \in {{PARTICIPANTS}}}
    /\ UNCHANGED <<votes, partState, prepareMessages, commitMessages>>

(*
 * ParticipantTimeout: Prepared participant times out (coordinator failed)
 * This models the blocking nature of 2PC - participant is stuck
 *)
\* ParticipantTimeout is intentionally not included because 2PC blocks here

\* ----- NEXT STATE RELATION -----
Next ==
    \/ \E t \in {{TRANSACTIONS}} : CoordinatorStartsPrepare(t)
    \/ \E t \in {{TRANSACTIONS}}, p \in {{PARTICIPANTS}} : ParticipantVotesCommit(t, p)
    \/ \E t \in {{TRANSACTIONS}}, p \in {{PARTICIPANTS}} : ParticipantVotesAbort(t, p)
    \/ \E t \in {{TRANSACTIONS}} : CoordinatorDecideCommit(t)
    \/ \E t \in {{TRANSACTIONS}} : CoordinatorDecideAbort(t)
    \/ \E t \in {{TRANSACTIONS}}, p \in {{PARTICIPANTS}} : ParticipantCommits(t, p)
    \/ \E t \in {{TRANSACTIONS}}, p \in {{PARTICIPANTS}} : ParticipantAborts(t, p)
    \* Uncomment to model coordinator timeout:
    \* \/ \E t \in {{TRANSACTIONS}} : CoordinatorTimeout(t)

Spec == Init /\ [][Next]_vars

\* ----- SAFETY INVARIANTS -----

(*
 * AgreementInvariant: All participants reach the same decision
 *)
AgreementInvariant ==
    \A t \in {{TRANSACTIONS}} :
        \A p1, p2 \in {{PARTICIPANTS}} :
            /\ (partState[t][p1] = P_COMMITTED => partState[t][p2] # P_ABORTED)
            /\ (partState[t][p1] = P_ABORTED => partState[t][p2] # P_COMMITTED)

(*
 * ValidityCommit: Commit only if all voted commit
 *)
ValidityCommit ==
    \A t \in {{TRANSACTIONS}} :
        coordState[t] = C_COMMITTED => AllVotedCommit(t)

(*
 * ValidityAbort: If any voted abort, no participant commits
 *)
ValidityAbort ==
    \A t \in {{TRANSACTIONS}} :
        AnyVotedAbort(t) =>
            \A p \in {{PARTICIPANTS}} : partState[t][p] # P_COMMITTED

(*
 * CoordinatorLeadsDecision: Participants only commit/abort after coordinator decides
 *)
CoordinatorLeadsDecision ==
    \A t \in {{TRANSACTIONS}}, p \in {{PARTICIPANTS}} :
        /\ (partState[t][p] = P_COMMITTED => coordState[t] = C_COMMITTED)
        /\ (partState[t][p] = P_ABORTED /\ coordState[t] # C_INIT =>
            coordState[t] \in {C_WAITING, C_ABORTED})

\* Combined safety invariant
Safety ==
    /\ AgreementInvariant
    /\ ValidityCommit
    /\ ValidityAbort

\* ----- LIVENESS PROPERTIES -----

(*
 * EventuallyDecides: Transaction eventually reaches a decision
 * (Only holds without failures)
 *)
\* EventuallyDecides ==
\*     \A t \in {{TRANSACTIONS}} :
\*         <>(coordState[t] \in {C_COMMITTED, C_ABORTED})

(*
 * AllParticipantsFinish: All participants eventually reach terminal state
 *)
\* AllParticipantsFinish ==
\*     \A t \in {{TRANSACTIONS}}, p \in {{PARTICIPANTS}} :
\*         <>(partState[t][p] \in {P_COMMITTED, P_ABORTED})

\* ----- FAIRNESS -----
Fairness ==
    /\ \A t \in {{TRANSACTIONS}} : WF_vars(CoordinatorStartsPrepare(t))
    /\ \A t \in {{TRANSACTIONS}} : WF_vars(CoordinatorDecideCommit(t))
    /\ \A t \in {{TRANSACTIONS}} : WF_vars(CoordinatorDecideAbort(t))
    /\ \A t \in {{TRANSACTIONS}}, p \in {{PARTICIPANTS}} :
        WF_vars(ParticipantCommits(t, p))
    /\ \A t \in {{TRANSACTIONS}}, p \in {{PARTICIPANTS}} :
        WF_vars(ParticipantAborts(t, p))

FairSpec == Spec /\ Fairness

\* ----- NOTES -----
(*
 * Known limitations of 2PC:
 * 1. Blocking: If coordinator fails after sending prepare, participants block
 * 2. Single point of failure: Coordinator is critical
 *
 * Alternatives to consider:
 * - 3PC (Three-Phase Commit): Adds pre-commit phase to reduce blocking
 * - Paxos/Raft: Consensus-based approach for replication
 * - Saga Pattern: Compensating transactions for long-running processes
 *)

=============================================================================

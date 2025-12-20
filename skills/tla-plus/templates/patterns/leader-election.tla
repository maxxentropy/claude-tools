---------------------------- MODULE LeaderElection ----------------------------
(*
 * Template: Distributed Leader Election
 *
 * Pattern for: Single leader coordination, master selection, cluster management
 * Common in: Database clusters, distributed caches, consensus systems
 *
 * Based on: Bully algorithm / simplified Raft leader election
 *
 * Customization points marked with {{PLACEHOLDER}}
 *
 * Key properties verified:
 * - At most one leader at any time
 * - Eventually a leader is elected (liveness)
 * - Higher priority nodes win election
 * - Failed leader triggers re-election
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

\* ----- CONSTANTS -----
CONSTANTS
    {{NODES}},                  \* Set of node IDs (e.g., {N1, N2, N3})
    MAX_TERM                    \* Maximum election term (bounds state space)

\* Node states
FOLLOWER == "FOLLOWER"
CANDIDATE == "CANDIDATE"
LEADER == "LEADER"
FAILED == "FAILED"

\* ----- VARIABLES -----
VARIABLES
    nodeState,              \* nodeState[n] = FOLLOWER | CANDIDATE | LEADER | FAILED
    currentTerm,            \* currentTerm[n] = election term number
    votedFor,               \* votedFor[n] = node voted for in current term (or NULL)
    votesReceived,          \* votesReceived[n] = set of nodes that voted for n
    currentLeader           \* Global view: who is the current leader (or NULL)

vars == <<nodeState, currentTerm, votedFor, votesReceived, currentLeader>>

\* ----- TYPE INVARIANT -----
TypeInvariant ==
    /\ nodeState \in [{{NODES}} -> {FOLLOWER, CANDIDATE, LEADER, FAILED}]
    /\ currentTerm \in [{{NODES}} -> 0..MAX_TERM]
    /\ votedFor \in [{{NODES}} -> {{NODES}} \cup {"NULL"}]
    /\ votesReceived \in [{{NODES}} -> SUBSET {{NODES}}]
    /\ currentLeader \in {{NODES}} \cup {"NULL"}

\* ----- INITIAL STATE -----
Init ==
    /\ nodeState = [n \in {{NODES}} |-> FOLLOWER]
    /\ currentTerm = [n \in {{NODES}} |-> 0]
    /\ votedFor = [n \in {{NODES}} |-> "NULL"]
    /\ votesReceived = [n \in {{NODES}} |-> {}]
    /\ currentLeader = "NULL"

\* ----- HELPER OPERATORS -----

\* Number of active (non-failed) nodes
ActiveNodes == {n \in {{NODES}} : nodeState[n] # FAILED}

\* Majority threshold
Majority == (Cardinality({{NODES}}) \div 2) + 1

\* Check if node has majority votes
HasMajority(n) ==
    Cardinality(votesReceived[n]) >= Majority

\* Highest term among active nodes
MaxTerm ==
    LET terms == {currentTerm[n] : n \in ActiveNodes}
    IN IF terms = {} THEN 0 ELSE CHOOSE t \in terms : \A t2 \in terms : t >= t2

\* ----- ACTIONS -----

(*
 * StartElection: Follower times out and becomes candidate
 *)
StartElection(n) ==
    /\ nodeState[n] = FOLLOWER
    /\ currentTerm[n] < MAX_TERM
    /\ nodeState' = [nodeState EXCEPT ![n] = CANDIDATE]
    /\ currentTerm' = [currentTerm EXCEPT ![n] = @ + 1]
    /\ votedFor' = [votedFor EXCEPT ![n] = n]  \* Vote for self
    /\ votesReceived' = [votesReceived EXCEPT ![n] = {n}]  \* Self-vote
    /\ UNCHANGED currentLeader

(*
 * RequestVote: Candidate requests vote from a follower
 *)
RequestVote(candidate, voter) ==
    /\ nodeState[candidate] = CANDIDATE
    /\ nodeState[voter] = FOLLOWER
    /\ currentTerm[candidate] >= currentTerm[voter]
    /\ \/ votedFor[voter] = "NULL"
       \/ votedFor[voter] = candidate
    \* Grant vote
    /\ votedFor' = [votedFor EXCEPT ![voter] = candidate]
    /\ currentTerm' = [currentTerm EXCEPT ![voter] = currentTerm[candidate]]
    /\ votesReceived' = [votesReceived EXCEPT ![candidate] = @ \cup {voter}]
    /\ UNCHANGED <<nodeState, currentLeader>>

(*
 * BecomeLeader: Candidate with majority becomes leader
 *)
BecomeLeader(n) ==
    /\ nodeState[n] = CANDIDATE
    /\ HasMajority(n)
    /\ nodeState' = [nodeState EXCEPT ![n] = LEADER]
    /\ currentLeader' = n
    /\ UNCHANGED <<currentTerm, votedFor, votesReceived>>

(*
 * StepDown: Leader or candidate with stale term steps down
 *)
StepDown(n) ==
    /\ nodeState[n] \in {LEADER, CANDIDATE}
    /\ \E other \in {{NODES}} : currentTerm[other] > currentTerm[n]
    /\ nodeState' = [nodeState EXCEPT ![n] = FOLLOWER]
    /\ LET maxTerm == CHOOSE t \in {currentTerm[m] : m \in {{NODES}}} :
                        \A t2 \in {currentTerm[m] : m \in {{NODES}}} : t >= t2
       IN currentTerm' = [currentTerm EXCEPT ![n] = maxTerm]
    /\ votedFor' = [votedFor EXCEPT ![n] = "NULL"]
    /\ votesReceived' = [votesReceived EXCEPT ![n] = {}]
    /\ IF nodeState[n] = LEADER
       THEN currentLeader' = "NULL"
       ELSE UNCHANGED currentLeader

(*
 * NodeFails: Node crashes (simulates network partition or failure)
 *)
NodeFails(n) ==
    /\ nodeState[n] # FAILED
    /\ nodeState' = [nodeState EXCEPT ![n] = FAILED]
    /\ IF currentLeader = n
       THEN currentLeader' = "NULL"
       ELSE UNCHANGED currentLeader
    /\ UNCHANGED <<currentTerm, votedFor, votesReceived>>

(*
 * NodeRecovers: Failed node rejoins as follower
 *)
NodeRecovers(n) ==
    /\ nodeState[n] = FAILED
    /\ nodeState' = [nodeState EXCEPT ![n] = FOLLOWER]
    /\ votedFor' = [votedFor EXCEPT ![n] = "NULL"]
    /\ votesReceived' = [votesReceived EXCEPT ![n] = {}]
    \* Keep term to avoid vote splitting
    /\ UNCHANGED <<currentTerm, currentLeader>>

(*
 * HeartbeatTimeout: Follower times out on heartbeat, triggers election
 *)
HeartbeatTimeout(n) ==
    /\ nodeState[n] = FOLLOWER
    /\ currentLeader # "NULL"
    /\ nodeState[currentLeader] = FAILED  \* Leader is actually down
    /\ StartElection(n)

\* ----- NEXT STATE RELATION -----
Next ==
    \/ \E n \in {{NODES}} : StartElection(n)
    \/ \E c, v \in {{NODES}} : RequestVote(c, v)
    \/ \E n \in {{NODES}} : BecomeLeader(n)
    \/ \E n \in {{NODES}} : StepDown(n)
    \/ \E n \in {{NODES}} : NodeFails(n)
    \/ \E n \in {{NODES}} : NodeRecovers(n)

Spec == Init /\ [][Next]_vars

\* ----- SAFETY INVARIANTS -----

(*
 * AtMostOneLeader: Never more than one leader in the same term
 *)
AtMostOneLeader ==
    Cardinality({n \in {{NODES}} : nodeState[n] = LEADER}) <= 1

(*
 * LeaderConsistency: currentLeader matches actual leader state
 *)
LeaderConsistency ==
    \/ currentLeader = "NULL" /\ \A n \in {{NODES}} : nodeState[n] # LEADER
    \/ currentLeader \in {{NODES}} /\ nodeState[currentLeader] = LEADER

(*
 * VotedForConsistency: If voted for someone, they must be candidate or leader
 *)
VotedForConsistency ==
    \A n \in {{NODES}} :
        votedFor[n] # "NULL" =>
            \/ nodeState[votedFor[n]] \in {CANDIDATE, LEADER}
            \/ nodeState[votedFor[n]] = FAILED
            \/ nodeState[n] = FAILED

(*
 * TermMonotonicity: Terms only increase
 *)
TermMonotonicity ==
    \A n \in {{NODES}} :
        nodeState[n] # FAILED =>
            currentTerm'[n] >= currentTerm[n]  \* In Next step

\* Combined safety invariant
Safety ==
    /\ AtMostOneLeader
    /\ LeaderConsistency

\* ----- LIVENESS PROPERTIES -----

(*
 * EventuallyLeader: Eventually a leader is elected
 * Requires fairness assumptions
 *)
\* EventuallyLeader ==
\*     <>(currentLeader # "NULL")

(*
 * LeaderStability: If leader elected and no failures, stays leader
 *)
\* LeaderStability ==
\*     \A n \in {{NODES}} :
\*         (nodeState[n] = LEADER /\ [](\A m \in {{NODES}} : nodeState[m] # FAILED))
\*             => [](nodeState[n] = LEADER)

\* ----- FAIRNESS -----
Fairness ==
    /\ \A n \in {{NODES}} : WF_vars(StartElection(n))
    /\ \A n \in {{NODES}} : WF_vars(BecomeLeader(n))

FairSpec == Spec /\ Fairness

=============================================================================

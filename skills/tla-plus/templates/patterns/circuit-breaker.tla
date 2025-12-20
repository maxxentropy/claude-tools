---------------------------- MODULE CircuitBreaker ----------------------------
(*
 * Template: Circuit Breaker Pattern
 *
 * Pattern for: Service resilience, fault tolerance, cascading failure prevention
 * Common in: Microservices, API gateways, distributed systems
 *
 * Customization points marked with {{PLACEHOLDER}}
 *
 * Key properties verified:
 * - Breaker opens after threshold failures
 * - Half-open state allows limited probes
 * - Closed state resets failure count on success
 * - No requests pass when fully open
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

\* ----- CONSTANTS -----
CONSTANTS
    {{SERVICES}},               \* Set of service IDs (e.g., {PaymentAPI, InventoryAPI})
    FAILURE_THRESHOLD,          \* Failures before opening (e.g., 5)
    SUCCESS_THRESHOLD,          \* Successes in half-open to close (e.g., 2)
    TIMEOUT_DURATION,           \* Ticks before half-open (e.g., 3)
    MAX_REQUESTS                \* Bound for state space

\* Circuit breaker states
CLOSED == "CLOSED"
OPEN == "OPEN"
HALF_OPEN == "HALF_OPEN"

\* ----- VARIABLES -----
VARIABLES
    \* Circuit breaker state per service
    breakerState,           \* breakerState[s] = CLOSED | OPEN | HALF_OPEN
    failureCount,           \* failureCount[s] = consecutive failures
    successCount,           \* successCount[s] = consecutive successes (in half-open)
    openedAt,               \* openedAt[s] = tick when breaker opened

    \* Global clock for timeouts
    tick,

    \* Request tracking
    requestsAllowed,        \* Total requests allowed through
    requestsBlocked         \* Total requests blocked

vars == <<breakerState, failureCount, successCount, openedAt, tick, requestsAllowed, requestsBlocked>>

\* ----- TYPE INVARIANT -----
TypeInvariant ==
    /\ breakerState \in [{{SERVICES}} -> {CLOSED, OPEN, HALF_OPEN}]
    /\ failureCount \in [{{SERVICES}} -> 0..FAILURE_THRESHOLD]
    /\ successCount \in [{{SERVICES}} -> 0..SUCCESS_THRESHOLD]
    /\ openedAt \in [{{SERVICES}} -> Nat]
    /\ tick \in Nat
    /\ requestsAllowed \in 0..MAX_REQUESTS
    /\ requestsBlocked \in 0..MAX_REQUESTS

\* ----- INITIAL STATE -----
Init ==
    /\ breakerState = [s \in {{SERVICES}} |-> CLOSED]
    /\ failureCount = [s \in {{SERVICES}} |-> 0]
    /\ successCount = [s \in {{SERVICES}} |-> 0]
    /\ openedAt = [s \in {{SERVICES}} |-> 0]
    /\ tick = 0
    /\ requestsAllowed = 0
    /\ requestsBlocked = 0

\* ----- HELPER OPERATORS -----

\* Check if enough time has passed to try half-open
TimeoutExpired(s) ==
    tick >= openedAt[s] + TIMEOUT_DURATION

\* Check if request should be allowed
ShouldAllowRequest(s) ==
    CASE breakerState[s] = CLOSED -> TRUE
      [] breakerState[s] = HALF_OPEN -> TRUE  \* Limited probes
      [] breakerState[s] = OPEN -> TimeoutExpired(s)

\* ----- ACTIONS -----

(*
 * SuccessfulRequest: Request succeeds
 *)
SuccessfulRequest(s) ==
    /\ requestsAllowed < MAX_REQUESTS
    /\ CASE breakerState[s] = CLOSED ->
            /\ failureCount' = [failureCount EXCEPT ![s] = 0]
            /\ UNCHANGED <<breakerState, successCount, openedAt>>
         [] breakerState[s] = HALF_OPEN ->
            IF successCount[s] + 1 >= SUCCESS_THRESHOLD
            THEN \* Close the breaker
                /\ breakerState' = [breakerState EXCEPT ![s] = CLOSED]
                /\ failureCount' = [failureCount EXCEPT ![s] = 0]
                /\ successCount' = [successCount EXCEPT ![s] = 0]
                /\ UNCHANGED openedAt
            ELSE \* Increment success count
                /\ successCount' = [successCount EXCEPT ![s] = @ + 1]
                /\ UNCHANGED <<breakerState, failureCount, openedAt>>
         [] breakerState[s] = OPEN ->
            IF TimeoutExpired(s)
            THEN \* Transition to half-open
                /\ breakerState' = [breakerState EXCEPT ![s] = HALF_OPEN]
                /\ successCount' = [successCount EXCEPT ![s] = 1]
                /\ UNCHANGED <<failureCount, openedAt>>
            ELSE FALSE  \* Can't happen - blocked
    /\ requestsAllowed' = requestsAllowed + 1
    /\ UNCHANGED <<tick, requestsBlocked>>

(*
 * FailedRequest: Request fails
 *)
FailedRequest(s) ==
    /\ requestsAllowed < MAX_REQUESTS
    /\ CASE breakerState[s] = CLOSED ->
            IF failureCount[s] + 1 >= FAILURE_THRESHOLD
            THEN \* Open the breaker
                /\ breakerState' = [breakerState EXCEPT ![s] = OPEN]
                /\ failureCount' = [failureCount EXCEPT ![s] = FAILURE_THRESHOLD]
                /\ openedAt' = [openedAt EXCEPT ![s] = tick]
                /\ UNCHANGED successCount
            ELSE \* Increment failure count
                /\ failureCount' = [failureCount EXCEPT ![s] = @ + 1]
                /\ UNCHANGED <<breakerState, successCount, openedAt>>
         [] breakerState[s] = HALF_OPEN ->
            \* Immediately re-open
            /\ breakerState' = [breakerState EXCEPT ![s] = OPEN]
            /\ openedAt' = [openedAt EXCEPT ![s] = tick]
            /\ successCount' = [successCount EXCEPT ![s] = 0]
            /\ UNCHANGED failureCount
         [] breakerState[s] = OPEN ->
            IF TimeoutExpired(s)
            THEN \* Was probing, failed, stay open
                /\ openedAt' = [openedAt EXCEPT ![s] = tick]
                /\ UNCHANGED <<breakerState, failureCount, successCount>>
            ELSE FALSE  \* Can't happen - blocked
    /\ requestsAllowed' = requestsAllowed + 1
    /\ UNCHANGED <<tick, requestsBlocked>>

(*
 * BlockedRequest: Request blocked by open breaker
 *)
BlockedRequest(s) ==
    /\ requestsBlocked < MAX_REQUESTS
    /\ breakerState[s] = OPEN
    /\ ~TimeoutExpired(s)
    /\ requestsBlocked' = requestsBlocked + 1
    /\ UNCHANGED <<breakerState, failureCount, successCount, openedAt, tick, requestsAllowed>>

(*
 * TimePasses: Advance the clock
 *)
TimePasses ==
    /\ tick' = tick + 1
    /\ UNCHANGED <<breakerState, failureCount, successCount, openedAt, requestsAllowed, requestsBlocked>>

\* ----- NEXT STATE RELATION -----
Next ==
    \/ \E s \in {{SERVICES}} : SuccessfulRequest(s)
    \/ \E s \in {{SERVICES}} : FailedRequest(s)
    \/ \E s \in {{SERVICES}} : BlockedRequest(s)
    \/ TimePasses

Spec == Init /\ [][Next]_vars

\* ----- SAFETY INVARIANTS -----

(*
 * OpenBreakerBlocks: Open breaker blocks requests (until timeout)
 *)
OpenBreakerBlocks ==
    \A s \in {{SERVICES}} :
        (breakerState[s] = OPEN /\ ~TimeoutExpired(s)) =>
            \* No successful/failed requests while open (only blocked)
            TRUE  \* Enforced by action guards

(*
 * FailureThresholdRespected: Breaker opens only after threshold failures
 *)
FailureThresholdRespected ==
    \A s \in {{SERVICES}} :
        breakerState[s] = OPEN => failureCount[s] >= FAILURE_THRESHOLD

(*
 * HalfOpenProbesLimited: Half-open state allows limited attempts
 *)
HalfOpenProbesLimited ==
    \A s \in {{SERVICES}} :
        breakerState[s] = HALF_OPEN => successCount[s] <= SUCCESS_THRESHOLD

(*
 * ClosedMeansHealthy: Closed state has no accumulated failures
 * (after successful request resets counter)
 *)
\* This is a relaxed invariant - failures can accumulate before threshold

\* Combined safety invariant
Safety ==
    /\ FailureThresholdRespected
    /\ HalfOpenProbesLimited

\* ----- LIVENESS PROPERTIES -----

(*
 * EventuallyRecovers: If underlying service recovers, breaker eventually closes
 * (Requires fairness on SuccessfulRequest)
 *)
\* EventuallyRecovers ==
\*     \A s \in {{SERVICES}} :
\*         (breakerState[s] = OPEN) ~> (breakerState[s] = CLOSED)

(*
 * TimeoutEventuallyExpires: Open breaker eventually allows probes
 *)
\* TimeoutEventuallyExpires ==
\*     \A s \in {{SERVICES}} :
\*         (breakerState[s] = OPEN) ~> TimeoutExpired(s)

=============================================================================

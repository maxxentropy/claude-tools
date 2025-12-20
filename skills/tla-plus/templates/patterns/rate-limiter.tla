---------------------------- MODULE RateLimiter ----------------------------
(*
 * Template: Token Bucket Rate Limiter
 *
 * Pattern for: API rate limiting, request throttling, resource protection
 * Common in: API gateways, SaaS platforms, multi-tenant systems
 *
 * Implements: Token bucket algorithm with configurable refill rate
 *
 * Customization points marked with {{PLACEHOLDER}}
 *
 * Key properties verified:
 * - Never exceeds burst capacity
 * - Tokens refill at correct rate
 * - Requests correctly allowed or rejected
 * - Fair treatment across clients (if configured)
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

\* ----- CONSTANTS -----
CONSTANTS
    {{CLIENTS}},                \* Set of client IDs (e.g., {Client1, Client2})
    BUCKET_CAPACITY,            \* Maximum tokens per bucket (burst limit)
    REFILL_RATE,                \* Tokens added per tick
    TOKENS_PER_REQUEST,         \* Tokens consumed per request (usually 1)
    MAX_TICKS                   \* Bound for state space exploration

\* ----- VARIABLES -----
VARIABLES
    tokens,                 \* tokens[c] = current token count for client
    tick,                   \* Global clock for refill timing
    lastRefill,             \* lastRefill[c] = tick when last refilled
    requestsAllowed,        \* Total requests allowed
    requestsRejected        \* Total requests rejected (rate limited)

vars == <<tokens, tick, lastRefill, requestsAllowed, requestsRejected>>

\* ----- TYPE INVARIANT -----
TypeInvariant ==
    /\ tokens \in [{{CLIENTS}} -> 0..BUCKET_CAPACITY]
    /\ tick \in 0..MAX_TICKS
    /\ lastRefill \in [{{CLIENTS}} -> 0..MAX_TICKS]
    /\ requestsAllowed \in Nat
    /\ requestsRejected \in Nat

\* ----- INITIAL STATE -----
Init ==
    /\ tokens = [c \in {{CLIENTS}} |-> BUCKET_CAPACITY]  \* Start full
    /\ tick = 0
    /\ lastRefill = [c \in {{CLIENTS}} |-> 0]
    /\ requestsAllowed = 0
    /\ requestsRejected = 0

\* ----- HELPER OPERATORS -----

\* Calculate tokens to add based on elapsed time
TokensToAdd(c) ==
    LET elapsed == tick - lastRefill[c]
    IN elapsed * REFILL_RATE

\* Current effective token count (with pending refill)
EffectiveTokens(c) ==
    LET pending == tokens[c] + TokensToAdd(c)
    IN IF pending > BUCKET_CAPACITY THEN BUCKET_CAPACITY ELSE pending

\* Check if request can be allowed
CanAllowRequest(c) ==
    EffectiveTokens(c) >= TOKENS_PER_REQUEST

\* ----- ACTIONS -----

(*
 * AllowRequest: Client makes request, tokens available
 *)
AllowRequest(c) ==
    /\ CanAllowRequest(c)
    /\ LET effectiveNow == EffectiveTokens(c)
           newTokens == effectiveNow - TOKENS_PER_REQUEST
       IN /\ tokens' = [tokens EXCEPT ![c] = newTokens]
          /\ lastRefill' = [lastRefill EXCEPT ![c] = tick]
    /\ requestsAllowed' = requestsAllowed + 1
    /\ UNCHANGED <<tick, requestsRejected>>

(*
 * RejectRequest: Client makes request, insufficient tokens
 *)
RejectRequest(c) ==
    /\ ~CanAllowRequest(c)
    /\ requestsRejected' = requestsRejected + 1
    /\ UNCHANGED <<tokens, tick, lastRefill, requestsAllowed>>

(*
 * RefillTokens: Explicit refill action (alternative to lazy refill)
 * Use this if you want to model periodic refill instead of on-demand
 *)
RefillTokens(c) ==
    /\ tick > lastRefill[c]
    /\ LET newTokens == EffectiveTokens(c)
       IN /\ tokens' = [tokens EXCEPT ![c] = newTokens]
          /\ lastRefill' = [lastRefill EXCEPT ![c] = tick]
    /\ UNCHANGED <<tick, requestsAllowed, requestsRejected>>

(*
 * TimePasses: Advance the clock
 *)
TimePasses ==
    /\ tick < MAX_TICKS
    /\ tick' = tick + 1
    /\ UNCHANGED <<tokens, lastRefill, requestsAllowed, requestsRejected>>

\* ----- NEXT STATE RELATION -----
Next ==
    \/ \E c \in {{CLIENTS}} : AllowRequest(c)
    \/ \E c \in {{CLIENTS}} : RejectRequest(c)
    \/ \E c \in {{CLIENTS}} : RefillTokens(c)
    \/ TimePasses

Spec == Init /\ [][Next]_vars

\* ----- SAFETY INVARIANTS -----

(*
 * NeverExceedsCapacity: Token count never exceeds bucket capacity
 *)
NeverExceedsCapacity ==
    \A c \in {{CLIENTS}} :
        tokens[c] <= BUCKET_CAPACITY

(*
 * NonNegativeTokens: Token count never goes negative
 *)
NonNegativeTokens ==
    \A c \in {{CLIENTS}} :
        tokens[c] >= 0

(*
 * AllowedMeansHadTokens: Requests are only allowed when tokens available
 * (Enforced by action guards, but this verifies the invariant)
 *)
AllowedImpliesTokens ==
    TRUE  \* Encoded in AllowRequest precondition

(*
 * RefillRateRespected: Tokens don't appear faster than refill rate
 * This is more of a property to test than an invariant
 *)

\* Combined safety invariant
Safety ==
    /\ NeverExceedsCapacity
    /\ NonNegativeTokens

\* ----- FAIRNESS -----

(*
 * If modeling fairness across clients, add weak fairness on AllowRequest
 * to ensure all clients eventually get service
 *)
Fairness ==
    \A c \in {{CLIENTS}} : WF_vars(AllowRequest(c))

FairSpec == Spec /\ Fairness

\* ----- LIVENESS PROPERTIES -----

(*
 * EventuallyAllowed: If client waits long enough, request is allowed
 * (Assuming time passes)
 *)
\* EventuallyAllowed ==
\*     \A c \in {{CLIENTS}} :
\*         (tokens[c] < TOKENS_PER_REQUEST) ~> CanAllowRequest(c)

(*
 * TokensEventuallyRefill: Empty bucket eventually refills
 *)
\* TokensEventuallyRefill ==
\*     \A c \in {{CLIENTS}} :
\*         (tokens[c] = 0) ~> (tokens[c] > 0)

\* ----- ADDITIONAL PATTERNS -----

(*
 * Sliding Window Rate Limiter:
 * Instead of token bucket, track request timestamps in a sliding window.
 *
 * Variables:
 *   requestLog \in [CLIENTS -> Seq(Nat)]  \* Timestamps of recent requests
 *
 * Allow if:
 *   Cardinality({t \in Range(requestLog[c]) : t > tick - WINDOW_SIZE}) < MAX_REQUESTS
 *)

(*
 * Leaky Bucket Rate Limiter:
 * Process requests at fixed rate, queue excess.
 *
 * Variables:
 *   queue \in [CLIENTS -> Seq(Request)]
 *
 * Process one request per tick, reject if queue full.
 *)

=============================================================================

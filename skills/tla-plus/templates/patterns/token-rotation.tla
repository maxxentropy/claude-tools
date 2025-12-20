---------------------------- MODULE TokenRotation ----------------------------
(*
 * Template: Token Rotation with Concurrent Refresh
 *
 * Pattern for: JWT refresh tokens, session management, API key rotation
 * Common in: Authentication systems, OAuth flows, credential rotation
 *
 * Customization points marked with {{PLACEHOLDER}}
 *
 * Key properties verified:
 * - Single active token per user at any time
 * - Revoked tokens cannot be refreshed
 * - Replacement chain integrity
 * - No double-refresh (same token refreshed twice)
 *)

EXTENDS Naturals, Sequences, FiniteSets, TLC

\* ----- CONSTANTS -----
CONSTANTS
    {{USERS}},              \* Set of user IDs (e.g., {U1, U2})
    MAX_TOKENS              \* Maximum tokens per user (bounds state space)

\* ----- VARIABLES -----
VARIABLES
    \* Token state
    tokens,                 \* tokens[tokenId] = token record
    nextTokenId,            \* Counter for generating unique token IDs
    userActiveToken,        \* userActiveToken[u] = current active token ID

    \* In-flight operations (models concurrent HTTP requests)
    refreshInProgress,      \* Sequence of refresh request records
    nextRequestId           \* Counter for request IDs

vars == <<tokens, nextTokenId, userActiveToken, refreshInProgress, nextRequestId>>

\* ----- TOKEN RECORD STRUCTURE -----
\* Each token has: userId, isRevoked, replacedByToken, createdAt
NullToken == [userId |-> "NULL", isRevoked |-> FALSE, replacedByToken |-> 0, createdAt |-> 0]

\* ----- TYPE INVARIANT -----
TypeInvariant ==
    /\ tokens \in [1..MAX_TOKENS -> [userId: {{USERS}} \cup {"NULL"},
                                      isRevoked: BOOLEAN,
                                      replacedByToken: 0..MAX_TOKENS,
                                      createdAt: Nat]]
    /\ nextTokenId \in 1..(MAX_TOKENS + 1)
    /\ userActiveToken \in [{{USERS}} -> 0..MAX_TOKENS]
    /\ nextRequestId \in Nat

\* ----- INITIAL STATE -----
Init ==
    /\ tokens = [t \in 1..MAX_TOKENS |-> NullToken]
    /\ nextTokenId = 1
    /\ userActiveToken = [u \in {{USERS}} |-> 0]
    /\ refreshInProgress = <<>>
    /\ nextRequestId = 1

\* ----- HELPER OPERATORS -----

\* Check if a token is valid for refresh
IsTokenValid(tokenId) ==
    /\ tokenId > 0
    /\ tokenId < nextTokenId
    /\ tokens[tokenId].userId # "NULL"
    /\ ~tokens[tokenId].isRevoked

\* Check if user has capacity for new token
CanCreateToken == nextTokenId <= MAX_TOKENS

\* ----- ACTIONS -----

(*
 * UserLogin: User logs in and receives initial token pair
 *)
UserLogin(u) ==
    /\ CanCreateToken
    /\ userActiveToken[u] = 0  \* User not already logged in
    /\ LET newTokenId == nextTokenId
       IN /\ tokens' = [tokens EXCEPT ![newTokenId] =
                        [userId |-> u,
                         isRevoked |-> FALSE,
                         replacedByToken |-> 0,
                         createdAt |-> nextTokenId]]
          /\ nextTokenId' = nextTokenId + 1
          /\ userActiveToken' = [userActiveToken EXCEPT ![u] = newTokenId]
    /\ UNCHANGED <<refreshInProgress, nextRequestId>>

(*
 * StartRefresh: Begin a token refresh operation (Phase 1: READ)
 *
 * Models reading current token state. Multiple concurrent requests
 * can read the same "valid" state - this is where races begin.
 *)
StartRefresh(u, tokenId) ==
    /\ IsTokenValid(tokenId)
    /\ tokens[tokenId].userId = u
    /\ LET reqId == nextRequestId
       IN /\ refreshInProgress' = Append(refreshInProgress,
                [reqId |-> reqId,
                 userId |-> u,
                 tokenId |-> tokenId,
                 readIsRevoked |-> tokens[tokenId].isRevoked,
                 phase |-> "read_complete"])
          /\ nextRequestId' = nextRequestId + 1
    /\ UNCHANGED <<tokens, nextTokenId, userActiveToken>>

(*
 * CompleteRefresh: Complete token refresh (Phase 2: CHECK-MODIFY-WRITE)
 *
 * CORRECT behavior: Re-check token state before writing.
 * If token was revoked between read and write, fail the refresh.
 *)
CompleteRefresh(reqIdx) ==
    /\ reqIdx \in 1..Len(refreshInProgress)
    /\ refreshInProgress[reqIdx].phase = "read_complete"
    /\ LET req == refreshInProgress[reqIdx]
           tokenId == req.tokenId
           u == req.userId
           currentToken == tokens[tokenId]
       IN
           \* Re-check if token is still valid (CRITICAL for correctness)
           IF currentToken.isRevoked
           THEN \* Token was revoked by another request - FAIL
                /\ refreshInProgress' = [refreshInProgress EXCEPT ![reqIdx].phase = "failed"]
                /\ UNCHANGED <<tokens, nextTokenId, userActiveToken, nextRequestId>>
           ELSE IF ~CanCreateToken
           THEN \* No capacity for new token
                /\ refreshInProgress' = [refreshInProgress EXCEPT ![reqIdx].phase = "failed"]
                /\ UNCHANGED <<tokens, nextTokenId, userActiveToken, nextRequestId>>
           ELSE \* Token still valid - proceed with rotation
                LET newTokenId == nextTokenId
                IN /\ tokens' = [tokens EXCEPT
                        \* Revoke old token and set replacement pointer
                        ![tokenId] = [@ EXCEPT !.isRevoked = TRUE,
                                               !.replacedByToken = newTokenId],
                        \* Create new token
                        ![newTokenId] = [userId |-> u,
                                         isRevoked |-> FALSE,
                                         replacedByToken |-> 0,
                                         createdAt |-> newTokenId]]
                   /\ nextTokenId' = nextTokenId + 1
                   /\ userActiveToken' = [userActiveToken EXCEPT ![u] = newTokenId]
                   /\ refreshInProgress' = [refreshInProgress EXCEPT ![reqIdx].phase = "completed"]
                   /\ UNCHANGED <<nextRequestId>>

(*
 * CleanupRequest: Remove completed/failed request from in-flight list
 *)
CleanupRequest(reqIdx) ==
    /\ reqIdx \in 1..Len(refreshInProgress)
    /\ refreshInProgress[reqIdx].phase \in {"completed", "failed"}
    /\ refreshInProgress' = SubSeq(refreshInProgress, 1, reqIdx-1) \o
                            SubSeq(refreshInProgress, reqIdx+1, Len(refreshInProgress))
    /\ UNCHANGED <<tokens, nextTokenId, userActiveToken, nextRequestId>>

(*
 * UserLogout: User explicitly logs out, revoking their token
 *)
UserLogout(u) ==
    /\ userActiveToken[u] > 0
    /\ LET tokenId == userActiveToken[u]
       IN /\ tokens' = [tokens EXCEPT ![tokenId].isRevoked = TRUE]
          /\ userActiveToken' = [userActiveToken EXCEPT ![u] = 0]
    /\ UNCHANGED <<nextTokenId, refreshInProgress, nextRequestId>>

\* ----- NEXT STATE RELATION -----
Next ==
    \/ \E u \in {{USERS}} : UserLogin(u)
    \/ \E u \in {{USERS}}, t \in 1..MAX_TOKENS : StartRefresh(u, t)
    \/ \E i \in 1..10 : CompleteRefresh(i)
    \/ \E i \in 1..10 : CleanupRequest(i)
    \/ \E u \in {{USERS}} : UserLogout(u)

Spec == Init /\ [][Next]_vars

\* ----- SAFETY INVARIANTS -----

(*
 * SingleActiveToken: Each user has at most one active (non-revoked) token
 *)
SingleActiveToken ==
    \A u \in {{USERS}} :
        Cardinality({t \in 1..(nextTokenId-1) :
            tokens[t].userId = u /\ ~tokens[t].isRevoked}) <= 1

(*
 * ActiveTokenMatchesUserRecord: userActiveToken points to the actual active token
 *)
ActiveTokenMatchesUserRecord ==
    \A u \in {{USERS}} :
        userActiveToken[u] > 0 =>
            /\ tokens[userActiveToken[u]].userId = u
            /\ ~tokens[userActiveToken[u]].isRevoked

(*
 * ReplacementChainIntegrity: If token A replaced by B, B exists and same user
 *)
ReplacementChainIntegrity ==
    \A t \in 1..(nextTokenId-1) :
        tokens[t].replacedByToken > 0 =>
            /\ tokens[t].replacedByToken < nextTokenId
            /\ tokens[tokens[t].replacedByToken].userId = tokens[t].userId

(*
 * NoDoubleRefresh: A token cannot be successfully refreshed twice
 *)
NoDoubleRefresh ==
    \A t \in 1..(nextTokenId-1) :
        tokens[t].isRevoked => tokens[t].replacedByToken > 0 \/ userActiveToken[tokens[t].userId] = 0

\* Combined safety invariant
Safety ==
    /\ SingleActiveToken
    /\ ActiveTokenMatchesUserRecord
    /\ ReplacementChainIntegrity

=============================================================================

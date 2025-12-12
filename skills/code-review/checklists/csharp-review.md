# C# Code Review Checklist

Quick checklist for reviewing C# code. Check each item and note findings.

## Correctness

- [ ] Logic handles all expected inputs correctly
- [ ] Edge cases handled (null, empty, boundary values)
- [ ] Off-by-one errors checked in loops/indexing
- [ ] Return values are correct and consistent
- [ ] Conditions use correct operators (== vs =, && vs &)

## Null Safety

- [ ] Nullable reference types enabled (`#nullable enable`)
- [ ] Null checks on parameters (`ArgumentNullException.ThrowIfNull`)
- [ ] Null-conditional operators used appropriately (`?.`, `??`)
- [ ] No unnecessary null-forgiving operators (`!`)
- [ ] `FirstOrDefault()` results checked before use

## Async/Await

- [ ] No `async void` (except event handlers)
- [ ] No `.Result` or `.Wait()` blocking calls
- [ ] `ConfigureAwait(false)` in library code
- [ ] Cancellation tokens propagated
- [ ] `Task.Run()` only for CPU-bound work
- [ ] Async methods named with `Async` suffix

## Resource Management

- [ ] `IDisposable` objects in `using` statements
- [ ] `IAsyncDisposable` with `await using`
- [ ] HttpClient managed via IHttpClientFactory
- [ ] Database connections properly scoped
- [ ] File handles closed in all paths

## LINQ & Collections

- [ ] No multiple enumeration of `IEnumerable`
- [ ] Deferred execution understood and handled
- [ ] `ToList()`/`ToArray()` used when materializing
- [ ] `Any()` instead of `Count() > 0`
- [ ] Appropriate collection type for use case

## Thread Safety

- [ ] Shared mutable state protected
- [ ] Thread-safe collections used (`ConcurrentDictionary`, etc.)
- [ ] No race conditions in check-then-act patterns
- [ ] Lock ordering consistent (deadlock prevention)
- [ ] `Interlocked` for simple atomic operations

## Exception Handling

- [ ] Specific exceptions caught (not bare `Exception`)
- [ ] Exceptions not swallowed silently
- [ ] Exception chaining with `throw ... from`
- [ ] Meaningful exception messages
- [ ] No exceptions in performance-critical paths

## Dependency Injection

- [ ] Dependencies injected via constructor
- [ ] Correct service lifetime (Scoped/Singleton/Transient)
- [ ] No captive dependencies (singleton → scoped)
- [ ] No service locator pattern
- [ ] Interfaces used for dependencies

## Entity Framework

- [ ] `Include()` for needed navigation properties
- [ ] `AsNoTracking()` for read-only queries
- [ ] No N+1 query patterns
- [ ] Projections (`Select`) to limit data fetched
- [ ] Transactions for multi-operation consistency

## Security

- [ ] Parameterized queries (no SQL concatenation)
- [ ] Input validation at boundaries
- [ ] No secrets in code
- [ ] Authorization checks present
- [ ] Sensitive data not logged

## Performance

- [ ] StringBuilder for string concatenation in loops
- [ ] No unnecessary allocations in hot paths
- [ ] Caching for expensive operations
- [ ] Appropriate data structures
- [ ] No premature optimization

## Maintainability

- [ ] Clear, descriptive names
- [ ] Single responsibility per method/class
- [ ] Methods not too long (<30 lines guideline)
- [ ] Complexity manageable (no deeply nested logic)
- [ ] Comments explain "why" not "what"

---

> **Note**: For architectural concerns (Resilience, Observability, API Design, Configuration),
> see the `architecture-review` skill checklist.

## Finding Template

```
#### [SEVERITY] Finding Title
**Location**: `path/file.cs:line`
**Category**: [Category from above]

**Issue**: Description of the problem

**Why It Matters**: Educational context

**Recommendation**:
```csharp
// Suggested fix
```
```

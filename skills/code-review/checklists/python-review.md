# Python Code Review Checklist

Quick checklist for reviewing Python code. Check each item and note findings.

## Correctness

- [ ] Logic handles all expected inputs correctly
- [ ] Edge cases handled (None, empty, boundary values)
- [ ] Off-by-one errors checked in loops/slicing
- [ ] Return values are correct and consistent
- [ ] Conditions use correct operators (`==` vs `is`, `and` vs `&`)

## Type Safety

- [ ] Type hints on function signatures
- [ ] `Optional` for nullable parameters/returns
- [ ] Generic types used correctly (`List[T]`, `Dict[K, V]`)
- [ ] `Sequence` for input, `List` for output
- [ ] No mutable default arguments

## Async/Await

- [ ] No blocking calls in async functions
- [ ] `await asyncio.gather()` for concurrent operations
- [ ] Proper timeout handling with `asyncio.timeout()`
- [ ] Tasks tracked (not fire-and-forget)
- [ ] Async context managers (`async with`)

## Resource Management

- [ ] Context managers for files (`with open()`)
- [ ] Database connections properly scoped
- [ ] HTTP sessions closed
- [ ] Cleanup in `finally` blocks or `__exit__`

## Collections & Iteration

- [ ] List comprehensions readable (not too complex)
- [ ] Generator expressions for large data
- [ ] `enumerate()` instead of manual indexing
- [ ] `zip()` for parallel iteration
- [ ] `dict.get()` with defaults vs KeyError

## Thread Safety

- [ ] GIL limitations understood (CPU vs I/O bound)
- [ ] Locks for shared mutable state
- [ ] Queue for thread communication
- [ ] No global mutable state accessed from threads
- [ ] Proper multiprocessing for CPU-bound work

## Exception Handling

- [ ] Specific exceptions caught (not bare `except:`)
- [ ] Exceptions not swallowed silently
- [ ] Exception chaining (`raise ... from`)
- [ ] Custom exceptions for domain errors
- [ ] Context added when re-raising

## Data Classes

- [ ] `@dataclass` for data containers
- [ ] `frozen=True` for immutable data
- [ ] `field(default_factory=...)` for mutable defaults
- [ ] `__post_init__` for validation
- [ ] Pydantic for external input validation

## Security

- [ ] Parameterized queries (no f-string SQL)
- [ ] No `eval()` or `exec()` with user input
- [ ] `yaml.safe_load()` not `yaml.load()`
- [ ] No `pickle` with untrusted data
- [ ] Path traversal prevention
- [ ] Secrets from environment, not code

## Testing

- [ ] Tests use descriptive names
- [ ] Fixtures for setup/teardown
- [ ] Mocks for external dependencies
- [ ] Parametrized tests for variations
- [ ] Async tests with `@pytest.mark.asyncio`

## Performance

- [ ] `str.join()` instead of `+=` in loops
- [ ] Generators for large sequences
- [ ] `@lru_cache` for expensive pure functions
- [ ] `__slots__` for memory-critical classes
- [ ] Appropriate data structures

## Maintainability

- [ ] PEP 8 naming conventions
- [ ] Functions have single responsibility
- [ ] Functions not too long (<30 lines guideline)
- [ ] No deeply nested logic
- [ ] Docstrings for public functions/classes

---

> **Note**: For architectural concerns (Resilience, Observability, API Design, Configuration),
> see the `architecture-review` skill checklist.

## Finding Template

```
#### [SEVERITY] Finding Title
**Location**: `path/file.py:line`
**Category**: [Category from above]

**Issue**: Description of the problem

**Why It Matters**: Educational context

**Recommendation**:
```python
# Suggested fix
```
```

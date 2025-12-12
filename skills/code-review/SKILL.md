---
name: code-review
description: |
  Perform per-change code reviews for C# and Python with language-specific best practices.
  Use when asked about: code review, review this code, check my code, review PR, best practices,
  is this code good, code quality, review changes, review my changes.
  Also triggers automatically after significant code changes.
  NOT for: architectural assessments, system design reviews (use architecture-review skill instead).
---

# Code Review Skill

Per-change code reviews for C# and Python focusing on correctness, safety, patterns, and maintainability.

## Role in Code Quality Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ code-review     │     │ senior-code-    │     │ unit-test-      │
│ skill           │ ──► │ reviewer agent  │ ──► │ architect agent │
│ (Checklist)     │     │ (Expert Judge)  │     │ (Test Coverage) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     SYSTEMATIC             DEEP ANALYSIS          VERIFICATION
```

This skill is the **SYSTEMATIC** phase. It applies structured checklists to catch common issues.

**For architectural concerns** (resilience, observability, API design, configuration, system structure),
use the `architecture-review` skill instead.

**For complex code requiring expert judgment** (concurrency, security-sensitive, "feels wrong"),
escalate to the `senior-code-reviewer` agent.

## Quick Start

```bash
# Review a specific file
# "Review src/Services/AuthService.cs"

# Review recent changes
# "Review my changes" or "Review what I just wrote"

# Review with specific focus
# "Review this code for thread safety"
# "Check this for security issues"
```

## Review Process

### 1. Detect Language & Context

First, identify:
- **Language**: C# (.cs) or Python (.py)
- **Framework**: ASP.NET Core, Blazor, FastAPI, Flask, etc.
- **Project patterns**: Check existing code for established conventions

### 2. Apply Review Checklist

Use the appropriate language-specific checklist:
- `checklists/csharp-review.md` - C# and .NET review checklist
- `checklists/python-review.md` - Python review checklist

### 3. Analyze Categories

Review code across these categories:

| Category | What to Check |
|----------|---------------|
| **Correctness** | Logic errors, edge cases, null handling, off-by-one errors |
| **Design** | SOLID principles, patterns, abstraction levels, coupling |
| **Thread Safety** | Race conditions, deadlocks, shared state, async/await |
| **Security** | Injection, auth, secrets, input validation, OWASP Top 10 |
| **Performance** | Allocations, complexity, database queries, caching |
| **Maintainability** | Naming, complexity, documentation, testability |
| **Error Handling** | Exception types, recovery, logging, user messages |

### 4. Classify Findings

Categorize each finding:

| Severity | Meaning | Action |
|----------|---------|--------|
| **CRITICAL** | Security vulnerability, data loss risk, crash | Must fix before merge |
| **HIGH** | Bug, race condition, significant design flaw | Should fix before merge |
| **MEDIUM** | Code smell, maintainability issue, minor bug | Fix soon |
| **LOW** | Style, naming, minor improvement | Consider fixing |
| **INFO** | Educational note, alternative approach | No action required |

### 5. Create Work Items

For CRITICAL and HIGH findings, create Azure DevOps work items:

```bash
# Check platform first
python3 skills/detect-platform.py

# Create bug for critical/high findings
az boards work-item create --org "$ORG" --project "$PROJECT" \
  --type "Bug" --title "Code Review: [Finding Title]" \
  --description "<h2>Finding</h2><p>Description...</p><h2>Location</h2><p>File:Line</p><h2>Recommendation</h2><p>How to fix...</p>"
```

## Review Output Format

Structure reviews as:

```markdown
## Code Review: [File/Component Name]

**Language**: C# | Python
**Framework**: [Detected framework]
**Lines Reviewed**: [Count]

### Summary
[1-2 sentence overview of code quality and main findings]

### Findings

#### [CRITICAL] Finding Title
**Location**: `path/to/file.cs:42`
**Category**: Security | Thread Safety | etc.

**Issue**: Clear description of the problem.

**Why It Matters**: Educational explanation of the risk/impact.

**Recommendation**:
```[language]
// Suggested fix
```

**Work Item**: AB#[number] (if created)

---

#### [HIGH] Next Finding...

### Positive Observations
- [What's done well - reinforce good practices]

### Summary Statistics
- Critical: X | High: X | Medium: X | Low: X
- Work items created: [list]
```

## Language-Specific Guidance

### C# Reviews

Reference: `references/csharp-best-practices.md`

Key areas:
- **Async/Await**: Proper async patterns, ConfigureAwait, cancellation tokens
- **Nullable References**: Null checks, nullable annotations, null-forgiving operator usage
- **Dispose Pattern**: IDisposable, using statements, async dispose
- **LINQ**: Deferred execution awareness, multiple enumeration, performance
- **Dependency Injection**: Service lifetimes, circular dependencies, captive dependencies
- **EF Core**: N+1 queries, tracking, transactions, migrations

### Python Reviews

Reference: `references/python-best-practices.md`

Key areas:
- **Type Hints**: Proper typing, Optional, Union, generics
- **Context Managers**: Resource cleanup, __enter__/__exit__
- **Async**: asyncio patterns, await in loops, task management
- **Data Classes**: Immutability, slots, field defaults
- **Exception Handling**: Specific exceptions, context, chaining
- **Testing**: pytest patterns, fixtures, mocking

## Thread Safety Analysis

### C# Concurrency Checklist

1. **Shared State**
   - Is mutable state accessed from multiple threads?
   - Are collections thread-safe (ConcurrentDictionary, etc.)?
   - Is locking used correctly (lock ordering, granularity)?

2. **Async Patterns**
   - Async void (only for event handlers)?
   - ConfigureAwait(false) in library code?
   - Cancellation token propagation?
   - Task.Run vs direct async?

3. **Race Conditions**
   - Check-then-act patterns?
   - Lazy initialization thread safety?
   - Event handler subscription races?

### Python Concurrency Checklist

1. **GIL Awareness**
   - CPU-bound vs I/O-bound work?
   - multiprocessing vs threading vs asyncio?

2. **Shared State**
   - Global variables accessed from threads?
   - Queue usage for thread communication?
   - Lock usage and potential deadlocks?

3. **Async Patterns**
   - Blocking calls in async code?
   - Proper await usage?
   - Task cancellation handling?

## Security Review

### OWASP Top 10 Checks

| Risk | What to Look For |
|------|------------------|
| Injection | SQL concatenation, command building, LDAP queries |
| Broken Auth | Hard-coded credentials, weak tokens, session handling |
| Sensitive Data | Logging secrets, unencrypted storage, PII handling |
| XXE | XML parsing without disabling external entities |
| Broken Access | Missing authorization checks, IDOR vulnerabilities |
| Misconfig | Debug enabled, default credentials, verbose errors |
| XSS | Unencoded output, innerHTML, template injection |
| Deserialization | Untrusted data deserialization, type handling |
| Vulnerable Components | Outdated packages, known CVEs |
| Logging | Missing audit logs, sensitive data in logs |

### C# Security Specifics
- SQL: Use parameterized queries, avoid string concatenation
- Crypto: Use modern algorithms (AES-GCM, RSA-OAEP), proper key management
- Auth: ASP.NET Identity, JWT validation, CORS configuration
- Secrets: User secrets, Key Vault, no secrets in code

### Python Security Specifics
- SQL: Use parameterized queries, ORM properly
- Pickle: Never unpickle untrusted data
- Eval/Exec: Avoid or sandbox completely
- YAML: Use safe_load, not load
- Requests: Verify SSL, timeout configuration

## Auto-Trigger Behavior

The skill should auto-suggest reviews when:

1. **New file created** with >50 lines of code
2. **Significant edit** touching >30% of a file
3. **Security-sensitive code** detected:
   - Authentication/authorization logic
   - Cryptographic operations
   - Database queries
   - External API calls
   - File system operations
4. **Concurrent code** detected:
   - async/await patterns
   - Thread/Task usage
   - Locking primitives

Auto-trigger message:
> "I notice you've made significant changes to [file]. Would you like me to review this code for [detected concerns]?"

## Escalation to Expert Review

Escalate to `senior-code-reviewer` agent when code requires expert judgment beyond checklists:

| Indicator | Action |
|-----------|--------|
| Complex concurrency | "Let me engage the senior-code-reviewer agent for this concurrent code" |
| Security-sensitive logic | "This auth code needs expert analysis" |
| Subtle bug intuition | "Something feels off here - escalating for deep analysis" |
| Performance-critical path | "This hot path needs expert review" |
| Legacy code changes | "This legacy code needs careful expert analysis" |

### Escalation Format

```markdown
## Escalation to senior-code-reviewer

### Code Under Review
[File path and line range]

### Initial Findings
[What the checklist-based review found]

### Reason for Escalation
[Why expert judgment is needed]

### Specific Concerns
- [Concern 1]
- [Concern 2]
```

## Integration with Other Skills

### senior-code-reviewer Agent (Expert Analysis)
Escalate when code requires:
- Expert judgment beyond checklists
- Deep concurrency analysis
- Security-sensitive review
- Teaching/explanation focus

### architecture-review Skill (Systemic Issues)
Escalate when findings indicate systemic issues:
- Pattern repeated across codebase
- Missing infrastructure (logging, error handling)
- Structural problems requiring refactoring

### unit-test-architect Agent (Test Coverage)
After review, engage for:
- Test coverage for new code
- Test strategy for complex logic
- Testability improvements

### WSR Integration
Include code review findings in weekly status reports:
```json
{
  "entries": [{
    "title": "Code review: AuthService security improvements",
    "status": "Completed",
    "objective": "Address security findings from code review",
    "work_items": [{"id": 123, "title": "Fix SQL injection in login"}]
  }]
}
```

### Azure DevOps Integration
- Create bugs for CRITICAL/HIGH findings
- Link to commits/PRs being reviewed
- Use proper HTML formatting for descriptions

## Example Review Session

**User**: "Review the changes I just made to UserService.cs"

**Claude**:
1. Identifies changed lines in UserService.cs
2. Detects C# language, ASP.NET Core framework
3. Loads `references/csharp-best-practices.md`
4. Analyzes against checklist
5. Produces structured review with findings
6. Offers to create work items for critical/high issues

## Files Reference

| File | Purpose |
|------|---------|
| `SKILL.md` | This file - skill documentation |
| `references/csharp-best-practices.md` | C# patterns, practices, anti-patterns |
| `references/python-best-practices.md` | Python patterns, practices, anti-patterns |
| `checklists/csharp-review.md` | C# review checklist |
| `checklists/python-review.md` | Python review checklist |

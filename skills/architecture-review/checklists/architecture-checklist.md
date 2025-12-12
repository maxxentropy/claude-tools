# Architecture Review Checklist

Quick assessment checklist for architectural reviews. Check each item and note findings.

---

## Project Structure

- [ ] Clear separation of layers (presentation, application, domain, infrastructure)
- [ ] Dependencies flow inward (toward domain)
- [ ] Domain has minimal/no external dependencies
- [ ] No circular project/module references
- [ ] Consistent folder/file naming conventions
- [ ] Entry points clearly identifiable

## Domain Design

- [ ] Bounded contexts identified and respected
- [ ] Aggregates have clear boundaries
- [ ] Entities vs Value Objects properly distinguished
- [ ] Domain events for cross-aggregate communication
- [ ] Repository interfaces in domain layer
- [ ] No infrastructure concerns in domain

## Dependency Injection

- [ ] Dependencies injected via constructors
- [ ] Service lifetimes appropriate (singleton/scoped/transient)
- [ ] No captive dependencies (singleton holding scoped)
- [ ] No service locator anti-pattern
- [ ] Composition root clearly defined
- [ ] Interfaces used for external dependencies

## Resilience

- [ ] Retry policies for transient failures
- [ ] Circuit breakers for external dependencies
- [ ] Timeouts configured on all external calls
- [ ] Bulkhead isolation for critical resources
- [ ] Fallback strategies defined
- [ ] Graceful degradation implemented

## Health & Monitoring

- [ ] Health check endpoints implemented (/health/ready, /health/live)
- [ ] Database connectivity checked
- [ ] External service health verified
- [ ] Kubernetes probes configured (if applicable)

## Observability

- [ ] Structured logging in use (not string concatenation)
- [ ] Correlation IDs propagated across services
- [ ] Appropriate log levels configured
- [ ] Sensitive data NOT logged
- [ ] Metrics exposed for key operations
- [ ] Distributed tracing implemented

## API Design

- [ ] Consistent REST conventions (verbs, routes, status codes)
- [ ] API versioning strategy in place
- [ ] Error responses follow standard format (Problem Details)
- [ ] Pagination for collection endpoints
- [ ] Request validation at boundaries
- [ ] Rate limiting implemented

## Configuration

- [ ] Typed configuration classes (Options pattern / Pydantic Settings)
- [ ] Secrets NOT in code or config files
- [ ] Secrets in secure store (Key Vault, Secrets Manager)
- [ ] Configuration validated at startup
- [ ] Environment-specific settings handled
- [ ] Feature flags for gradual rollout (if needed)

## Database Architecture

- [ ] Repository pattern abstracts data access
- [ ] Unit of Work for transaction management
- [ ] Connection pooling configured
- [ ] Read-only queries optimized (no tracking)
- [ ] N+1 queries avoided
- [ ] Migration strategy defined

## Security

- [ ] Authentication mechanism appropriate
- [ ] Authorization checks at boundaries
- [ ] CORS policy explicitly defined
- [ ] Input validation comprehensive
- [ ] SQL injection prevented (parameterized queries)
- [ ] Secrets rotation possible

## Concurrency Architecture

- [ ] Concurrency model fits workload (CPU-bound vs I/O-bound)
- [ ] Async patterns used consistently throughout
- [ ] Shared mutable state minimized or eliminated
- [ ] Thread-safe data structures where shared state required
- [ ] Backpressure handling for producer/consumer scenarios
- [ ] Work queues bounded to prevent memory exhaustion
- [ ] Graceful cancellation propagated through async chains
- [ ] Parallel processing throttled appropriately
- [ ] Actor/channel patterns for complex coordination (if applicable)
- [ ] Deadlock risks analyzed (lock ordering, async over sync)

## Testing

- [ ] Unit tests isolated (no external dependencies)
- [ ] Integration tests use test containers/fixtures
- [ ] API tests cover critical paths
- [ ] Test data factories/builders used
- [ ] Coverage on critical business logic

## Deployment & Operations

- [ ] Containerization ready (Dockerfile)
- [ ] CI/CD pipeline defined
- [ ] Environment parity (dev/staging/prod)
- [ ] Graceful shutdown handling
- [ ] Rolling deployment possible

---

## Finding Template

```
### [P1/P2/P3/P4] Finding Title
**Category**: [Category from above]
**Current State**: Description of what exists
**Impact**: Why this matters (risk/debt/limitation)
**Recommendation**: What to change
**Effort**: [S/M/L/XL]
```

## Priority Definitions

| Priority | Urgency | Action |
|----------|---------|--------|
| **P1 - Critical** | Security risk, data integrity, stability | This sprint |
| **P2 - High** | Significant tech debt, scalability blocker | Next 2-4 sprints |
| **P3 - Medium** | Maintainability, missing best practice | Backlog |
| **P4 - Low** | Minor improvement, optimization | When touching |

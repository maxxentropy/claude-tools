---
name: architecture-review
description: |
  Perform comprehensive architectural assessments of codebases.
  Use when asked about: architecture review, system design review, assess the architecture,
  review the codebase structure, architectural assessment, tech debt assessment,
  how is this system designed, evaluate the architecture, review project structure.
---

# Architecture Review Skill

Comprehensive architectural assessment for C# and Python codebases, analyzing system design, resilience patterns, observability, API design, and infrastructure concerns.

## Role in Architecture Workflow

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│ architecture-   │     │ software-       │     │ code-review     │
│ review skill    │ ──► │ architect agent │ ──► │ skill           │
│ (What exists?)  │     │ (What to build?)│     │ (Is it right?)  │
└─────────────────┘     └─────────────────┘     └─────────────────┘
     ASSESS                  DESIGN                 IMPLEMENT
       ▲                                                │
       └────────────────────────────────────────────────┘
                    (Continuous improvement)
```

This skill is the **ASSESS** phase. It evaluates existing architecture and produces findings that feed into design decisions.

## When to Use This Skill

| Situation | Use Architecture Review |
|-----------|------------------------|
| Starting on new codebase | Understand before changing |
| Planning major refactoring | Assess current state, plan target state |
| Periodic health check | Quarterly/bi-annual assessment |
| Performance/scaling concerns | Identify bottlenecks and design issues |
| Tech debt prioritization | Catalog and prioritize improvements |
| Onboarding | Generate architectural documentation |

**Not for**: Individual PR reviews, single-file changes, quick code checks. Use `code-review` skill instead.
**Not for**: Designing new systems or features. Use `software-architect` agent instead.

## Assessment Modes

### Quick Assessment (~15 min)
Fast health check focusing on critical concerns:
- Project structure and layering
- Obvious anti-patterns
- Security red flags
- Missing resilience patterns

```
"Give me a quick architectural health check of this codebase"
```

### Full Assessment (~45-60 min)
Comprehensive review of all categories:
- Complete checklist evaluation
- All reference patterns applied
- Detailed findings with recommendations
- Work items for P1/P2 issues

```
"Perform a full architectural assessment of this system"
```

### Focused Assessment
Deep dive into specific concern:
- Single category analysis
- Detailed pattern matching
- Specific recommendations

```
"Assess the resilience patterns in this codebase"
"Evaluate the observability setup"
"Review the API design architecture"
```

## Quick Start

```bash
# Full architectural assessment
# "Review the architecture of this codebase"

# Focused assessment
# "Assess the resilience patterns in this system"
# "Review the API design"
# "Evaluate the observability setup"

# Comparative
# "How well does this follow Clean Architecture?"
# "Does this codebase follow DDD patterns?"
```

## Review Process

### 1. Define Scope

Before starting, clarify:
- **Subsystem**: Entire codebase, specific service, or layer?
- **Quality Attributes**: What matters most? (scalability, reliability, security, maintainability)
- **Deployment Model**: Monolith, microservices, serverless?
- **Constraints**: Team size, timeline, existing tech debt?

### 2. Codebase Exploration

Systematically explore:

```bash
# Project structure
ls -la
find . -name "*.csproj" -o -name "*.sln" -o -name "pyproject.toml" -o -name "setup.py"

# Dependencies
cat *.csproj | grep PackageReference  # .NET
cat requirements.txt pyproject.toml    # Python

# Entry points
find . -name "Program.cs" -o -name "Startup.cs" -o -name "main.py" -o -name "app.py"

# Configuration
find . -name "appsettings*.json" -o -name "*.env*" -o -name "config*.py"
```

### 3. Apply Assessment Framework

Use the checklist: `checklists/architecture-checklist.md`

Reference documents:
- `references/architecture-patterns.md` - Core patterns (language-agnostic)
- `references/dotnet-architecture.md` - .NET specific patterns
- `references/python-architecture.md` - Python specific patterns

### 4. Assessment Categories

| Category | What to Assess |
|----------|----------------|
| **Structure** | Project organization, layering, dependency direction |
| **Domain Design** | Bounded contexts, aggregates, domain events |
| **Resilience** | Retry policies, circuit breakers, health checks, fallbacks |
| **Observability** | Logging infrastructure, metrics, distributed tracing |
| **API Design** | REST conventions, versioning, error responses |
| **Configuration** | Secrets management, environment handling, validation |
| **Data Access** | Repository patterns, connection management, migrations |
| **Security** | AuthN/AuthZ architecture, secrets, CORS, TLS |
| **Testing** | Test architecture, coverage strategy, test isolation |
| **Infrastructure** | Deployment, containerization, CI/CD |

### 5. Classify Findings

| Priority | Meaning | Action |
|----------|---------|--------|
| **P1 - Critical** | Security risk, data integrity, system stability | Immediate attention |
| **P2 - High** | Significant tech debt, scalability blocker | Plan for next sprint |
| **P3 - Medium** | Maintainability issue, missing best practice | Add to backlog |
| **P4 - Low** | Minor improvement, optimization opportunity | Consider when touching |

### 6. Create Work Items

For P1 and P2 findings, create tech debt or feature work items:

```bash
# Check platform first
python3 skills/detect-platform.py

# Create tech debt item
az boards work-item create --org "$ORG" --project "$PROJECT" \
  --type "Feature" --title "Architecture: [Finding Title]" \
  --description "<h2>Current State</h2><p>...</p><h2>Target State</h2><p>...</p><h2>Effort</h2><p>...</p>"
```

## Assessment Output Format

```markdown
# Architecture Assessment: [Project Name]

**Date**: YYYY-MM-DD
**Scope**: [What was reviewed]
**Quality Focus**: [Scalability | Reliability | Security | Maintainability]

## Executive Summary

[2-3 paragraph overview: current state, key strengths, primary concerns, recommendations]

## Architecture Overview

### Current Structure
[Describe the current architecture - layers, components, data flow]

### Technology Stack
| Layer | Technology |
|-------|------------|
| Presentation | ... |
| Application | ... |
| Domain | ... |
| Infrastructure | ... |
| Data | ... |

## Assessment by Category

### 1. Project Structure
**Rating**: [Strong | Adequate | Needs Improvement | Critical]

**Observations**:
- [What exists]

**Findings**:
#### [P2] Finding Title
**Current**: Description of current state
**Impact**: Why this matters
**Recommendation**: What to change
**Effort**: [S/M/L/XL]

### 2. Resilience Patterns
[Same format...]

### 3. Observability
[Same format...]

[Continue for each category...]

## Strengths
- [What's done well - reinforce good decisions]

## Priority Findings Summary

| Priority | Count | Categories |
|----------|-------|------------|
| P1 Critical | X | ... |
| P2 High | X | ... |
| P3 Medium | X | ... |
| P4 Low | X | ... |

## Recommended Roadmap

### Immediate (This Sprint)
- [ ] P1 items...

### Short-term (Next 2-4 Sprints)
- [ ] P2 items...

### Medium-term (Quarter)
- [ ] P3 items...

## Work Items Created
- AB#XXX: [Title]
- AB#XXX: [Title]
```

## Pattern Reference

### Core Patterns (Language-Agnostic)

**Clean Architecture**
- Dependencies point inward
- Domain has no external dependencies
- Use cases orchestrate domain
- Infrastructure implements interfaces

**Domain-Driven Design**
- Bounded contexts with clear boundaries
- Aggregates for consistency boundaries
- Domain events for cross-aggregate communication
- Repository pattern for persistence abstraction

**CQRS (Command Query Responsibility Segregation)**
- Separate read and write models
- Optimized query paths
- Event sourcing for audit/replay (optional)

### .NET Architecture Assessment

Focus areas:
- **Dependency Injection**: IServiceCollection setup, lifetimes, composition root
- **Configuration**: IOptions pattern, secrets management, environment handling
- **Resilience**: Polly policies, IHttpClientFactory, health checks
- **Observability**: Serilog/ILogger setup, OpenTelemetry, correlation IDs
- **API Design**: Controller patterns, model validation, Problem Details
- **EF Core**: DbContext lifetime, migrations, repository abstraction

### Python Architecture Assessment

Focus areas:
- **Project Structure**: src layout, packaging, dependency management
- **Dependency Injection**: Manual DI, dependency-injector, FastAPI Depends
- **Configuration**: Pydantic Settings, environment variables, secrets
- **Resilience**: tenacity, circuit breakers, health endpoints
- **Observability**: structlog, OpenTelemetry, Prometheus metrics
- **API Design**: FastAPI/Flask patterns, Pydantic models, error handling
- **Data Access**: SQLAlchemy patterns, Alembic migrations, session management

## Anti-Patterns to Identify

### Structural Anti-Patterns
- **Big Ball of Mud**: No clear structure, everything depends on everything
- **Distributed Monolith**: Microservices with tight coupling
- **Anemic Domain Model**: Logic in services, entities are just data bags
- **God Class**: Single class doing too much

### Resilience Anti-Patterns
- **No Timeouts**: External calls without timeout configuration
- **Retry Storm**: Aggressive retries without backoff
- **No Circuit Breaker**: Cascading failures from downstream issues
- **Missing Health Checks**: No way to know if service is healthy

### Observability Anti-Patterns
- **Log and Forget**: Logging without correlation or structure
- **Alert Fatigue**: Too many alerts, important ones ignored
- **No Metrics**: Flying blind on performance and usage
- **PII in Logs**: Sensitive data exposed in log files

### Configuration Anti-Patterns
- **Secrets in Code**: Credentials committed to repository
- **Environment Blindness**: Same config for all environments
- **No Validation**: Invalid config causes runtime errors
- **God Config**: Single config file with everything

## Remediation Workflow

After completing an assessment, guide remediation based on finding priority:

### P1 Critical Findings
Immediate action required:
1. **Document the risk**: Create urgent work item with full context
2. **Design fix**: Engage `software-architect` agent for remediation design
3. **Implement**: Apply fix with expedited code review
4. **Verify**: Re-assess the specific area

```
"I found a P1 security issue. Let me engage the software-architect agent to design the remediation."
```

### P2 High Findings
Plan for next sprint:
1. **Create ADR**: If architectural change, use `software-architect` agent to create ADR
2. **Create work items**: Break down into implementable tasks
3. **Prioritize**: Stack rank against other tech debt

```
"For this P2 finding about missing circuit breakers, let me create an ADR using the software-architect agent."
```

### P3/P4 Findings
Backlog management:
1. **Document in assessment report**: Include in recommendations
2. **Create backlog items**: Track for future sprints
3. **Address opportunistically**: Fix when touching related code

### Remediation Design Handoff

When findings require architectural changes, hand off to `software-architect` agent:

```markdown
## Remediation Request for software-architect

### Finding
[P-level] [Title from assessment]

### Current State
[Description of existing architecture]

### Impact
[Why this matters - from assessment]

### Constraints
- [Constraint 1: e.g., "Cannot change database schema"]
- [Constraint 2: e.g., "Must maintain backward compatibility"]

### Request
Design a solution that addresses this finding while respecting the constraints.
Include ADR if this is a significant architectural change.
```

## Integration with Other Skills

### software-architect Agent (Design Phase)
After assessment, use the agent to:
- Design remediation for P1/P2 findings
- Create ADRs for architectural changes
- Plan migration strategies
- Evaluate technology alternatives

```
"Use the software-architect agent to design a solution for the resilience gaps identified in the assessment"
```

### code-review Skill (Implementation Phase)
Architecture review identifies systemic issues; code review handles specific implementations:
- Architecture review finds: "No retry policy for external calls"
- Code review catches: "This specific HTTP call needs retry"

### docgen Skill (Documentation)
Use `docgen` skill to generate architecture documentation after assessment:
- System context diagrams
- Component diagrams
- Decision records (ADRs)

### azure-devops / github Skills (Work Tracking)
Create and track work items:
- Create epics for major architectural changes
- Create features for improvement initiatives
- Track tech debt items
- Link findings to work items

## Files Reference

| File | Purpose |
|------|---------|
| `SKILL.md` | This file - skill documentation |
| `references/architecture-patterns.md` | Core patterns (Clean Architecture, DDD, CQRS) |
| `references/dotnet-architecture.md` | .NET specific architectural patterns |
| `references/python-architecture.md` | Python specific architectural patterns |
| `checklists/architecture-checklist.md` | Quick assessment checklist |

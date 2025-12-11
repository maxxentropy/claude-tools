# WSR Entry Template

## Standard Entry Format

```markdown
## [Title - max 80 chars, action-oriented]

**Status:** [Completed | In Progress | Blocked | On Hold]
**Domain:** [Development | Architecture | Infrastructure | Security | Documentation | Support]
**Priority:** [High | Medium | Low]
**Timeline:** [Date range]

### Objective/Background
[2-3 sentences: why undertaken, context, alignment with goals]

### Solution/Approach
[Technical approach, key decisions, tools/patterns used]

### Business Impact
[Value delivered, user improvements, quantifiable metrics]

### Technical Impact
[Code quality, performance, security improvements]

### Risk Assessment & Mitigation
[Risks identified, mitigation strategies applied]

### Next Steps
[Follow-up actions, future phases, monitoring needs]

**Work Items:** AB#1234, AB#1235
**Key Commits:** `abc1234` - brief description
**Pipeline Status:** X runs, Y% success rate
```

## Status Definitions

- **Completed**: All work finished, tested, merged
- **In Progress**: Actively being worked on
- **Blocked**: Cannot proceed due to external dependency
- **On Hold**: Intentionally paused

## Domain Mapping

| Area/Type | Domain |
|-----------|--------|
| Feature development | Development |
| System design, refactoring | Architecture |
| CI/CD, deployment | Infrastructure |
| Auth, encryption | Security |
| Docs, guides | Documentation |
| Bug fixes, support | Support |
| Research, spikes | Investigation |

## Priority Guidelines

- **High**: Customer-facing, critical bugs, security, deadlines
- **Medium**: Planned sprint work, improvements
- **Low**: Tech debt, nice-to-haves

## Examples

### Quick Fix
```markdown
## Fixed Temperature Unit Conversion Bug

**Status:** Completed
**Domain:** Support
**Priority:** Medium
**Timeline:** December 5, 2024

### Objective/Background
Customer reported incorrect temperature readings when display set to Celsius.

### Solution/Approach
Added F-to-C conversion in TemperatureFormatter.cs with unit tests.

### Business Impact
Resolved customer issue, improved data accuracy for international deployments.

**Work Items:** AB#1250
**Key Commits:** `a1b2c3d` - Fix temperature unit conversion
```

### Major Feature
```markdown
## Serial Port Resilience Implementation

**Status:** Completed
**Domain:** Development
**Priority:** High
**Timeline:** December 1-7, 2024

### Objective/Background
Implemented retry and reconnection logic for serial port communication to address reliability issues in field deployments.

### Solution/Approach
- Polly-based retry with exponential backoff (100ms-30s)
- Connection health monitoring with heartbeat
- Circuit breaker pattern (opens after 5 failures)

### Business Impact
- Reduced support calls 60%
- Improved reliability from 94% to 99.5%

### Technical Impact
- Added Polly package for resilience patterns
- Increased test coverage to 87%

### Risk Assessment & Mitigation
- **Risk**: Retry storms during outages → Circuit breaker, backoff cap
- **Risk**: Data loss during reconnection → Ring buffer (1000 readings)

### Next Steps
- Monitor field metrics for 2 weeks
- Create operational runbook

**Work Items:** AB#1234, AB#1235, AB#1240
**Key Commits:** `a1b2c3d` - Retry policies, `e4f5g6h` - Circuit breaker
**Pipeline Status:** 12 runs, 92% success
```

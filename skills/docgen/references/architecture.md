# Architecture Documentation Template

## Required Context

Before writing, gather:
1. Output from `scan_dotnet.py` (structure, patterns, frameworks)
2. Key files: Program.cs/Startup.cs, DI configuration, domain entities
3. Existing README.md

## Document Structure

```markdown
# Architecture Overview

## Purpose
[One paragraph: what the system does, why it exists]

## High-Level Architecture

```mermaid
graph TB
    subgraph Presentation
        API[Web API]
    end
    subgraph Application
        Handlers[Command/Query Handlers]
    end
    subgraph Domain
        Entities[Entities]
    end
    subgraph Infrastructure
        DbContext[EF DbContext]
    end
    API --> Handlers --> Entities
    Handlers --> DbContext
```

## Project Structure

| Project | Purpose | Dependencies |
|---------|---------|--------------|
| ProjectName.Domain | Core business logic | None |
| ProjectName.Application | Use cases, interfaces | Domain |
| ProjectName.Infrastructure | Data access, external services | Application |
| ProjectName.Api | HTTP endpoints | Application |

## Key Patterns

### [Pattern Name]
[Explanation with code example from codebase]

## Technology Stack
- **Framework**: .NET 8
- **Database**: [from analysis]
- **Messaging**: [if applicable]
```

## Mermaid Templates

### Component Diagram
```mermaid
graph TB
    subgraph Presentation
        API[Web API]
    end
    subgraph Application
        Handlers[Command/Query Handlers]
        Services[Application Services]
    end
    subgraph Domain
        Entities[Entities]
        ValueObjects[Value Objects]
    end
    subgraph Infrastructure
        DbContext[EF DbContext]
        Repositories[Repositories]
    end
    API --> Handlers
    Handlers --> Services
    Services --> Entities
    Handlers --> Repositories
    Repositories --> DbContext
```

### Sequence Diagram
```mermaid
sequenceDiagram
    participant Client
    participant API
    participant Handler
    participant Repository
    participant Database
    
    Client->>API: POST /api/resource
    API->>Handler: Handle(Command)
    Handler->>Repository: Save(Entity)
    Repository->>Database: INSERT
    Database-->>Repository: Success
    Repository-->>Handler: Entity
    Handler-->>API: Result
    API-->>Client: 201 Created
```

## Quality Checklist

- [ ] Diagram reflects actual project structure
- [ ] All projects documented
- [ ] Patterns explained with real code examples
- [ ] Technology choices listed
- [ ] No placeholder text

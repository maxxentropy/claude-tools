# Architecture Patterns Reference

Core architectural patterns and principles applicable across all languages. For language-specific implementation details, see `dotnet-architecture.md` or `python-architecture.md`.

---

## 1. Layered Architecture

### Pattern Description

Organize code into horizontal layers with clear responsibilities and dependencies flowing downward.

```
┌─────────────────────────────┐
│      Presentation Layer     │  UI, API Controllers, CLI
├─────────────────────────────┤
│      Application Layer      │  Use Cases, Orchestration
├─────────────────────────────┤
│        Domain Layer         │  Business Logic, Entities
├─────────────────────────────┤
│     Infrastructure Layer    │  Database, External Services
└─────────────────────────────┘
```

### Key Principles

- **Dependency Rule**: Upper layers depend on lower layers, never reverse
- **Abstraction**: Each layer hides its implementation details
- **Single Responsibility**: Each layer has one reason to change

### Good Signs
- Clear folder/project structure matching layers
- Interfaces defined at layer boundaries
- No direct database calls from presentation layer
- Business logic contained in domain layer

### Warning Signs
- Circular dependencies between layers
- Business logic in controllers/views
- Infrastructure concerns in domain layer
- "Leaky abstractions" exposing implementation details

---

## 2. Clean Architecture

### Pattern Description

A refinement of layered architecture with strict dependency inversion. The domain is at the center, with dependencies pointing inward.

```
┌───────────────────────────────────────┐
│            Infrastructure             │
│  ┌───────────────────────────────┐   │
│  │         Application           │   │
│  │  ┌───────────────────────┐   │   │
│  │  │       Domain          │   │   │
│  │  │  Entities, Services   │   │   │
│  │  └───────────────────────┘   │   │
│  │   Use Cases, Interfaces      │   │
│  └───────────────────────────────┘   │
│   Controllers, Gateways, Presenters  │
└───────────────────────────────────────┘
```

### Key Principles

- **Independence**: Domain knows nothing about frameworks, databases, UI
- **Testability**: Business rules can be tested without external elements
- **Flexibility**: External components can be swapped without domain changes

### Layer Responsibilities

| Layer | Responsibility | Changes When |
|-------|---------------|--------------|
| **Entities** | Enterprise business rules | Business fundamentals change |
| **Use Cases** | Application business rules | Application behavior changes |
| **Interface Adapters** | Convert data between layers | External interface changes |
| **Frameworks** | Technical implementation | Technology choices change |

### Good Signs
- Domain project has zero external dependencies
- Use cases define input/output boundaries
- Repository interfaces in domain, implementations in infrastructure
- Controllers are thin, delegating to use cases

### Warning Signs
- DbContext or ORM types in domain entities
- Framework attributes on domain objects
- Use cases directly accessing databases
- Business logic in controllers

---

## 3. Domain-Driven Design (DDD)

### Strategic Patterns

#### Bounded Contexts

Explicit boundaries within which a domain model applies consistently.

```
┌─────────────────┐    ┌─────────────────┐
│   Sales Context │    │ Inventory Ctxt  │
│                 │    │                 │
│  Customer       │    │  Product        │
│  Order          │◄──►│  Stock          │
│  LineItem       │    │  Warehouse      │
└─────────────────┘    └─────────────────┘
        │                      │
        ▼                      ▼
┌─────────────────────────────────────────┐
│           Shared Kernel                 │
│   (Carefully managed shared concepts)   │
└─────────────────────────────────────────┘
```

**Good Signs**:
- Clear module/service boundaries
- Each context owns its data
- Integration via events or APIs
- Ubiquitous language within each context

**Warning Signs**:
- One model for everything
- Shared database tables across contexts
- Tight coupling between modules
- Inconsistent terminology

#### Context Mapping

Relationships between bounded contexts:

| Pattern | Description | When to Use |
|---------|-------------|-------------|
| **Shared Kernel** | Shared code/model | Tight collaboration, small shared area |
| **Customer/Supplier** | Upstream/downstream | Clear dependency direction |
| **Conformist** | Downstream accepts upstream model | No influence over upstream |
| **Anti-Corruption Layer** | Translation layer | Protect from external model |
| **Open Host Service** | Published API/protocol | Many consumers |
| **Published Language** | Shared interchange format | Integration standard |

### Tactical Patterns

#### Entities

Objects with identity that persists over time.

```
Good: Identity matters, lifecycle tracking needed
- User, Order, Product, Account

Bad: Using entities for everything
- Money, Address, DateRange (should be Value Objects)
```

#### Value Objects

Immutable objects defined by their attributes, not identity.

```
Good: Immutable, equality by value
- Money(100, USD)
- Address(street, city, zip)
- DateRange(start, end)

Bad: Mutable value objects
- money.Amount = 200  // Should create new instance
```

#### Aggregates

Cluster of entities and value objects with a root entity.

```
Order (Aggregate Root)
├── LineItems (Entity, only accessed via Order)
├── ShippingAddress (Value Object)
└── PaymentDetails (Value Object)

Rules:
- External references only to root
- Root enforces invariants
- Transactions respect aggregate boundaries
```

**Sizing Aggregates**:
- Prefer smaller aggregates
- Include only what's needed for invariants
- Reference other aggregates by ID, not object reference
- Use domain events for cross-aggregate operations

#### Domain Events

Record something significant that happened in the domain.

```
OrderPlaced { OrderId, CustomerId, Items, Total, Timestamp }
PaymentReceived { PaymentId, OrderId, Amount, Method }
InventoryReserved { OrderId, Items, WarehouseId }
```

**Good Signs**:
- Named in past tense (something happened)
- Immutable
- Contain all relevant data
- Enable loose coupling

**Warning Signs**:
- Events triggering synchronous operations
- Events missing data, requiring lookups
- Circular event chains
- Events as RPC disguised

#### Repository Pattern

Abstract persistence of aggregates.

```
// Interface in Domain
interface IOrderRepository {
    Order GetById(OrderId id);
    void Save(Order order);
}

// Implementation in Infrastructure
class SqlOrderRepository : IOrderRepository {
    // EF Core / SQLAlchemy implementation
}
```

---

## 4. CQRS (Command Query Responsibility Segregation)

### Pattern Description

Separate read and write models for different optimization paths.

```
┌─────────────┐         ┌─────────────────────┐
│   Client    │         │    Read Model       │
│             │───GET──►│  (Denormalized,     │
│             │         │   query-optimized)  │
│             │         └─────────────────────┘
│             │
│             │         ┌─────────────────────┐
│             │──POST──►│   Write Model       │
│             │         │  (Domain model,     │
│             │         │   normalized)       │
└─────────────┘         └─────────────────────┘
```

### When to Use

**Good Fit**:
- Read/write ratio heavily skewed (10:1 or more)
- Complex domain logic for writes
- Different scaling needs for reads vs writes
- Reporting requirements differ from transactional

**Poor Fit**:
- Simple CRUD operations
- Small scale, low complexity
- Team unfamiliar with pattern
- No significant read/write asymmetry

### Implementation Levels

| Level | Complexity | Description |
|-------|------------|-------------|
| **1. Separate Methods** | Low | Different service methods for read/write |
| **2. Separate Models** | Medium | Different DTOs/projections for queries |
| **3. Separate Data Stores** | High | Different databases for read/write |

### With Event Sourcing

```
Command → Domain → Event → Event Store
                      │
                      ├──► Projection 1 (SQL for queries)
                      ├──► Projection 2 (Search index)
                      └──► Projection 3 (Analytics)
```

**Benefits**:
- Complete audit trail
- Temporal queries ("state at time X")
- Rebuild projections from events
- Debug by replaying events

**Challenges**:
- Eventual consistency
- Event versioning
- Projection rebuild time
- Increased complexity

---

## 5. Event-Driven Architecture

### Pattern Description

Components communicate through asynchronous events rather than direct calls.

```
┌──────────┐     Event      ┌──────────┐
│ Service  │───Published───►│  Event   │
│    A     │                │  Broker  │
└──────────┘                └────┬─────┘
                                 │
                    ┌────────────┼────────────┐
                    ▼            ▼            ▼
               ┌────────┐  ┌────────┐   ┌────────┐
               │Service │  │Service │   │Service │
               │   B    │  │   C    │   │   D    │
               └────────┘  └────────┘   └────────┘
```

### Event Types

| Type | Purpose | Example |
|------|---------|---------|
| **Domain Event** | Something happened in domain | OrderPlaced |
| **Integration Event** | Cross-service communication | OrderReadyForShipment |
| **Notification Event** | Inform without expecting action | UserLoggedIn |
| **Event-Carried State Transfer** | Event contains full state | CustomerUpdated { full data } |

### Patterns

#### Choreography

Services react to events independently, no central coordinator.

```
Order Service ──OrderPlaced──► Payment Service
                    │
                    └──────────► Inventory Service
                    │
                    └──────────► Notification Service
```

**Pros**: Loose coupling, services evolve independently
**Cons**: Hard to understand flow, distributed debugging

#### Orchestration

Central coordinator manages the workflow.

```
                    ┌─────────────┐
                    │ Order Saga  │
                    │ Coordinator │
                    └──────┬──────┘
                           │
          ┌────────────────┼────────────────┐
          ▼                ▼                ▼
     ┌─────────┐     ┌─────────┐      ┌─────────┐
     │ Payment │     │Inventory│      │Shipping │
     └─────────┘     └─────────┘      └─────────┘
```

**Pros**: Clear flow, easier debugging, explicit failure handling
**Cons**: Central point of coupling, coordinator complexity

### Saga Pattern

Manage distributed transactions through compensating actions.

```
OrderSaga:
1. Create Order (pending)
2. Reserve Inventory
   - If fails: Cancel Order
3. Process Payment
   - If fails: Release Inventory, Cancel Order
4. Ship Order
   - If fails: Refund Payment, Release Inventory, Cancel Order
5. Complete Order
```

---

## 6. Microservices Patterns

### Service Decomposition

#### By Business Capability

```
E-commerce System:
├── Catalog Service (product information)
├── Inventory Service (stock management)
├── Order Service (order processing)
├── Payment Service (payment processing)
├── Shipping Service (logistics)
└── Customer Service (user management)
```

#### By Subdomain (DDD)

```
Core Domain: Order Processing (competitive advantage)
Supporting: Inventory, Shipping (necessary but not differentiating)
Generic: Authentication, Notifications (commodity)
```

### Communication Patterns

| Pattern | Use When | Considerations |
|---------|----------|----------------|
| **Sync REST/gRPC** | Need immediate response | Tight coupling, cascading failures |
| **Async Messaging** | Fire-and-forget, eventual consistency | Complexity, message ordering |
| **Event Streaming** | Real-time, high volume | Infrastructure cost, exactly-once semantics |

### Data Patterns

#### Database per Service

Each service owns its data, no shared databases.

**Benefits**:
- Services can evolve independently
- Right database for the job
- No schema coupling

**Challenges**:
- Cross-service queries
- Data consistency
- Data duplication

#### API Composition

Aggregate data from multiple services at query time.

```
┌───────────────┐
│ API Gateway / │──────┬──────────┬──────────┐
│  Composition  │      │          │          │
└───────────────┘      ▼          ▼          ▼
              ┌─────────┐  ┌─────────┐  ┌─────────┐
              │ Orders  │  │ Products│  │Customers│
              └─────────┘  └─────────┘  └─────────┘
```

### Resilience Patterns

See language-specific references for implementation details:
- Circuit Breaker
- Bulkhead
- Retry with Backoff
- Timeout
- Fallback

---

## 7. Anti-Patterns to Avoid

### Distributed Monolith

**Symptoms**:
- Services must deploy together
- One service change breaks others
- Shared database between services
- Synchronous call chains

**Resolution**:
- Define clear service boundaries
- Use async communication
- Accept eventual consistency
- Database per service

### Big Ball of Mud

**Symptoms**:
- No clear structure
- Any component can depend on any other
- Fear of changes ("don't touch that")
- Long build times, large deployments

**Resolution**:
- Identify bounded contexts
- Introduce module boundaries
- Strangler fig migration
- Automated architecture tests

### Anemic Domain Model

**Symptoms**:
- Entities are pure data structures
- All logic in service classes
- Getters/setters everywhere
- No encapsulation

**Resolution**:
- Push behavior into entities
- Use value objects
- Enforce invariants in aggregates
- Rich domain model

### Golden Hammer

**Symptoms**:
- Same architecture for all problems
- "We always use microservices"
- Technology choice drives design
- Over-engineering simple problems

**Resolution**:
- Start simple, evolve as needed
- Architecture decisions based on context
- Evaluate trade-offs honestly
- "Boring" technology is often right

---

## Assessment Questions

Use these to evaluate an architecture:

### Structure
1. Can you explain the architecture in 2 minutes?
2. Where does business logic live?
3. How do components communicate?
4. What are the deployment units?

### Quality Attributes
1. How does the system handle 10x load?
2. What happens when [component X] fails?
3. How long to add a new feature?
4. How do you know the system is healthy?

### Trade-offs
1. What did you optimize for?
2. What did you sacrifice?
3. What would you do differently today?
4. What's the biggest technical debt?

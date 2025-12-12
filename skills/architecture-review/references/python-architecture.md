# Python Architecture Reference

Python-specific architectural patterns, infrastructure concerns, and system-level best practices. For language-agnostic patterns, see `architecture-patterns.md`.

---

## Table of Contents
1. [Project Structure](#1-project-structure)
2. [Dependency Injection](#2-dependency-injection)
3. [Resilience Patterns](#3-resilience-patterns)
4. [Observability](#4-observability)
5. [API Design (FastAPI)](#5-api-design-fastapi)
6. [Configuration Management](#6-configuration-management)
7. [Database Architecture](#7-database-architecture)
8. [Background Tasks](#8-background-tasks)
9. [Security Architecture](#9-security-architecture)
10. [Testing Architecture](#10-testing-architecture)
11. [Concurrency Architecture](#11-concurrency-architecture)

---

## 1. Project Structure

### Modern Python Project Layout

```
my_project/
├── src/
│   └── my_project/
│       ├── __init__.py
│       ├── main.py              # Application entry point
│       ├── config.py            # Settings management
│       │
│       ├── domain/              # Business logic (no external deps)
│       │   ├── __init__.py
│       │   ├── entities/
│       │   ├── value_objects/
│       │   ├── events/
│       │   └── interfaces/      # Abstract repositories
│       │
│       ├── application/         # Use cases
│       │   ├── __init__.py
│       │   ├── commands/
│       │   ├── queries/
│       │   └── services/
│       │
│       ├── infrastructure/      # External concerns
│       │   ├── __init__.py
│       │   ├── database/
│       │   ├── external_services/
│       │   └── messaging/
│       │
│       └── api/                 # Presentation
│           ├── __init__.py
│           ├── routes/
│           ├── dependencies.py
│           └── middleware.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
│
├── pyproject.toml
├── Dockerfile
└── docker-compose.yml
```

### pyproject.toml Configuration

```toml
[project]
name = "my-project"
version = "1.0.0"
requires-python = ">=3.11"
dependencies = [
    "fastapi>=0.100.0",
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "sqlalchemy>=2.0.0",
    "structlog>=23.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=7.0.0",
    "pytest-asyncio>=0.21.0",
    "pytest-cov>=4.0.0",
    "mypy>=1.0.0",
    "ruff>=0.1.0",
]

[tool.ruff]
line-length = 88
select = ["E", "F", "I", "UP", "B", "SIM"]

[tool.mypy]
python_version = "3.11"
strict = true

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]
```

### Dependency Rules

```
api → application → domain
        ↓
  infrastructure → domain
```

**Domain**: Pure Python, no external dependencies
**Application**: Domain + lightweight libs (pydantic for DTOs)
**Infrastructure**: SQLAlchemy, httpx, redis, etc.
**API**: FastAPI, routes, middleware

---

## 2. Dependency Injection

### FastAPI Dependency Injection

```python
# GOOD: Dependencies with proper scoping
from fastapi import Depends, FastAPI
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Annotated, AsyncGenerator

app = FastAPI()

# Database session dependency
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise

# Repository dependency
async def get_order_repository(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> OrderRepository:
    return SqlOrderRepository(db)

# Service dependency (composed)
async def get_order_service(
    repo: Annotated[OrderRepository, Depends(get_order_repository)],
    events: Annotated[EventPublisher, Depends(get_event_publisher)]
) -> OrderService:
    return OrderService(repo, events)

# Route using dependencies
@app.post("/orders")
async def create_order(
    request: CreateOrderRequest,
    service: Annotated[OrderService, Depends(get_order_service)]
) -> OrderResponse:
    return await service.create_order(request)
```

### Dependency-Injector Library

```python
# GOOD: For complex applications
from dependency_injector import containers, providers

class Container(containers.DeclarativeContainer):
    config = providers.Configuration()

    # Infrastructure
    db_engine = providers.Singleton(
        create_async_engine,
        config.database.url,
    )

    session_factory = providers.Factory(
        async_sessionmaker,
        db_engine,
    )

    # Repositories
    order_repository = providers.Factory(
        SqlOrderRepository,
        session_factory=session_factory,
    )

    # Services
    order_service = providers.Factory(
        OrderService,
        repository=order_repository,
        event_publisher=event_publisher,
    )

# Wire to FastAPI
container = Container()
container.config.from_pydantic(Settings())

@app.post("/orders")
@inject
async def create_order(
    request: CreateOrderRequest,
    service: OrderService = Depends(Provide[Container.order_service])
) -> OrderResponse:
    return await service.create_order(request)
```

---

## 3. Resilience Patterns

### Retry with Tenacity

```python
# GOOD: Retry with exponential backoff
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    before_sleep_log,
)
import structlog

logger = structlog.get_logger()

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.ConnectError)),
    before_sleep=before_sleep_log(logger, structlog.stdlib.INFO),
)
async def fetch_external_data(url: str) -> dict:
    async with httpx.AsyncClient(timeout=10.0) as client:
        response = await client.get(url)
        response.raise_for_status()
        return response.json()

# GOOD: Class-based retry configuration
class RetryConfig:
    TRANSIENT_ERRORS = (
        httpx.TimeoutException,
        httpx.ConnectError,
        httpx.ReadTimeout,
    )

    @staticmethod
    def standard():
        return retry(
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception_type(RetryConfig.TRANSIENT_ERRORS),
        )

    @staticmethod
    def aggressive():
        return retry(
            stop=stop_after_attempt(5),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=30),
            retry=retry_if_exception_type(RetryConfig.TRANSIENT_ERRORS),
        )
```

### Circuit Breaker

```python
# GOOD: Circuit breaker pattern
from circuitbreaker import circuit
import httpx

class PaymentGateway:
    @circuit(failure_threshold=5, recovery_timeout=30)
    async def process_payment(self, payment: Payment) -> PaymentResult:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(
                f"{self.base_url}/payments",
                json=payment.model_dump()
            )
            response.raise_for_status()
            return PaymentResult(**response.json())

# GOOD: Manual circuit breaker with state
from enum import Enum
from datetime import datetime, timedelta

class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"

class CircuitBreaker:
    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout: timedelta = timedelta(seconds=30)
    ):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time: datetime | None = None

    async def call(self, func, *args, **kwargs):
        if self.state == CircuitState.OPEN:
            if self._should_attempt_reset():
                self.state = CircuitState.HALF_OPEN
            else:
                raise CircuitOpenError("Circuit is open")

        try:
            result = await func(*args, **kwargs)
            self._on_success()
            return result
        except Exception as e:
            self._on_failure()
            raise
```

### Timeout Handling

```python
# GOOD: Async timeout with asyncio
import asyncio

async def fetch_with_timeout(url: str, timeout: float = 10.0) -> dict:
    async with asyncio.timeout(timeout):
        async with httpx.AsyncClient() as client:
            response = await client.get(url)
            return response.json()

# GOOD: Graceful timeout handling
async def fetch_with_fallback(url: str) -> dict:
    try:
        async with asyncio.timeout(5.0):
            return await fetch_from_primary(url)
    except asyncio.TimeoutError:
        logger.warning("Primary timed out, using fallback")
        return await fetch_from_cache(url)
```

### Health Checks

```python
# GOOD: Health check endpoints
from fastapi import FastAPI, status
from pydantic import BaseModel

class HealthStatus(BaseModel):
    status: str
    checks: dict[str, str]

@app.get("/health/live", status_code=status.HTTP_200_OK)
async def liveness() -> dict:
    """Kubernetes liveness probe - is the process running?"""
    return {"status": "alive"}

@app.get("/health/ready")
async def readiness(
    db: AsyncSession = Depends(get_db)
) -> HealthStatus:
    """Kubernetes readiness probe - can we handle traffic?"""
    checks = {}

    # Check database
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "healthy"
    except Exception as e:
        checks["database"] = f"unhealthy: {e}"

    # Check Redis
    try:
        await redis.ping()
        checks["redis"] = "healthy"
    except Exception as e:
        checks["redis"] = f"unhealthy: {e}"

    all_healthy = all(v == "healthy" for v in checks.values())
    return HealthStatus(
        status="healthy" if all_healthy else "unhealthy",
        checks=checks
    )
```

---

## 4. Observability

### Structured Logging with structlog

```python
# GOOD: structlog configuration
import structlog
from structlog.stdlib import filter_by_level

def configure_logging(json_format: bool = True):
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
    ]

    if json_format:
        processors.append(structlog.processors.JSONRenderer())
    else:
        processors.append(structlog.dev.ConsoleRenderer())

    structlog.configure(
        processors=processors,
        wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=True,
    )

# Usage
logger = structlog.get_logger()

async def process_order(order_id: int) -> None:
    log = logger.bind(order_id=order_id)
    log.info("Processing order")

    try:
        result = await do_processing()
        log.info("Order processed", result=result)
    except Exception as e:
        log.error("Order processing failed", error=str(e))
        raise
```

### Correlation IDs

```python
# GOOD: Correlation ID middleware
from contextvars import ContextVar
import uuid

correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")

class CorrelationIdMiddleware:
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        correlation_id = headers.get(
            b"x-correlation-id",
            str(uuid.uuid4()).encode()
        ).decode()

        correlation_id_var.set(correlation_id)
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        async def send_with_correlation(message):
            if message["type"] == "http.response.start":
                headers = list(message.get("headers", []))
                headers.append((b"x-correlation-id", correlation_id.encode()))
                message["headers"] = headers
            await send(message)

        await self.app(scope, receive, send_with_correlation)

app.add_middleware(CorrelationIdMiddleware)
```

### Metrics with Prometheus

```python
# GOOD: Prometheus metrics
from prometheus_client import Counter, Histogram, Gauge, generate_latest
from starlette.responses import Response

# Define metrics
REQUEST_COUNT = Counter(
    "http_requests_total",
    "Total HTTP requests",
    ["method", "endpoint", "status"]
)

REQUEST_LATENCY = Histogram(
    "http_request_duration_seconds",
    "HTTP request latency",
    ["method", "endpoint"],
    buckets=[0.01, 0.05, 0.1, 0.5, 1.0, 5.0]
)

ORDERS_IN_PROGRESS = Gauge(
    "orders_in_progress",
    "Number of orders currently being processed"
)

# Middleware to collect metrics
class MetricsMiddleware:
    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        start_time = time.perf_counter()
        status_code = 500

        async def send_wrapper(message):
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration = time.perf_counter() - start_time
            endpoint = scope.get("path", "unknown")
            method = scope.get("method", "unknown")

            REQUEST_COUNT.labels(method, endpoint, status_code).inc()
            REQUEST_LATENCY.labels(method, endpoint).observe(duration)

# Expose metrics endpoint
@app.get("/metrics")
async def metrics():
    return Response(
        content=generate_latest(),
        media_type="text/plain"
    )
```

### OpenTelemetry Integration

```python
# GOOD: OpenTelemetry setup
from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

def configure_tracing(service_name: str, otlp_endpoint: str):
    provider = TracerProvider()
    processor = BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
    provider.add_span_processor(processor)
    trace.set_tracer_provider(provider)

    # Auto-instrument
    FastAPIInstrumentor.instrument_app(app)
    HTTPXClientInstrumentor().instrument()
    SQLAlchemyInstrumentor().instrument(engine=engine)

# Custom spans
tracer = trace.get_tracer(__name__)

async def process_order(order_id: int) -> Order:
    with tracer.start_as_current_span("process_order") as span:
        span.set_attribute("order.id", order_id)

        order = await fetch_order(order_id)
        span.set_attribute("order.total", float(order.total))

        with tracer.start_as_current_span("validate_inventory"):
            await validate_inventory(order)

        with tracer.start_as_current_span("process_payment"):
            await process_payment(order)

        return order
```

---

## 5. API Design (FastAPI)

### Router Organization

```python
# GOOD: Organized routers
from fastapi import APIRouter, FastAPI

# api/routes/orders.py
router = APIRouter(prefix="/orders", tags=["orders"])

@router.get("", response_model=list[OrderResponse])
async def list_orders(
    skip: int = 0,
    limit: int = Query(default=20, le=100),
    service: OrderService = Depends(get_order_service)
) -> list[OrderResponse]:
    return await service.list_orders(skip=skip, limit=limit)

@router.get("/{order_id}", response_model=OrderResponse)
async def get_order(
    order_id: int,
    service: OrderService = Depends(get_order_service)
) -> OrderResponse:
    order = await service.get_order(order_id)
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

# main.py
app = FastAPI(title="Order Service", version="1.0.0")
app.include_router(orders.router, prefix="/api/v1")
app.include_router(customers.router, prefix="/api/v1")
```

### Error Handling

```python
# GOOD: Consistent error responses
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

class ErrorResponse(BaseModel):
    error: str
    detail: str | None = None
    code: str | None = None

class DomainException(Exception):
    def __init__(self, message: str, code: str | None = None):
        self.message = message
        self.code = code

class NotFoundException(DomainException):
    pass

class ValidationError(DomainException):
    pass

# Exception handlers
@app.exception_handler(NotFoundException)
async def not_found_handler(request: Request, exc: NotFoundException):
    return JSONResponse(
        status_code=404,
        content=ErrorResponse(
            error="Not Found",
            detail=exc.message,
            code=exc.code
        ).model_dump()
    )

@app.exception_handler(ValidationError)
async def validation_handler(request: Request, exc: ValidationError):
    return JSONResponse(
        status_code=400,
        content=ErrorResponse(
            error="Validation Error",
            detail=exc.message,
            code=exc.code
        ).model_dump()
    )

@app.exception_handler(Exception)
async def generic_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        status_code=500,
        content=ErrorResponse(error="Internal Server Error").model_dump()
    )
```

### Request/Response Models

```python
# GOOD: Pydantic models for validation
from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from enum import Enum

class OrderStatus(str, Enum):
    PENDING = "pending"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"

class CreateOrderRequest(BaseModel):
    customer_id: int = Field(..., gt=0)
    items: list[OrderItemRequest] = Field(..., min_length=1)
    notes: str | None = Field(default=None, max_length=500)

    @field_validator("items")
    @classmethod
    def validate_items(cls, v):
        if len(v) > 100:
            raise ValueError("Maximum 100 items per order")
        return v

class OrderResponse(BaseModel):
    id: int
    status: OrderStatus
    total: Decimal
    created_at: datetime
    items: list[OrderItemResponse]

    model_config = ConfigDict(from_attributes=True)

# Pagination
class PaginatedResponse(BaseModel, Generic[T]):
    items: list[T]
    total: int
    page: int
    page_size: int
    has_more: bool
```

### API Versioning

```python
# GOOD: URL-based versioning
v1_router = APIRouter(prefix="/api/v1")
v2_router = APIRouter(prefix="/api/v2")

# V1 - Original
@v1_router.get("/orders/{order_id}")
async def get_order_v1(order_id: int) -> OrderResponseV1:
    ...

# V2 - Breaking changes
@v2_router.get("/orders/{order_id}")
async def get_order_v2(order_id: int) -> OrderResponseV2:
    ...

app.include_router(v1_router)
app.include_router(v2_router)

# GOOD: Header-based versioning (alternative)
@app.get("/orders/{order_id}")
async def get_order(
    order_id: int,
    api_version: str = Header(default="1.0", alias="X-API-Version")
):
    if api_version.startswith("2."):
        return await get_order_v2_impl(order_id)
    return await get_order_v1_impl(order_id)
```

---

## 6. Configuration Management

### Pydantic Settings

```python
# GOOD: Typed, validated configuration
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field, PostgresDsn, field_validator
from functools import lru_cache

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        env_nested_delimiter="__",
        extra="ignore"
    )

    # Application
    app_name: str = "MyService"
    debug: bool = False
    environment: str = Field(default="development", pattern="^(development|staging|production)$")

    # Database
    database_url: PostgresDsn
    database_pool_size: int = Field(default=5, ge=1, le=100)

    # External Services
    payment_api_url: str
    payment_api_key: str = Field(..., min_length=32)
    payment_timeout_seconds: float = 10.0

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    @field_validator("debug")
    @classmethod
    def disable_debug_in_production(cls, v, info):
        if v and info.data.get("environment") == "production":
            raise ValueError("Debug mode not allowed in production")
        return v

@lru_cache
def get_settings() -> Settings:
    return Settings()

# Usage in FastAPI
@app.on_event("startup")
async def startup():
    settings = get_settings()
    logger.info("Starting", environment=settings.environment)
```

### Secret Management

```python
# GOOD: Secrets from environment
class Settings(BaseSettings):
    # These come from environment, never from files
    database_password: str = Field(..., alias="DATABASE_PASSWORD")
    api_secret_key: str = Field(..., alias="API_SECRET_KEY")
    jwt_secret: str = Field(..., alias="JWT_SECRET")

# GOOD: AWS Secrets Manager integration
import boto3
import json

def get_secret(secret_name: str) -> dict:
    client = boto3.client("secretsmanager")
    response = client.get_secret_value(SecretId=secret_name)
    return json.loads(response["SecretString"])

# GOOD: HashiCorp Vault integration
import hvac

def get_vault_secret(path: str) -> dict:
    client = hvac.Client(url=os.environ["VAULT_ADDR"])
    client.token = os.environ["VAULT_TOKEN"]
    secret = client.secrets.kv.v2.read_secret_version(path=path)
    return secret["data"]["data"]

# BAD: Never commit secrets
settings = Settings(
    database_password="secret123",  # NEVER!
    api_key="sk-..."  # NEVER!
)
```

---

## 7. Database Architecture

### SQLAlchemy 2.0 Setup

```python
# GOOD: Async SQLAlchemy configuration
from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession
)
from sqlalchemy.orm import DeclarativeBase

class Base(DeclarativeBase):
    pass

engine = create_async_engine(
    settings.database_url,
    pool_size=settings.database_pool_size,
    max_overflow=10,
    pool_pre_ping=True,
    echo=settings.debug,
)

async_session_maker = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# Context manager for sessions
@asynccontextmanager
async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
```

### Repository Pattern

```python
# GOOD: Repository abstraction
from abc import ABC, abstractmethod
from typing import Generic, TypeVar

T = TypeVar("T")

class Repository(ABC, Generic[T]):
    @abstractmethod
    async def get_by_id(self, id: int) -> T | None:
        pass

    @abstractmethod
    async def add(self, entity: T) -> T:
        pass

    @abstractmethod
    async def update(self, entity: T) -> T:
        pass

    @abstractmethod
    async def delete(self, entity: T) -> None:
        pass

# Implementation
class SqlOrderRepository(Repository[Order]):
    def __init__(self, session: AsyncSession):
        self._session = session

    async def get_by_id(self, id: int) -> Order | None:
        return await self._session.get(Order, id)

    async def get_with_items(self, id: int) -> Order | None:
        stmt = (
            select(Order)
            .options(selectinload(Order.items))
            .where(Order.id == id)
        )
        result = await self._session.execute(stmt)
        return result.scalar_one_or_none()

    async def add(self, entity: Order) -> Order:
        self._session.add(entity)
        await self._session.flush()
        return entity
```

### Alembic Migrations

```python
# alembic/env.py
from logging.config import fileConfig
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

config = context.config
target_metadata = Base.metadata

def run_migrations_offline():
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
    )
    with context.begin_transaction():
        context.run_migrations()

async def run_migrations_online():
    connectable = create_async_engine(
        config.get_main_option("sqlalchemy.url"),
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()
```

---

## 8. Background Tasks

### FastAPI Background Tasks

```python
# GOOD: Simple background tasks
from fastapi import BackgroundTasks

@app.post("/orders")
async def create_order(
    request: CreateOrderRequest,
    background_tasks: BackgroundTasks
) -> OrderResponse:
    order = await order_service.create(request)

    # Non-blocking follow-up tasks
    background_tasks.add_task(send_confirmation_email, order.id)
    background_tasks.add_task(update_inventory, order.items)

    return order
```

### Celery for Heavy Tasks

```python
# GOOD: Celery configuration
from celery import Celery

celery_app = Celery(
    "tasks",
    broker=settings.redis_url,
    backend=settings.redis_url,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    task_track_started=True,
    task_time_limit=300,
)

# Task definition
@celery_app.task(bind=True, max_retries=3)
def process_order_task(self, order_id: int):
    try:
        process_order_sync(order_id)
    except TransientError as e:
        raise self.retry(exc=e, countdown=60)

# Enqueue from FastAPI
@app.post("/orders/{order_id}/process")
async def start_processing(order_id: int):
    task = process_order_task.delay(order_id)
    return {"task_id": task.id}
```

### ARQ for Async Tasks

```python
# GOOD: ARQ for async background tasks
from arq import create_pool
from arq.connections import RedisSettings

async def process_order(ctx, order_id: int):
    """Background task that runs async."""
    async with get_session() as session:
        order = await get_order(session, order_id)
        await process(order)

class WorkerSettings:
    functions = [process_order]
    redis_settings = RedisSettings.from_dsn(settings.redis_url)

# Enqueue
@app.post("/orders/{order_id}/process")
async def start_processing(order_id: int):
    redis = await create_pool(RedisSettings.from_dsn(settings.redis_url))
    job = await redis.enqueue_job("process_order", order_id)
    return {"job_id": job.job_id}
```

---

## 9. Security Architecture

### JWT Authentication

```python
# GOOD: JWT authentication
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="token")

async def get_current_user(
    token: str = Depends(oauth2_scheme)
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        payload = jwt.decode(
            token,
            settings.jwt_secret,
            algorithms=["HS256"]
        )
        user_id: int = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await user_service.get_by_id(user_id)
    if user is None:
        raise credentials_exception
    return user

# Protected route
@app.get("/me")
async def get_me(user: User = Depends(get_current_user)) -> UserResponse:
    return user
```

### Permission-Based Authorization

```python
# GOOD: Permission checking
from enum import Enum
from functools import wraps

class Permission(str, Enum):
    READ_ORDERS = "orders:read"
    WRITE_ORDERS = "orders:write"
    ADMIN = "admin"

def require_permissions(*permissions: Permission):
    def decorator(func):
        @wraps(func)
        async def wrapper(*args, user: User = Depends(get_current_user), **kwargs):
            user_permissions = set(user.permissions)
            required = set(permissions)

            if not required.issubset(user_permissions):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Insufficient permissions"
                )

            return await func(*args, user=user, **kwargs)
        return wrapper
    return decorator

@app.delete("/orders/{order_id}")
@require_permissions(Permission.WRITE_ORDERS)
async def delete_order(order_id: int, user: User) -> None:
    await order_service.delete(order_id)
```

### Rate Limiting

```python
# GOOD: Rate limiting middleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.get("/api/orders")
@limiter.limit("100/minute")
async def list_orders(request: Request):
    ...

# Per-user rate limiting
def get_user_identifier(request: Request) -> str:
    if hasattr(request.state, "user"):
        return f"user:{request.state.user.id}"
    return get_remote_address(request)

limiter = Limiter(key_func=get_user_identifier)
```

---

## 10. Testing Architecture

### Test Structure

```
tests/
├── conftest.py              # Shared fixtures
├── unit/
│   ├── domain/
│   │   └── test_order.py
│   └── application/
│       └── test_order_service.py
├── integration/
│   ├── conftest.py          # DB fixtures
│   ├── test_order_repository.py
│   └── test_api.py
└── e2e/
    └── test_order_flow.py
```

### Fixtures

```python
# conftest.py
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker

@pytest.fixture
def anyio_backend():
    return "asyncio"

@pytest.fixture
async def db_session():
    """Create isolated database session for tests."""
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False
    )

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    session_maker = async_sessionmaker(engine, expire_on_commit=False)

    async with session_maker() as session:
        yield session

@pytest.fixture
async def client(db_session):
    """Test client with overridden dependencies."""
    def override_get_db():
        return db_session

    app.dependency_overrides[get_db] = override_get_db

    async with AsyncClient(app=app, base_url="http://test") as client:
        yield client

    app.dependency_overrides.clear()
```

### Integration Tests

```python
# test_api.py
@pytest.mark.asyncio
async def test_create_order(client: AsyncClient, db_session: AsyncSession):
    # Arrange
    customer = Customer(name="Test", email="test@example.com")
    db_session.add(customer)
    await db_session.commit()

    # Act
    response = await client.post(
        "/api/v1/orders",
        json={
            "customer_id": customer.id,
            "items": [{"product_id": 1, "quantity": 2}]
        }
    )

    # Assert
    assert response.status_code == 201
    data = response.json()
    assert data["customer_id"] == customer.id
    assert len(data["items"]) == 1
```

---

## 11. Concurrency Architecture

### Python Concurrency Model Selection

| Model | Use When | Implementation |
|-------|----------|----------------|
| **asyncio** | I/O-bound, many connections | `async`/`await`, `asyncio.gather` |
| **Threading** | I/O-bound, simple parallelism | `threading`, `concurrent.futures` |
| **Multiprocessing** | CPU-bound work | `multiprocessing`, `ProcessPoolExecutor` |
| **Queue-Based** | Producer/consumer, decoupling | `asyncio.Queue`, `queue.Queue` |

### GIL Considerations

```python
# The GIL (Global Interpreter Lock) affects concurrency strategy

# CPU-BOUND: GIL is a bottleneck - use multiprocessing
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

def cpu_intensive(data):
    """Heavy computation - runs in separate process."""
    return heavy_calculation(data)

async def process_batch(items: list) -> list:
    # Use process pool for CPU-bound work
    with ProcessPoolExecutor(max_workers=multiprocessing.cpu_count()) as pool:
        loop = asyncio.get_event_loop()
        tasks = [
            loop.run_in_executor(pool, cpu_intensive, item)
            for item in items
        ]
        return await asyncio.gather(*tasks)

# I/O-BOUND: GIL releases during I/O - asyncio or threading work well
async def fetch_all(urls: list[str]) -> list[dict]:
    async with httpx.AsyncClient() as client:
        tasks = [client.get(url) for url in urls]
        responses = await asyncio.gather(*tasks)
        return [r.json() for r in responses]
```

### Asyncio Architecture Patterns

```python
# GOOD: Bounded concurrency with semaphore
class BoundedClient:
    def __init__(self, max_concurrent: int = 10):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._client = httpx.AsyncClient()

    async def fetch(self, url: str) -> dict:
        async with self._semaphore:
            response = await self._client.get(url)
            return response.json()

    async def fetch_all(self, urls: list[str]) -> list[dict]:
        tasks = [self.fetch(url) for url in urls]
        return await asyncio.gather(*tasks, return_exceptions=True)

# GOOD: Task group for structured concurrency (Python 3.11+)
async def process_orders(order_ids: list[int]) -> list[Order]:
    results = []
    async with asyncio.TaskGroup() as tg:
        for order_id in order_ids:
            task = tg.create_task(process_order(order_id))
            results.append(task)
    return [task.result() for task in results]

# GOOD: Timeout with proper cleanup
async def fetch_with_timeout(url: str, timeout: float = 10.0) -> dict:
    try:
        async with asyncio.timeout(timeout):
            async with httpx.AsyncClient() as client:
                response = await client.get(url)
                return response.json()
    except asyncio.TimeoutError:
        logger.warning(f"Timeout fetching {url}")
        raise
```

### Queue-Based Processing

```python
# GOOD: Producer/consumer with asyncio.Queue
class OrderProcessor:
    def __init__(self, num_workers: int = 4, queue_size: int = 1000):
        self._queue: asyncio.Queue[Order] = asyncio.Queue(maxsize=queue_size)
        self._num_workers = num_workers
        self._workers: list[asyncio.Task] = []

    async def start(self):
        """Start worker tasks."""
        self._workers = [
            asyncio.create_task(self._worker(f"worker-{i}"))
            for i in range(self._num_workers)
        ]

    async def stop(self):
        """Graceful shutdown."""
        # Wait for queue to drain
        await self._queue.join()
        # Cancel workers
        for worker in self._workers:
            worker.cancel()
        await asyncio.gather(*self._workers, return_exceptions=True)

    async def submit(self, order: Order):
        """Submit order for processing (blocks if queue full = backpressure)."""
        await self._queue.put(order)

    async def _worker(self, name: str):
        """Process orders from queue."""
        while True:
            try:
                order = await self._queue.get()
                try:
                    await self._process(order)
                finally:
                    self._queue.task_done()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"{name} error: {e}")

    async def _process(self, order: Order):
        # Processing logic
        ...
```

### Thread Pool for Blocking Operations

```python
# GOOD: Run blocking code in thread pool
import asyncio
from concurrent.futures import ThreadPoolExecutor
from functools import partial

# Global thread pool for blocking operations
_executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix="blocking-")

async def run_blocking(func, *args, **kwargs):
    """Run blocking function in thread pool."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(
        _executor,
        partial(func, *args, **kwargs)
    )

# Usage
async def get_file_hash(path: str) -> str:
    """Compute hash without blocking event loop."""
    def _compute_hash(p: str) -> str:
        import hashlib
        with open(p, 'rb') as f:
            return hashlib.sha256(f.read()).hexdigest()

    return await run_blocking(_compute_hash, path)

# GOOD: Starlette's run_in_threadpool
from starlette.concurrency import run_in_threadpool

@app.post("/upload")
async def upload_file(file: UploadFile):
    content = await file.read()
    # Run blocking operation in thread pool
    result = await run_in_threadpool(process_file_sync, content)
    return {"result": result}
```

### Parallel Processing with ProcessPoolExecutor

```python
# GOOD: CPU-bound parallel processing
from concurrent.futures import ProcessPoolExecutor
import multiprocessing

class ParallelProcessor:
    def __init__(self, max_workers: int | None = None):
        self._max_workers = max_workers or multiprocessing.cpu_count()

    async def map(self, func, items: list) -> list:
        """Apply function to items in parallel across processes."""
        loop = asyncio.get_event_loop()

        with ProcessPoolExecutor(max_workers=self._max_workers) as executor:
            # Submit all tasks
            futures = [
                loop.run_in_executor(executor, func, item)
                for item in items
            ]
            # Gather results
            return await asyncio.gather(*futures)

# Usage
processor = ParallelProcessor()

def analyze_image(image_path: str) -> dict:
    """CPU-intensive image analysis."""
    # This runs in separate process, bypassing GIL
    ...

results = await processor.map(analyze_image, image_paths)
```

### Actor Pattern

```python
# GOOD: Simple actor implementation
from dataclasses import dataclass
from typing import Any

@dataclass
class Message:
    type: str
    payload: Any
    reply_to: asyncio.Queue | None = None

class Actor:
    def __init__(self, mailbox_size: int = 1000):
        self._mailbox: asyncio.Queue[Message] = asyncio.Queue(maxsize=mailbox_size)
        self._running = False

    async def start(self):
        self._running = True
        while self._running:
            try:
                msg = await self._mailbox.get()
                result = await self.handle(msg)
                if msg.reply_to:
                    await msg.reply_to.put(result)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Actor error handling {msg.type}: {e}")

    async def stop(self):
        self._running = False

    async def send(self, msg: Message):
        await self._mailbox.put(msg)

    async def ask(self, msg: Message, timeout: float = 10.0) -> Any:
        """Send message and wait for reply."""
        reply_queue: asyncio.Queue = asyncio.Queue(maxsize=1)
        msg.reply_to = reply_queue
        await self.send(msg)
        return await asyncio.wait_for(reply_queue.get(), timeout)

    async def handle(self, msg: Message) -> Any:
        """Override in subclass."""
        raise NotImplementedError

# Usage
class OrderActor(Actor):
    def __init__(self):
        super().__init__()
        self._orders: dict[int, Order] = {}

    async def handle(self, msg: Message) -> Any:
        match msg.type:
            case "create":
                order = Order(**msg.payload)
                self._orders[order.id] = order
                return order
            case "get":
                return self._orders.get(msg.payload["id"])
            case _:
                raise ValueError(f"Unknown message type: {msg.type}")
```

### Concurrency Anti-Patterns

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| **Unbounded gather** | Memory exhaustion | Use semaphore for bounded concurrency |
| **Fire and Forget** | Lost errors | Use TaskGroup, track tasks |
| **Blocking in async** | Event loop starvation | `run_in_executor` for blocking ops |
| **Shared Mutable State** | Race conditions | Queues, actors, locks |
| **No Backpressure** | Memory exhaustion | Bounded queues |
| **Wrong Pool Type** | GIL bottleneck | ProcessPool for CPU, ThreadPool for I/O |

---

## Anti-Patterns Summary

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| **Global State** | Mutable globals shared across requests | Dependency injection, context vars |
| **Sync in Async** | Blocking calls in async functions | Use async libraries (httpx, aiofiles) |
| **God Module** | Single module with all logic | Split by domain/layer |
| **No Typing** | Runtime errors, poor IDE support | Type hints + mypy strict mode |
| **Bare Except** | Swallowing all errors | Catch specific exceptions |
| **Hardcoded Config** | Different env = code changes | Pydantic Settings |
| **No Health Checks** | Silent failures | /health/ready, /health/live |
| **Missing Correlation** | Can't trace requests | Correlation ID middleware |
| **Unbounded Concurrency** | Resource exhaustion | Semaphores, bounded queues |

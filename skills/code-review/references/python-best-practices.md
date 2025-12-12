# Python Best Practices Reference

Comprehensive reference for Python code review covering patterns, anti-patterns, and best practices.

## Table of Contents
1. [Type Hints](#type-hints)
2. [Async/Await](#asyncawait)
3. [Context Managers](#context-managers)
4. [Exception Handling](#exception-handling)
5. [Data Classes](#data-classes)
6. [Collections & Iteration](#collections--iteration)
7. [Thread Safety](#thread-safety)
8. [Testing](#testing)
9. [Design Patterns](#design-patterns)
10. [Security](#security)
11. [Performance](#performance)

> **Note**: For architectural patterns (Resilience, Observability, API Design, Configuration),
> see the `architecture-review` skill reference documents.

---

## Type Hints

### Basic Type Annotations

```python
# GOOD: Clear type hints
from typing import Optional, List, Dict, Union, Callable

def get_user(user_id: int) -> Optional[User]:
    """Fetch user by ID, returns None if not found."""
    return db.query(User).filter_by(id=user_id).first()

def process_items(items: List[str]) -> Dict[str, int]:
    """Count occurrences of each item."""
    return {item: items.count(item) for item in set(items)}

# GOOD: Union types (Python 3.10+ can use |)
def parse_id(value: Union[str, int]) -> int:
    return int(value)

# Python 3.10+
def parse_id(value: str | int) -> int:
    return int(value)
```

### Generic Types

```python
from typing import TypeVar, Generic, Sequence

T = TypeVar('T')

# GOOD: Generic class
class Repository(Generic[T]):
    def __init__(self, model_class: type[T]) -> None:
        self._model = model_class

    def get_by_id(self, id: int) -> Optional[T]:
        return db.query(self._model).get(id)

    def get_all(self) -> List[T]:
        return db.query(self._model).all()

# GOOD: Callable type hints
def apply_transform(
    items: List[T],
    transform: Callable[[T], T]
) -> List[T]:
    return [transform(item) for item in items]
```

### Type Aliases

```python
from typing import TypeAlias, NewType

# Type alias for complex types
JsonDict: TypeAlias = Dict[str, Any]
UserId = NewType('UserId', int)  # Distinct type for type checker

def get_user(user_id: UserId) -> JsonDict:
    ...

# Usage
user_id = UserId(123)  # Explicit construction
get_user(user_id)      # OK
get_user(123)          # Type checker warning
```

### Common Mistakes

```python
# BAD: Using List instead of Sequence for input (too restrictive)
def process(items: List[str]) -> None:  # Requires exactly List
    ...

# GOOD: Accept any sequence
def process(items: Sequence[str]) -> None:  # Accepts list, tuple, etc.
    ...

# BAD: Mutable default argument
def add_item(item: str, items: List[str] = []) -> List[str]:  # DANGER!
    items.append(item)
    return items

# GOOD: Use None as default
def add_item(item: str, items: Optional[List[str]] = None) -> List[str]:
    if items is None:
        items = []
    items.append(item)
    return items
```

---

## Async/Await

### Basic Patterns

```python
import asyncio
from typing import List

# GOOD: Proper async function
async def fetch_user(user_id: int) -> User:
    async with aiohttp.ClientSession() as session:
        async with session.get(f"/users/{user_id}") as response:
            data = await response.json()
            return User(**data)

# GOOD: Concurrent execution
async def fetch_all_users(user_ids: List[int]) -> List[User]:
    tasks = [fetch_user(uid) for uid in user_ids]
    return await asyncio.gather(*tasks)

# GOOD: With error handling
async def fetch_all_users_safe(user_ids: List[int]) -> List[Optional[User]]:
    tasks = [fetch_user(uid) for uid in user_ids]
    results = await asyncio.gather(*tasks, return_exceptions=True)
    return [r if not isinstance(r, Exception) else None for r in results]
```

### Anti-Patterns

```python
# BAD: Blocking call in async code
async def process_file(path: str) -> str:
    with open(path) as f:  # BLOCKING!
        return f.read()

# GOOD: Use async file operations
import aiofiles

async def process_file(path: str) -> str:
    async with aiofiles.open(path) as f:
        return await f.read()

# BAD: Sequential awaits when concurrent is possible
async def fetch_data() -> tuple:
    user = await fetch_user(1)      # Wait
    orders = await fetch_orders(1)   # Then wait again
    return user, orders

# GOOD: Concurrent execution
async def fetch_data() -> tuple:
    user, orders = await asyncio.gather(
        fetch_user(1),
        fetch_orders(1)
    )
    return user, orders

# BAD: Creating tasks without awaiting
async def process():
    asyncio.create_task(background_work())  # Fire and forget - may not complete
    return "done"

# GOOD: Track background tasks
class TaskManager:
    def __init__(self):
        self._tasks: set[asyncio.Task] = set()

    def create_task(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def wait_all(self):
        await asyncio.gather(*self._tasks, return_exceptions=True)
```

### Timeouts and Cancellation

```python
# GOOD: Timeout handling
async def fetch_with_timeout(url: str, timeout: float = 30.0) -> str:
    try:
        async with asyncio.timeout(timeout):
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    return await response.text()
    except asyncio.TimeoutError:
        raise ServiceTimeoutError(f"Request to {url} timed out")

# GOOD: Cancellation handling
async def long_running_task(cancel_event: asyncio.Event) -> None:
    while not cancel_event.is_set():
        await do_work()
        await asyncio.sleep(1)
```

---

## Context Managers

### Basic Usage

```python
# GOOD: Using context manager for resources
with open("file.txt") as f:
    content = f.read()
# File automatically closed

# GOOD: Multiple context managers
with open("input.txt") as infile, open("output.txt", "w") as outfile:
    outfile.write(infile.read().upper())

# GOOD: contextlib for simple cases
from contextlib import contextmanager

@contextmanager
def timer(name: str):
    start = time.time()
    try:
        yield
    finally:
        elapsed = time.time() - start
        print(f"{name}: {elapsed:.2f}s")

with timer("processing"):
    do_work()
```

### Async Context Managers

```python
from contextlib import asynccontextmanager

@asynccontextmanager
async def get_db_connection():
    conn = await create_connection()
    try:
        yield conn
    finally:
        await conn.close()

async def query_users():
    async with get_db_connection() as conn:
        return await conn.fetch("SELECT * FROM users")
```

### Class-Based Context Manager

```python
class DatabaseTransaction:
    def __init__(self, connection):
        self._conn = connection
        self._transaction = None

    def __enter__(self):
        self._transaction = self._conn.begin()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            self._transaction.rollback()
        else:
            self._transaction.commit()
        return False  # Don't suppress exceptions

# Async version
class AsyncDatabaseTransaction:
    async def __aenter__(self):
        self._transaction = await self._conn.begin()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if exc_type is not None:
            await self._transaction.rollback()
        else:
            await self._transaction.commit()
        return False
```

---

## Exception Handling

### Best Practices

```python
# GOOD: Catch specific exceptions
try:
    user = get_user(user_id)
except UserNotFoundError:
    return None
except DatabaseError as e:
    logger.error("Database error: %s", e)
    raise ServiceError("Unable to fetch user") from e

# GOOD: Exception chaining
try:
    data = parse_config(path)
except json.JSONDecodeError as e:
    raise ConfigurationError(f"Invalid config file: {path}") from e

# BAD: Bare except
try:
    do_something()
except:  # Catches everything including KeyboardInterrupt!
    pass

# BAD: Catching Exception and ignoring
try:
    do_something()
except Exception:
    pass  # Bugs hidden forever

# GOOD: Log and re-raise if needed
try:
    do_something()
except Exception:
    logger.exception("Unexpected error in do_something")
    raise
```

### Custom Exceptions

```python
# GOOD: Domain exception hierarchy
class DomainError(Exception):
    """Base exception for domain errors."""
    def __init__(self, message: str, code: str = "UNKNOWN"):
        super().__init__(message)
        self.code = code

class ValidationError(DomainError):
    """Raised when validation fails."""
    def __init__(self, message: str, field: Optional[str] = None):
        super().__init__(message, code="VALIDATION_ERROR")
        self.field = field

class NotFoundError(DomainError):
    """Raised when entity is not found."""
    def __init__(self, entity_type: str, entity_id: Any):
        super().__init__(
            f"{entity_type} with ID {entity_id} not found",
            code="NOT_FOUND"
        )
        self.entity_type = entity_type
        self.entity_id = entity_id
```

### Context in Exceptions

```python
# GOOD: Add context when re-raising
def process_user_file(path: str) -> List[User]:
    try:
        with open(path) as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ConfigurationError(f"User file not found: {path}")
    except json.JSONDecodeError as e:
        raise ConfigurationError(
            f"Invalid JSON in {path} at line {e.lineno}"
        ) from e

    try:
        return [User(**item) for item in data]
    except (KeyError, TypeError) as e:
        raise ConfigurationError(
            f"Invalid user data structure in {path}"
        ) from e
```

---

## Data Classes

### Basic Usage

```python
from dataclasses import dataclass, field
from typing import List, Optional

# GOOD: Simple data class
@dataclass
class User:
    id: int
    name: str
    email: str
    is_active: bool = True

# GOOD: Frozen (immutable) data class
@dataclass(frozen=True)
class Point:
    x: float
    y: float

# GOOD: With default factory for mutable defaults
@dataclass
class Order:
    id: int
    customer_id: int
    items: List[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)
```

### Advanced Features

```python
from dataclasses import dataclass, field, asdict, astuple

@dataclass
class Config:
    host: str
    port: int = 8080
    debug: bool = field(default=False, repr=False)  # Excluded from repr
    _cache: dict = field(default_factory=dict, init=False, repr=False)

    def __post_init__(self):
        """Validation after initialization."""
        if self.port < 1 or self.port > 65535:
            raise ValueError(f"Invalid port: {self.port}")

# Slots for memory efficiency (Python 3.10+)
@dataclass(slots=True)
class Point:
    x: float
    y: float
```

### Pydantic Models (for validation)

```python
from pydantic import BaseModel, EmailStr, Field, validator

class UserCreate(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    email: EmailStr
    age: int = Field(..., ge=0, le=150)

    @validator('name')
    def name_must_not_be_empty(cls, v):
        if not v.strip():
            raise ValueError('Name cannot be empty')
        return v.strip()

    class Config:
        frozen = True  # Immutable
```

---

## Collections & Iteration

### Comprehensions

```python
# GOOD: List comprehension
squares = [x**2 for x in range(10)]

# GOOD: Dict comprehension
word_lengths = {word: len(word) for word in words}

# GOOD: Set comprehension
unique_lengths = {len(word) for word in words}

# GOOD: Generator expression for large data
total = sum(x**2 for x in range(1000000))  # Memory efficient

# BAD: Nested comprehensions that are hard to read
result = [[y*2 for y in x if y > 0] for x in matrix if len(x) > 2]

# GOOD: Break down complex comprehensions
def process_row(row: List[int]) -> List[int]:
    return [y * 2 for y in row if y > 0]

result = [process_row(x) for x in matrix if len(x) > 2]
```

### Itertools

```python
from itertools import chain, groupby, islice, zip_longest

# Chain multiple iterables
all_items = chain(list1, list2, list3)

# Group by key
sorted_data = sorted(data, key=lambda x: x.category)
for category, items in groupby(sorted_data, key=lambda x: x.category):
    print(f"{category}: {list(items)}")

# Take first N items
first_ten = list(islice(items, 10))

# Zip with fill value
for a, b in zip_longest(list1, list2, fillvalue=None):
    ...
```

### Dictionary Operations

```python
# GOOD: Use .get() with default
value = data.get("key", "default")

# GOOD: setdefault for conditional insert
cache.setdefault(key, []).append(item)

# GOOD: dict.update() for merging
config = {"debug": False, "port": 8080}
config.update(overrides)

# Python 3.9+: Union operator
merged = defaults | overrides

# GOOD: collections.defaultdict
from collections import defaultdict
word_count = defaultdict(int)
for word in words:
    word_count[word] += 1
```

---

## Thread Safety

### Threading Basics

```python
import threading
from queue import Queue

# GOOD: Thread-safe counter with Lock
class Counter:
    def __init__(self):
        self._value = 0
        self._lock = threading.Lock()

    def increment(self) -> int:
        with self._lock:
            self._value += 1
            return self._value

# GOOD: Thread communication via Queue
def worker(queue: Queue, results: Queue):
    while True:
        item = queue.get()
        if item is None:
            break
        result = process(item)
        results.put(result)
        queue.task_done()

# GOOD: Thread pool
from concurrent.futures import ThreadPoolExecutor

with ThreadPoolExecutor(max_workers=4) as executor:
    futures = [executor.submit(process, item) for item in items]
    results = [f.result() for f in futures]
```

### Multiprocessing for CPU-bound Work

```python
from multiprocessing import Pool, cpu_count

# GOOD: Process pool for CPU-bound work
def compute_heavy(x: int) -> int:
    return sum(i**2 for i in range(x))

with Pool(cpu_count()) as pool:
    results = pool.map(compute_heavy, range(100))
```

### Thread-Local Storage

```python
import threading

# Thread-local storage for per-thread state
thread_local = threading.local()

def get_connection():
    if not hasattr(thread_local, "connection"):
        thread_local.connection = create_connection()
    return thread_local.connection
```

### Common Pitfalls

```python
# BAD: Race condition
counter = 0
def increment():
    global counter
    counter += 1  # Not atomic!

# BAD: Deadlock potential
lock1 = threading.Lock()
lock2 = threading.Lock()

def func1():
    with lock1:
        with lock2:  # If func2 holds lock2 and wants lock1 = deadlock
            ...

def func2():
    with lock2:
        with lock1:
            ...

# GOOD: Consistent lock ordering
def func1():
    with lock1:
        with lock2:
            ...

def func2():
    with lock1:  # Same order
        with lock2:
            ...
```

---

## Testing

### Pytest Basics

```python
import pytest
from unittest.mock import Mock, patch, AsyncMock

# GOOD: Clear test naming
def test_user_creation_with_valid_data():
    user = User(name="John", email="john@example.com")
    assert user.name == "John"
    assert user.email == "john@example.com"

# GOOD: Parametrized tests
@pytest.mark.parametrize("input,expected", [
    ("hello", "HELLO"),
    ("World", "WORLD"),
    ("", ""),
])
def test_uppercase(input: str, expected: str):
    assert input.upper() == expected

# GOOD: Testing exceptions
def test_invalid_user_raises_error():
    with pytest.raises(ValidationError) as exc_info:
        User(name="", email="invalid")
    assert "name" in str(exc_info.value)
```

### Fixtures

```python
@pytest.fixture
def sample_user() -> User:
    return User(id=1, name="Test", email="test@example.com")

@pytest.fixture
def db_session():
    session = create_test_session()
    yield session
    session.rollback()
    session.close()

# GOOD: Fixture with cleanup
@pytest.fixture
def temp_file(tmp_path):
    file_path = tmp_path / "test.txt"
    file_path.write_text("test content")
    yield file_path
    # Cleanup happens automatically with tmp_path
```

### Mocking

```python
# GOOD: Mock external services
def test_fetch_user_calls_api(mocker):
    mock_response = Mock()
    mock_response.json.return_value = {"id": 1, "name": "John"}

    mocker.patch("requests.get", return_value=mock_response)

    user = fetch_user(1)
    assert user.name == "John"

# GOOD: Async mocking
@pytest.mark.asyncio
async def test_async_fetch():
    with patch("aiohttp.ClientSession.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.__aenter__.return_value.json = AsyncMock(
            return_value={"id": 1}
        )
        result = await fetch_data()
        assert result["id"] == 1
```

---

## Design Patterns

### Dependency Injection

```python
# BAD: Hard-coded dependency
class UserService:
    def __init__(self):
        self._repo = PostgresUserRepository()  # Tight coupling

# GOOD: Injected dependency
class UserService:
    def __init__(self, repository: UserRepository):
        self._repo = repository

# Usage
service = UserService(PostgresUserRepository())
test_service = UserService(InMemoryUserRepository())  # Easy testing
```

### Repository Pattern

```python
from abc import ABC, abstractmethod

class UserRepository(ABC):
    @abstractmethod
    def get_by_id(self, user_id: int) -> Optional[User]:
        ...

    @abstractmethod
    def save(self, user: User) -> User:
        ...

class SqlAlchemyUserRepository(UserRepository):
    def __init__(self, session: Session):
        self._session = session

    def get_by_id(self, user_id: int) -> Optional[User]:
        return self._session.query(User).get(user_id)

    def save(self, user: User) -> User:
        self._session.add(user)
        self._session.flush()
        return user
```

### Factory Pattern

```python
from enum import Enum

class NotificationType(Enum):
    EMAIL = "email"
    SMS = "sms"
    PUSH = "push"

class NotificationFactory:
    _handlers: Dict[NotificationType, type] = {
        NotificationType.EMAIL: EmailNotifier,
        NotificationType.SMS: SmsNotifier,
        NotificationType.PUSH: PushNotifier,
    }

    @classmethod
    def create(cls, notification_type: NotificationType) -> Notifier:
        handler_class = cls._handlers.get(notification_type)
        if not handler_class:
            raise ValueError(f"Unknown notification type: {notification_type}")
        return handler_class()
```

---

## Security

### Input Validation

```python
# BAD: No validation
def process_user_input(data: dict):
    query = f"SELECT * FROM users WHERE name = '{data['name']}'"  # SQL Injection!

# GOOD: Parameterized queries
def get_user_by_name(name: str) -> Optional[User]:
    return session.execute(
        text("SELECT * FROM users WHERE name = :name"),
        {"name": name}
    ).fetchone()

# GOOD: Input validation with Pydantic
from pydantic import BaseModel, validator
import re

class UserInput(BaseModel):
    username: str
    email: str

    @validator('username')
    def validate_username(cls, v):
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('Username must be alphanumeric')
        return v
```

### Secrets Management

```python
# BAD: Hardcoded secrets
API_KEY = "sk-1234567890"  # In code!

# GOOD: Environment variables
import os
API_KEY = os.environ.get("API_KEY")
if not API_KEY:
    raise EnvironmentError("API_KEY not set")

# GOOD: Using python-dotenv for local development
from dotenv import load_dotenv
load_dotenv()

# GOOD: Never log secrets
logger.info("Connecting to API")  # Don't log the key!
```

### Dangerous Functions

```python
# BAD: eval/exec with user input
user_expr = request.get("expression")
result = eval(user_expr)  # CODE EXECUTION!

# BAD: pickle with untrusted data
import pickle
data = pickle.loads(untrusted_bytes)  # CODE EXECUTION!

# BAD: yaml.load without SafeLoader
import yaml
data = yaml.load(file)  # CODE EXECUTION!

# GOOD: Use safe alternatives
data = yaml.safe_load(file)

# GOOD: Use json instead of pickle for data exchange
import json
data = json.loads(untrusted_string)
```

### Path Traversal

```python
# BAD: Direct path concatenation
def read_file(filename: str) -> str:
    path = f"/uploads/{filename}"  # ../../../etc/passwd works!
    return open(path).read()

# GOOD: Validate and sanitize paths
from pathlib import Path

def read_file(filename: str, base_dir: str = "/uploads") -> str:
    base = Path(base_dir).resolve()
    file_path = (base / filename).resolve()

    # Ensure path is within base directory
    if not str(file_path).startswith(str(base)):
        raise ValueError("Invalid file path")

    return file_path.read_text()
```

---

## Performance

### Profiling

```python
# GOOD: Use cProfile for CPU profiling
import cProfile
import pstats

profiler = cProfile.Profile()
profiler.enable()
# ... code to profile ...
profiler.disable()
stats = pstats.Stats(profiler).sort_stats('cumtime')
stats.print_stats(10)

# GOOD: memory_profiler for memory
from memory_profiler import profile

@profile
def memory_heavy_function():
    ...
```

### String Operations

```python
# BAD: String concatenation in loop
result = ""
for item in items:
    result += str(item)  # O(n²) - creates new string each time

# GOOD: Use join
result = "".join(str(item) for item in items)

# GOOD: Use f-strings for formatting
name = "John"
age = 30
message = f"Name: {name}, Age: {age}"  # Fastest option
```

### Generator vs List

```python
# BAD: Creating large list in memory
def get_all_lines(files: List[str]) -> List[str]:
    result = []
    for f in files:
        result.extend(open(f).readlines())  # All in memory!
    return result

# GOOD: Generator for memory efficiency
def get_all_lines(files: List[str]):
    for f in files:
        with open(f) as file:
            yield from file  # Lazy evaluation
```

### Caching

```python
from functools import lru_cache, cache

# GOOD: LRU cache for expensive computations
@lru_cache(maxsize=128)
def fibonacci(n: int) -> int:
    if n < 2:
        return n
    return fibonacci(n - 1) + fibonacci(n - 2)

# Python 3.9+: Unlimited cache
@cache
def expensive_computation(x: int) -> int:
    ...

# GOOD: Cache with timeout using cachetools
from cachetools import TTLCache

cache = TTLCache(maxsize=100, ttl=300)  # 5 minute TTL
```

### Slots for Memory

```python
# Regular class - uses __dict__
class Point:
    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y

# With slots - more memory efficient
class Point:
    __slots__ = ['x', 'y']

    def __init__(self, x: float, y: float):
        self.x = x
        self.y = y
```

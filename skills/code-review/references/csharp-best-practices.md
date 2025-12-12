# C# Best Practices Reference

Comprehensive reference for C# code review covering patterns, anti-patterns, and best practices.

## Table of Contents
1. [Async/Await](#asyncawait)
2. [Null Safety](#null-safety)
3. [Dispose Pattern](#dispose-pattern)
4. [LINQ](#linq)
5. [Dependency Injection](#dependency-injection)
6. [Entity Framework Core](#entity-framework-core)
7. [Thread Safety](#thread-safety)
8. [Exception Handling](#exception-handling)
9. [Design Patterns](#design-patterns)
10. [Security](#security)
11. [Performance](#performance)
12. [Serialization](#serialization)

> **Note**: For architectural patterns (Resilience, Observability, API Design, Configuration),
> see the `architecture-review` skill reference documents.

---

## Async/Await

### Best Practices

```csharp
// GOOD: Async all the way
public async Task<User> GetUserAsync(int id, CancellationToken ct = default)
{
    return await _dbContext.Users
        .FirstOrDefaultAsync(u => u.Id == id, ct);
}

// GOOD: ConfigureAwait(false) in library code
public async Task<string> FetchDataAsync()
{
    var response = await _httpClient.GetAsync(url).ConfigureAwait(false);
    return await response.Content.ReadAsStringAsync().ConfigureAwait(false);
}

// GOOD: Proper cancellation token propagation
public async Task ProcessItemsAsync(IEnumerable<Item> items, CancellationToken ct)
{
    foreach (var item in items)
    {
        ct.ThrowIfCancellationRequested();
        await ProcessItemAsync(item, ct);
    }
}
```

### Anti-Patterns

```csharp
// BAD: Async void (except event handlers)
public async void ProcessData() // Should be Task
{
    await DoWorkAsync();
}

// BAD: Blocking on async code (deadlock risk)
public User GetUser(int id)
{
    return GetUserAsync(id).Result; // DEADLOCK in UI/ASP.NET contexts
}

// BAD: Unnecessary async/await
public async Task<int> GetValueAsync()
{
    return await Task.FromResult(42); // Just return Task.FromResult(42)
}

// BAD: Fire and forget without error handling
public void StartProcess()
{
    _ = ProcessAsync(); // Exceptions silently swallowed
}

// BETTER: Fire and forget with error handling
public void StartProcess()
{
    _ = ProcessAsync().ContinueWith(t =>
        _logger.LogError(t.Exception, "Process failed"),
        TaskContinuationOptions.OnlyOnFaulted);
}
```

### Thread Safety with Async

```csharp
// BAD: Shared state without synchronization
private List<string> _results = new();
public async Task AddResultAsync(string result)
{
    _results.Add(result); // Race condition
}

// GOOD: Thread-safe collection
private ConcurrentBag<string> _results = new();
public async Task AddResultAsync(string result)
{
    _results.Add(result);
}

// GOOD: SemaphoreSlim for async locking
private readonly SemaphoreSlim _semaphore = new(1, 1);
public async Task UpdateStateAsync()
{
    await _semaphore.WaitAsync();
    try
    {
        // Critical section
    }
    finally
    {
        _semaphore.Release();
    }
}
```

---

## Null Safety

### Nullable Reference Types

```csharp
// GOOD: Explicit nullability
public class UserService
{
    private readonly ILogger<UserService> _logger; // Non-null
    private ICache? _cache; // Nullable

    public User? GetUser(int id) // May return null
    {
        return _cache?.Get<User>($"user:{id}");
    }

    public User GetUserOrThrow(int id) // Never returns null
    {
        return GetUser(id) ?? throw new NotFoundException($"User {id} not found");
    }
}
```

### Null Checks

```csharp
// GOOD: Guard clauses with ArgumentNullException.ThrowIfNull (.NET 6+)
public void ProcessUser(User user)
{
    ArgumentNullException.ThrowIfNull(user);
    // Process user
}

// GOOD: Null-conditional and null-coalescing
public string GetDisplayName(User? user)
{
    return user?.DisplayName ?? user?.Email ?? "Unknown";
}

// BAD: Null-forgiving operator hiding real issues
public void Process(User? user)
{
    var name = user!.Name; // Dangerous - can still throw
}

// GOOD: Pattern matching for null checks
public void Process(User? user)
{
    if (user is { Name: var name, Email: var email })
    {
        // Both name and email are non-null here
    }
}
```

---

## Dispose Pattern

### Basic IDisposable

```csharp
// GOOD: Proper dispose pattern
public class ResourceManager : IDisposable
{
    private readonly HttpClient _httpClient;
    private bool _disposed;

    public ResourceManager()
    {
        _httpClient = new HttpClient();
    }

    public void Dispose()
    {
        Dispose(true);
        GC.SuppressFinalize(this);
    }

    protected virtual void Dispose(bool disposing)
    {
        if (_disposed) return;

        if (disposing)
        {
            _httpClient.Dispose();
        }

        _disposed = true;
    }
}
```

### Async Dispose

```csharp
// GOOD: IAsyncDisposable for async cleanup
public class AsyncResourceManager : IAsyncDisposable
{
    private readonly DbConnection _connection;

    public async ValueTask DisposeAsync()
    {
        await _connection.CloseAsync();
        await _connection.DisposeAsync();
    }
}

// GOOD: Using declaration (C# 8+)
public async Task ProcessAsync()
{
    await using var connection = new SqlConnection(connectionString);
    await connection.OpenAsync();
    // Connection disposed at end of scope
}
```

### Common Mistakes

```csharp
// BAD: Not disposing in all paths
public void Process()
{
    var stream = new FileStream(path, FileMode.Open);
    if (!IsValid(stream))
        return; // LEAK: stream not disposed
    // ...
    stream.Dispose();
}

// GOOD: Using statement ensures disposal
public void Process()
{
    using var stream = new FileStream(path, FileMode.Open);
    if (!IsValid(stream))
        return; // Stream still disposed
    // ...
}
```

---

## LINQ

### Performance Considerations

```csharp
// BAD: Multiple enumeration
public void Process(IEnumerable<Item> items)
{
    if (!items.Any()) return;     // First enumeration
    var count = items.Count();    // Second enumeration
    foreach (var item in items)   // Third enumeration
    {
        // ...
    }
}

// GOOD: Materialize once if multiple operations needed
public void Process(IEnumerable<Item> items)
{
    var itemList = items.ToList();
    if (itemList.Count == 0) return;
    foreach (var item in itemList)
    {
        // ...
    }
}

// BAD: LINQ in tight loop with allocations
for (int i = 0; i < 1000000; i++)
{
    var filtered = items.Where(x => x.Id == i).FirstOrDefault(); // Allocates
}

// GOOD: Use direct lookup
var lookup = items.ToDictionary(x => x.Id);
for (int i = 0; i < 1000000; i++)
{
    lookup.TryGetValue(i, out var item);
}
```

### Deferred Execution Awareness

```csharp
// BAD: Deferred execution surprise
public IEnumerable<Item> GetItems()
{
    using var connection = new SqlConnection(connectionString);
    connection.Open();

    return connection.Query<Item>("SELECT * FROM Items");
    // Connection disposed before enumeration!
}

// GOOD: Materialize before returning
public IEnumerable<Item> GetItems()
{
    using var connection = new SqlConnection(connectionString);
    connection.Open();

    return connection.Query<Item>("SELECT * FROM Items").ToList();
}

// GOOD: Or use yield with connection scope
public IEnumerable<Item> GetItems()
{
    using var connection = new SqlConnection(connectionString);
    connection.Open();

    foreach (var item in connection.Query<Item>("SELECT * FROM Items"))
    {
        yield return item;
    }
}
```

---

## Dependency Injection

### Service Lifetimes

```csharp
// Scoped service - one per request
services.AddScoped<IUserService, UserService>();

// Singleton - one for entire app
services.AddSingleton<ICacheService, CacheService>();

// Transient - new instance every time
services.AddTransient<IEmailBuilder, EmailBuilder>();
```

### Common Mistakes

```csharp
// BAD: Captive dependency - singleton holding scoped service
public class SingletonService // Registered as Singleton
{
    private readonly IScopedService _scopedService; // PROBLEM!

    public SingletonService(IScopedService scopedService)
    {
        _scopedService = scopedService; // Captured, never released
    }
}

// GOOD: Use IServiceScopeFactory
public class SingletonService
{
    private readonly IServiceScopeFactory _scopeFactory;

    public SingletonService(IServiceScopeFactory scopeFactory)
    {
        _scopeFactory = scopeFactory;
    }

    public async Task DoWorkAsync()
    {
        using var scope = _scopeFactory.CreateScope();
        var scopedService = scope.ServiceProvider.GetRequiredService<IScopedService>();
        // Use scopedService
    }
}

// BAD: Service locator anti-pattern
public class BadService
{
    public void DoWork()
    {
        var service = ServiceLocator.Get<IOtherService>(); // Hidden dependency
    }
}

// GOOD: Constructor injection
public class GoodService
{
    private readonly IOtherService _otherService;

    public GoodService(IOtherService otherService)
    {
        _otherService = otherService; // Explicit dependency
    }
}
```

---

## Entity Framework Core

### Query Optimization

```csharp
// BAD: N+1 query problem
var orders = await _context.Orders.ToListAsync();
foreach (var order in orders)
{
    var customer = order.Customer; // Lazy load - N additional queries!
}

// GOOD: Eager loading
var orders = await _context.Orders
    .Include(o => o.Customer)
    .ToListAsync();

// GOOD: Projection to avoid over-fetching
var orderDtos = await _context.Orders
    .Select(o => new OrderDto
    {
        Id = o.Id,
        CustomerName = o.Customer.Name,
        Total = o.Items.Sum(i => i.Price)
    })
    .ToListAsync();

// BAD: Loading entire entity for existence check
var exists = await _context.Users.FirstOrDefaultAsync(u => u.Email == email) != null;

// GOOD: Use Any() for existence
var exists = await _context.Users.AnyAsync(u => u.Email == email);
```

### Change Tracking

```csharp
// GOOD: Disable tracking for read-only queries
var users = await _context.Users
    .AsNoTracking()
    .Where(u => u.IsActive)
    .ToListAsync();

// BAD: Tracking entities you won't modify
public async Task<IEnumerable<UserDto>> GetUsersAsync()
{
    return await _context.Users.ToListAsync(); // Tracked unnecessarily
}
```

### Transactions

```csharp
// GOOD: Explicit transaction for multiple operations
await using var transaction = await _context.Database.BeginTransactionAsync();
try
{
    await _context.Orders.AddAsync(order);
    await _context.SaveChangesAsync();

    await _paymentService.ProcessAsync(order);

    await transaction.CommitAsync();
}
catch
{
    await transaction.RollbackAsync();
    throw;
}
```

---

## Thread Safety

### Immutability

```csharp
// GOOD: Immutable record
public record UserDto(int Id, string Name, string Email);

// GOOD: Readonly collections
public class Configuration
{
    public IReadOnlyList<string> AllowedHosts { get; init; } = Array.Empty<string>();
    public IReadOnlyDictionary<string, string> Settings { get; init; } =
        new Dictionary<string, string>();
}
```

### Locking Patterns

```csharp
// GOOD: Lock on dedicated object
private readonly object _lock = new();
private int _counter;

public void Increment()
{
    lock (_lock)
    {
        _counter++;
    }
}

// BAD: Lock on this or Type
lock (this) { } // Other code can lock on same instance
lock (typeof(MyClass)) { } // Global lock on type

// GOOD: Interlocked for simple operations
private int _counter;
public void Increment() => Interlocked.Increment(ref _counter);

// GOOD: ReaderWriterLockSlim for read-heavy scenarios
private readonly ReaderWriterLockSlim _rwLock = new();
private Dictionary<string, string> _cache = new();

public string? Get(string key)
{
    _rwLock.EnterReadLock();
    try
    {
        return _cache.TryGetValue(key, out var value) ? value : null;
    }
    finally
    {
        _rwLock.ExitReadLock();
    }
}
```

### Thread-Safe Collections

```csharp
// Thread-safe alternatives
ConcurrentDictionary<TKey, TValue>  // Instead of Dictionary
ConcurrentBag<T>                    // Instead of List (unordered)
ConcurrentQueue<T>                  // Thread-safe FIFO
ConcurrentStack<T>                  // Thread-safe LIFO
ImmutableList<T>                    // Immutable, create new on modify
Channel<T>                          // Producer-consumer scenarios
```

---

## Exception Handling

### Best Practices

```csharp
// GOOD: Catch specific exceptions
try
{
    await _httpClient.GetAsync(url);
}
catch (HttpRequestException ex)
{
    _logger.LogError(ex, "HTTP request failed for {Url}", url);
    throw new ServiceException("Failed to fetch data", ex);
}
catch (TaskCanceledException) when (cancellationToken.IsCancellationRequested)
{
    _logger.LogInformation("Request cancelled");
    throw;
}

// BAD: Catching Exception and swallowing
try
{
    DoWork();
}
catch (Exception) // Too broad
{
    // Silently swallowed - bugs hidden
}

// GOOD: Exception filters
try
{
    await ProcessAsync();
}
catch (SqlException ex) when (ex.Number == 1205) // Deadlock
{
    _logger.LogWarning("Deadlock detected, retrying...");
    await ProcessAsync(); // Retry
}
```

### Custom Exceptions

```csharp
// GOOD: Domain-specific exceptions
public class DomainException : Exception
{
    public string Code { get; }

    public DomainException(string code, string message) : base(message)
    {
        Code = code;
    }
}

public class EntityNotFoundException : DomainException
{
    public EntityNotFoundException(string entityType, object id)
        : base("NOT_FOUND", $"{entityType} with ID {id} not found")
    {
    }
}
```

---

## Design Patterns

### Dependency Inversion

```csharp
// BAD: Concrete dependency
public class OrderService
{
    private readonly SqlOrderRepository _repository = new(); // Tight coupling
}

// GOOD: Depend on abstraction
public class OrderService
{
    private readonly IOrderRepository _repository;

    public OrderService(IOrderRepository repository)
    {
        _repository = repository;
    }
}
```

### Repository Pattern

```csharp
// Generic repository interface
public interface IRepository<T> where T : class
{
    Task<T?> GetByIdAsync(int id, CancellationToken ct = default);
    Task<IEnumerable<T>> GetAllAsync(CancellationToken ct = default);
    Task AddAsync(T entity, CancellationToken ct = default);
    Task UpdateAsync(T entity, CancellationToken ct = default);
    Task DeleteAsync(T entity, CancellationToken ct = default);
}

// Specific repository with domain methods
public interface IOrderRepository : IRepository<Order>
{
    Task<IEnumerable<Order>> GetByCustomerAsync(int customerId, CancellationToken ct = default);
    Task<Order?> GetWithItemsAsync(int orderId, CancellationToken ct = default);
}
```

### Options Pattern

```csharp
// Configuration class
public class SmtpSettings
{
    public const string SectionName = "SmtpSettings";

    public string Server { get; set; } = string.Empty;
    public int Port { get; set; } = 587;
    public bool UseSsl { get; set; } = true;
    public string Username { get; set; } = string.Empty;
}

// Registration
services.Configure<SmtpSettings>(configuration.GetSection(SmtpSettings.SectionName));

// Usage
public class EmailService
{
    private readonly SmtpSettings _settings;

    public EmailService(IOptions<SmtpSettings> options)
    {
        _settings = options.Value;
    }
}
```

---

## Security

### SQL Injection Prevention

```csharp
// BAD: String concatenation
var sql = $"SELECT * FROM Users WHERE Email = '{email}'"; // VULNERABLE

// GOOD: Parameterized queries
var users = await _context.Users
    .FromSqlInterpolated($"SELECT * FROM Users WHERE Email = {email}")
    .ToListAsync();

// GOOD: LINQ (automatically parameterized)
var user = await _context.Users.FirstOrDefaultAsync(u => u.Email == email);
```

### Secrets Management

```csharp
// BAD: Hardcoded secrets
var connectionString = "Server=prod;Password=secret123"; // In code!

// GOOD: Configuration with User Secrets (dev) / Key Vault (prod)
var connectionString = _configuration.GetConnectionString("Database");

// GOOD: Avoid logging secrets
_logger.LogInformation("Connecting to {Server}",
    new Uri(connectionString).Host); // Only log safe parts
```

### Input Validation

```csharp
// GOOD: Validate at boundaries
public async Task<IActionResult> CreateUser([FromBody] CreateUserRequest request)
{
    if (!ModelState.IsValid)
        return BadRequest(ModelState);

    // Sanitize/validate beyond model binding
    if (request.Email.Contains(".."))
        return BadRequest("Invalid email format");

    // Process...
}

// Data annotations
public class CreateUserRequest
{
    [Required]
    [StringLength(100, MinimumLength = 2)]
    public string Name { get; set; } = string.Empty;

    [Required]
    [EmailAddress]
    public string Email { get; set; } = string.Empty;

    [Required]
    [MinLength(8)]
    [RegularExpression(@"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).+$")]
    public string Password { get; set; } = string.Empty;
}
```

---

## Performance

### Allocations

```csharp
// BAD: String concatenation in loop
var result = "";
foreach (var item in items)
{
    result += item.ToString(); // New string each iteration
}

// GOOD: StringBuilder
var sb = new StringBuilder();
foreach (var item in items)
{
    sb.Append(item);
}
var result = sb.ToString();

// GOOD: String.Join for simple cases
var result = string.Join("", items);

// GOOD: Span<T> for high-performance scenarios
public int ParseInt(ReadOnlySpan<char> span)
{
    return int.Parse(span);
}
```

### Object Pooling

```csharp
// GOOD: ArrayPool for temporary arrays
var pool = ArrayPool<byte>.Shared;
var buffer = pool.Rent(1024);
try
{
    // Use buffer
}
finally
{
    pool.Return(buffer);
}

// GOOD: ObjectPool for expensive objects
services.AddSingleton<ObjectPool<StringBuilder>>(
    new DefaultObjectPoolProvider().CreateStringBuilderPool());
```

### Caching

```csharp
// GOOD: IMemoryCache for local caching
public async Task<User?> GetUserAsync(int id)
{
    return await _cache.GetOrCreateAsync($"user:{id}", async entry =>
    {
        entry.AbsoluteExpirationRelativeToNow = TimeSpan.FromMinutes(5);
        return await _repository.GetByIdAsync(id);
    });
}
```

---

## Serialization

### JSON Best Practices

```csharp
// GOOD: Configure JSON options consistently
services.AddControllers()
    .AddJsonOptions(options =>
    {
        options.JsonSerializerOptions.PropertyNamingPolicy = JsonNamingPolicy.CamelCase;
        options.JsonSerializerOptions.DefaultIgnoreCondition = JsonIgnoreCondition.WhenWritingNull;
        options.JsonSerializerOptions.Converters.Add(new JsonStringEnumConverter());
    });

// GOOD: Handle unknown properties gracefully
var options = new JsonSerializerOptions
{
    PropertyNameCaseInsensitive = true,
    UnmappedMemberHandling = JsonUnmappedMemberHandling.Skip // Ignore unknown fields
};

// GOOD: Source-generated serialization for performance
[JsonSerializable(typeof(Order))]
[JsonSerializable(typeof(List<Order>))]
public partial class AppJsonContext : JsonSerializerContext { }

// Usage
var json = JsonSerializer.Serialize(order, AppJsonContext.Default.Order);
```

### Versioning

```csharp
// GOOD: Use nullable properties for backward compatibility
public class OrderDto
{
    public int Id { get; init; }
    public string Status { get; init; } = string.Empty;

    // New field added in v2 - nullable for backward compat
    public string? TrackingNumber { get; init; }

    // Deprecated in v2 - keep for backward compat
    [Obsolete("Use ShippingAddress instead")]
    public string? Address { get; init; }

    public AddressDto? ShippingAddress { get; init; }
}
```

### Custom Converters

```csharp
// GOOD: Custom converter for special types
public class DateOnlyConverter : JsonConverter<DateOnly>
{
    private const string Format = "yyyy-MM-dd";

    public override DateOnly Read(ref Utf8JsonReader reader, Type typeToConvert,
        JsonSerializerOptions options)
    {
        return DateOnly.ParseExact(reader.GetString()!, Format);
    }

    public override void Write(Utf8JsonWriter writer, DateOnly value,
        JsonSerializerOptions options)
    {
        writer.WriteStringValue(value.ToString(Format));
    }
}
```

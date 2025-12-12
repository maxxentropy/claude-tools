# .NET Architecture Reference

.NET-specific architectural patterns, infrastructure concerns, and system-level best practices. For language-agnostic patterns, see `architecture-patterns.md`.

---

## Table of Contents
1. [Project Structure](#1-project-structure)
2. [Dependency Injection Architecture](#2-dependency-injection-architecture)
3. [Resilience Patterns](#3-resilience-patterns)
4. [Observability](#4-observability)
5. [API Design](#5-api-design)
6. [Configuration Management](#6-configuration-management)
7. [Database Architecture](#7-database-architecture)
8. [Middleware Pipeline](#8-middleware-pipeline)
9. [Background Services](#9-background-services)
10. [Security Architecture](#10-security-architecture)
11. [Concurrency Architecture](#11-concurrency-architecture)

---

## 1. Project Structure

### Clean Architecture Solution Layout

```
Solution/
├── src/
│   ├── Domain/                    # Core business logic
│   │   ├── Entities/
│   │   ├── ValueObjects/
│   │   ├── Events/
│   │   ├── Exceptions/
│   │   └── Interfaces/            # Repository interfaces
│   │
│   ├── Application/               # Use cases, orchestration
│   │   ├── Commands/
│   │   ├── Queries/
│   │   ├── DTOs/
│   │   ├── Interfaces/            # Service interfaces
│   │   ├── Behaviors/             # MediatR behaviors
│   │   └── Mappings/              # AutoMapper profiles
│   │
│   ├── Infrastructure/            # External concerns
│   │   ├── Data/                  # EF Core, repositories
│   │   ├── Services/              # External service clients
│   │   ├── Identity/              # Auth implementation
│   │   └── DependencyInjection.cs
│   │
│   └── WebApi/                    # Presentation
│       ├── Controllers/
│       ├── Middleware/
│       ├── Filters/
│       └── Program.cs
│
├── tests/
│   ├── Domain.Tests/
│   ├── Application.Tests/
│   ├── Infrastructure.Tests/
│   └── WebApi.Tests/
│
└── Solution.sln
```

### Dependency Rules

```
WebApi → Application → Domain
           ↓
      Infrastructure → Domain
```

**Domain**: Zero external dependencies (no NuGet packages except maybe primitives)
**Application**: MediatR, FluentValidation, AutoMapper
**Infrastructure**: EF Core, HttpClient, Azure SDKs
**WebApi**: ASP.NET Core

### Good Signs
- Domain project references no other projects
- Application defines interfaces, Infrastructure implements
- No circular project references
- Clear separation of concerns

### Warning Signs
- Domain references Infrastructure
- DbContext exposed outside Infrastructure
- Controllers with business logic
- Shared project with everything

---

## 2. Dependency Injection Architecture

### Composition Root

```csharp
// GOOD: Organize registrations by layer
public static class DependencyInjection
{
    public static IServiceCollection AddApplication(this IServiceCollection services)
    {
        services.AddMediatR(cfg => cfg.RegisterServicesFromAssembly(typeof(DependencyInjection).Assembly));
        services.AddAutoMapper(typeof(DependencyInjection).Assembly);
        services.AddValidatorsFromAssembly(typeof(DependencyInjection).Assembly);

        // Register behaviors (pipeline)
        services.AddTransient(typeof(IPipelineBehavior<,>), typeof(ValidationBehavior<,>));
        services.AddTransient(typeof(IPipelineBehavior<,>), typeof(LoggingBehavior<,>));

        return services;
    }
}

// Infrastructure layer
public static class InfrastructureDependencyInjection
{
    public static IServiceCollection AddInfrastructure(
        this IServiceCollection services,
        IConfiguration configuration)
    {
        // Database
        services.AddDbContext<ApplicationDbContext>(options =>
            options.UseSqlServer(configuration.GetConnectionString("DefaultConnection")));

        // Repositories
        services.AddScoped<IOrderRepository, SqlOrderRepository>();
        services.AddScoped<IUnitOfWork, UnitOfWork>();

        // External services
        services.AddHttpClient<IPaymentGateway, StripePaymentGateway>();

        return services;
    }
}

// Program.cs - Composition root
builder.Services.AddApplication();
builder.Services.AddInfrastructure(builder.Configuration);
```

### Service Lifetime Guidance

| Lifetime | Use For | Watch Out For |
|----------|---------|---------------|
| **Singleton** | Stateless services, caches, configuration | Injecting scoped dependencies |
| **Scoped** | DbContext, unit of work, request-specific | Capturing in singletons |
| **Transient** | Lightweight, stateless utilities | Expensive to create objects |

### Captive Dependency Prevention

```csharp
// BAD: Singleton capturing scoped service
public class CachingOrderService  // Singleton
{
    private readonly IOrderRepository _repo;  // Scoped - CAPTURED!

    public CachingOrderService(IOrderRepository repo)
    {
        _repo = repo;  // This instance never released!
    }
}

// GOOD: Use IServiceScopeFactory
public class CachingOrderService  // Singleton
{
    private readonly IServiceScopeFactory _scopeFactory;

    public CachingOrderService(IServiceScopeFactory scopeFactory)
    {
        _scopeFactory = scopeFactory;
    }

    public async Task<Order> GetOrderAsync(int id)
    {
        using var scope = _scopeFactory.CreateScope();
        var repo = scope.ServiceProvider.GetRequiredService<IOrderRepository>();
        return await repo.GetByIdAsync(id);
    }
}
```

---

## 3. Resilience Patterns

### Polly Policy Configuration

```csharp
// GOOD: Centralized resilience policies
public static class ResiliencePolicies
{
    public static IAsyncPolicy<HttpResponseMessage> GetRetryPolicy()
    {
        return HttpPolicyExtensions
            .HandleTransientHttpError()
            .Or<TimeoutException>()
            .WaitAndRetryAsync(
                retryCount: 3,
                sleepDurationProvider: attempt =>
                    TimeSpan.FromSeconds(Math.Pow(2, attempt)),
                onRetry: (outcome, delay, attempt, context) =>
                {
                    Log.Warning(
                        "Retry {Attempt} after {Delay}s due to {Error}",
                        attempt, delay.TotalSeconds, outcome.Exception?.Message);
                });
    }

    public static IAsyncPolicy<HttpResponseMessage> GetCircuitBreakerPolicy()
    {
        return HttpPolicyExtensions
            .HandleTransientHttpError()
            .CircuitBreakerAsync(
                handledEventsAllowedBeforeBreaking: 5,
                durationOfBreak: TimeSpan.FromSeconds(30),
                onBreak: (result, duration) =>
                    Log.Warning("Circuit broken for {Duration}s", duration.TotalSeconds),
                onReset: () => Log.Information("Circuit reset"),
                onHalfOpen: () => Log.Information("Circuit half-open"));
    }

    public static IAsyncPolicy<HttpResponseMessage> GetTimeoutPolicy()
    {
        return Policy.TimeoutAsync<HttpResponseMessage>(
            TimeSpan.FromSeconds(10),
            TimeoutStrategy.Optimistic);
    }
}
```

### HttpClientFactory Integration

```csharp
// GOOD: Named client with policies
services.AddHttpClient("PaymentApi", client =>
{
    client.BaseAddress = new Uri(configuration["PaymentApi:BaseUrl"]!);
    client.DefaultRequestHeaders.Add("Accept", "application/json");
})
.AddPolicyHandler(ResiliencePolicies.GetRetryPolicy())
.AddPolicyHandler(ResiliencePolicies.GetCircuitBreakerPolicy())
.AddPolicyHandler(ResiliencePolicies.GetTimeoutPolicy());

// GOOD: Typed client
services.AddHttpClient<IPaymentGateway, StripePaymentGateway>()
    .AddPolicyHandler(ResiliencePolicies.GetRetryPolicy());
```

### Bulkhead Isolation

```csharp
// GOOD: Isolate failure domains
services.AddHttpClient("CriticalApi")
    .AddPolicyHandler(Policy.BulkheadAsync<HttpResponseMessage>(
        maxParallelization: 10,
        maxQueuingActions: 100));

services.AddHttpClient("NonCriticalApi")
    .AddPolicyHandler(Policy.BulkheadAsync<HttpResponseMessage>(
        maxParallelization: 5,
        maxQueuingActions: 20));
```

### Health Checks

```csharp
// GOOD: Comprehensive health checks
services.AddHealthChecks()
    .AddDbContextCheck<ApplicationDbContext>("database")
    .AddRedis(configuration["Redis:ConnectionString"]!, "redis")
    .AddUrlGroup(new Uri(configuration["PaymentApi:HealthUrl"]!), "payment-api")
    .AddCheck<CustomHealthCheck>("custom");

app.MapHealthChecks("/health/ready", new HealthCheckOptions
{
    Predicate = check => check.Tags.Contains("ready")
});

app.MapHealthChecks("/health/live", new HealthCheckOptions
{
    Predicate = _ => false  // Just check if app responds
});
```

---

## 4. Observability

### Serilog Configuration

```csharp
// GOOD: Structured logging with Serilog
Log.Logger = new LoggerConfiguration()
    .MinimumLevel.Information()
    .MinimumLevel.Override("Microsoft", LogEventLevel.Warning)
    .MinimumLevel.Override("Microsoft.Hosting.Lifetime", LogEventLevel.Information)
    .Enrich.FromLogContext()
    .Enrich.WithMachineName()
    .Enrich.WithEnvironmentName()
    .Enrich.WithProperty("Application", "MyApp")
    .WriteTo.Console(new JsonFormatter())
    .WriteTo.Seq(configuration["Seq:ServerUrl"]!)
    .CreateLogger();

builder.Host.UseSerilog();
```

### Correlation ID Propagation

```csharp
// GOOD: Middleware for correlation
public class CorrelationIdMiddleware
{
    private const string Header = "X-Correlation-ID";
    private readonly RequestDelegate _next;

    public async Task InvokeAsync(HttpContext context)
    {
        var correlationId = context.Request.Headers[Header].FirstOrDefault()
            ?? Activity.Current?.Id
            ?? Guid.NewGuid().ToString();

        context.Items["CorrelationId"] = correlationId;
        context.Response.Headers[Header] = correlationId;

        using (LogContext.PushProperty("CorrelationId", correlationId))
        {
            await _next(context);
        }
    }
}

// GOOD: Propagate to outbound requests
services.AddHttpClient("ExternalApi")
    .AddHttpMessageHandler<CorrelationIdDelegatingHandler>();

public class CorrelationIdDelegatingHandler : DelegatingHandler
{
    private readonly IHttpContextAccessor _accessor;

    protected override Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken cancellationToken)
    {
        if (_accessor.HttpContext?.Items["CorrelationId"] is string correlationId)
        {
            request.Headers.Add("X-Correlation-ID", correlationId);
        }
        return base.SendAsync(request, cancellationToken);
    }
}
```

### OpenTelemetry Setup

```csharp
// GOOD: Full observability with OpenTelemetry
builder.Services.AddOpenTelemetry()
    .ConfigureResource(resource => resource.AddService("MyApp"))
    .WithTracing(tracing => tracing
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddEntityFrameworkCoreInstrumentation()
        .AddSource("MyApp.Activities")
        .AddOtlpExporter())
    .WithMetrics(metrics => metrics
        .AddAspNetCoreInstrumentation()
        .AddHttpClientInstrumentation()
        .AddRuntimeInstrumentation()
        .AddMeter("MyApp.Metrics")
        .AddOtlpExporter());
```

### Custom Metrics

```csharp
// GOOD: Business metrics
public class OrderMetrics
{
    private static readonly Meter Meter = new("MyApp.Orders", "1.0.0");

    private static readonly Counter<int> OrdersCreated =
        Meter.CreateCounter<int>("orders_created_total");

    private static readonly Histogram<double> OrderProcessingDuration =
        Meter.CreateHistogram<double>("order_processing_duration_seconds");

    private static readonly ObservableGauge<int> PendingOrders;

    public void RecordOrderCreated(string region, string type)
    {
        OrdersCreated.Add(1,
            new("region", region),
            new("type", type));
    }

    public IDisposable MeasureProcessing()
    {
        var sw = Stopwatch.StartNew();
        return new DisposableAction(() =>
            OrderProcessingDuration.Record(sw.Elapsed.TotalSeconds));
    }
}
```

---

## 5. API Design

### Versioning Strategy

```csharp
// GOOD: URL path versioning
services.AddApiVersioning(options =>
{
    options.DefaultApiVersion = new ApiVersion(1, 0);
    options.AssumeDefaultVersionWhenUnspecified = true;
    options.ReportApiVersions = true;
    options.ApiVersionReader = new UrlSegmentApiVersionReader();
});

[ApiController]
[ApiVersion("1.0")]
[Route("api/v{version:apiVersion}/[controller]")]
public class OrdersController : ControllerBase { }

// V2 with breaking changes
[ApiController]
[ApiVersion("2.0")]
[Route("api/v{version:apiVersion}/[controller]")]
public class OrdersV2Controller : ControllerBase { }
```

### Problem Details (RFC 7807)

```csharp
// GOOD: Consistent error responses
builder.Services.AddProblemDetails(options =>
{
    options.CustomizeProblemDetails = context =>
    {
        context.ProblemDetails.Extensions["traceId"] =
            Activity.Current?.Id ?? context.HttpContext.TraceIdentifier;
        context.ProblemDetails.Extensions["instance"] =
            context.HttpContext.Request.Path;
    };
});

// GOOD: Exception handler producing Problem Details
public class GlobalExceptionHandler : IExceptionHandler
{
    public async ValueTask<bool> TryHandleAsync(
        HttpContext context,
        Exception exception,
        CancellationToken ct)
    {
        var problem = exception switch
        {
            ValidationException ex => new ProblemDetails
            {
                Type = "https://api.example.com/errors/validation",
                Title = "Validation Failed",
                Status = StatusCodes.Status400BadRequest,
                Detail = ex.Message,
                Extensions = { ["errors"] = ex.Errors }
            },
            NotFoundException ex => new ProblemDetails
            {
                Type = "https://api.example.com/errors/not-found",
                Title = "Resource Not Found",
                Status = StatusCodes.Status404NotFound,
                Detail = ex.Message
            },
            ConflictException ex => new ProblemDetails
            {
                Type = "https://api.example.com/errors/conflict",
                Title = "Conflict",
                Status = StatusCodes.Status409Conflict,
                Detail = ex.Message
            },
            _ => new ProblemDetails
            {
                Type = "https://api.example.com/errors/internal",
                Title = "Internal Server Error",
                Status = StatusCodes.Status500InternalServerError
            }
        };

        context.Response.StatusCode = problem.Status ?? 500;
        await context.Response.WriteAsJsonAsync(problem, ct);
        return true;
    }
}
```

### Request/Response Models

```csharp
// GOOD: Separate input/output models
public record CreateOrderRequest
{
    [Required]
    public int CustomerId { get; init; }

    [Required, MinLength(1)]
    public List<OrderItemRequest> Items { get; init; } = new();

    public string? Notes { get; init; }
}

public record OrderResponse
{
    public int Id { get; init; }
    public string Status { get; init; } = string.Empty;
    public decimal Total { get; init; }
    public DateTime CreatedAt { get; init; }
    public List<OrderItemResponse> Items { get; init; } = new();

    // HATEOAS links
    public Dictionary<string, string> Links { get; init; } = new();
}
```

---

## 6. Configuration Management

### Options Pattern with Validation

```csharp
// GOOD: Strongly-typed, validated configuration
public class DatabaseSettings
{
    public const string Section = "Database";

    [Required]
    public string ConnectionString { get; set; } = string.Empty;

    [Range(1, 100)]
    public int MaxPoolSize { get; set; } = 10;

    [Range(1, 300)]
    public int CommandTimeoutSeconds { get; set; } = 30;

    public bool EnableSensitiveDataLogging { get; set; } = false;
}

// Registration with validation
services.AddOptions<DatabaseSettings>()
    .Bind(configuration.GetSection(DatabaseSettings.Section))
    .ValidateDataAnnotations()
    .ValidateOnStart();

// Custom validation
services.AddOptions<DatabaseSettings>()
    .Bind(configuration.GetSection(DatabaseSettings.Section))
    .Validate(settings =>
    {
        if (settings.EnableSensitiveDataLogging &&
            !builder.Environment.IsDevelopment())
        {
            return false;
        }
        return true;
    }, "Sensitive data logging only allowed in Development");
```

### Secret Management

```csharp
// GOOD: Development - User Secrets
// dotnet user-secrets set "Database:Password" "dev-password"

// GOOD: Production - Azure Key Vault
builder.Configuration.AddAzureKeyVault(
    new Uri($"https://{builder.Configuration["KeyVault:Name"]}.vault.azure.net/"),
    new DefaultAzureCredential());

// GOOD: Key Vault reference in App Service
// @Microsoft.KeyVault(VaultName=myvault;SecretName=DbPassword)

// Configuration hierarchy (last wins)
builder.Configuration
    .AddJsonFile("appsettings.json")
    .AddJsonFile($"appsettings.{env.EnvironmentName}.json", optional: true)
    .AddEnvironmentVariables()
    .AddUserSecrets<Program>(optional: true)
    .AddAzureKeyVault(...);
```

### Environment-Specific Configuration

```csharp
// appsettings.Development.json
{
    "Logging": { "LogLevel": { "Default": "Debug" } },
    "Database": { "EnableSensitiveDataLogging": true }
}

// appsettings.Production.json
{
    "Logging": { "LogLevel": { "Default": "Warning" } },
    "Database": { "MaxPoolSize": 50 }
}

// GOOD: Feature flags per environment
services.AddFeatureManagement(configuration.GetSection("FeatureFlags"));
```

---

## 7. Database Architecture

### DbContext Configuration

```csharp
// GOOD: Separate read/write contexts (CQRS)
public class WriteDbContext : DbContext
{
    public DbSet<Order> Orders => Set<Order>();
    public DbSet<Customer> Customers => Set<Customer>();

    protected override void OnModelCreating(ModelBuilder modelBuilder)
    {
        modelBuilder.ApplyConfigurationsFromAssembly(typeof(WriteDbContext).Assembly);
    }
}

public class ReadDbContext : DbContext
{
    protected override void OnConfiguring(DbContextOptionsBuilder optionsBuilder)
    {
        optionsBuilder.UseQueryTrackingBehavior(QueryTrackingBehavior.NoTracking);
    }
}
```

### Repository Pattern

```csharp
// GOOD: Generic repository with specifications
public interface IRepository<T> where T : class, IAggregateRoot
{
    Task<T?> GetByIdAsync(int id, CancellationToken ct = default);
    Task<T?> GetBySpecAsync(ISpecification<T> spec, CancellationToken ct = default);
    Task<List<T>> ListAsync(ISpecification<T> spec, CancellationToken ct = default);
    Task AddAsync(T entity, CancellationToken ct = default);
    void Update(T entity);
    void Remove(T entity);
}

// GOOD: Unit of Work
public interface IUnitOfWork
{
    IOrderRepository Orders { get; }
    ICustomerRepository Customers { get; }
    Task<int> SaveChangesAsync(CancellationToken ct = default);
}
```

### Migration Strategy

```csharp
// GOOD: Apply migrations at startup (with caution)
if (app.Environment.IsDevelopment())
{
    using var scope = app.Services.CreateScope();
    var db = scope.ServiceProvider.GetRequiredService<ApplicationDbContext>();
    await db.Database.MigrateAsync();
}

// GOOD: For production - separate migration deployment
// Use DbUp, FluentMigrator, or manual scripts via CI/CD

// BAD: EnsureCreated in production (doesn't run migrations)
context.Database.EnsureCreated(); // Don't use in production!
```

---

## 8. Middleware Pipeline

### Pipeline Order

```csharp
// GOOD: Correct middleware ordering
var app = builder.Build();

// 1. Exception handling (first - catches all)
app.UseExceptionHandler();

// 2. HTTPS redirection
app.UseHttpsRedirection();

// 3. Static files (before routing)
app.UseStaticFiles();

// 4. Routing
app.UseRouting();

// 5. CORS (after routing, before auth)
app.UseCors("MyPolicy");

// 6. Authentication (before authorization)
app.UseAuthentication();

// 7. Authorization
app.UseAuthorization();

// 8. Custom middleware
app.UseMiddleware<CorrelationIdMiddleware>();

// 9. Endpoints
app.MapControllers();
app.MapHealthChecks("/health");
```

### Custom Middleware

```csharp
// GOOD: Request timing middleware
public class RequestTimingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<RequestTimingMiddleware> _logger;

    public async Task InvokeAsync(HttpContext context)
    {
        var sw = Stopwatch.StartNew();

        try
        {
            await _next(context);
        }
        finally
        {
            sw.Stop();
            _logger.LogInformation(
                "Request {Method} {Path} completed in {ElapsedMs}ms with status {StatusCode}",
                context.Request.Method,
                context.Request.Path,
                sw.ElapsedMilliseconds,
                context.Response.StatusCode);
        }
    }
}
```

---

## 9. Background Services

### Hosted Service Pattern

```csharp
// GOOD: Background processing with proper shutdown
public class OrderProcessingService : BackgroundService
{
    private readonly IServiceScopeFactory _scopeFactory;
    private readonly ILogger<OrderProcessingService> _logger;

    protected override async Task ExecuteAsync(CancellationToken stoppingToken)
    {
        _logger.LogInformation("Order processing service starting");

        while (!stoppingToken.IsCancellationRequested)
        {
            try
            {
                using var scope = _scopeFactory.CreateScope();
                var processor = scope.ServiceProvider
                    .GetRequiredService<IOrderProcessor>();

                await processor.ProcessPendingOrdersAsync(stoppingToken);

                await Task.Delay(TimeSpan.FromSeconds(30), stoppingToken);
            }
            catch (OperationCanceledException) when (stoppingToken.IsCancellationRequested)
            {
                // Graceful shutdown
                break;
            }
            catch (Exception ex)
            {
                _logger.LogError(ex, "Error processing orders");
                await Task.Delay(TimeSpan.FromMinutes(1), stoppingToken);
            }
        }

        _logger.LogInformation("Order processing service stopped");
    }
}
```

### Queue Processing

```csharp
// GOOD: Channel-based producer/consumer
public class BackgroundTaskQueue
{
    private readonly Channel<Func<CancellationToken, Task>> _queue;

    public BackgroundTaskQueue(int capacity = 100)
    {
        _queue = Channel.CreateBounded<Func<CancellationToken, Task>>(
            new BoundedChannelOptions(capacity)
            {
                FullMode = BoundedChannelFullMode.Wait
            });
    }

    public async ValueTask QueueAsync(
        Func<CancellationToken, Task> workItem,
        CancellationToken ct = default)
    {
        await _queue.Writer.WriteAsync(workItem, ct);
    }

    public async ValueTask<Func<CancellationToken, Task>> DequeueAsync(
        CancellationToken ct)
    {
        return await _queue.Reader.ReadAsync(ct);
    }
}
```

---

## 10. Security Architecture

### Authentication Setup

```csharp
// GOOD: JWT authentication
services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Authority = configuration["Auth:Authority"];
        options.Audience = configuration["Auth:Audience"];
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateIssuer = true,
            ValidateAudience = true,
            ValidateLifetime = true,
            ClockSkew = TimeSpan.Zero
        };
    });

// GOOD: Policy-based authorization
services.AddAuthorization(options =>
{
    options.AddPolicy("AdminOnly", policy =>
        policy.RequireRole("Admin"));

    options.AddPolicy("CanEditOrders", policy =>
        policy.RequireClaim("permission", "orders:write"));

    options.AddPolicy("SameOrganization", policy =>
        policy.Requirements.Add(new SameOrganizationRequirement()));
});
```

### CORS Configuration

```csharp
// GOOD: Explicit CORS policy
services.AddCors(options =>
{
    options.AddPolicy("Production", builder =>
    {
        builder
            .WithOrigins(
                "https://app.example.com",
                "https://admin.example.com")
            .WithMethods("GET", "POST", "PUT", "DELETE")
            .WithHeaders("Authorization", "Content-Type")
            .AllowCredentials();
    });

    options.AddPolicy("Development", builder =>
    {
        builder
            .AllowAnyOrigin()
            .AllowAnyMethod()
            .AllowAnyHeader();
    });
});

// BAD: Allow everything in production
app.UseCors(builder => builder.AllowAnyOrigin()); // DANGEROUS!
```

### Rate Limiting

```csharp
// GOOD: Rate limiting (.NET 7+)
services.AddRateLimiter(options =>
{
    options.GlobalLimiter = PartitionedRateLimiter.Create<HttpContext, string>(context =>
        RateLimitPartition.GetFixedWindowLimiter(
            partitionKey: context.User.Identity?.Name ?? context.Request.Headers.Host.ToString(),
            factory: _ => new FixedWindowRateLimiterOptions
            {
                PermitLimit = 100,
                Window = TimeSpan.FromMinutes(1)
            }));

    options.AddPolicy("Api", context =>
        RateLimitPartition.GetTokenBucketLimiter(
            partitionKey: context.User.Identity?.Name ?? "anonymous",
            factory: _ => new TokenBucketRateLimiterOptions
            {
                TokenLimit = 100,
                ReplenishmentPeriod = TimeSpan.FromSeconds(10),
                TokensPerPeriod = 10
            }));
});

app.UseRateLimiter();
```

---

## 11. Concurrency Architecture

### Concurrency Model Selection

| Model | Use When | .NET Implementation |
|-------|----------|---------------------|
| **Async/Await** | I/O-bound work, web requests | `async`/`await`, `Task` |
| **Parallel Processing** | CPU-bound, data parallelism | `Parallel.ForEach`, PLINQ |
| **Channel-Based** | Producer/consumer, pipelines | `System.Threading.Channels` |
| **Actor Model** | Message passing, isolation | Akka.NET, Orleans, Proto.Actor |
| **Dataflow** | Complex pipelines, buffering | `System.Threading.Tasks.Dataflow` |

### Thread Pool Configuration

```csharp
// GOOD: Configure thread pool for high-throughput scenarios
// Only adjust if you've measured and identified bottlenecks
ThreadPool.SetMinThreads(
    workerThreads: Environment.ProcessorCount * 2,
    completionPortThreads: Environment.ProcessorCount);

// GOOD: Monitor thread pool health
public class ThreadPoolHealthCheck : IHealthCheck
{
    public Task<HealthCheckResult> CheckHealthAsync(
        HealthCheckContext context,
        CancellationToken ct = default)
    {
        ThreadPool.GetAvailableThreads(out int workers, out int io);
        ThreadPool.GetMaxThreads(out int maxWorkers, out int maxIo);

        var workerUtilization = 1.0 - ((double)workers / maxWorkers);
        var ioUtilization = 1.0 - ((double)io / maxIo);

        if (workerUtilization > 0.9 || ioUtilization > 0.9)
        {
            return Task.FromResult(HealthCheckResult.Degraded(
                $"Thread pool exhaustion: Workers={workerUtilization:P0}, IO={ioUtilization:P0}"));
        }

        return Task.FromResult(HealthCheckResult.Healthy());
    }
}
```

### Channel-Based Architecture

```csharp
// GOOD: Producer/consumer with backpressure
public class OrderPipeline
{
    private readonly Channel<Order> _incomingOrders;
    private readonly Channel<Order> _validatedOrders;
    private readonly Channel<Order> _processedOrders;

    public OrderPipeline(int boundedCapacity = 1000)
    {
        var options = new BoundedChannelOptions(boundedCapacity)
        {
            FullMode = BoundedChannelFullMode.Wait,  // Backpressure
            SingleReader = false,
            SingleWriter = false
        };

        _incomingOrders = Channel.CreateBounded<Order>(options);
        _validatedOrders = Channel.CreateBounded<Order>(options);
        _processedOrders = Channel.CreateBounded<Order>(options);
    }

    public async Task StartPipelineAsync(CancellationToken ct)
    {
        // Multiple consumers for each stage
        var validationTasks = Enumerable.Range(0, 4)
            .Select(_ => ValidateOrdersAsync(ct));

        var processingTasks = Enumerable.Range(0, 8)
            .Select(_ => ProcessOrdersAsync(ct));

        await Task.WhenAll(
            Task.WhenAll(validationTasks),
            Task.WhenAll(processingTasks));
    }

    private async Task ValidateOrdersAsync(CancellationToken ct)
    {
        await foreach (var order in _incomingOrders.Reader.ReadAllAsync(ct))
        {
            if (await ValidateAsync(order))
            {
                await _validatedOrders.Writer.WriteAsync(order, ct);
            }
        }
    }
}
```

### Parallel Processing Strategies

```csharp
// GOOD: Parallel.ForEachAsync for async operations (.NET 6+)
await Parallel.ForEachAsync(
    items,
    new ParallelOptions
    {
        MaxDegreeOfParallelism = Environment.ProcessorCount,
        CancellationToken = ct
    },
    async (item, token) =>
    {
        await ProcessItemAsync(item, token);
    });

// GOOD: Partitioning for CPU-bound work
var partitioner = Partitioner.Create(items, loadBalance: true);
Parallel.ForEach(
    partitioner,
    new ParallelOptions { MaxDegreeOfParallelism = Environment.ProcessorCount },
    item => ProcessCpuBound(item));

// GOOD: PLINQ for data transformations
var results = items
    .AsParallel()
    .WithDegreeOfParallelism(Environment.ProcessorCount)
    .WithCancellation(ct)
    .Where(item => item.IsValid)
    .Select(item => Transform(item))
    .ToList();
```

### Semaphore-Based Throttling

```csharp
// GOOD: Limit concurrent external calls
public class ThrottledHttpClient
{
    private readonly HttpClient _client;
    private readonly SemaphoreSlim _semaphore;

    public ThrottledHttpClient(HttpClient client, int maxConcurrent = 10)
    {
        _client = client;
        _semaphore = new SemaphoreSlim(maxConcurrent, maxConcurrent);
    }

    public async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken ct = default)
    {
        await _semaphore.WaitAsync(ct);
        try
        {
            return await _client.SendAsync(request, ct);
        }
        finally
        {
            _semaphore.Release();
        }
    }
}

// GOOD: Per-resource throttling
public class ResourceThrottler
{
    private readonly ConcurrentDictionary<string, SemaphoreSlim> _semaphores = new();

    public async Task<T> ExecuteAsync<T>(
        string resourceKey,
        int maxConcurrent,
        Func<Task<T>> operation,
        CancellationToken ct = default)
    {
        var semaphore = _semaphores.GetOrAdd(
            resourceKey,
            _ => new SemaphoreSlim(maxConcurrent, maxConcurrent));

        await semaphore.WaitAsync(ct);
        try
        {
            return await operation();
        }
        finally
        {
            semaphore.Release();
        }
    }
}
```

### Dataflow Pipelines

```csharp
// GOOD: TPL Dataflow for complex processing pipelines
using System.Threading.Tasks.Dataflow;

public class ImageProcessingPipeline
{
    private readonly TransformBlock<string, byte[]> _downloadBlock;
    private readonly TransformBlock<byte[], Image> _decodeBlock;
    private readonly TransformBlock<Image, Image> _resizeBlock;
    private readonly ActionBlock<Image> _saveBlock;

    public ImageProcessingPipeline()
    {
        var options = new ExecutionDataflowBlockOptions
        {
            MaxDegreeOfParallelism = Environment.ProcessorCount,
            BoundedCapacity = 100  // Backpressure
        };

        _downloadBlock = new TransformBlock<string, byte[]>(
            url => DownloadAsync(url), options);

        _decodeBlock = new TransformBlock<byte[], Image>(
            bytes => DecodeImage(bytes), options);

        _resizeBlock = new TransformBlock<Image, Image>(
            image => ResizeImage(image), options);

        _saveBlock = new ActionBlock<Image>(
            image => SaveImage(image), options);

        // Link the pipeline
        var linkOptions = new DataflowLinkOptions { PropagateCompletion = true };
        _downloadBlock.LinkTo(_decodeBlock, linkOptions);
        _decodeBlock.LinkTo(_resizeBlock, linkOptions);
        _resizeBlock.LinkTo(_saveBlock, linkOptions);
    }

    public async Task ProcessAsync(IEnumerable<string> urls)
    {
        foreach (var url in urls)
        {
            await _downloadBlock.SendAsync(url);
        }

        _downloadBlock.Complete();
        await _saveBlock.Completion;
    }
}
```

### Actor Model with Channels

```csharp
// GOOD: Simple actor pattern using channels
public abstract class Actor<TMessage>
{
    private readonly Channel<TMessage> _mailbox;
    private readonly Task _processingTask;

    protected Actor(int capacity = 1000)
    {
        _mailbox = Channel.CreateBounded<TMessage>(capacity);
        _processingTask = ProcessMessagesAsync();
    }

    public ValueTask SendAsync(TMessage message, CancellationToken ct = default)
        => _mailbox.Writer.WriteAsync(message, ct);

    protected abstract Task HandleAsync(TMessage message);

    private async Task ProcessMessagesAsync()
    {
        await foreach (var message in _mailbox.Reader.ReadAllAsync())
        {
            try
            {
                await HandleAsync(message);
            }
            catch (Exception ex)
            {
                // Log and continue - actor doesn't die from message errors
                OnError(ex, message);
            }
        }
    }

    protected virtual void OnError(Exception ex, TMessage message) { }
}

// Usage
public class OrderActor : Actor<OrderCommand>
{
    private readonly Dictionary<int, Order> _orders = new();

    protected override Task HandleAsync(OrderCommand command)
    {
        return command switch
        {
            CreateOrder create => HandleCreate(create),
            UpdateOrder update => HandleUpdate(update),
            _ => Task.CompletedTask
        };
    }
}
```

### Concurrency Anti-Patterns

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| **Unbounded Parallelism** | Thread pool exhaustion | Use `MaxDegreeOfParallelism` |
| **Fire and Forget** | Lost errors, resource leaks | Track tasks, handle errors |
| **Sync over Async** | Deadlocks, thread starvation | Async all the way |
| **Shared Mutable State** | Race conditions | Channels, actors, immutability |
| **No Backpressure** | Memory exhaustion | Bounded channels/queues |
| **Global Locks** | Contention, deadlocks | Fine-grained, lock-free structures |

---

## Anti-Patterns Summary

| Anti-Pattern | Problem | Solution |
|--------------|---------|----------|
| **God Controller** | Controller with all logic | Extract to services/handlers |
| **Anemic Services** | Services just calling repos | Add domain logic to entities |
| **DbContext Everywhere** | Direct DbContext in controllers | Repository + Unit of Work |
| **Config Sprawl** | Settings all over | Options pattern, validated |
| **Sync over Async** | .Result, .Wait() | Async all the way |
| **Missing Resilience** | No retry/timeout | Polly policies |
| **Log and Pray** | Unstructured logging | Structured logging + correlation |
| **Any Origin CORS** | Allow all origins | Explicit allowed origins |
| **Unbounded Parallelism** | Thread exhaustion | Bounded concurrency |

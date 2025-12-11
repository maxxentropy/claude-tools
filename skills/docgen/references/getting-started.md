# Getting Started Documentation Template

## Required Context

Before writing, gather:
1. Output from `scan_dotnet.py` (frameworks, target framework)
2. Configuration files: appsettings.json, docker-compose.yml
3. Program.cs/Startup.cs entry point

## Document Structure

```markdown
# Getting Started

## Prerequisites

- [.NET X SDK](https://dotnet.microsoft.com/download)
- [Additional requirements from analysis]

### Verify Prerequisites
```bash
dotnet --version
# Should output: X.0.x or higher
```

## Installation

### 1. Clone Repository
```bash
git clone https://github.com/[org]/[repo].git
cd [repo]
```

### 2. Restore Dependencies
```bash
dotnet restore
```

### 3. Build
```bash
dotnet build
```

## Configuration

Copy example config:
```bash
cp src/[Project]/appsettings.example.json src/[Project]/appsettings.json
```

Required settings:
| Setting | Description | Example |
|---------|-------------|---------|
| ConnectionStrings:Default | Database | Server=localhost;... |

Environment variables:
```bash
export DATABASE_CONNECTION="..."
```

## Running the Application

```bash
cd src/[MainProject]
dotnet run
```

Expected output:
```
Now listening on: https://localhost:5001
Application started.
```

Verify: Open https://localhost:5001/swagger

## Quick Start Example

[Simple usage example appropriate to project type]

## Running Tests

```bash
dotnet test
```

## Common Issues

### Port in Use
```bash
dotnet run --urls "https://localhost:5002"
```

### SSL Certificate
```bash
dotnet dev-certs https --trust
```

## Next Steps

- [Architecture Overview](architecture/overview.md)
- [API Reference](api/README.md)
```

## Quality Checklist

- [ ] Prerequisites match TargetFramework
- [ ] Commands tested
- [ ] Config examples realistic (no real secrets)
- [ ] Port numbers match configuration
- [ ] Common issues based on real problems

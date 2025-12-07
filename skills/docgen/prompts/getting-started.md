# Getting Started Documentation Prompt

Use this prompt structure when generating onboarding/getting started documentation.

## Context to Gather First

Before writing, ensure you have:
1. Output from `scan_dotnet.py` (frameworks, target frameworks)
2. Contents of:
   - README.md (existing)
   - Program.cs / Startup.cs
   - appsettings.json or configuration files
   - Any docker-compose.yml or Dockerfile
3. Solution structure and main entry point project

## Prompt Template

```
Based on my analysis of this .NET codebase, generate a Getting Started guide for new developers.

## Codebase Analysis Results
[Paste scan_dotnet.py JSON output]

## Configuration Files
[Paste appsettings.json, docker-compose.yml, etc.]

## Entry Point Code
[Paste Program.cs or relevant startup code]

## Requirements for the Document

1. **Prerequisites Section**
   - Required SDK version (from TargetFramework)
   - Required tools (Docker, database, etc.)
   - IDE recommendations
   - Any external dependencies

2. **Installation Steps**
   - Clone command
   - Package restore
   - Build verification

3. **Configuration**
   - Required environment variables
   - Configuration file explanations
   - Secrets management (if applicable)
   - Connection strings (patterns, not actual values)

4. **Running the Application**
   - Command to run
   - Expected startup output
   - How to verify it's working
   - Debug vs Release considerations

5. **Quick Start Example**
   - A simple "hello world" style example
   - First API call or basic usage
   - Expected output

6. **Common Issues**
   - Known setup problems and solutions
   - Platform-specific notes (Windows/Mac/Linux)
   - Port conflicts
   - Permission issues

7. **Next Steps**
   - Links to other documentation
   - Key concepts to understand
   - Recommended reading order

## Output Format
- Clear numbered steps for procedures
- Code blocks for all commands
- Callout boxes for warnings/tips
- Screenshots or terminal output examples where helpful
```

## Template Structure

```markdown
# Getting Started

This guide will help you set up and run [Project Name] on your local machine.

## Prerequisites

Before you begin, ensure you have the following installed:

- [.NET 8 SDK](https://dotnet.microsoft.com/download) (or later)
- [Additional requirement]
- [Additional requirement]

### Verify Prerequisites

```bash
dotnet --version
# Should output: 8.0.x or higher
```

## Installation

### 1. Clone the Repository

```bash
git clone https://github.com/[org]/[repo].git
cd [repo]
```

### 2. Restore Dependencies

```bash
dotnet restore
```

### 3. Build the Solution

```bash
dotnet build
```

You should see output ending with:
```
Build succeeded.
    0 Warning(s)
    0 Error(s)
```

## Configuration

### Required Configuration

Copy the example configuration file:

```bash
cp src/[Project]/appsettings.example.json src/[Project]/appsettings.json
```

Update the following settings:

| Setting | Description | Example |
|---------|-------------|---------|
| `ConnectionStrings:Default` | Database connection | `Server=localhost;...` |
| `ApiKey` | External service key | `your-key-here` |

### Environment Variables

For sensitive configuration, use environment variables:

```bash
export DATABASE_CONNECTION="Server=localhost;..."
export API_KEY="your-key-here"
```

## Running the Application

### Development Mode

```bash
cd src/[MainProject]
dotnet run
```

Expected output:
```
info: Microsoft.Hosting.Lifetime[14]
      Now listening on: https://localhost:5001
      Now listening on: http://localhost:5000
info: Microsoft.Hosting.Lifetime[0]
      Application started. Press Ctrl+C to shut down.
```

### Verify It's Working

Open your browser to: `https://localhost:5001/swagger`

Or test with curl:
```bash
curl https://localhost:5001/api/health
```

## Quick Start Example

[Provide a simple example appropriate to the project type]

### For an API:
```bash
# Create a new resource
curl -X POST https://localhost:5001/api/[resource] \
  -H "Content-Type: application/json" \
  -d '{"name": "Test"}'

# Expected response:
# {"id": 1, "name": "Test"}
```

### For a Library:
```csharp
using [Namespace];

var client = new [MainClass]();
var result = await client.DoSomethingAsync();
Console.WriteLine(result);
```

## Running Tests

```bash
dotnet test
```

## Common Issues

### Port Already in Use

If you see `Address already in use`, change the port in `launchSettings.json` or use:

```bash
dotnet run --urls "https://localhost:5002"
```

### Database Connection Failed

Ensure your database is running and the connection string is correct:

```bash
# For Docker-based databases:
docker-compose up -d database
```

### SSL Certificate Errors

For development, trust the .NET dev certificate:

```bash
dotnet dev-certs https --trust
```

## Next Steps

- Read the [Architecture Overview](architecture/overview.md)
- Explore the [API Reference](api/README.md)
- Review the [Domain Model](domain/models.md)

## Getting Help

- Check existing [GitHub Issues](https://github.com/[org]/[repo]/issues)
- Review the [FAQ](faq.md)
- Contact the team at [contact info]
```

## Quality Checklist

Before finalizing getting started documentation, verify:

- [ ] Prerequisites match actual requirements (TargetFramework)
- [ ] All commands have been tested
- [ ] Configuration examples are realistic
- [ ] Sensitive values are placeholder, not real
- [ ] Port numbers match actual configuration
- [ ] Links to other docs are correct
- [ ] Common issues are based on real problems

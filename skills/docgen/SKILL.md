# Documentation Generator Skill

Generate comprehensive documentation for .NET/C# codebases.

## When to Use

Use this skill when asked to:
- Generate documentation for a codebase
- Document a .NET project or solution
- Create architecture documentation
- Document APIs or domain models
- Create a getting started guide

## Prerequisites

The following scripts must be available:
- `~/.claude/skills/docgen/scripts/scan_dotnet.py` - Codebase scanner
- `~/.claude/skills/docgen/scripts/find_endpoints.py` - API endpoint extractor

## Workflow

### Phase 1: Analysis

#### Step 1.1: Scan the Codebase Structure

```bash
python3 ~/.claude/skills/docgen/scripts/scan_dotnet.py /path/to/codebase
```

This outputs JSON with:
- Solution and project structure
- Target frameworks
- Package references (NuGet)
- Project references (dependencies)
- Detected patterns (Repository, CQRS, DDD, MediatR, etc.)
- Namespace organization
- File counts and lines of code

#### Step 1.2: Extract API Endpoints (if web project)

```bash
python3 ~/.claude/skills/docgen/scripts/find_endpoints.py /path/to/codebase
```

This outputs JSON with:
- Controllers and their base routes
- All HTTP endpoints (GET, POST, PUT, DELETE, PATCH)
- Route templates
- Parameters and their sources (body, query, route)
- Response types

#### Step 1.3: Identify Key Files to Read

Based on the scan results, identify files to read for deeper understanding:

**Always read:**
- README.md (if exists) - understand existing documentation
- CLAUDE.md (if exists) - understand project-specific context
- Main Program.cs or Startup.cs - understand configuration
- Key domain entities (in Domain or Core projects)

**For Clean Architecture projects, prioritize:**
- Domain layer: Entities, Aggregates, Value Objects
- Application layer: Commands, Queries, Handlers
- Infrastructure layer: DbContext, Repositories

**For libraries, prioritize:**
- Public API surface (public classes/interfaces)
- Extension methods
- Configuration/Options classes

### Phase 2: Planning

#### Step 2.1: Create Documentation Plan

Based on the analysis, determine which documents to generate:

| Document Type | When to Include |
|--------------|-----------------|
| Architecture Overview | Always |
| Getting Started | Always |
| API Reference | If web project with endpoints |
| Domain Model | If DDD patterns detected |
| Configuration Guide | If Options/Configuration classes found |
| Testing Guide | If test projects exist |

#### Step 2.2: Create Progress Tracker

Create a progress file in the target codebase:

```bash
mkdir -p /path/to/codebase/docs
```

Create `/path/to/codebase/docs/.docgen-progress.json`:

```json
{
  "status": "in_progress",
  "created": "2024-01-15T10:30:00Z",
  "codebase": "/path/to/codebase",
  "tasks": [
    {"id": "architecture", "name": "Architecture Overview", "status": "pending", "output": "architecture/overview.md"},
    {"id": "getting-started", "name": "Getting Started", "status": "pending", "output": "getting-started.md"},
    {"id": "api", "name": "API Reference", "status": "pending", "output": "api/README.md"}
  ]
}
```

### Phase 3: Generation

For each task in the plan:

#### Step 3.1: Read Relevant Source Files

Use the analysis to identify which files to read for each document type.

#### Step 3.2: Generate the Document

Write markdown documentation following these quality standards:

**Content Standards:**
- Start with a clear purpose statement
- Include concrete code examples from the actual codebase
- Reference specific file paths where relevant
- Use Mermaid diagrams for architecture visualization
- Define domain terms in a glossary section

**Formatting Standards:**
- Use consistent heading hierarchy (# for title, ## for sections)
- Include a table of contents for longer documents
- Keep code blocks with appropriate language hints (```csharp)
- Use tables for structured data (endpoints, configuration options)

#### Step 3.3: Write the Document

```bash
# Create directory if needed
mkdir -p /path/to/codebase/docs/architecture

# Write the document content to the file
cat > /path/to/codebase/docs/architecture/overview.md << 'EOF'
# Architecture Overview
...content...
EOF
```

#### Step 3.4: Update Progress

Update the progress tracker:
```json
{"id": "architecture", "name": "Architecture Overview", "status": "complete", "output": "architecture/overview.md"}
```

### Phase 4: Finalization

#### Step 4.1: Generate README Navigation

Create `docs/README.md` with links to all generated documents:

```markdown
# Documentation

## Contents

- [Architecture Overview](architecture/overview.md)
- [Getting Started](getting-started.md)
- [API Reference](api/README.md)
...
```

#### Step 4.2: Generate Glossary (if DDD project)

If domain terms were identified, create `docs/GLOSSARY.md` with definitions.

#### Step 4.3: Update Progress to Complete

```json
{
  "status": "complete",
  "completed": "2024-01-15T11:45:00Z",
  ...
}
```

## Document Templates

### Architecture Overview Template

```markdown
# Architecture Overview

## Purpose

[One paragraph describing what this system does and why it exists]

## High-Level Architecture

[Mermaid diagram showing major components]

## Project Structure

| Project | Purpose | Dependencies |
|---------|---------|--------------|
| ProjectName.Domain | Core business logic | None |
| ... | ... | ... |

## Key Patterns

### [Pattern Name]

[Explanation of how this pattern is used, with code example]

## Technology Stack

- **Framework**: .NET 8
- **Database**: [if applicable]
- **Messaging**: [if applicable]
...
```

### API Reference Template

```markdown
# API Reference

## Base URL

`https://localhost:5001/api`

## Authentication

[Authentication requirements if any]

## Endpoints

### [Controller Name]

#### [HTTP Method] [Route]

**Description**: [What this endpoint does]

**Parameters**:
| Name | Type | Location | Required | Description |
|------|------|----------|----------|-------------|

**Response**:
```json
{
  "example": "response"
}
```
```

### Getting Started Template

```markdown
# Getting Started

## Prerequisites

- .NET 8 SDK
- [Other requirements]

## Installation

```bash
git clone [repo]
cd [project]
dotnet restore
```

## Configuration

[Key configuration settings]

## Running the Application

```bash
dotnet run --project src/[MainProject]
```

## Quick Start Example

[Simple code example showing basic usage]
```

## Tips for Quality Documentation

1. **Be Specific**: Reference actual class names, file paths, and line numbers
2. **Show, Don't Tell**: Include real code examples from the codebase
3. **Explain the Why**: Don't just document what something does, explain why it was designed that way
4. **Keep It Current**: Note the date of generation and any known limitations
5. **Link Generously**: Cross-reference between documents
6. **Consider the Audience**: Write for developers who are new to the codebase

## Error Handling

If a script fails:
1. Check that Python 3 is available
2. Verify the path is correct and contains .NET projects
3. Check file permissions

If the codebase structure is unusual:
1. Fall back to manual file exploration
2. Document what you find, even if scripts didn't detect everything
3. Note limitations in the generated documentation

## Output Structure

```
docs/
├── README.md                 # Navigation and index
├── GLOSSARY.md              # Domain terms (if applicable)
├── .docgen-progress.json    # Progress tracking
├── architecture/
│   └── overview.md          # System architecture
├── api/
│   └── README.md            # API documentation
├── domain/
│   └── models.md            # Domain model documentation
└── getting-started.md       # Onboarding guide
```

# Documentation Generator Skill

## Purpose

Generate comprehensive documentation for .NET/C# codebases, including:
- Architecture overview
- API documentation
- Domain model documentation
- Getting started guide

## Status

🚧 **In Development** - Scripts and templates coming in next step.

## When to Use

Use this skill when asked to:
- Generate documentation for a codebase
- Document a .NET project
- Create architecture docs
- Document APIs

## Quick Reference

Once complete, this skill will provide:

1. **Scripts** (`scripts/`)
   - `scan_dotnet.py` - Scan .NET project structure
   - `find_endpoints.py` - Extract API endpoints

2. **Templates** (`templates/`)
   - Document templates for each doc type

3. **Prompts** (`prompts/`)
   - Analysis prompts to guide documentation

## Workflow (Preview)

1. Scan codebase structure
2. Create documentation plan
3. Generate each document using templates
4. Track progress in `.docgen-progress.json`
5. Output to `docs/` folder in target project

# Git Worktrees Skill

Intelligent git worktree management for parallel branch development, seamlessly integrated with the existing feature workflow.

## Overview

The **git-worktrees** skill enables developers to work on multiple branches simultaneously without the friction of stashing, committing incomplete work, or losing context. It provides a simple CLI that wraps git's powerful worktree feature with smart defaults, safety guardrails, and deep integration with Azure DevOps work items.

## Key Benefits

- **Zero Context Switching Cost** - Keep multiple branches active in separate directories
- **PR Reviews Without Disruption** - Review code while preserving uncommitted work
- **Parallel Development** - Work on multiple features simultaneously
- **Emergency Hotfixes** - Handle production issues without stopping feature work
- **Safe Experimentation** - Try risky changes in isolated worktrees
- **Long-Running Operations** - Run builds/tests while continuing development

## Quick Start

```bash
# Create worktree from work item
worktree create feature 1234
# → Creates: ../my-repo-feature-AB#1234-add-authentication/
# → Fetches title from Azure DevOps
# → Installs dependencies
# → Opens in VS Code

# Work in the worktree
cd ../my-repo-feature-AB#1234-add-authentication
git commit -am "Add login endpoint"  # AB#1234 auto-appended
feature pr  # Create pull request

# After PR merged, clean up
worktree cleanup --merged
```

## Documentation

| Document | Purpose |
|----------|---------|
| **[SKILL.md](SKILL.md)** | Claude integration guide - How Claude uses this skill |
| **[architecture.md](docs/architecture.md)** | Complete architecture, design decisions, use cases |
| **[implementation-guide.md](docs/implementation-guide.md)** | Command specs, code patterns, testing strategy |
| **User Guide** *(coming soon)* | End-user tutorials and workflows |
| **Troubleshooting** *(coming soon)* | Common issues and solutions |

## Core Commands

```bash
# Create worktrees
worktree create feature <work-item-id>    # From work item
worktree create pr <pr-id>                # For PR review
worktree create branch <branch-name>      # From branch
worktree create main [name]               # Extra main copy

# Manage worktrees
worktree list [--verbose] [--stale]       # List all
worktree status [name]                    # Detailed status
worktree open <name> [--ide code]         # Open in IDE
worktree sync [name] [--all]              # Pull latest

# Clean up
worktree remove <name> [--force]          # Remove one
worktree cleanup --merged                 # Remove merged
worktree cleanup --stale 7                # Remove old
```

## Use Cases

### 1. Parallel Feature Development
Working on feature A, need to start feature B without stopping.

```bash
worktree create feature 1234  # Feature B
cd ../my-repo-feature-AB#1234-*
code .  # New VS Code window
# Feature A remains active in original window
```

### 2. PR Review Without Context Loss
Review a PR while keeping current work intact.

```bash
worktree create pr 5678  # Creates review worktree
cd ../my-repo-review-pr-5678
npm test  # Test the PR
gh pr review 5678 --approve
cd - && worktree remove review-pr-5678
```

### 3. Emergency Hotfix
Production bug requires immediate fix mid-feature.

```bash
worktree create fix 9999 --base production
cd ../my-repo-fix-AB#9999-*
# Fix, test, deploy
feature pr  # Create hotfix PR
cd -  # Resume feature work immediately
```

### 4. Side-by-Side Comparison
Compare old and new implementations.

```bash
worktree create branch old-implementation
# Open both in split-screen editors
diff -r main/src/ old-implementation/src/
```

### 5. Long-Running Operations
Run integration tests without blocking development.

```bash
worktree create main tests
cd ../my-repo-tests && npm run test:integration &
cd -  # Continue coding while tests run
```

## Integration Points

### Feature Workflow
- Uses same work item fetching (`feature_workflow.py`)
- Same branch naming: `feature/AB#1234-title`
- Pre-commit hooks work in all worktrees
- `feature pr` works from any worktree

### Azure DevOps
- Auto-fetches work item titles
- Links work items via branch names
- Creates PRs with work item references
- Shares `.ado/config.json`

### GitHub
- Fetches PR branches via `gh` CLI
- Creates review worktrees
- Integrates with PR workflow

### IDEs
- VS Code: Opens in new windows
- JetBrains IDEs: Independent `.idea/` per worktree
- Auto-detects IDE from project markers

## Design Principles

1. **Simplicity First** - Make worktrees as easy as `git checkout`
2. **Safety & Guardrails** - Prevent data loss with comprehensive validation
3. **Feature Workflow Integration** - Seamless compatibility with existing tools
4. **Intelligence** - Claude proactively suggests worktree use cases

## Architecture Highlights

### Directory Structure
```
my-repo/                          # Main worktree (project root)
my-repo-feature-AB#1234/          # Feature worktrees (siblings)
my-repo-review-pr-5678/           # Review worktrees
my-repo-experiments/              # Experimental worktrees
```

### Shared vs. Isolated
- **Shared:** `.git/` database, git hooks, configuration files
- **Isolated:** Working directory, dependencies, build artifacts, IDE settings

### Safety Checks
- Warns about uncommitted changes before removal
- Detects unpushed commits
- Offers commit/stash/backup options
- Requires confirmation for destructive operations

### Dependency Management
- Auto-detects: npm, yarn, pip, poetry, .NET, Rust, Go
- Isolated by default for safety
- Configurable sharing for speed
- Smart caching to minimize disk usage

## Implementation Status

**Current Phase:** Design Complete

### Deliverables
- ✅ Architecture document (30+ pages)
- ✅ Implementation guide with code patterns
- ✅ SKILL.md for Claude integration
- ✅ Command specifications
- ✅ Use case analysis
- ✅ Integration design

### Next Steps
1. Implement `scripts/worktree.sh` (main CLI)
2. Implement Python helpers (manager, dependencies, IDE launcher)
3. Write comprehensive tests (unit + integration)
4. Create user guide and troubleshooting docs
5. Deploy and gather feedback

## Installation *(when implemented)*

```bash
# Run installation script
./skills/git-worktrees/scripts/install.sh

# Reload shell
source ~/.zshrc  # or ~/.bashrc

# Verify
worktree --help

# Configure (optional)
worktree config worktree.defaultIDE code
worktree config worktree.autoInstallDeps true

# Test
cd your-repo
worktree create branch test-worktree --no-deps
worktree list
worktree remove test-worktree --force
```

## Configuration

Default configuration (`.git/worktree/config.json`):

```json
{
  "version": "1.0",
  "basePath": "../",
  "defaultIDE": "code",
  "autoInstallDeps": true,
  "autoCleanup": false,
  "staleThresholdDays": 7,
  "sharedDeps": ["node_modules", ".npm"],
  "isolatedDeps": [".venv", "venv", "target", "bin", "obj"]
}
```

Customize via:
```bash
worktree config worktree.defaultIDE idea
worktree config worktree.staleThresholdDays 14
```

## Best Practices

### When to Use Worktrees

✅ **Use worktrees when:**
- Working on multiple features simultaneously
- Reviewing PRs without disrupting work
- Running long builds/tests
- Comparing branches side-by-side
- Handling emergency hotfixes

⚠️ **Use stash instead when:**
- Making quick, temporary branch switches
- Fixing a single file

⚠️ **Use new clone instead when:**
- Working with different remotes
- Need complete isolation

### Lifecycle Management

```
CREATE → DEVELOP → SYNC → PR → MERGE → CLEANUP
   ↓        ↓        ↓      ↓     ↓        ↓
  Safe   Isolated  Fresh  Track Merge   Auto-
  Path   Deps     Changes  PR   Detect  Clean
```

## Common Workflows

**Typical Development Flow:**
```bash
# 1. Start work
worktree create feature 1234

# 2. Develop
cd ../my-repo-feature-AB#1234-*
git commit -am "Changes"

# 3. Create PR
feature pr

# 4. Address feedback (worktree still exists)
git commit -am "Address review comments"
git push

# 5. After merge, cleanup
worktree cleanup --merged
```

**PR Review Flow:**
```bash
# 1. Review request comes in
worktree create pr 5678

# 2. Review
cd ../my-repo-review-pr-5678
npm test
gh pr review 5678 --comment "Looks good!"

# 3. Cleanup
cd - && worktree remove review-pr-5678
```

## Claude Integration

Claude should suggest worktrees when detecting:

1. **Uncommitted changes + context switch request**
   - "I see you have changes. Let me create a worktree to preserve them."

2. **Parallel work mentioned**
   - "Perfect for worktrees! I'll create separate workspaces."

3. **Long-running operations**
   - "Use worktrees to run tests while continuing to code."

4. **Risky experiments**
   - "Create an experimental worktree to keep your main work safe."

5. **Emergency fixes**
   - "I'll create a hotfix worktree from production."

## Troubleshooting

### Common Issues

**"Worktree already exists"**
```bash
worktree list  # Find existing
worktree remove <name>  # Remove old one
```

**Broken worktrees after manual deletion**
```bash
git worktree prune  # Clean up broken references
```

**Dependencies not installing**
```bash
worktree create feature 1234 --no-deps  # Skip auto-install
cd ../worktree && npm install  # Manual install
```

## Contributing

This skill is designed to integrate seamlessly with:
- Existing `feature` workflow (`scripts/feature.sh`)
- Azure DevOps skill (`skills/azure-devops/`)
- GitHub skill (`skills/github/`)
- Pre-commit hooks

When implementing:
1. Follow bash patterns from `feature.sh`
2. Use Python helpers for complex logic
3. Maintain compatibility with all platforms (macOS, Linux, WSL)
4. Add comprehensive tests

## Success Metrics

- **Time to Context Switch:** < 30 seconds (vs 5-10 minutes with stash)
- **Developer Adoption:** 90% use worktrees for PR reviews
- **Satisfaction:** 80%+ agree "worktrees improve workflow"
- **Auto-cleanup Rate:** 80% of merged worktrees cleaned automatically

## Credits

**Design Philosophy:** "The best architecture is the simplest one that will still work in 2 years."

**Inspiration:**
- Git worktrees (Git 2.5+)
- Existing `feature` workflow
- Modern developer workflows (monorepos, microservices, parallel development)

**Integration:**
- Azure DevOps work item linking
- GitHub PR workflow
- IDE multi-window support
- Pre-commit hook compatibility

---

**Status:** Design Complete | **Next:** Implementation
**Maintainer:** Software Architect Agent
**Version:** 1.0

# Git Worktrees Skill - Architecture & Design

**Version:** 1.0
**Status:** Design Phase
**Author:** Software Architect Agent
**Date:** 2025-12-17

---

## Executive Summary

The **git-worktrees** skill provides intelligent git worktree management for developers working on multiple branches simultaneously. It extends the existing `feature` workflow with parallel workspace capabilities, enabling:

- **Parallel development** across multiple feature branches
- **Zero-downtime PR reviews** without stashing or committing incomplete work
- **Safe worktree lifecycle management** with automatic cleanup and validation
- **Seamless IDE integration** for opening worktrees in new windows
- **Smart dependency handling** for shared resources (node_modules, .venv, build artifacts)

This skill is designed for Claude Code to help developers leverage git worktrees effectively while maintaining the simplicity and safety of the existing feature workflow.

---

## Problem Statement

### Current Pain Points

1. **Context Switching is Expensive**
   - `git checkout` discards working directory state
   - Requires committing incomplete work or complex stashing
   - Rebuilds dependencies after every branch switch
   - Loses IDE context (open files, breakpoints, etc.)

2. **PR Reviews Disrupt Work**
   - Must commit or stash current work to review a PR
   - Can't easily compare branches side-by-side
   - Running tests on one branch blocks coding on another

3. **Hotfixes Are Disruptive**
   - Emergency fixes interrupt feature work
   - Risk of mixing incomplete feature code with hotfixes
   - Long build/test cycles block returning to feature work

4. **Monorepo Challenges**
   - Large codebases make cloning expensive
   - Multiple services need simultaneous development
   - Shared tooling requires consistent versions across workspaces

### Why Git Worktrees?

Git worktrees solve these by allowing **multiple working directories** attached to a single repository:

```
my-repo/
├── .git/                    # Shared git database
├── main/                    # Main worktree (original checkout)
│   ├── src/
│   └── package.json
├── feature-1234/            # Feature worktree
│   ├── src/                 # Different branch, same repo
│   └── package.json
└── review-5678/             # PR review worktree
    ├── src/
    └── package.json
```

**Benefits:**
- Each worktree has independent working directory and index
- All share `.git` database (no duplication)
- Switch between branches by switching directories
- Keep IDE windows open per worktree
- Run builds/tests in parallel

---

## Design Goals

### Primary Goals

1. **Simplicity First**
   - Make worktrees as easy as `git checkout`
   - Hide git complexity behind intuitive commands
   - Provide smart defaults for common scenarios

2. **Safety & Guardrails**
   - Prevent data loss from accidental deletions
   - Detect and warn about uncommitted changes
   - Validate worktree state before operations

3. **Feature Workflow Integration**
   - Seamless integration with existing `feature` command
   - Support Azure DevOps work item linking
   - Maintain pre-commit hook compatibility

4. **IDE-Friendly**
   - Support opening worktrees in new IDE windows
   - Preserve IDE settings per worktree
   - Handle IDE-specific files (.idea, .vscode)

5. **Resource Efficiency**
   - Smart dependency sharing when safe
   - Avoid unnecessary rebuilds
   - Minimize disk space usage

### Non-Goals

- Replace `git checkout` for simple branch switches
- Manage submodules (separate concern)
- Implement custom merge strategies
- Provide distributed worktree synchronization

---

## Use Cases & Scenarios

### 1. Feature Development Workflows

#### UC1.1: Parallel Feature Development

**Scenario:** Working on feature A, need to start feature B without stopping A.

```bash
# Currently on feature/A with uncommitted changes
worktree create feature 1234  # Creates worktree for feature/AB#1234-feature-b
cd ../feature-AB#1234-feature-b
code .  # Opens new VS Code window
# Continue on feature A in original window
```

**Why worktrees?** Both features progress independently, no stashing needed.

#### UC1.2: Long-Running Builds

**Scenario:** Running integration tests (10+ minutes) while continuing development.

```bash
# Start tests in current worktree
npm run test:integration &

# Switch to another worktree for coding
worktree list
cd ../main
# Continue coding while tests run in background
```

**Why worktrees?** Tests run without blocking development.

### 2. PR Review Workflows

#### UC2.1: Quick PR Review

**Scenario:** Reviewing a PR while keeping current work intact.

```bash
# On feature branch with uncommitted changes
worktree create-pr 5678  # Creates review/pr-5678
cd ../review-pr-5678
# Review, test, comment
cd -
worktree remove review-pr-5678  # Clean up when done
```

**Why worktrees?** Review without disrupting current work.

#### UC2.2: Side-by-Side Comparison

**Scenario:** Comparing two implementations or debugging across branches.

```bash
worktree create branch old-implementation
# Open both in split-screen editors
diff -r main/src/ old-implementation/src/
```

**Why worktrees?** Direct file-level comparison.

#### UC2.3: PR Testing with Local Changes

**Scenario:** Testing a PR with your local unpushed changes.

```bash
# Create worktree for PR
worktree create-pr 5678
cd ../review-pr-5678

# Cherry-pick your local commits
git cherry-pick feature-branch

# Test combined changes
npm test
```

**Why worktrees?** Safe experimentation without affecting either branch.

### 3. Hotfix Workflows

#### UC3.1: Emergency Production Fix

**Scenario:** Production issue requires immediate fix while feature is in progress.

```bash
# On feature/AB#1234 with extensive uncommitted changes
worktree create fix 5678  # Creates fix/AB#5678-from-main
cd ../fix-AB#5678-critical-bug
# Fix, test, deploy
feature pr  # Create hotfix PR
cd -
# Resume feature work immediately
```

**Why worktrees?** Zero context switch cost for emergencies.

#### UC3.2: Hotfix Verification

**Scenario:** Verify hotfix works on production while feature continues.

```bash
# Create worktree from production tag
worktree create main production-v1.2.3
cd ../production-v1.2.3
# Apply hotfix, test against prod data
```

**Why worktrees?** Isolated environment for production testing.

### 4. Monorepo Scenarios

#### UC4.1: Multiple Service Development

**Scenario:** Working on 3 microservices simultaneously in a monorepo.

```bash
worktree create feature 1234  # API changes
worktree create feature 1235  # UI changes
worktree create feature 1236  # Worker changes

# Run each service in its own terminal/IDE window
# Services can communicate locally while developing
```

**Why worktrees?** Parallel development with instant feedback.

#### UC4.2: Migration Testing

**Scenario:** Testing database migration while keeping stable environment.

```bash
worktree create main stable
cd ../migration-test-1234
# Run migration, test, observe
# If fails, stable environment untouched
```

**Why worktrees?** Safe experimentation with destructive operations.

### 5. CI/CD Integration

#### UC5.1: Local Pipeline Testing

**Scenario:** Testing CI pipeline changes without affecting main checkout.

```bash
worktree create branch ci-pipeline-test
cd ../ci-pipeline-test
# Test pipeline locally
act -W .github/workflows/ci.yml  # Using act for local GitHub Actions
```

**Why worktrees?** Isolated CI testing environment.

### 6. Debugging & Comparison

#### UC6.1: Bisect with Worktree

**Scenario:** Binary search for bug introduction while keeping current work.

```bash
worktree create main bisect-session
cd ../bisect-session
git bisect start
git bisect bad HEAD
git bisect good v1.0.0
# Test each revision without disrupting main workspace
```

**Why worktrees?** Bisect without losing current context.

#### UC6.2: Performance Regression Investigation

**Scenario:** Compare performance between old and new implementations.

```bash
worktree create branch before-refactor
# Build and benchmark both versions simultaneously
npm run benchmark  # In main worktree
cd ../before-refactor && npm run benchmark
# Compare results
```

**Why worktrees?** Fair performance comparison with identical conditions.

---

## CLI Design

### Command Structure

```
worktree <command> [options] [arguments]
```

### Core Commands

#### `worktree create <type> <id-or-branch> [options]`

Creates a new worktree with smart defaults.

**Types:**
- `feature <work-item-id>` - Create from work item (integrates with feature workflow)
- `fix <work-item-id>` - Create fix branch
- `pr <pr-id>` - Create from PR
- `branch <branch-name>` - Create from arbitrary branch
- `main [name]` - Create from main branch

**Options:**
- `--path <path>` - Custom path (default: auto-generated from branch name)
- `--base <branch>` - Base branch (default: main)
- `--no-track` - Don't set up tracking
- `--no-deps` - Don't install dependencies
- `--ide <ide>` - Open in IDE (code, idea, none)

**Examples:**

```bash
# Create from work item (integrates with feature workflow)
worktree create feature 1234
# → Creates: ../feature-AB#1234-add-authentication/
# → Fetches title from Azure DevOps
# → Branches from main

# Create for PR review
worktree create pr 5678
# → Creates: ../review-pr-5678/
# → Fetches PR branch

# Create from specific branch
worktree create branch release/v2.0
# → Creates: ../release-v2.0/

# Create with custom path
worktree create feature 1234 --path ~/workspaces/auth-feature

# Create without auto-installing dependencies
worktree create pr 5678 --no-deps
```

**Behavior:**
1. Validates no uncommitted changes in path location
2. Creates worktree directory
3. Checks out appropriate branch
4. Optionally installs dependencies (--no-deps to skip)
5. Optionally opens in IDE
6. Prints next steps

**Output:**
```
✓ Created worktree: feature-AB#1234-add-authentication
  Path: /Users/sean/source/my-repo-feature-AB#1234-add-authentication
  Branch: feature/AB#1234-add-authentication
  Base: main

→ Installing dependencies...
✓ Dependencies installed

Next steps:
  cd ../feature-AB#1234-add-authentication
  code .  # Open in VS Code

Or use:
  worktree open feature-AB#1234-add-authentication
```

---

#### `worktree list [options]`

Lists all worktrees with status.

**Options:**
- `--verbose, -v` - Show detailed information
- `--json` - Output as JSON
- `--stale` - Show only stale/cleanup candidates

**Examples:**

```bash
worktree list
```

**Output:**
```
Current worktrees:
  main                          [main] (clean)
    /Users/sean/source/my-repo

  feature-AB#1234-auth          [feature/AB#1234-add-authentication] (3 uncommitted)
    /Users/sean/source/my-repo-feature-AB#1234-auth
    Work Item: AB#1234
    Ahead: 2 commits | Behind: 0 commits

  review-pr-5678               [pr/5678-fix-validation] (clean)
    /Users/sean/source/my-repo-review-pr-5678
    PR: #5678
    Age: 2 days
```

With `--verbose`:
```
  feature-AB#1234-auth
    Path: /Users/sean/source/my-repo-feature-AB#1234-auth
    Branch: feature/AB#1234-add-authentication
    Status: 3 files modified
    Commits: 2 ahead, 0 behind main
    Work Item: AB#1234 - Add authentication system
    Created: 2025-12-15 14:30
    Last active: 2 hours ago
```

With `--stale`:
```
Stale worktrees (consider cleanup):
  review-pr-5678               [pr/5678-fix-validation]
    PR merged 5 days ago
    Suggest: worktree remove review-pr-5678
```

---

#### `worktree switch <name-or-path>`

Switches to a worktree (changes directory).

**Arguments:**
- `<name-or-path>` - Worktree name or path

**Examples:**

```bash
worktree switch feature-AB#1234
# Changes to that worktree directory

worktree switch main
# Switches to main worktree
```

**Behavior:**
1. Validates worktree exists
2. Optionally warns about uncommitted changes in current location
3. Changes directory (via `cd` command printed for shell to execute)

**Note:** Due to shell limitations, this prints a command for the user to execute:
```
→ To switch to worktree, run:
  cd /Users/sean/source/my-repo-feature-AB#1234-auth
```

Or use shell integration (see Integration section).

---

#### `worktree open <name> [options]`

Opens a worktree in an IDE.

**Options:**
- `--ide <ide>` - IDE to use (code, idea, pycharm, auto)
- `--new-window` - Force new window

**Examples:**

```bash
worktree open feature-AB#1234
# Opens in VS Code (default from config)

worktree open review-pr-5678 --ide idea
# Opens in IntelliJ IDEA
```

**Supported IDEs:**
- `code` - Visual Studio Code
- `idea` - IntelliJ IDEA
- `pycharm` - PyCharm
- `rider` - JetBrains Rider
- `auto` - Detect from repo configuration

---

#### `worktree remove <name> [options]`

Removes a worktree with safety checks.

**Options:**
- `--force` - Force removal even with uncommitted changes
- `--keep-branch` - Don't delete the branch

**Examples:**

```bash
worktree remove review-pr-5678
# Removes worktree, asks about uncommitted changes

worktree remove old-experiment --force
# Force remove even with uncommitted changes
```

**Safety Checks:**
1. Warn if uncommitted changes exist
2. Warn if unpushed commits exist
3. Confirm before deletion
4. Optionally delete associated branch

**Output:**
```
⚠ Warning: Worktree has uncommitted changes:
  - src/auth.js (modified)
  - tests/auth.test.js (new)

Options:
  1. Commit changes
  2. Stash changes
  3. Force delete (LOSE CHANGES)
  4. Cancel

Choice [4]:
```

---

#### `worktree cleanup [options]`

Cleans up stale worktrees.

**Options:**
- `--dry-run` - Show what would be removed
- `--merged` - Remove worktrees for merged branches
- `--stale <days>` - Remove worktrees inactive for N days
- `--all` - Remove all non-main worktrees (dangerous!)

**Examples:**

```bash
worktree cleanup --dry-run
# Shows what would be cleaned

worktree cleanup --merged
# Removes worktrees for merged PRs/branches

worktree cleanup --stale 7
# Removes worktrees untouched for 7+ days
```

**Output:**
```
Cleanup candidates:

Merged branches (safe to remove):
  review-pr-5678    [merged 5 days ago]
  fix-AB#999        [merged 12 days ago]

Stale worktrees (inactive 7+ days):
  experiment-123    [last active: 14 days ago]

Would remove 3 worktrees.
Run without --dry-run to proceed.
```

---

#### `worktree sync <name> [options]`

Synchronizes a worktree with its remote.

**Options:**
- `--rebase` - Use rebase instead of merge
- `--all` - Sync all worktrees

**Examples:**

```bash
worktree sync feature-AB#1234
# Fetches and pulls latest changes

worktree sync --all
# Syncs all worktrees
```

**Behavior:**
1. Fetch from remote
2. Show commits ahead/behind
3. Pull with merge or rebase
4. Report conflicts if any

---

#### `worktree status [name]`

Shows detailed status of a worktree.

**Arguments:**
- `[name]` - Worktree name (default: current)

**Examples:**

```bash
worktree status
# Status of current worktree

worktree status feature-AB#1234
# Status of specific worktree
```

**Output:**
```
Worktree: feature-AB#1234-add-authentication
Path: /Users/sean/source/my-repo-feature-AB#1234-auth
Branch: feature/AB#1234-add-authentication
Work Item: AB#1234 - Add authentication system

Status:
  3 files modified
  1 file staged
  0 untracked files

Commits:
  2 ahead of main
  0 behind main

Remote:
  Up to date with origin/feature/AB#1234-add-authentication

Dependencies:
  node_modules: 1234 packages (shared with main)
  .venv: Python 3.11 (isolated)

Disk usage: 45 MB (excluding shared)
Last active: 2 hours ago
Created: 2025-12-15 14:30
```

---

#### `worktree config [key] [value]`

Get or set configuration.

**Examples:**

```bash
worktree config
# Show all configuration

worktree config worktree.defaultIDE code
# Set default IDE

worktree config worktree.autoCleanup true
# Enable automatic cleanup of merged branches
```

**Configuration Options:**

```yaml
worktree:
  # Base directory for worktrees (default: repository parent)
  basePath: "../"

  # Default IDE (code, idea, pycharm, rider, none)
  defaultIDE: "code"

  # Auto-install dependencies after creation
  autoInstallDeps: true

  # Auto-cleanup merged branches
  autoCleanup: false

  # Stale threshold in days
  staleThresholdDays: 7

  # Shared dependencies (symlink instead of duplicate)
  sharedDeps:
    - "node_modules"
    - ".npm"

  # Isolated dependencies (never share)
  isolatedDeps:
    - ".venv"
    - "venv"
    - ".tox"
    - "target"  # Rust
    - "bin"     # .NET
    - "obj"     # .NET
```

---

### Advanced Commands

#### `worktree foreach <command>`

Runs a command in all worktrees.

**Examples:**

```bash
worktree foreach git fetch
# Fetch in all worktrees

worktree foreach npm test
# Run tests in all worktrees

worktree foreach 'git log --oneline -1'
# Show latest commit in each
```

---

#### `worktree snapshot <name>`

Creates a snapshot of worktree state for later restoration.

**Examples:**

```bash
worktree snapshot feature-AB#1234 --tag experiment-1
# Saves current state

worktree restore experiment-1
# Restores snapshot
```

**Use cases:**
- Before risky refactoring
- Saving multiple experimental approaches
- Creating checkpoints during debugging

---

## Best Practices & Conventions

### Directory Naming

**Convention:** `{repo-name}-{branch-slug}/`

**Examples:**
```
my-repo/                          # Main worktree (original)
my-repo-feature-AB#1234-auth/     # Feature worktree
my-repo-review-pr-5678/           # PR review worktree
my-repo-fix-AB#999-hotfix/        # Hotfix worktree
my-repo-main-stable/              # Secondary main worktree
```

**Rationale:**
- Consistent with feature branch naming
- Easy to identify in file managers
- Works across different shells and file systems
- Avoids naming collisions

### Worktree Organization

**Recommended structure:**

```
~/source/
├── my-repo/                      # Main worktree (project root)
├── my-repo-feature-AB#1234/      # Feature worktrees (siblings)
├── my-repo-review-pr-5678/       # Review worktrees (siblings)
└── my-repo-experiments/          # Experimental worktrees
```

**Alternative (grouped):**

```
~/source/
└── my-repo/
    ├── .git/                     # Shared git database
    ├── main/                     # Main worktree
    ├── worktrees/
    │   ├── feature-1234/
    │   ├── feature-1235/
    │   └── review-5678/
    └── experiments/
```

**Recommendation:** Use sibling structure for compatibility with existing tools and simpler paths.

### When to Use Worktrees vs. Alternatives

#### Use Worktrees When:

✅ **Parallel work on multiple features**
   - You need both branches active simultaneously
   - Example: Working on API and UI features that interact

✅ **PR reviews without disrupting work**
   - You have uncommitted changes you don't want to stash
   - Example: Reviewing a PR mid-feature development

✅ **Long-running operations**
   - Builds, tests, or deployments that block other work
   - Example: Running integration tests while continuing development

✅ **Side-by-side comparison**
   - Need to directly compare implementations
   - Example: Debugging regression by comparing old vs. new code

✅ **Multiple stable environments**
   - Testing different configurations simultaneously
   - Example: Production bug fix while feature development continues

#### Use Stash Instead When:

⚠️ **Quick branch switches**
   - Simple, temporary context switches
   - Example: Checking something on another branch for 2 minutes

⚠️ **Single-file quick fixes**
   - Tiny changes that don't need a full worktree
   - Example: Fixing a typo in README

#### Use New Clone Instead When:

⚠️ **Different remote repositories**
   - Working on forks or mirrors
   - Different authentication contexts

⚠️ **Isolated experimentation**
   - You want complete isolation from main repo
   - Example: Testing a destructive script

### Branch Lifecycle in Worktrees

```
┌─────────────────────────────────────────────────────────────┐
│                   WORKTREE LIFECYCLE                         │
└─────────────────────────────────────────────────────────────┘

1. CREATE
   worktree create feature 1234
   ↓

2. DEVELOP
   cd ../feature-AB#1234-*
   # Make changes, commit
   ↓

3. SYNC (optional)
   worktree sync feature-AB#1234
   ↓

4. CREATE PR
   feature pr  # From within worktree
   ↓

5. REVIEW CYCLE
   # Keep worktree for addressing feedback
   # Or work on next task in different worktree
   ↓

6. MERGE
   feature finish  # Merges PR
   ↓

7. CLEANUP
   worktree remove feature-AB#1234
   # Or use auto-cleanup
   worktree cleanup --merged
```

### Dependency Management Strategies

#### Strategy 1: Shared Node Modules (Symlink)

**Use when:** Dependencies are stable and rarely change.

```bash
# After creating worktree
cd ../feature-AB#1234
rm -rf node_modules
ln -s ../my-repo/node_modules .
```

**Pros:**
- Saves disk space
- Faster worktree creation

**Cons:**
- Version conflicts if branches diverge
- Can't test different dependency versions

**Recommendation:** Use for short-lived review worktrees.

#### Strategy 2: Isolated Dependencies

**Use when:** Dependencies differ between branches.

```bash
# Dependencies are independent per worktree
cd ../feature-AB#1234
npm install  # Separate node_modules
```

**Pros:**
- Complete isolation
- Safe for incompatible dependency versions

**Cons:**
- Uses more disk space
- Slower to set up

**Recommendation:** Use for long-lived feature worktrees.

#### Strategy 3: Shared Build Cache

**Use when:** Build artifacts can be shared.

```bash
# Share npm cache across worktrees
export NPM_CONFIG_CACHE=~/.npm-cache-shared
npm install
```

**Pros:**
- Faster installs
- Less disk usage

**Cons:**
- More complex setup

**Recommendation:** Configure globally in `.npmrc`.

#### Language-Specific Guidance

**Python:**
- **Virtual environments (`.venv`)**: Always isolate (never share)
- **pip cache**: Share via `PIP_CACHE_DIR`

```bash
export PIP_CACHE_DIR=~/.cache/pip-shared
python -m venv .venv
```

**.NET:**
- **NuGet packages**: Share via global packages folder (default behavior)
- **Build output (`bin/`, `obj/`)**: Always isolate (gitignored)

```bash
# Build artifacts are isolated by default
dotnet restore  # Uses shared NuGet cache
```

**Node.js:**
- **node_modules**: Use isolated for safety, symlink for speed
- **npm cache**: Share via `NPM_CONFIG_CACHE`

**Rust:**
- **Cargo packages**: Share via `CARGO_HOME` (default behavior)
- **target/ directory**: Always isolate

**Go:**
- **Module cache**: Share via `GOMODCACHE` (default behavior)
- **Build cache**: Share via `GOCACHE`

---

## Integration Points

### Feature Workflow Integration

The `worktree` skill extends the existing `feature` workflow:

```
┌─────────────────────────────────────────────────────────────┐
│                 FEATURE + WORKTREE INTEGRATION               │
└─────────────────────────────────────────────────────────────┘

EXISTING FEATURE WORKFLOW:
  feature start 1234  →  Create branch  →  feature pr  →  feature finish

NEW WORKTREE WORKFLOW:
  worktree create feature 1234  →  Develop  →  feature pr  →  worktree cleanup
```

**Integration patterns:**

1. **Creating Feature Worktrees**
   ```bash
   # Uses same work item fetching as feature.sh
   worktree create feature 1234
   # Internally calls feature_workflow.py to get title
   ```

2. **PR Creation from Worktree**
   ```bash
   cd ../feature-AB#1234-auth
   feature pr  # Works normally from within worktree
   ```

3. **Cleanup After Merge**
   ```bash
   feature finish  # Merges PR
   worktree cleanup --merged  # Removes worktree
   ```

**Shared Components:**
- `scripts/feature_workflow.py` - Work item title fetching
- `scripts/detect_platform.py` - Platform detection
- Pre-commit hooks - Work in all worktrees

### IDE Integration

#### Visual Studio Code

**Workspace Settings:** Each worktree can have its own `.vscode/settings.json`.

```json
{
  "worktree.name": "feature-AB#1234",
  "worktree.branch": "feature/AB#1234-add-authentication",
  "worktree.workItem": "AB#1234"
}
```

**Opening Worktrees:**
```bash
worktree open feature-AB#1234
# Executes: code /path/to/worktree
```

**Multi-root Workspace:** For comparing worktrees side-by-side:
```bash
worktree compare main feature-AB#1234
# Creates multi-root workspace with both worktrees
```

#### JetBrains IDEs (IntelliJ, PyCharm, Rider)

**Project Settings:** Each worktree gets independent `.idea/` directory.

```bash
worktree open feature-AB#1234 --ide idea
# Executes: idea /path/to/worktree
```

**Recommendation:** Use separate IDE windows per worktree for clarity.

### Pre-commit Hooks

**Challenge:** Hooks are symlinked to `.git/hooks` (shared across worktrees).

**Solution:** Hooks work automatically in all worktrees.

**Work Item Linking:** Pre-commit hook detects branch name in each worktree:

```bash
# In feature-AB#1234 worktree
git commit -m "Add login"
# Hook appends: "Add login AB#1234"

# In fix-AB#5678 worktree
git commit -m "Fix validation"
# Hook appends: "Fix validation AB#5678"
```

**Testing:** Hook verification works per-worktree:

```bash
cd ../feature-AB#1234
git commit -m "Test" --no-verify  # Bypasses hook in this worktree only
```

### Azure DevOps Integration

**Work Item Linking:** Same as feature workflow.

**Configuration:** `.ado/config.json` is shared across worktrees (in main `.git/`).

**PR Creation:**
```bash
cd ../feature-AB#1234-auth
feature pr  # Detects work item from branch name
# Creates PR with AB#1234 link
```

**Work Item Queries:**
```bash
# Works from any worktree
python3 ~/.claude/skills/azure-devops/scripts/query-work-items.py --preset my-active
```

### Shared Resources

#### Shared Across Worktrees (in `.git/`)
- Configuration (`.ado/config.json`, `.worktree/config.json`)
- Git hooks
- Git LFS objects
- Shared scripts

#### Isolated Per Worktree
- `.vscode/` or `.idea/` (IDE settings)
- `node_modules/`, `.venv/`, `target/` (dependencies)
- Build artifacts (`bin/`, `obj/`, `dist/`)
- `.env` files (environment-specific)

#### User Choice (Configurable)
- Test databases (can share or isolate)
- Log files (typically isolate)
- Temporary files (typically isolate)

---

## Safety & Guardrails

### Pre-operation Validation

Before any worktree operation, validate:

1. **Git Repository Check**
   ```bash
   git rev-parse --show-toplevel
   ```

2. **Clean Working Tree** (for certain operations)
   ```bash
   git diff --quiet HEAD
   ```

3. **No Existing Worktree Conflict**
   ```bash
   git worktree list | grep -q <path>
   ```

4. **Branch Exists** (for checkout)
   ```bash
   git show-ref --verify refs/heads/<branch>
   ```

### Preventing Data Loss

#### Uncommitted Changes Protection

```bash
worktree remove feature-AB#1234
```

**Output:**
```
⚠ Warning: Worktree has uncommitted changes:

  Modified:
    src/auth.js
    src/utils.js

  Untracked:
    tests/auth.test.js

Options:
  1. Commit changes now
  2. Stash changes
  3. Create a backup branch
  4. Force delete (LOSE ALL CHANGES)
  5. Cancel

Your choice [5]:
```

**Implementation:**
```bash
# Check for uncommitted changes
if ! git -C "$WORKTREE_PATH" diff --quiet HEAD; then
    echo "⚠ Uncommitted changes detected"
    # Prompt user
fi
```

#### Unpushed Commits Protection

```bash
worktree remove feature-AB#1234
```

**Output:**
```
⚠ Warning: Branch has 3 unpushed commits:

  abc123 Add authentication endpoints
  def456 Add tests
  789abc Update documentation

Recommendation: Push before removing.

Options:
  1. Push now
  2. Create backup branch
  3. Force delete (LOSE COMMITS)
  4. Cancel

Your choice [4]:
```

**Implementation:**
```bash
# Check for unpushed commits
LOCAL=$(git rev-parse @)
REMOTE=$(git rev-parse @{u} 2>/dev/null)

if [ "$LOCAL" != "$REMOTE" ]; then
    echo "⚠ Unpushed commits detected"
fi
```

### Handling Edge Cases

#### Merge Conflicts Across Worktrees

**Scenario:** User merges in one worktree, conflicts in another.

**Detection:**
```bash
worktree sync feature-AB#1234
```

**Output:**
```
⚠ Conflict detected:
  Branch feature/AB#1234 has diverged from main.

  Your branch: 3 commits ahead, 5 commits behind

  This will likely cause merge conflicts.

  Recommendation: Resolve in this worktree or delete and recreate.

Continue sync? [y/N]:
```

#### Locked Index Files

**Scenario:** Git operation in progress (rebase, merge).

**Detection:**
```bash
if [ -f "$WORKTREE_PATH/.git/index.lock" ]; then
    echo "⚠ Git operation in progress in this worktree"
    echo "Complete or abort the operation before removing."
    exit 1
fi
```

#### Broken Worktrees

**Scenario:** Worktree directory deleted manually.

**Detection:**
```bash
git worktree list
```

**Output:**
```
/path/to/main     abc123 [main]
/path/to/feature  def456 [feature/AB#1234] (missing)
```

**Repair:**
```bash
worktree repair
# Or
git worktree prune
```

### Concurrent Operations

**Challenge:** Multiple worktrees can modify `.git/` database concurrently.

**Git's Protection:** Git uses file locks to prevent corruption.

**Our Protection:** Warn users about potential conflicts:

```bash
worktree sync --all
```

**Output:**
```
→ Syncing multiple worktrees...
  ⚠ Warning: Syncing all worktrees simultaneously may cause conflicts.
  Recommend syncing one at a time if you have uncommitted changes.

Continue? [y/N]:
```

---

## Claude-Specific Considerations

### How Claude Uses This Skill

Claude should invoke this skill when users mention:

**Trigger phrases:**
- "Create a worktree"
- "Review PR without switching branches"
- "Work on multiple features"
- "Need to test something without losing my changes"
- "git worktree"
- "parallel branches"

**Skill description for YAML frontmatter:**
```yaml
description: |
  Manage git worktrees for parallel branch development. Use when asked about:
  worktrees, working on multiple branches, PR review without switching,
  parallel development, testing without committing changes.
  Integrates with feature workflow for work item linking.
```

### Context Awareness

Claude needs to track:

1. **Current Worktree Location**
   ```bash
   git rev-parse --show-toplevel
   # Determine which worktree user is in
   ```

2. **Available Worktrees**
   ```bash
   worktree list --json
   # Load worktree inventory
   ```

3. **Repository State**
   - Uncommitted changes in current worktree
   - Active PRs associated with worktrees
   - Merged branches eligible for cleanup

### Suggesting Worktree Use

Claude should proactively suggest worktrees when detecting:

**Scenario 1: User has uncommitted changes and mentions switching branches**

```
User: "I need to review PR #5678"

Claude detects:
  - Uncommitted changes in current branch
  - User wants to switch context

Claude suggests:
  "I see you have uncommitted changes. Instead of stashing, would you like me to
   create a worktree for reviewing PR #5678? This keeps your current work intact."

  Command: worktree create pr 5678
```

**Scenario 2: User wants to test something risky**

```
User: "I want to try refactoring the auth module but I'm not sure it'll work"

Claude suggests:
  "This sounds like a good use case for a worktree. I can create an experimental
   worktree so you can try the refactoring without affecting your main workspace."

  Command: worktree create branch experiment-auth-refactor
```

**Scenario 3: User mentions long build times**

```
User: "The integration tests take 20 minutes and I can't code while they run"

Claude suggests:
  "You could use worktrees to run tests in one workspace while coding in another.
   Let me show you how to set that up."

  Commands:
    worktree create main tests
    cd ../my-repo-tests && npm run test:integration &
    cd -  # Back to main workspace
```

### Error Handling & Recovery

Claude should handle common errors gracefully:

#### Error: Worktree Path Already Exists

```
Error: Path '/path/to/worktree' already exists

Claude response:
  "That worktree path is already occupied. Options:
   1. Use a different name: worktree create feature 1234 --path custom-name
   2. Remove existing: worktree remove <name>
   3. List existing worktrees: worktree list"
```

#### Error: Branch Doesn't Exist

```
Error: Branch 'feature/AB#9999' not found

Claude response:
  "That branch doesn't exist yet. Would you like me to:
   1. Create a new branch: worktree create feature 9999 (fetches from ADO)
   2. Fetch from remote: git fetch && worktree create branch feature/AB#9999
   3. List available branches: git branch -a"
```

#### Error: Uncommitted Changes in Target Path

```
Error: Cannot create worktree - path has uncommitted changes

Claude response:
  "The target path has uncommitted changes. This usually means a previous worktree
   wasn't cleaned up properly. Options:
   1. Clean up: worktree cleanup --stale
   2. Repair: worktree repair
   3. Manual fix: rm -rf /path/to/worktree && worktree create ..."
```

### Progress Tracking

For long-running operations, Claude should provide progress updates:

```bash
worktree create feature 1234
```

**Claude's output:**
```
→ Creating worktree for AB#1234...
  ✓ Fetched work item: "Add authentication system"
  ✓ Created worktree at: ../my-repo-feature-AB#1234-add-authentication
  ✓ Checked out branch: feature/AB#1234-add-authentication
  → Installing dependencies (this may take a minute)...
  ✓ Installed 1,234 packages
  ✓ Opened in VS Code

Done! Your worktree is ready.
```

### Teaching Opportunities

Claude should educate users about worktree benefits:

**After successful worktree creation:**
```
"✓ Worktree created successfully!

Pro tip: You can now work on this feature in one terminal/IDE window while
keeping your main branch available in another. No more stashing or losing context!

To switch back: worktree switch main
To see all worktrees: worktree list"
```

**When user struggles with stashing:**
```
"I notice you're using git stash frequently. Worktrees might simplify your workflow.
Instead of stash/unstash, you could:

  worktree create branch experiment
  # Work in isolation
  worktree remove experiment  # When done

Would you like me to show you how?"
```

---

## Implementation Considerations

### Technology Stack

**Primary Script:** Bash (for shell integration and git operations)
- Location: `scripts/worktree.sh`
- Alias: `alias worktree="$HOME/source/tools/claude-tools/scripts/worktree.sh"`

**Python Helper:** For complex logic (JSON parsing, ADO integration)
- Location: `skills/git-worktrees/scripts/worktree_manager.py`
- Used for: Configuration, state tracking, IDE integration

**Dependencies:**
- `git` (2.5+, for worktree support)
- `python3` (for helper scripts)
- `jq` (optional, for JSON output)
- `az` or `gh` (for work item/PR integration)

### File Structure

```
skills/git-worktrees/
├── SKILL.md                          # Skill documentation
├── docs/
│   ├── architecture.md               # This document
│   ├── user-guide.md                 # End-user documentation
│   └── troubleshooting.md            # Common issues
├── scripts/
│   ├── worktree_manager.py           # Python helper
│   ├── check_prerequisites.py        # Prerequisites validation
│   ├── dependency_handler.py         # Smart dependency management
│   └── ide_launcher.py               # IDE integration
├── tests/
│   ├── test_worktree_manager.py
│   └── test_dependency_handler.py
└── examples/
    ├── basic-workflow.sh             # Example workflows
    └── advanced-scenarios.sh

scripts/ (root)
├── worktree.sh                       # Main CLI script
└── feature_workflow.py               # Shared with feature.sh
```

### Configuration Storage

**Location:** `.git/worktree/config.json`

**Why `.git/worktree/`?**
- Shared across all worktrees
- Not tracked in version control
- Persists with repository
- Separate from user's `.gitconfig`

**Schema:**
```json
{
  "version": "1.0",
  "basePath": "../",
  "defaultIDE": "code",
  "autoInstallDeps": true,
  "autoCleanup": false,
  "staleThresholdDays": 7,
  "sharedDeps": ["node_modules", ".npm"],
  "isolatedDeps": [".venv", "venv", "target", "bin", "obj"],
  "worktrees": {
    "feature-AB#1234-auth": {
      "path": "/Users/sean/source/my-repo-feature-AB#1234-auth",
      "branch": "feature/AB#1234-add-authentication",
      "workItem": "AB#1234",
      "created": "2025-12-17T10:30:00Z",
      "lastActive": "2025-12-17T14:45:00Z"
    }
  }
}
```

### State Tracking

**Challenge:** Track worktree usage and state for cleanup suggestions.

**Solution:** Update `lastActive` timestamp on worktree access.

**Implementation:**
```python
# In worktree_manager.py
def track_access(worktree_name: str):
    """Update lastActive timestamp for worktree."""
    config = load_config()
    if worktree_name in config['worktrees']:
        config['worktrees'][worktree_name]['lastActive'] = datetime.now().isoformat()
        save_config(config)
```

**Trigger:** On `worktree switch`, `worktree open`, or any git operation in worktree.

### Dependency Detection

**Challenge:** Auto-detect dependency systems and handle them appropriately.

**Solution:** Check for common dependency files:

```python
# dependency_handler.py
def detect_dependencies(worktree_path: str) -> Dict[str, str]:
    """Detect dependency systems in worktree."""
    deps = {}

    # Node.js
    if os.path.exists(f"{worktree_path}/package.json"):
        deps['nodejs'] = 'npm' if os.path.exists(f"{worktree_path}/package-lock.json") else 'yarn'

    # Python
    if os.path.exists(f"{worktree_path}/requirements.txt"):
        deps['python'] = 'pip'
    elif os.path.exists(f"{worktree_path}/pyproject.toml"):
        deps['python'] = 'poetry'

    # .NET
    if glob.glob(f"{worktree_path}/**/*.csproj", recursive=True):
        deps['dotnet'] = 'nuget'

    # Rust
    if os.path.exists(f"{worktree_path}/Cargo.toml"):
        deps['rust'] = 'cargo'

    # Go
    if os.path.exists(f"{worktree_path}/go.mod"):
        deps['go'] = 'go'

    return deps

def install_dependencies(worktree_path: str, deps: Dict[str, str]):
    """Install dependencies based on detected systems."""
    for system, tool in deps.items():
        print(f"→ Installing {system} dependencies using {tool}...")

        if tool == 'npm':
            subprocess.run(['npm', 'install'], cwd=worktree_path)
        elif tool == 'pip':
            subprocess.run(['pip', 'install', '-r', 'requirements.txt'], cwd=worktree_path)
        # ... etc
```

### IDE Detection & Launching

```python
# ide_launcher.py
def detect_ide(worktree_path: str) -> str:
    """Auto-detect IDE from project markers."""

    if os.path.exists(f"{worktree_path}/.vscode"):
        return 'code'
    elif os.path.exists(f"{worktree_path}/.idea"):
        # Check for specific JetBrains IDE
        if glob.glob(f"{worktree_path}/**/*.csproj", recursive=True):
            return 'rider'
        elif os.path.exists(f"{worktree_path}/requirements.txt"):
            return 'pycharm'
        else:
            return 'idea'

    return 'none'

def launch_ide(worktree_path: str, ide: str = 'auto'):
    """Launch IDE for worktree."""

    if ide == 'auto':
        ide = detect_ide(worktree_path)

    commands = {
        'code': ['code', worktree_path],
        'idea': ['idea', worktree_path],
        'pycharm': ['pycharm', worktree_path],
        'rider': ['rider', worktree_path],
    }

    if ide in commands:
        subprocess.run(commands[ide])
    else:
        print(f"IDE '{ide}' not configured")
```

### Shell Integration

**Challenge:** `worktree switch` needs to change the current shell's directory.

**Solution 1: Print command for user to execute**
```bash
worktree switch feature-AB#1234
# Output:
# → To switch, run: cd /path/to/worktree
```

**Solution 2: Shell function (recommended)**
```bash
# In ~/.zshrc or ~/.bashrc
worktree() {
    local cmd="$1"
    shift

    if [ "$cmd" = "switch" ]; then
        local target_path=$(worktree.sh get-path "$@")
        if [ -n "$target_path" ]; then
            cd "$target_path"
        fi
    else
        worktree.sh "$cmd" "$@"
    fi
}
```

**Recommendation:** Provide shell function in setup instructions.

### Platform Compatibility

**Primary Target:** macOS and Linux

**Considerations:**
- **Path Handling:** Use forward slashes, convert on Windows
- **Symlinks:** Supported on Unix, may need junction on Windows
- **Shell:** Bash 4+ or Zsh
- **Git:** 2.5+ for worktree support

**Windows Support:** WSL recommended, native support via Git Bash (limited).

---

## Edge Cases & Mitigations

### 1. Disk Space Exhaustion

**Scenario:** Multiple worktrees with large dependencies fill disk.

**Mitigation:**
- Track disk usage per worktree
- Warn when total usage exceeds threshold
- Suggest cleanup: `worktree cleanup --stale`

**Implementation:**
```bash
worktree status feature-AB#1234
# Output includes: "Disk usage: 450 MB (excluding shared)"

worktree list
# Output includes: "Total disk usage: 2.3 GB across 5 worktrees"
```

### 2. Dependency Version Conflicts

**Scenario:** Worktrees need different dependency versions (e.g., Node 14 vs Node 18).

**Mitigation:**
- Always isolate dependencies (never symlink by default)
- Support `.nvmrc` or similar version files
- Warn when version files differ

**Implementation:**
```bash
worktree create feature 1234
# Detects .nvmrc difference:
# ⚠ Warning: This branch requires Node 18, main uses Node 16
# Dependencies will be isolated.
```

### 3. Git LFS Objects

**Scenario:** Large files managed by Git LFS may be duplicated.

**Mitigation:**
- Git LFS stores objects in `.git/lfs` (shared across worktrees)
- No special handling needed

**Note to users:**
```
Git LFS objects are shared across worktrees automatically.
No duplicate downloads occur.
```

### 4. Submodules

**Scenario:** Worktrees with submodules may have issues.

**Mitigation:**
- Detect submodules: `git submodule status`
- Warn that submodules need manual init: `git submodule update --init`

**Future Enhancement:** Auto-initialize submodules in new worktrees.

### 5. Bare Repositories

**Scenario:** User has a bare repository (common in CI/CD).

**Mitigation:**
- Detect bare repo: `git rev-parse --is-bare-repository`
- Require at least one non-bare worktree

### 6. Remote Tracking Branch Deletion

**Scenario:** Remote branch deleted, but worktree still exists.

**Detection:**
```bash
git fetch --prune
worktree list
# Shows: "feature-AB#1234 (remote deleted)"
```

**Suggestion:**
```
⚠ Remote branch deleted for worktree: feature-AB#1234
  Suggest: worktree remove feature-AB#1234
```

### 7. Rename or Move Worktree

**Scenario:** User manually moves worktree directory.

**Impact:** Git loses track of worktree.

**Detection:**
```bash
git worktree list
# Shows: /old/path (missing)
```

**Repair:**
```bash
worktree repair
# Prompts to update paths or prune missing worktrees
```

### 8. Concurrent Git Operations

**Scenario:** Two worktrees perform conflicting operations simultaneously.

**Git's Protection:** Index locks prevent corruption.

**User Experience:** May see "index.lock" errors.

**Mitigation:**
- Document that some operations are exclusive
- Suggest retrying after a moment

### 9. Very Large Repositories

**Scenario:** Cloning worktree in massive monorepo is slow.

**Mitigation:**
- Use sparse checkout: `git sparse-checkout set <path>`
- Document performance considerations

**Future Enhancement:** Support sparse worktrees.

### 10. Nested Worktrees

**Scenario:** User tries to create worktree inside another worktree.

**Mitigation:**
- Detect and prevent: Check if path is within another worktree
- Suggest sibling placement instead

---

## Example Workflows

### Workflow 1: Parallel Feature Development

**Scenario:** Working on two related features that need separate branches.

```bash
# Start feature A
feature start 1234
# → Creates feature/AB#1234-add-user-auth

# Work on feature A
git commit -am "Add login endpoint"

# Need to start feature B without losing A's progress
worktree create feature 1235
# → Creates ../my-repo-feature-AB#1235-add-admin-panel/

# Work on feature B in new terminal
cd ../my-repo-feature-AB#1235-add-admin-panel
git commit -am "Add admin dashboard"

# Switch back to feature A
cd -

# Both features progress independently
# Create PRs when ready
cd ../my-repo-feature-AB#1234-add-user-auth && feature pr
cd ../my-repo-feature-AB#1235-add-admin-panel && feature pr

# After both merged
worktree cleanup --merged
# Removes both worktrees
```

### Workflow 2: PR Review with Local Testing

**Scenario:** Review colleague's PR and test it with your local changes.

```bash
# On feature/local-changes with uncommitted work
worktree create pr 5678
# → Creates ../my-repo-review-pr-5678/

cd ../my-repo-review-pr-5678

# Test PR as-is
npm test

# Test with your local changes
git cherry-pick feature/local-changes
npm test

# Leave feedback on PR
gh pr review 5678 --approve

# Clean up
cd -
worktree remove review-pr-5678
```

### Workflow 3: Emergency Hotfix

**Scenario:** Production bug while in middle of feature development.

```bash
# On feature/AB#1234 with extensive uncommitted changes
worktree create fix 9999 --base production
# → Creates ../my-repo-fix-AB#9999-critical-bug from production branch

cd ../my-repo-fix-AB#9999-critical-bug

# Fix bug, test
git commit -am "Fix null pointer in payment processing AB#9999"

# Create hotfix PR
feature pr

# Deploy immediately
# ... deployment steps ...

# Return to feature work (still intact)
cd -

# After hotfix merged
worktree remove fix-AB#9999
```

### Workflow 4: Comparing Implementations

**Scenario:** Compare performance of old vs. new algorithm.

```bash
# Create worktree for old implementation
worktree create branch before-optimization

# Benchmark old implementation
cd ../my-repo-before-optimization
npm run benchmark > /tmp/old-results.txt

# Benchmark new implementation
cd -
npm run benchmark > /tmp/new-results.txt

# Compare results
diff /tmp/old-results.txt /tmp/new-results.txt

# Clean up
worktree remove before-optimization
```

### Workflow 5: Monorepo Multi-Service Development

**Scenario:** Developing API, web UI, and worker simultaneously.

```bash
# Create worktrees for each service
worktree create feature 1234  # API changes
worktree create feature 1235  # UI changes
worktree create feature 1236  # Worker changes

# Terminal 1: API
cd ../my-repo-feature-AB#1234-api
npm run dev

# Terminal 2: UI
cd ../my-repo-feature-AB#1235-ui
npm run dev

# Terminal 3: Worker
cd ../my-repo-feature-AB#1236-worker
npm run dev

# All services run simultaneously, call each other
# Test integration locally

# Commit and push each separately
cd ../my-repo-feature-AB#1234-api && feature pr
cd ../my-repo-feature-AB#1235-ui && feature pr
cd ../my-repo-feature-AB#1236-worker && feature pr

# Clean up after merge
worktree cleanup --merged
```

---

## Success Metrics

### User Experience Metrics

1. **Time to Context Switch**
   - **Current (without worktrees):** ~5-10 minutes (stash, checkout, restore deps)
   - **Target (with worktrees):** <30 seconds

2. **PR Review Friction**
   - **Current:** 70% of developers stash or commit incomplete work
   - **Target:** 90% use worktrees for reviews

3. **Developer Satisfaction**
   - **Survey question:** "Worktrees improve my workflow"
   - **Target:** 80% agree or strongly agree

### Technical Metrics

1. **Disk Usage**
   - **Monitor:** Total disk usage across worktrees
   - **Target:** <2x single clone size for typical use (3-5 worktrees)

2. **Cleanup Rate**
   - **Monitor:** % of worktrees auto-cleaned after merge
   - **Target:** 80% automatic cleanup

3. **Error Rate**
   - **Monitor:** Worktree operation failures
   - **Target:** <5% failure rate

---

## Future Enhancements

### Phase 1: Core Functionality (Current Design)
- Basic worktree creation/removal
- Feature workflow integration
- Safety checks and cleanup

### Phase 2: Enhanced Automation
- **Auto-cleanup after merge:** Detect merged PRs and remove worktrees
- **Dependency optimization:** Smart symlink decisions based on branch age
- **Background sync:** Auto-fetch in all worktrees periodically

### Phase 3: Advanced Features
- **Worktree templates:** Pre-configured worktrees for common tasks
- **Snapshot/restore:** Save and restore worktree state
- **Multi-worktree operations:** Batch operations across worktrees

### Phase 4: Team Collaboration
- **Shared worktree registry:** Team members see each other's active worktrees
- **Worktree recommendations:** Suggest worktrees based on team activity
- **Integration with code review tools:** Auto-create review worktrees

### Phase 5: Performance Optimization
- **Sparse worktrees:** Partial checkouts for massive repos
- **Lazy dependency install:** Only install deps when needed
- **Parallel operations:** Speed up multi-worktree operations

---

## Conclusion

The **git-worktrees** skill brings professional-grade parallel development capabilities to Claude Code users while maintaining the simplicity and safety of the existing `feature` workflow. By providing intelligent defaults, strong safety guardrails, and seamless IDE integration, it makes git worktrees accessible to developers of all skill levels.

**Key Design Principles:**
1. **Simplicity:** Make worktrees as easy as `git checkout`
2. **Safety:** Prevent data loss with comprehensive validation
3. **Integration:** Seamless compatibility with existing tooling
4. **Intelligence:** Claude proactively suggests worktree use cases

**Next Steps:**
1. Review this architecture with stakeholders
2. Implement core commands (create, list, remove)
3. Integrate with feature workflow
4. Add comprehensive tests
5. Write user documentation
6. Deploy and gather feedback

This design positions git worktrees as a first-class workflow tool, empowering developers to work efficiently across multiple branches without sacrificing safety or simplicity.

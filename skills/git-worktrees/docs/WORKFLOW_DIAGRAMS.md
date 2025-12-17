# Git Worktrees - Workflow Diagrams

Visual representations of key workflows and architecture.

---

## System Architecture

```
┌────────────────────────────────────────────────────────────────────────────┐
│                         GIT WORKTREES SKILL ECOSYSTEM                       │
└────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────┐
│   User / Claude     │
│   ───────────────   │
│   "Create worktree" │
│   "Review PR #5678" │
└──────────┬──────────┘
           │
           ▼
┌────────────────────────────────────────────────────────────┐
│                    worktree.sh (Bash CLI)                  │
│  ────────────────────────────────────────────────────────  │
│  create | list | remove | cleanup | status | sync | open  │
└─────────┬──────────────────────────────────┬───────────────┘
          │                                  │
          ├─────────┬────────────────────────┼────────────────┐
          ▼         ▼                        ▼                ▼
┌──────────────┐ ┌──────────────────┐ ┌─────────────┐ ┌──────────────┐
│   Git Core   │ │  Python Helpers  │ │  External   │ │ Config Store │
│  ──────────  │ │  ──────────────  │ │  Services   │ │  ──────────  │
│ git worktree │ │ worktree_mgr.py  │ │ Azure DevOps│ │ .git/worktree│
│ git status   │ │ dependency_h.py  │ │ GitHub      │ │ /config.json │
│ git branch   │ │ ide_launcher.py  │ │ feature.sh  │ │              │
└──────────────┘ └──────────────────┘ └─────────────┘ └──────────────┘
          │                │                   │                │
          └────────────────┴───────────────────┴────────────────┘
                                     │
                                     ▼
         ┌───────────────────────────────────────────────────┐
         │              Worktree Ecosystem                   │
         │  ───────────────────────────────────────────────  │
         │  main/            feature-AB#1234/   review-pr-X/ │
         │  ├── .git/        ├── src/          ├── src/      │
         │  ├── src/         ├── node_modules  ├── tests/    │
         │  └── tests/       └── .vscode/      └── .vscode/  │
         └───────────────────────────────────────────────────┘
```

---

## Command Flow: `worktree create feature 1234`

```
┌──────────────────────────────────────────────────────────────────────┐
│                   CREATE FEATURE WORKTREE FLOW                        │
└──────────────────────────────────────────────────────────────────────┘

User/Claude: worktree create feature 1234
       │
       ▼
[1] Validation
    ├─ Check git repo exists
    ├─ Check clean working tree (no uncommitted changes)
    └─ Check path doesn't exist
       │
       ▼
[2] Fetch Work Item Title
    ├─ Call feature_workflow.py get-title 1234
    ├─ Azure DevOps API call
    └─ Returns: "Add authentication system"
       │
       ▼
[3] Generate Branch Name
    ├─ Slugify title: "add-authentication-system"
    ├─ Create branch name: "feature/AB#1234-add-authentication-system"
    └─ Generate path: "../my-repo-feature-AB#1234-add-authentication-system"
       │
       ▼
[4] Create Git Worktree
    ├─ git worktree add -b <branch> <path> main
    ├─ Creates directory structure
    └─ Checks out new branch
       │
       ▼
[5] Track Metadata
    ├─ Call worktree_manager.py track-create
    ├─ Write to .git/worktree/config.json:
    │   {
    │     "name": "feature-AB#1234-...",
    │     "path": "/full/path",
    │     "branch": "feature/AB#1234-...",
    │     "workItem": "AB#1234",
    │     "created": "2025-12-17T10:30:00Z",
    │     "lastActive": "2025-12-17T10:30:00Z"
    │   }
    └─ Metadata stored
       │
       ▼
[6] Install Dependencies (unless --no-deps)
    ├─ Call dependency_handler.py install
    ├─ Detect: package.json → npm
    ├─ Run: npm install in worktree
    └─ Report: "✓ Installed 1,234 packages"
       │
       ▼
[7] Open in IDE (unless --ide none)
    ├─ Call ide_launcher.py launch
    ├─ Detect IDE from config or project markers
    ├─ Execute: code /path/to/worktree
    └─ Opens new VS Code window
       │
       ▼
[8] Display Next Steps
    ├─ Print worktree info
    ├─ Show path and branch
    └─ Suggest: cd ../worktree, make changes, feature pr
       │
       ▼
    SUCCESS ✓
```

---

## Command Flow: `worktree remove feature-AB#1234`

```
┌──────────────────────────────────────────────────────────────────────┐
│                    REMOVE WORKTREE FLOW (SAFE)                        │
└──────────────────────────────────────────────────────────────────────┘

User/Claude: worktree remove feature-AB#1234
       │
       ▼
[1] Locate Worktree
    ├─ Call worktree_manager.py get-path
    ├─ Lookup in .git/worktree/config.json
    └─ Returns: /full/path/to/worktree
       │
       ▼
[2] Get Branch Name
    ├─ cd /path && git rev-parse --abbrev-ref HEAD
    └─ Returns: "feature/AB#1234-add-authentication-system"
       │
       ▼
[3] SAFETY CHECK: Uncommitted Changes (unless --force)
    ├─ cd /path && git status --porcelain
    ├─ Found changes? ──YES──┐
    │                         ▼
    │                  ┌─────────────────────────┐
    │                  │ ⚠ Warning: Uncommitted  │
    │                  │   src/auth.js          │
    │                  │   tests/auth.test.js   │
    │                  │                         │
    │                  │ Options:                │
    │                  │  1. Commit changes      │
    │                  │  2. Stash changes       │
    │                  │  3. Force delete        │
    │                  │  4. Cancel              │
    │                  └────────┬────────────────┘
    │                           │
    │                           ├─ 1 → git add && git commit
    │                           ├─ 2 → git stash push
    │                           ├─ 3 → Set force=true
    │                           └─ 4 → EXIT
    │
    └─ No changes? ──NO──┐
                         ▼
[4] SAFETY CHECK: Unpushed Commits (unless --force)
    ├─ git log @{u}.. --oneline
    ├─ Found commits? ──YES──┐
    │                         ▼
    │                  ┌─────────────────────────┐
    │                  │ ⚠ Warning: Unpushed     │
    │                  │   abc123 Add auth       │
    │                  │   def456 Add tests      │
    │                  │                         │
    │                  │ Options:                │
    │                  │  1. Push now            │
    │                  │  2. Backup branch       │
    │                  │  3. Force delete        │
    │                  │  4. Cancel              │
    │                  └────────┬────────────────┘
    │                           │
    │                           ├─ 1 → git push
    │                           ├─ 2 → git branch backup-*
    │                           ├─ 3 → Set force=true
    │                           └─ 4 → EXIT
    │
    └─ No unpushed? ──NO──┐
                          ▼
[5] Remove Worktree
    ├─ force? → git worktree remove --force /path
    └─ safe → git worktree remove /path
       │
       ▼
[6] Ask About Branch Deletion (unless --keep-branch)
    ├─ "Delete branch 'feature/AB#1234-...'? [y/N]"
    ├─ Yes? ──┐
    │         ├─ git branch -d <branch>
    │         ├─ Not merged? → Prompt for force delete
    │         └─ git branch -D <branch>
    └─ No? → Keep branch
       │
       ▼
[7] Update Metadata
    ├─ Call worktree_manager.py track-remove
    └─ Remove from .git/worktree/config.json
       │
       ▼
    SUCCESS ✓
```

---

## Workflow: Parallel Feature Development

```
┌────────────────────────────────────────────────────────────────────┐
│               PARALLEL FEATURE DEVELOPMENT WORKFLOW                 │
└────────────────────────────────────────────────────────────────────┘

TIMELINE:
─────────────────────────────────────────────────────────────────────►

T0: Start Feature A
    │
    ├─ feature start 1234
    ├─ Work on Feature A
    └─ Uncommitted changes in progress
       │
       ▼
T1: Urgent: Need to start Feature B (without losing Feature A work)
    │
    ├─ worktree create feature 1235
    ├─ Creates: ../my-repo-feature-AB#1235-feature-b/
    └─ Opens new VS Code window
       │
       ▼
T2: Parallel Development
    │
    ├─ Window 1 (main):        Feature A (uncommitted work intact)
    ├─ Window 2 (worktree):    Feature B (clean slate)
    │
    ├─ Commit to Feature A:    git commit -am "WIP" in main
    ├─ Commit to Feature B:    git commit -am "Add B" in worktree
    │
    └─ Both features progress independently
       │
       ▼
T3: Create PRs
    │
    ├─ In main window:         feature pr  # Creates PR for Feature A
    └─ In worktree window:     feature pr  # Creates PR for Feature B
       │
       ▼
T4: Address Review Feedback
    │
    ├─ Feature A feedback →    Work in main window
    └─ Feature B feedback →    Work in worktree window
       │
       ▼
T5: PRs Merged
    │
    ├─ Feature A merged
    ├─ Feature B merged
    └─ Clean up: worktree cleanup --merged
       │
       ▼
    DONE: Both features delivered in parallel ✓


DIRECTORY STATE AT T2:
──────────────────────

my-repo/                          ← Feature A worktree (original)
├── .git/                         ← Shared git database
├── src/
│   ├── feature-a.js             ← Feature A changes (uncommitted)
│   └── common.js
└── tests/
    └── feature-a.test.js        ← Feature A tests

my-repo-feature-AB#1235-feature-b/  ← Feature B worktree
├── src/
│   ├── feature-b.js             ← Feature B changes (committed)
│   └── common.js                ← Same base files
└── tests/
    └── feature-b.test.js        ← Feature B tests

KEY INSIGHT: Both worktrees active, no stashing, no context switching!
```

---

## Workflow: PR Review Without Disruption

```
┌────────────────────────────────────────────────────────────────────┐
│                    PR REVIEW WORKFLOW                               │
└────────────────────────────────────────────────────────────────────┘

SCENARIO: You're mid-feature, colleague asks you to review PR #5678

TRADITIONAL APPROACH (Pain):
────────────────────────────
Current state: feature/AB#1234 with uncommitted changes
    │
    ├─ git stash                 ← Save your work
    ├─ git checkout main
    ├─ gh pr checkout 5678
    ├─ Review, test
    ├─ git checkout feature/AB#1234
    └─ git stash pop             ← Restore your work
       │
       ▼
    Problems:
    • Stash conflicts if files overlap
    • Forget to pop stash
    • Context lost (open files, breakpoints)
    • Can't compare your work with PR


WORKTREE APPROACH (Smooth):
───────────────────────────
Current state: feature/AB#1234 with uncommitted changes
    │
    ├─ worktree create pr 5678   ← Create review worktree
    ├─ Creates: ../my-repo-review-pr-5678/
    └─ Opens new VS Code window
       │
       ▼
    Both workspaces active:
    ├─ Window 1 (main):        Your feature (uncommitted work intact)
    └─ Window 2 (review):      PR #5678 (clean checkout)
       │
       ▼
    Review workflow:
    ├─ In review window:       npm test
    ├─ In review window:       Read code, leave comments
    ├─ In review window:       gh pr review 5678 --approve
    └─ Meanwhile, Window 1 still has your work ready
       │
       ▼
    Clean up:
    ├─ cd -                      ← Return to main workspace
    └─ worktree remove review-pr-5678
       │
       ▼
    DONE: PR reviewed, your work untouched ✓


VISUAL STATE:
─────────────

BEFORE worktree create:
  my-repo/ [feature/AB#1234]
  ├── src/auth.js (modified, uncommitted) ← Your work in progress
  └── tests/auth.test.js (new, unstaged)

DURING review (both exist):
  my-repo/ [feature/AB#1234]
  ├── src/auth.js (modified, uncommitted) ← Still here!
  └── tests/auth.test.js (new, unstaged)

  my-repo-review-pr-5678/ [pr/5678]
  ├── src/validation.js (PR changes)     ← Review this
  └── tests/validation.test.js

AFTER cleanup:
  my-repo/ [feature/AB#1234]
  ├── src/auth.js (modified, uncommitted) ← Exactly as you left it
  └── tests/auth.test.js (new, unstaged)

KEY INSIGHT: Zero context loss, instant return to your work!
```

---

## Workflow: Emergency Hotfix

```
┌────────────────────────────────────────────────────────────────────┐
│                    EMERGENCY HOTFIX WORKFLOW                        │
└────────────────────────────────────────────────────────────────────┘

SCENARIO: Production down, needs immediate fix, you're mid-feature

TIMELINE:
─────────────────────────────────────────────────────────────────────►

T0: Working on Feature (Large, Incomplete)
    │
    feature/AB#1234-new-dashboard
    ├── src/dashboard.js (300 lines changed, uncommitted)
    ├── src/charts.js (150 lines changed, uncommitted)
    └── tests/ (half-written tests)
       │
       ▼
T1: 🚨 ALERT: Production bug in payment processing
    │
    ├─ Can't commit current work (incomplete, breaks tests)
    ├─ Can't stash (too much work, risky)
    └─ Need to fix NOW on production branch
       │
       ▼
T2: Create Hotfix Worktree
    │
    ├─ worktree create fix 9999 --base production
    ├─ Creates: ../my-repo-fix-AB#9999-payment-bug/
    ├─ Branched from: production tag v1.2.3
    └─ Opens new terminal/IDE window
       │
       ▼
T3: Fix in Isolation
    │
    my-repo/ (feature work)          my-repo-fix-AB#9999/ (hotfix)
    ├── Untouched                    ├── src/payment.js (fix)
    ├── Dashboard work still here    ├── tests/payment.test.js
    └── Can continue after fix       └── git commit -am "Fix null ptr"
       │
       ▼
T4: Deploy Hotfix
    │
    In hotfix worktree:
    ├─ npm test                      ← Passes
    ├─ feature pr                    ← Create hotfix PR
    ├─ PR approved
    ├─ Deploy to production
    └─ feature finish                ← Merge and close
       │
       ▼
T5: Return to Feature Work
    │
    ├─ cd -                          ← Back to main workspace
    ├─ Dashboard work exactly as left
    ├─ No merge conflicts
    └─ No stash pop needed
       │
       ▼
T6: Clean Up
    │
    ├─ worktree remove fix-AB#9999   ← Hotfix worktree gone
    └─ Continue feature development
       │
       ▼
    DONE: Hotfix deployed, feature work resumed ✓


COMPARISON:
───────────

WITHOUT WORKTREES:
  1. git stash (pray nothing conflicts)     → 2 min
  2. git checkout production                → 1 min
  3. Create branch, fix bug                 → 20 min
  4. Test, commit, push                     → 5 min
  5. git checkout feature/AB#1234           → 1 min
  6. git stash pop (pray nothing conflicts) → 2 min
  TOTAL: ~31 min, high stress, data loss risk

WITH WORKTREES:
  1. worktree create fix 9999 --base prod  → 30 sec
  2. Fix bug in isolation                   → 20 min
  3. Test, commit, push                     → 5 min
  4. cd - (return to feature)               → 1 sec
  5. worktree remove fix-AB#9999            → 5 sec
  TOTAL: ~26 min, zero stress, no data loss risk

SAVINGS: 5 minutes + eliminated stress + guaranteed safety
```

---

## Integration Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│            INTEGRATION WITH EXISTING ECOSYSTEM                      │
└────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  FEATURE WORKFLOW (scripts/feature.sh)                          │
│  ───────────────────────────────────────────────────────────    │
│  feature start 1234  →  Creates branch                          │
│  feature pr          →  Creates PR with work item link         │
│  feature finish      →  Merges PR and cleans up                │
└─────────────┬───────────────────────────────────────────────────┘
              │
              │ Shared Components:
              ├─ feature_workflow.py (work item fetching)
              ├─ detect_platform.py (Azure DevOps vs GitHub)
              ├─ Pre-commit hooks (work item linking)
              └─ Branch naming conventions
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  GIT WORKTREES SKILL (skills/git-worktrees/)                    │
│  ───────────────────────────────────────────────────────────    │
│  worktree create feature 1234  →  Uses feature_workflow.py     │
│  worktree create pr 5678       →  Uses gh/az pr checkout       │
│  worktree cleanup --merged     →  Detects merged PRs           │
└─────────────┬───────────────────────────────────────────────────┘
              │
              │ Integrates With:
              ├─ Azure DevOps Skill
              ├─ GitHub Skill
              ├─ Pre-commit Hooks
              └─ IDE Integration
              │
              ▼
┌─────────────────────────────────────────────────────────────────┐
│  AZURE DEVOPS SKILL (skills/azure-devops/)                      │
│  ───────────────────────────────────────────────────────────    │
│  query-work-items.py --preset my-active                         │
│  create-work-item.py --type Task --title "..."                 │
│  .ado/config.json (shared across worktrees)                    │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  GITHUB SKILL (skills/github/)                                  │
│  ───────────────────────────────────────────────────────────    │
│  gh pr checkout 5678                                            │
│  gh pr review 5678 --approve                                    │
│  gh pr list --author @me                                        │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  PRE-COMMIT HOOKS (.git/hooks/)                                 │
│  ───────────────────────────────────────────────────────────    │
│  pre-commit: Extract AB#ID from branch, append to message       │
│  prepare-commit-msg: Work item linking                          │
│  ✓ Works in ALL worktrees (hooks are in shared .git/)          │
└─────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────┐
│  IDE INTEGRATION                                                │
│  ───────────────────────────────────────────────────────────    │
│  VS Code:      code /path/to/worktree (new window)             │
│  IntelliJ:     idea /path/to/worktree (new window)             │
│  PyCharm:      pycharm /path/to/worktree                       │
│  Rider:        rider /path/to/worktree                         │
│  ✓ Each worktree has own .vscode/ or .idea/ settings           │
└─────────────────────────────────────────────────────────────────┘


DATA FLOW: Create Feature Worktree with Work Item
──────────────────────────────────────────────────

worktree create feature 1234
       │
       ├─ [1] Call feature_workflow.py get-title 1234
       │       │
       │       └─ Reads .ado/config.json (Azure DevOps settings)
       │       └─ Calls Azure DevOps API
       │       └─ Returns: "Add authentication system"
       │
       ├─ [2] Create branch: feature/AB#1234-add-authentication-system
       │       │
       │       └─ git worktree add -b <branch> <path> main
       │
       ├─ [3] Track metadata in .git/worktree/config.json
       │       │
       │       └─ { workItem: "AB#1234", ... }
       │
       ├─ [4] Install dependencies
       │       │
       │       └─ Detects package.json → npm install
       │
       └─ [5] Open in IDE
               │
               └─ code /path/to/worktree


SHARED STATE:
─────────────

.git/                                    ← Shared across ALL worktrees
├── hooks/                               ← Pre-commit hooks
│   └── pre-commit                       ← Work item linking
├── worktree/
│   └── config.json                      ← Worktree metadata
├── objects/                             ← Git database (no duplication)
└── refs/                                ← Branch references

.ado/config.json                         ← Azure DevOps settings (shared)

Each worktree has:
├── .vscode/ or .idea/                   ← IDE settings (isolated)
├── node_modules/ or .venv/              ← Dependencies (isolated)
└── src/, tests/, etc.                   ← Working files (isolated)
```

---

## Claude Decision Tree

```
┌────────────────────────────────────────────────────────────────────┐
│               WHEN SHOULD CLAUDE SUGGEST WORKTREES?                 │
└────────────────────────────────────────────────────────────────────┘

User Request
     │
     ├─ Contains: "review PR", "check out PR", "review #XXXX"
     │  AND git status shows uncommitted changes?
     │      │
     │      YES → SUGGEST WORKTREE
     │      │     "I see you have uncommitted changes. Let me create a
     │      │      worktree for PR review to preserve your work:
     │      │      worktree create pr XXXX"
     │      │
     │      NO → Standard PR checkout
     │
     ├─ Contains: "multiple features", "parallel", "work on two branches"
     │      │
     │      → SUGGEST WORKTREES
     │        "Perfect use case for worktrees! I'll create separate
     │         workspaces:
     │         worktree create feature 1234
     │         worktree create feature 1235"
     │
     ├─ Contains: "experiment", "try", "not sure if", "risky"
     │      │
     │      → SUGGEST WORKTREE
     │        "Create an experimental worktree for safe exploration:
     │         worktree create branch experiment-<name>
     │         If it works, merge it; if not, delete the worktree."
     │
     ├─ Contains: "hotfix", "urgent", "production", "emergency"
     │  AND currently on feature branch?
     │      │
     │      → SUGGEST WORKTREE
     │        "I'll create a hotfix worktree from production:
     │         worktree create fix XXXX --base production
     │         Your feature work will remain untouched."
     │
     ├─ Contains: "build takes", "tests take", "long running"
     │      │
     │      → SUGGEST WORKTREES
     │        "Use worktrees to run tests while continuing development:
     │         worktree create main tests
     │         cd ../tests && npm test &
     │         cd - # Continue coding"
     │
     ├─ Contains: "compare", "old version", "before refactor"
     │      │
     │      → SUGGEST WORKTREE
     │        "Create a worktree for side-by-side comparison:
     │         worktree create branch old-implementation
     │         diff -r main/ old-implementation/"
     │
     ├─ User types "git stash" frequently (pattern detection)
     │      │
     │      → TEACH ABOUT WORKTREES
     │        "I notice you use git stash often. Worktrees might simplify
     │         your workflow. Instead of stash/unstash, you could use
     │         worktrees for parallel workspaces. Want to try?"
     │
     └─ None of above
            │
            → Don't suggest worktrees
              Use standard git commands


CONFIDENCE LEVELS:
──────────────────

HIGH CONFIDENCE (proactively suggest):
  • Uncommitted changes + PR review request
  • Explicit parallel work mentioned
  • Emergency hotfix on feature branch

MEDIUM CONFIDENCE (suggest with explanation):
  • Long-running operations
  • Experimental work
  • Branch comparison

LOW CONFIDENCE (teach opportunity):
  • Frequent stashing
  • Multiple git checkout in short time
  • Complaints about context switching
```

---

These diagrams provide visual clarity on:
1. System architecture and data flow
2. Command execution sequences
3. Real-world workflow scenarios
4. Integration patterns
5. Claude's decision-making process

Use these to understand how all the pieces fit together and to guide implementation decisions.

# Installation Guide

## Prerequisites

- macOS (tested on Sequoia)
- Claude Code installed
- Python 3.9+ (for helper scripts)

## Step-by-Step Setup

### 1. Place the Tools Repo

Move or copy the `claude-tools` folder (the `skills/` directory and its contents) to your source directory:

```bash
mv ~/Downloads/claude-tools ~/source/claude-tools
```

Or wherever you keep your git repos. The key is this becomes a git repo you can version control.

### 2. Initialize Git

```bash
cd ~/source/claude-tools
git init
git add .
git commit -m "Initial commit: claude-tools skills library"
```

Optionally push to GitHub:
```bash
git remote add origin git@github.com:YOUR_USERNAME/claude-tools.git
git push -u origin main
```

### 3. Create Symlink in ~/.claude/

This makes the skills accessible to Claude Code:

```bash
ln -s ~/source/claude-tools/skills ~/.claude/skills
```

Verify:
```bash
ls -la ~/.claude/skills
# Should show: skills -> /Users/YOUR_USER/source/claude-tools/skills
```

### 4. Install Global CLAUDE.md

Copy the global CLAUDE.md to your home directory:

```bash
cp ~/source/claude-tools/CLAUDE.md ~/CLAUDE.md
```

This file will be inherited by all projects under your home directory.

### 5. Verify Setup

Your structure should now look like:

```
~/
├── CLAUDE.md                           # Global instructions
├── .claude/
│   ├── settings.json                   # Existing Claude Code config
│   └── skills -> ~/source/claude-tools/skills  # Symlink
└── source/
    ├── claude-tools/                   # This repo
    │   ├── skills/
    │   │   └── docgen/
    │   └── ...
    └── your-other-projects/
```

## Testing

Open Claude Code in any project directory:

```bash
cd ~/source/some-project
claude
```

Then ask:
```
What skills do you have access to?
```

Claude should reference the skills from `~/.claude/skills/`.

## Troubleshooting

### Claude doesn't see the skills

1. Check the symlink exists: `ls -la ~/.claude/skills`
2. Check ~/CLAUDE.md exists and references the skills
3. Restart Claude Code

### Scripts don't run

1. Make scripts executable: `chmod +x ~/.claude/skills/docgen/scripts/*.py`
2. Ensure Python 3 is in your PATH

## Updating Skills

Since this is a git repo, you can:

```bash
cd ~/source/claude-tools
git pull  # If you pushed to remote
```

The symlink means Claude Code immediately sees updates.

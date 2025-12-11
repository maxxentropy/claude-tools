# Installation

## Prerequisites

- macOS/Linux (or WSL on Windows)
- Claude Code installed
- Python 3.9+ (for scripts)

## Setup

### 1. Clone Repository

```bash
git clone https://github.com/YOUR_USERNAME/claude-tools.git ~/source/claude-tools
cd ~/source/claude-tools
```

### 2. Create Symlinks

```bash
# Link skills directory
ln -s ~/source/claude-tools/skills ~/.claude/skills

# Link global CLAUDE.md
ln -s ~/source/claude-tools/CLAUDE.md ~/CLAUDE.md
```

### 3. Make Scripts Executable

```bash
find ~/.claude/skills -name "*.py" -exec chmod +x {} \;
```

### 4. Verify

```bash
ls -la ~/.claude/skills
# Should show: skills -> ~/source/claude-tools/skills

cat ~/CLAUDE.md
# Should show the global configuration
```

## Test

Open Claude Code in any project:

```bash
cd ~/source/some-project
claude
```

Ask: "What skills do you have access to?"

## Updating

```bash
cd ~/source/claude-tools
git pull
```

The symlink means Claude Code immediately sees updates.

## Troubleshooting

### Claude doesn't see skills
1. Check symlink: `ls -la ~/.claude/skills`
2. Check CLAUDE.md: `cat ~/CLAUDE.md`
3. Restart Claude Code

### Scripts don't run
1. Make executable: `chmod +x path/to/script.py`
2. Check Python: `python3 --version`

#!/bin/bash
# feature.sh - Streamlined feature branch workflow
#
# Makes feature branches almost as easy as committing to main:
#   feature start 1234              # Creates feature/AB#1234-work-item-title
#   feature pr                      # Pushes and creates PR
#   feature finish                  # Merges PR and cleans up
#
# Integrates with Azure DevOps work items for automatic naming.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# =============================================================================
# Helper Functions
# =============================================================================

print_error() {
    echo -e "${RED}Error:${NC} $1" >&2
}

print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_info() {
    echo -e "${BLUE}→${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}Warning:${NC} $1"
}

check_git_repo() {
    if [[ -z "$REPO_ROOT" ]]; then
        print_error "Not in a git repository"
        exit 1
    fi
}

check_clean_working_tree() {
    if ! git diff --quiet HEAD 2>/dev/null; then
        print_error "You have uncommitted changes. Commit or stash them first."
        echo "  git stash       # Stash changes"
        echo "  git stash pop   # Restore later"
        exit 1
    fi
}

get_current_branch() {
    git rev-parse --abbrev-ref HEAD
}

get_default_branch() {
    # Try to detect default branch
    if git show-ref --verify --quiet refs/heads/main; then
        echo "main"
    elif git show-ref --verify --quiet refs/heads/master; then
        echo "master"
    else
        echo "main"
    fi
}

detect_platform() {
    # Check for platform detection script
    local detector="$SCRIPT_DIR/../skills/azure-devops/scripts/detect_platform.py"
    if [[ -f "$detector" ]]; then
        python3 "$detector" 2>/dev/null || echo "unknown"
    else
        # Fallback: check for gh or az
        if command -v gh &>/dev/null && gh auth status &>/dev/null 2>&1; then
            echo "github"
        elif command -v az &>/dev/null; then
            echo "azdo"
        else
            echo "unknown"
        fi
    fi
}

slugify() {
    # Convert text to URL-safe slug
    echo "$1" | \
        tr '[:upper:]' '[:lower:]' | \
        sed 's/[^a-z0-9]/-/g' | \
        sed 's/--*/-/g' | \
        sed 's/^-//' | \
        sed 's/-$//' | \
        cut -c1-50
}

# =============================================================================
# Feature Workflow Python Helper
# =============================================================================

get_work_item_title() {
    local work_item_id="$1"
    local helper="$SCRIPT_DIR/feature_workflow.py"

    if [[ -f "$helper" ]]; then
        python3 "$helper" get-title "$work_item_id" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# =============================================================================
# Commands
# =============================================================================

cmd_start() {
    local work_item_id="$1"
    local description="${2:-}"
    local prefix="${3:-feature}"

    if [[ -z "$work_item_id" ]]; then
        echo "Usage: feature start <work-item-id> [description] [prefix]"
        echo ""
        echo "Arguments:"
        echo "  work-item-id   Azure DevOps work item ID (required)"
        echo "  description    Branch description (optional, fetched from work item)"
        echo "  prefix         Branch prefix: feature, fix, bugfix (default: feature)"
        echo ""
        echo "Examples:"
        echo "  feature start 1234                    # Auto-fetches title from ADO"
        echo "  feature start 1234 'add-login-page'   # Manual description"
        echo "  feature start 1234 'fix-auth' fix     # Creates fix/AB#1234-fix-auth"
        exit 1
    fi

    check_git_repo
    check_clean_working_tree

    local current=$(get_current_branch)
    local default=$(get_default_branch)

    # Warn if not on default branch
    if [[ "$current" != "$default" && "$current" != "develop" ]]; then
        print_warning "You're on '$current', not '$default'"
        read -p "Continue anyway? [y/N] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # Get description from work item if not provided
    if [[ -z "$description" ]]; then
        print_info "Fetching work item #$work_item_id from Azure DevOps..."
        description=$(get_work_item_title "$work_item_id")
        if [[ -z "$description" ]]; then
            print_warning "Could not fetch work item title. Using ID only."
            description=""
        else
            print_info "Found: $description"
        fi
    fi

    # Build branch name
    local slug=$(slugify "$description")
    local branch_name
    if [[ -n "$slug" ]]; then
        branch_name="$prefix/AB#$work_item_id-$slug"
    else
        branch_name="$prefix/AB#$work_item_id"
    fi

    # Check if branch exists
    if git show-ref --verify --quiet "refs/heads/$branch_name"; then
        print_info "Branch '$branch_name' already exists"
        read -p "Switch to it? [Y/n] " -n 1 -r
        echo
        if [[ $REPLY =~ ^[Nn]$ ]]; then
            exit 0
        fi
        git checkout "$branch_name"
        print_success "Switched to $branch_name"
    else
        # Create and checkout
        git checkout -b "$branch_name"
        print_success "Created and switched to $branch_name"
    fi

    echo ""
    echo -e "${CYAN}Next steps:${NC}"
    echo "  1. Make your changes"
    echo "  2. Commit: git add . && git commit -m 'Your message'"
    echo "     (AB#$work_item_id will be auto-appended by pre-commit hook)"
    echo "  3. Create PR: feature pr"
}

cmd_pr() {
    local draft=""
    local title=""
    local body=""

    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case "$1" in
            --draft|-d)
                draft="--draft"
                shift
                ;;
            --title|-t)
                title="$2"
                shift 2
                ;;
            *)
                shift
                ;;
        esac
    done

    check_git_repo

    local branch=$(get_current_branch)
    local default=$(get_default_branch)

    # Check we're on a feature branch
    if [[ "$branch" == "$default" || "$branch" == "master" || "$branch" == "main" ]]; then
        print_error "You're on '$branch'. Switch to a feature branch first."
        echo "  feature start <work-item-id>"
        exit 1
    fi

    # Check for uncommitted changes
    if ! git diff --quiet HEAD 2>/dev/null; then
        print_warning "You have uncommitted changes"
        read -p "Commit them now? [Y/n] " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Nn]$ ]]; then
            git add -A
            read -p "Commit message: " commit_msg
            git commit -m "$commit_msg"
        fi
    fi

    # Push branch
    print_info "Pushing branch to origin..."
    if ! git push -u origin "$branch" 2>/dev/null; then
        git push --set-upstream origin "$branch"
    fi
    print_success "Pushed $branch"

    # Extract work item ID from branch name
    local work_item_id=""
    if [[ "$branch" =~ AB#([0-9]+) ]]; then
        work_item_id="${BASH_REMATCH[1]}"
    fi

    # Generate title if not provided
    if [[ -z "$title" ]]; then
        # Use first commit message or branch name
        local first_commit=$(git log "$default..$branch" --format="%s" --reverse | head -1)
        if [[ -n "$first_commit" ]]; then
            title="$first_commit"
        else
            title="$branch"
        fi
    fi

    # Generate body
    body="## Summary"$'\n\n'

    # Add commit list
    local commits=$(git log "$default..$branch" --format="- %s" --reverse)
    if [[ -n "$commits" ]]; then
        body+="$commits"$'\n\n'
    fi

    # Add work item link
    if [[ -n "$work_item_id" ]]; then
        body+="## Work Item"$'\n\n'
        body+="AB#$work_item_id"$'\n\n'
    fi

    body+="## Test Plan"$'\n\n'
    body+="- [ ] Tested locally"$'\n'

    # Detect platform and create PR
    local platform=$(detect_platform)
    print_info "Creating PR on $platform..."

    case "$platform" in
        github)
            if ! command -v gh &>/dev/null; then
                print_error "GitHub CLI (gh) not installed"
                echo "  brew install gh && gh auth login"
                exit 1
            fi

            gh pr create \
                --title "$title" \
                --body "$body" \
                --base "$default" \
                $draft

            print_success "PR created!"
            echo ""
            gh pr view --web 2>/dev/null || gh pr view
            ;;

        azdo|azure-devops)
            if ! command -v az &>/dev/null; then
                print_error "Azure CLI (az) not installed"
                echo "  brew install azure-cli"
                echo "  az extension add --name azure-devops"
                echo "  az login"
                exit 1
            fi

            local draft_flag=""
            if [[ -n "$draft" ]]; then
                draft_flag="--draft true"
            fi

            az repos pr create \
                --title "$title" \
                --description "$body" \
                --target-branch "$default" \
                $draft_flag \
                --open

            print_success "PR created!"
            ;;

        *)
            print_error "Could not detect platform (GitHub or Azure DevOps)"
            echo "Make sure you're authenticated:"
            echo "  gh auth login      # For GitHub"
            echo "  az login           # For Azure DevOps"
            exit 1
            ;;
    esac
}

cmd_status() {
    check_git_repo

    local branch=$(get_current_branch)
    local default=$(get_default_branch)

    echo -e "${CYAN}Branch:${NC} $branch"

    # Show commits ahead/behind
    local ahead=$(git rev-list --count "$default..$branch" 2>/dev/null || echo "0")
    local behind=$(git rev-list --count "$branch..$default" 2>/dev/null || echo "0")
    echo -e "${CYAN}Status:${NC} $ahead ahead, $behind behind $default"

    # Show uncommitted changes
    local changes=$(git status --porcelain | wc -l | tr -d ' ')
    if [[ "$changes" -gt 0 ]]; then
        echo -e "${CYAN}Changes:${NC} $changes uncommitted files"
    fi

    # Check for PR
    local platform=$(detect_platform)
    case "$platform" in
        github)
            echo ""
            if gh pr view &>/dev/null; then
                echo -e "${CYAN}Pull Request:${NC}"
                gh pr view --json state,title,url --template '  {{.title}}
  State: {{.state}}
  URL: {{.url}}
'
            else
                echo -e "${CYAN}Pull Request:${NC} None (run 'feature pr' to create)"
            fi
            ;;
        azdo|azure-devops)
            echo ""
            echo -e "${CYAN}Pull Request:${NC} Run 'az repos pr list' to check"
            ;;
    esac

    # Show work item if detected
    if [[ "$branch" =~ AB#([0-9]+) ]]; then
        local work_item_id="${BASH_REMATCH[1]}"
        echo ""
        echo -e "${CYAN}Work Item:${NC} AB#$work_item_id"
    fi
}

cmd_finish() {
    check_git_repo

    local branch=$(get_current_branch)
    local default=$(get_default_branch)

    if [[ "$branch" == "$default" ]]; then
        print_error "Already on $default"
        exit 1
    fi

    local platform=$(detect_platform)

    # Check PR status and merge
    case "$platform" in
        github)
            if ! gh pr view &>/dev/null; then
                print_error "No PR found for this branch"
                echo "Create one with: feature pr"
                exit 1
            fi

            local pr_state=$(gh pr view --json state --jq '.state')
            if [[ "$pr_state" == "MERGED" ]]; then
                print_info "PR already merged"
            elif [[ "$pr_state" == "OPEN" ]]; then
                print_info "Merging PR..."
                gh pr merge --squash --delete-branch
                print_success "PR merged and branch deleted"
            else
                print_error "PR is $pr_state"
                exit 1
            fi
            ;;

        azdo|azure-devops)
            print_info "For Azure DevOps, complete the PR in the web interface"
            print_info "Then run: feature cleanup"
            exit 0
            ;;

        *)
            print_error "Could not detect platform"
            exit 1
            ;;
    esac

    # Switch to default branch
    git checkout "$default"
    git pull

    print_success "Done! Now on $default"
}

cmd_cleanup() {
    check_git_repo

    local branch=$(get_current_branch)
    local default=$(get_default_branch)

    if [[ "$branch" == "$default" ]]; then
        # Already on default, just prune
        print_info "Pruning merged branches..."
        git fetch --prune

        # Delete local branches that no longer have remotes
        git branch -vv | grep ': gone]' | awk '{print $1}' | while read -r b; do
            print_info "Deleting $b (remote deleted)"
            git branch -d "$b" 2>/dev/null || git branch -D "$b"
        done

        print_success "Cleanup complete"
    else
        # On a feature branch, switch and delete
        print_info "Switching to $default..."
        git checkout "$default"
        git pull

        print_info "Deleting local branch $branch..."
        git branch -d "$branch" 2>/dev/null || {
            print_warning "Branch not fully merged"
            read -p "Force delete? [y/N] " -n 1 -r
            echo
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                git branch -D "$branch"
            fi
        }

        print_success "Cleanup complete"
    fi
}

cmd_list() {
    check_git_repo

    echo -e "${CYAN}Local feature branches:${NC}"
    git branch | grep -E '^\s*(feature|fix|bugfix)/' || echo "  (none)"

    echo ""
    echo -e "${CYAN}Open PRs:${NC}"

    local platform=$(detect_platform)
    case "$platform" in
        github)
            gh pr list --author "@me" 2>/dev/null || echo "  (none or not authenticated)"
            ;;
        azdo|azure-devops)
            az repos pr list --creator "$(az account show --query user.name -o tsv)" --status active 2>/dev/null || echo "  (run 'az login' to see)"
            ;;
        *)
            echo "  (authenticate with gh or az to see PRs)"
            ;;
    esac
}

usage() {
    echo "feature - Streamlined feature branch workflow"
    echo ""
    echo -e "${CYAN}Usage:${NC}"
    echo "  feature start <work-item-id> [description]  Create feature branch"
    echo "  feature pr [--draft]                        Push and create PR"
    echo "  feature status                              Show branch/PR status"
    echo "  feature finish                              Merge PR and cleanup"
    echo "  feature cleanup                             Delete merged branches"
    echo "  feature list                                List feature branches/PRs"
    echo ""
    echo -e "${CYAN}Quick workflow:${NC}"
    echo "  feature start 1234          # Create branch from work item"
    echo "  # ... make changes ..."
    echo "  git commit -am 'message'    # Commit (AB#1234 auto-appended)"
    echo "  feature pr                  # Create pull request"
    echo "  feature finish              # After PR approved, merge & cleanup"
    echo ""
    echo -e "${CYAN}Examples:${NC}"
    echo "  feature start 1234                      # Fetches title from ADO"
    echo "  feature start 1234 'add-dark-mode'      # Manual description"
    echo "  feature start 5678 'fix-login' fix      # fix/AB#5678-fix-login"
    echo "  feature pr --draft                      # Create draft PR"
}

# =============================================================================
# Main
# =============================================================================

case "${1:-}" in
    start)
        shift
        cmd_start "$@"
        ;;
    pr)
        shift
        cmd_pr "$@"
        ;;
    status|s)
        cmd_status
        ;;
    finish|done)
        cmd_finish
        ;;
    cleanup|clean)
        cmd_cleanup
        ;;
    list|ls)
        cmd_list
        ;;
    help|--help|-h)
        usage
        ;;
    "")
        usage
        ;;
    *)
        print_error "Unknown command: $1"
        echo ""
        usage
        exit 1
        ;;
esac

#!/bin/bash
#
# Universal Python Test Runner
# ============================
# Sets up a virtual environment, installs dependencies, and runs pytest.
#
# Usage:
#   ./scripts/run_python_tests.sh <project-dir> [pytest-args...]
#
# Examples:
#   ./scripts/run_python_tests.sh skills/azure-devops/scripts
#   ./scripts/run_python_tests.sh skills/azure-devops/scripts -v --tb=short
#   ./scripts/run_python_tests.sh skills/azure-devops/scripts -k "test_branch"
#   ./scripts/run_python_tests.sh .  # Run from project root
#
# The script will:
#   1. Look for pyproject.toml or requirements*.txt in the project directory
#   2. Create a .venv if one doesn't exist
#   3. Install dependencies (skips if already installed)
#   4. Run pytest with any additional arguments passed
#
# Exit codes:
#   0 - All tests passed
#   1 - Tests failed
#   2 - Setup/configuration error

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Logging functions
info() { echo -e "${BLUE}ℹ${NC} $1"; }
success() { echo -e "${GREEN}✓${NC} $1"; }
warn() { echo -e "${YELLOW}⚠${NC} $1"; }
error() { echo -e "${RED}✗${NC} $1" >&2; }

# Show usage
usage() {
    echo "Usage: $0 <project-dir> [pytest-args...]"
    echo ""
    echo "Arguments:"
    echo "  project-dir    Directory containing Python project (with pyproject.toml or requirements.txt)"
    echo "  pytest-args    Optional arguments passed to pytest"
    echo ""
    echo "Examples:"
    echo "  $0 skills/azure-devops/scripts"
    echo "  $0 skills/azure-devops/scripts -v"
    echo "  $0 skills/azure-devops/scripts -k 'test_parse'"
    exit 2
}

# Parse arguments
if [[ $# -lt 1 ]] || [[ "$1" == "-h" ]] || [[ "$1" == "--help" ]]; then
    usage
fi

PROJECT_DIR="$1"
shift  # Remaining args go to pytest
PYTEST_ARGS=("$@")

# Resolve to absolute path
PROJECT_DIR="$(cd "$PROJECT_DIR" 2>/dev/null && pwd)" || {
    error "Directory not found: $1"
    exit 2
}

info "Project directory: $PROJECT_DIR"

# Configuration
VENV_DIR="$PROJECT_DIR/.venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"
VENV_PYTEST="$VENV_DIR/bin/pytest"
MARKER_FILE="$VENV_DIR/.deps_installed"

# Detect dependency file
detect_deps_file() {
    if [[ -f "$PROJECT_DIR/pyproject.toml" ]]; then
        echo "pyproject.toml"
    elif [[ -f "$PROJECT_DIR/requirements-dev.txt" ]]; then
        echo "requirements-dev.txt"
    elif [[ -f "$PROJECT_DIR/requirements-test.txt" ]]; then
        echo "requirements-test.txt"
    elif [[ -f "$PROJECT_DIR/requirements.txt" ]]; then
        echo "requirements.txt"
    else
        echo ""
    fi
}

# Get checksum of dependency file for caching
get_deps_checksum() {
    local deps_file="$1"
    if [[ -n "$deps_file" ]] && [[ -f "$PROJECT_DIR/$deps_file" ]]; then
        if command -v md5sum &> /dev/null; then
            md5sum "$PROJECT_DIR/$deps_file" | cut -d' ' -f1
        elif command -v md5 &> /dev/null; then
            md5 -q "$PROJECT_DIR/$deps_file"
        else
            # Fallback: use file modification time
            stat -f %m "$PROJECT_DIR/$deps_file" 2>/dev/null || stat -c %Y "$PROJECT_DIR/$deps_file"
        fi
    else
        echo "none"
    fi
}

# Check if dependencies need to be installed
needs_install() {
    local deps_file="$1"
    local current_checksum="$2"

    # No venv = needs install
    [[ ! -d "$VENV_DIR" ]] && return 0

    # No marker file = needs install
    [[ ! -f "$MARKER_FILE" ]] && return 0

    # Checksum changed = needs install
    local stored_checksum
    stored_checksum=$(cat "$MARKER_FILE" 2>/dev/null || echo "")
    [[ "$stored_checksum" != "$current_checksum" ]] && return 0

    # pytest not installed = needs install
    [[ ! -f "$VENV_PYTEST" ]] && return 0

    return 1
}

# Create virtual environment
create_venv() {
    info "Creating virtual environment..."
    python3 -m venv "$VENV_DIR"

    # Upgrade pip to avoid warnings
    "$VENV_PIP" install --upgrade pip -q
    success "Virtual environment created"
}

# Extract dependencies from pyproject.toml
# This handles projects that aren't installable packages
extract_pyproject_deps() {
    local pyproject="$1"
    local deps=""

    # Try to extract test dependencies using Python
    deps=$("$VENV_PYTHON" -c "
import sys
try:
    import tomllib
except ImportError:
    try:
        import tomli as tomllib
    except ImportError:
        sys.exit(0)

try:
    with open('$pyproject', 'rb') as f:
        data = tomllib.load(f)

    # Get main dependencies
    main_deps = data.get('project', {}).get('dependencies', [])

    # Get test dependencies
    optional = data.get('project', {}).get('optional-dependencies', {})
    test_deps = optional.get('test', []) + optional.get('dev', [])

    all_deps = list(set(main_deps + test_deps))
    print(' '.join(all_deps))
except Exception:
    pass
" 2>/dev/null)

    echo "$deps"
}

# Install dependencies
install_deps() {
    local deps_file="$1"

    info "Installing dependencies..."

    if [[ "$deps_file" == "pyproject.toml" ]]; then
        # First check if this is a proper installable package (has build-system)
        if grep -q '\[build-system\]' "$PROJECT_DIR/pyproject.toml" 2>/dev/null; then
            # It's an installable package, use pip install -e
            if grep -q '\[project.optional-dependencies\]' "$PROJECT_DIR/pyproject.toml" 2>/dev/null; then
                "$VENV_PIP" install -e "$PROJECT_DIR[test]" -q 2>/dev/null || \
                "$VENV_PIP" install -e "$PROJECT_DIR" -q 2>/dev/null || true
            else
                "$VENV_PIP" install -e "$PROJECT_DIR" -q 2>/dev/null || true
            fi
        else
            # Not an installable package - extract and install deps directly
            # First ensure we have tomli for older Python versions
            "$VENV_PIP" install tomli -q 2>/dev/null || true

            local deps
            deps=$(extract_pyproject_deps "$PROJECT_DIR/pyproject.toml")

            if [[ -n "$deps" ]]; then
                # shellcheck disable=SC2086
                "$VENV_PIP" install $deps -q
            fi
        fi
        # Ensure pytest is installed even if not in deps
        "$VENV_PIP" install pytest -q 2>/dev/null || true
    elif [[ -n "$deps_file" ]]; then
        "$VENV_PIP" install -r "$PROJECT_DIR/$deps_file" -q
        # Ensure pytest is installed even if not in deps
        "$VENV_PIP" install pytest -q 2>/dev/null || true
    else
        # No deps file, just install pytest
        warn "No dependency file found, installing pytest only"
        "$VENV_PIP" install pytest -q
    fi

    success "Dependencies installed"
}

# Find test files
find_tests() {
    local tests_found=0

    # Check for tests/ directory
    if [[ -d "$PROJECT_DIR/tests" ]]; then
        tests_found=1
    fi

    # Check for test_*.py files
    if ls "$PROJECT_DIR"/test_*.py 1>/dev/null 2>&1; then
        tests_found=1
    fi

    # Check for *_test.py files
    if ls "$PROJECT_DIR"/*_test.py 1>/dev/null 2>&1; then
        tests_found=1
    fi

    return $((1 - tests_found))
}

# Main execution
main() {
    # Detect dependency file
    DEPS_FILE=$(detect_deps_file)
    if [[ -n "$DEPS_FILE" ]]; then
        info "Found dependency file: $DEPS_FILE"
    else
        warn "No dependency file found (pyproject.toml or requirements.txt)"
    fi

    # Get checksum for caching
    DEPS_CHECKSUM=$(get_deps_checksum "$DEPS_FILE")

    # Setup virtual environment if needed
    if needs_install "$DEPS_FILE" "$DEPS_CHECKSUM"; then
        if [[ ! -d "$VENV_DIR" ]]; then
            create_venv
        fi
        install_deps "$DEPS_FILE"

        # Store checksum for future runs
        echo "$DEPS_CHECKSUM" > "$MARKER_FILE"
    else
        success "Dependencies up to date (cached)"
    fi

    # Verify pytest is available
    if [[ ! -f "$VENV_PYTEST" ]]; then
        error "pytest not found in virtual environment"
        exit 2
    fi

    # Check for tests
    if ! find_tests; then
        warn "No test files found in $PROJECT_DIR"
        warn "Expected: tests/ directory, test_*.py, or *_test.py files"
        exit 0
    fi

    # Run pytest
    echo ""
    info "Running pytest..."
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Change to project directory and run tests
    cd "$PROJECT_DIR"

    # Build pytest command
    # Add the project dir to PYTHONPATH so local imports work
    export PYTHONPATH="$PROJECT_DIR:${PYTHONPATH:-}"

    # Run pytest with any additional args
    if [[ ${#PYTEST_ARGS[@]} -gt 0 ]]; then
        "$VENV_PYTEST" "${PYTEST_ARGS[@]}"
    else
        # Default: verbose with short traceback
        "$VENV_PYTEST" -v --tb=short
    fi

    local exit_code=$?

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    if [[ $exit_code -eq 0 ]]; then
        success "All tests passed"
    else
        error "Tests failed (exit code: $exit_code)"
    fi

    return $exit_code
}

# Run main
main

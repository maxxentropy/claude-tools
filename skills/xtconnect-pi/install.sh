#!/bin/bash
#
# Install xtpi CLI tool
#
# Usage:
#   ./install.sh           # Install to ~/.local/bin (recommended)
#   ./install.sh --global  # Install to /usr/local/bin (requires sudo)
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
XTPI_PATH="$SCRIPT_DIR/scripts/xtpi"

# Color output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

echo -e "${CYAN}XTConnect Pi CLI Installer${NC}"
echo "==============================="
echo

# Check if xtpi script exists
if [ ! -f "$XTPI_PATH" ]; then
    echo -e "${RED}Error: xtpi script not found at $XTPI_PATH${NC}"
    exit 1
fi

# Determine install location
if [ "$1" = "--global" ]; then
    INSTALL_DIR="/usr/local/bin"
    NEED_SUDO=true
else
    INSTALL_DIR="$HOME/.local/bin"
    NEED_SUDO=false
fi

# Create install directory if needed
if [ ! -d "$INSTALL_DIR" ]; then
    echo "Creating $INSTALL_DIR..."
    if [ "$NEED_SUDO" = true ]; then
        sudo mkdir -p "$INSTALL_DIR"
    else
        mkdir -p "$INSTALL_DIR"
    fi
fi

# Create symlink
LINK_PATH="$INSTALL_DIR/xtpi"
echo "Installing xtpi to $LINK_PATH..."

if [ "$NEED_SUDO" = true ]; then
    sudo ln -sf "$XTPI_PATH" "$LINK_PATH"
else
    ln -sf "$XTPI_PATH" "$LINK_PATH"
fi

echo -e "${GREEN}✓ Installed successfully${NC}"
echo

# Check if install directory is in PATH
if [[ ":$PATH:" != *":$INSTALL_DIR:"* ]]; then
    echo -e "${YELLOW}Note: $INSTALL_DIR is not in your PATH${NC}"
    echo
    echo "Add this to your shell profile (~/.zshrc or ~/.bashrc):"
    echo
    echo -e "  ${CYAN}export PATH=\"$INSTALL_DIR:\$PATH\"${NC}"
    echo
    echo "Then reload your shell:"
    echo
    echo -e "  ${CYAN}source ~/.zshrc${NC}"
    echo
else
    echo "Verify installation:"
    echo
    echo -e "  ${CYAN}xtpi --help${NC}"
fi

echo
echo "Quick start:"
echo -e "  ${CYAN}xtpi discover${NC}            # Find nodes on network"
echo -e "  ${CYAN}xtpi connect <hostname>${NC}  # Connect to a node"
echo -e "  ${CYAN}xtpi status${NC}              # Show node status"
echo -e "  ${CYAN}xtpi serial --live${NC}       # Monitor serial traffic"

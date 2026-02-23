#!/usr/bin/env bash
# optimize-anything installer / uninstaller
#
# Install:
#   curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash
#
# Uninstall:
#   curl -fsSL https://raw.githubusercontent.com/ASRagab/optimize-anything/main/install.sh | bash -s -- --uninstall
#
# What install does:
#   1. Installs uv (if not already installed)
#   2. Installs optimize-anything as a global CLI tool via uv tool install
#   3. Verifies the installation
#
# Environment variables:
#   OPTIMIZE_ANYTHING_REPO  - Git URL or local path to install from (default: GitHub repo)
#   OPTIMIZE_ANYTHING_REF   - Git ref to install (default: main)

set -euo pipefail

# --- Configuration ---
REPO="${OPTIMIZE_ANYTHING_REPO:-git+https://github.com/ASRagab/optimize-anything}"
REF="${OPTIMIZE_ANYTHING_REF:-main}"

# Local paths don't use @ref syntax
if [[ "${REPO}" == /* ]] || [[ "${REPO}" == ./* ]]; then
    INSTALL_SOURCE="${REPO}"
else
    INSTALL_SOURCE="${REPO}@${REF}"
fi

# --- Colors (if terminal supports them) ---
if [ -t 1 ]; then
    BOLD="\033[1m"
    GREEN="\033[32m"
    YELLOW="\033[33m"
    RED="\033[31m"
    RESET="\033[0m"
else
    BOLD="" GREEN="" YELLOW="" RED="" RESET=""
fi

info()  { echo -e "${BOLD}${GREEN}==>${RESET} ${BOLD}$1${RESET}"; }
warn()  { echo -e "${BOLD}${YELLOW}warning:${RESET} $1"; }
error() { echo -e "${BOLD}${RED}error:${RESET} $1" >&2; }

# --- Uninstall ---
uninstall() {
    echo ""
    echo -e "${BOLD}optimize-anything uninstaller${RESET}"
    echo ""

    if ! command -v uv &>/dev/null; then
        error "uv is not installed — nothing to uninstall"
        exit 1
    fi

    if uv tool uninstall optimize-anything 2>&1; then
        info "optimize-anything has been uninstalled"
        echo ""
        echo "The isolated environment and CLI executable have been removed."
        echo "uv itself was NOT removed. To remove uv: uv self uninstall"
    else
        warn "optimize-anything may not be installed via uv tool"
        echo ""
        echo "If installed from source, just delete the cloned directory."
    fi
}

# --- Install: Step 1 ---
install_uv() {
    if command -v uv &>/dev/null; then
        info "uv is already installed ($(uv --version))"
        return 0
    fi

    info "Installing uv..."
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Source the env so uv is available in this session
    export PATH="$HOME/.local/bin:$HOME/.cargo/bin:$PATH"

    if ! command -v uv &>/dev/null; then
        error "uv installation failed. Install manually: https://docs.astral.sh/uv/"
        exit 1
    fi

    info "uv installed ($(uv --version))"
}

# --- Install: Step 2 ---
install_tool() {
    info "Installing optimize-anything from ${INSTALL_SOURCE}..."

    if uv tool install "${INSTALL_SOURCE}" --force 2>&1; then
        info "optimize-anything installed successfully"
    else
        error "Installation failed"
        echo ""
        echo "Troubleshooting:"
        echo "  - Check the repo URL: ${REPO}"
        echo "  - Try installing manually: uv tool install '${INSTALL_SOURCE}'"
        echo "  - For local installs: uv tool install /path/to/optimize-anything"
        exit 1
    fi
}

# --- Install: Step 3 ---
verify() {
    export PATH="$HOME/.local/bin:$PATH"

    if command -v optimize-anything &>/dev/null; then
        info "Verification passed"
        echo ""
        echo -e "${BOLD}optimize-anything is ready!${RESET}"
        echo ""
        echo "  optimize-anything optimize --help    # See CLI options"
        echo "  optimize-anything explain seed.txt   # Preview optimization"
        echo "  optimize-anything budget seed.txt    # Get budget recommendation"
        echo ""
        echo "To uninstall: uv tool uninstall optimize-anything"
        echo ""
        echo "If the command is not found, add this to your shell profile:"
        echo '  export PATH="$HOME/.local/bin:$PATH"'
    else
        warn "optimize-anything was installed but is not on your PATH"
        echo ""
        echo "Add this to your ~/.bashrc or ~/.zshrc:"
        echo '  export PATH="$HOME/.local/bin:$PATH"'
        echo ""
        echo "Then restart your shell or run: source ~/.bashrc"
    fi
}

# --- Main ---
main() {
    # Check for --uninstall flag
    for arg in "$@"; do
        if [ "$arg" = "--uninstall" ] || [ "$arg" = "uninstall" ]; then
            uninstall
            exit 0
        fi
    done

    echo ""
    echo -e "${BOLD}optimize-anything installer${RESET}"
    echo ""

    install_uv
    install_tool
    verify
}

main "$@"

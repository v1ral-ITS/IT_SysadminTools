#!/usr/bin/env bash
# install.sh -- one-shot installer for IT_SysadminTools.
#
# Usage:
#   curl -fsSL https://raw.githubusercontent.com/v1ral-ITS/IT_SysadminTools/main/install.sh | bash
#   curl -fsSL https://raw.githubusercontent.com/v1ral-ITS/IT_SysadminTools/main/install.sh | bash -s -- --version v0.2.0
#   curl -fsSL https://raw.githubusercontent.com/v1ral-ITS/IT_SysadminTools/main/install.sh | bash -s -- --prefix ~/.local
#
# Installs:
#   IT_Backupmanager   -> $PREFIX/bin/IT_Backupmanager   (binary from GitHub Releases)
#   IT_MountMyDrives   -> $PREFIX/bin/IT_MountMyDrives   (shell script)
#   mounts.conf.example to $XDG_CONFIG_HOME/IT_SysadminTools/ (if missing)

set -euo pipefail

REPO="v1ral-ITS/IT_SysadminTools"
VERSION="latest"
PREFIX="/usr/local"
DRY_RUN=0
DOWNLOADER=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) VERSION="$2"; shift 2 ;;
        --version=*) VERSION="${1#*=}"; shift ;;
        --prefix) PREFIX="$2"; shift 2 ;;
        --prefix=*) PREFIX="${1#*=}"; shift ;;
        --dry-run|-n) DRY_RUN=1; shift ;;
        -h|--help)
            sed -n '2,12p' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            exit 2
            ;;
    esac
done

log() { printf '\033[1;34m[install]\033[0m %s\n' "$*"; }
err() { printf '\033[1;31m[error]\033[0m %s\n' "$*" >&2; }

run() {
    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[dry] $*"
    else
        # shellcheck disable=SC2294
        eval "$@"
    fi
}

pick_downloader() {
    if command -v curl >/dev/null 2>&1; then
        DOWNLOADER="curl -fsSL"
    elif command -v wget >/dev/null 2>&1; then
        DOWNLOADER="wget -qO-"
    else
        err "Need curl or wget to download release artifacts."
        exit 1
    fi
}

resolve_version() {
    if [[ "$VERSION" != "latest" ]]; then return 0; fi
    log "Resolving latest release tag from GitHub API..."
    local api="https://api.github.com/repos/$REPO/releases/latest"
    local tag
    tag="$($DOWNLOADER "$api" | grep -oE '"tag_name": *"[^"]+"' | head -1 | sed 's/.*"\([^"]*\)"$/\1/')"
    if [[ -z "$tag" ]]; then
        err "Could not resolve latest release tag for $REPO."
        exit 1
    fi
    VERSION="$tag"
    log "Latest is $VERSION"
}

need_sudo() {
    # Decide if we need sudo for the install steps (write to $PREFIX/bin).
    if [[ -w "$PREFIX/bin" ]] || mkdir -p "$PREFIX/bin" 2>/dev/null && [[ -w "$PREFIX/bin" ]]; then
        SUDO=""
    elif command -v sudo >/dev/null 2>&1; then
        SUDO="sudo"
    else
        err "$PREFIX/bin is not writable and sudo is not available."
        err "Try --prefix \$HOME/.local"
        exit 1
    fi
}

install_binary() {
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT

    local base="https://github.com/$REPO/releases/download/$VERSION"
    log "Downloading IT_Backupmanager binary..."
    if [[ "$DOWNLOADER" == curl* ]]; then
        run "curl -fsSL '$base/IT_Backupmanager'        -o '$tmp/IT_Backupmanager'"
        run "curl -fsSL '$base/IT_Backupmanager.sha256' -o '$tmp/IT_Backupmanager.sha256'"
    else
        run "wget -q '$base/IT_Backupmanager'        -O '$tmp/IT_Backupmanager'"
        run "wget -q '$base/IT_Backupmanager.sha256' -O '$tmp/IT_Backupmanager.sha256'"
    fi

    if [[ "$DRY_RUN" -eq 0 ]]; then
        log "Verifying sha256..."
        (cd "$tmp" && sha256sum -c IT_Backupmanager.sha256)
    fi

    log "Installing to $PREFIX/bin/IT_Backupmanager"
    run "$SUDO install -m 0755 '$tmp/IT_Backupmanager' '$PREFIX/bin/IT_Backupmanager'"
}

install_mount_script() {
    local tmp
    tmp="$(mktemp -d)"
    trap 'rm -rf "$tmp"' EXIT

    local raw="https://raw.githubusercontent.com/$REPO/$VERSION"
    log "Downloading IT_MountMyDrives.sh..."
    if [[ "$DOWNLOADER" == curl* ]]; then
        run "curl -fsSL '$raw/IT_MountMyDrives.sh'    -o '$tmp/IT_MountMyDrives'"
        run "curl -fsSL '$raw/mounts.conf.example'    -o '$tmp/mounts.conf.example'"
    else
        run "wget -q '$raw/IT_MountMyDrives.sh'    -O '$tmp/IT_MountMyDrives'"
        run "wget -q '$raw/mounts.conf.example'    -O '$tmp/mounts.conf.example'"
    fi

    log "Installing to $PREFIX/bin/IT_MountMyDrives"
    run "$SUDO install -m 0755 '$tmp/IT_MountMyDrives' '$PREFIX/bin/IT_MountMyDrives'"

    local cfg_dir="${XDG_CONFIG_HOME:-$HOME/.config}/IT_SysadminTools"
    if [[ ! -f "$cfg_dir/mounts.conf" ]]; then
        log "Seeding example config at $cfg_dir/mounts.conf.example"
        run "mkdir -p '$cfg_dir'"
        run "install -m 0644 '$tmp/mounts.conf.example' '$cfg_dir/mounts.conf.example'"
        echo
        echo "  Next step: copy and edit the config:"
        echo "    cp '$cfg_dir/mounts.conf.example' '$cfg_dir/mounts.conf'"
        echo "    \$EDITOR '$cfg_dir/mounts.conf'"
        echo
    else
        log "Config already exists at $cfg_dir/mounts.conf -- leaving it alone."
    fi
}

main() {
    pick_downloader
    resolve_version
    need_sudo

    log "Installing $REPO@$VERSION to $PREFIX/bin (dry_run=$DRY_RUN)"

    install_binary
    install_mount_script

    log "Done."
    log "Try: IT_Backupmanager --help"
    log "Try: IT_MountMyDrives --help"
}

main "$@"

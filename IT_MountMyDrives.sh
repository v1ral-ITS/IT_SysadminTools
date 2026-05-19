#!/usr/bin/env bash
# IT_MountMyDrives.sh
# Mount a user-defined set of drives by filesystem LABEL or by DEVICE path.
# All mount targets come from a config file. Edit the config, not the script.

set -uo pipefail

PROG_NAME="$(basename "$0")"

log_dir() {
    local state_home="${XDG_STATE_HOME:-}"
    if [[ -z "$state_home" ]]; then
        local home_dir
        if [[ -n "${SUDO_USER:-}" ]]; then
            home_dir="$(getent passwd "$SUDO_USER" | cut -d: -f6)"
        else
            home_dir="${HOME:-/root}"
        fi
        state_home="$home_dir/.local/state"
    fi
    echo "$state_home/IT_SysadminTools/logs"
}

start_logging() {
    local dir
    dir="$(log_dir)"
    mkdir -p "$dir" 2>/dev/null || return 0
    local stamp
    stamp="$(date '+%Y-%m-%d_%H-%M-%S')"
    LOG_FILE="$dir/IT_MountMyDrives-$stamp.log"

    # Fix ownership if root-via-sudo so the real user can read it later.
    if [[ -n "${SUDO_UID:-}" && -n "${SUDO_GID:-}" ]]; then
        chown -R "$SUDO_UID:$SUDO_GID" "$dir" 2>/dev/null || true
    fi

    echo "Logging to: $LOG_FILE"
    # Tee all subsequent stdout/stderr into the log.
    exec > >(tee -a "$LOG_FILE") 2>&1

    echo "=== IT_MountMyDrives started at $(date -Iseconds) ==="
    echo "argv: $* (dry_run=$DRY_RUN)"
    echo "uid=$UID sudo_user=${SUDO_USER:-}"
}

print_usage() {
    cat <<EOF
Usage: $PROG_NAME [--config PATH] [--dry-run] [--help]

Mount drives listed in a config file. Each non-comment line is one of:

    label  <FS_LABEL>  <MOUNTPOINT>  [fstype]  [mount_options]
    device <DEVICE>    <MOUNTPOINT>  [fstype]  [mount_options]

Lines starting with '#' or blank lines are ignored.

Config search order (first match wins):
  1. \$IT_MOUNT_CONFIG environment variable
  2. --config PATH argument
  3. \$XDG_CONFIG_HOME/IT_SysadminTools/mounts.conf
     (or \$HOME/.config/IT_SysadminTools/mounts.conf)
  4. /etc/IT_SysadminTools/mounts.conf
  5. ./mounts.conf next to this script

--dry-run shows what would be mounted without actually mounting. Safe to run
without sudo. Useful for sanity-checking a new mounts.conf.

Run with --help for this message. See mounts.conf.example for a sample.
EOF
}

CONFIG_ARG=""
DRY_RUN=0
ORIG_ARGS=("$@")
while [[ $# -gt 0 ]]; do
    case "$1" in
        --config)
            CONFIG_ARG="${2:-}"
            shift 2
            ;;
        --config=*)
            CONFIG_ARG="${1#*=}"
            shift
            ;;
        --dry-run|-n)
            DRY_RUN=1
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo "Unknown argument: $1" >&2
            print_usage >&2
            exit 2
            ;;
    esac
done

# Resolve the directory of this script for the local-fallback config lookup.
SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" &>/dev/null && pwd)"

# Compute the real user's $HOME even when running under sudo.
real_home() {
    if [[ -n "${SUDO_USER:-}" ]]; then
        getent passwd "$SUDO_USER" | cut -d: -f6
    else
        echo "${HOME:-/root}"
    fi
}

resolve_config() {
    local candidates=()

    if [[ -n "${IT_MOUNT_CONFIG:-}" ]]; then
        candidates+=("$IT_MOUNT_CONFIG")
    fi

    if [[ -n "$CONFIG_ARG" ]]; then
        candidates+=("$CONFIG_ARG")
    fi

    local xdg
    xdg="${XDG_CONFIG_HOME:-$(real_home)/.config}"
    candidates+=("$xdg/IT_SysadminTools/mounts.conf")
    candidates+=("/etc/IT_SysadminTools/mounts.conf")
    candidates+=("$SCRIPT_DIR/mounts.conf")

    for path in "${candidates[@]}"; do
        if [[ -f "$path" ]]; then
            echo "$path"
            return 0
        fi
    done

    return 1
}

mount_one() {
    local kind="$1"
    local identifier="$2"
    local mountpoint="$3"
    local fstype="${4:-}"
    local options="${5:-}"
    local dev=""

    if [[ -z "$identifier" || -z "$mountpoint" ]]; then
        echo "Skipping malformed entry: kind=$kind identifier='$identifier' mountpoint='$mountpoint'" >&2
        return 1
    fi

    if [[ "$DRY_RUN" -eq 0 ]]; then
        mkdir -p "$mountpoint"
    elif [[ ! -d "$mountpoint" ]]; then
        echo "[dry]  would create mountpoint $mountpoint"
    fi

    if findmnt -rn -M "$mountpoint" >/dev/null 2>&1; then
        echo "[skip] $mountpoint is already a mountpoint"
        return 0
    fi

    case "$kind" in
        label)
            dev="$(blkid -L "$identifier" -c /dev/null 2>/dev/null || true)"
            if [[ -z "$dev" ]]; then
                if [[ "$DRY_RUN" -eq 1 ]]; then
                    echo "[dry]  no device with LABEL='$identifier' present right now"
                    return 0
                fi
                echo "[fail] no device found with LABEL='$identifier'" >&2
                return 1
            fi
            ;;
        device)
            dev="$identifier"
            if [[ ! -b "$dev" ]]; then
                if [[ "$DRY_RUN" -eq 1 ]]; then
                    echo "[dry]  '$dev' is not a block device right now"
                    return 0
                fi
                echo "[fail] '$dev' is not a block device" >&2
                return 1
            fi
            ;;
        *)
            echo "[fail] unknown entry kind '$kind' (expected 'label' or 'device')" >&2
            return 1
            ;;
    esac

    if findmnt -rn -S "$dev" >/dev/null 2>&1; then
        local already
        already="$(findmnt -rn -S "$dev" -o TARGET | head -n1)"
        echo "[skip] $dev is already mounted at $already"
        return 0
    fi

    local -a mount_cmd=(mount)
    [[ -n "$fstype" ]] && mount_cmd+=(-t "$fstype")
    [[ -n "$options" ]] && mount_cmd+=(-o "$options")
    mount_cmd+=("$dev" "$mountpoint")

    if [[ "$DRY_RUN" -eq 1 ]]; then
        echo "[dry]  would run: ${mount_cmd[*]}"
        return 0
    fi

    if "${mount_cmd[@]}"; then
        echo "[ok]   mounted $dev at $mountpoint"
        return 0
    fi

    echo "[fail] mount failed: ${mount_cmd[*]}" >&2
    return 1
}

main() {
    # Auto-elevate AFTER parsing flags so --help and --dry-run work without sudo.
    if [[ "$UID" -ne 0 && "$DRY_RUN" -eq 0 ]]; then
        exec sudo --preserve-env=IT_MOUNT_CONFIG,XDG_CONFIG_HOME,HOME "$0" "${ORIG_ARGS[@]}"
    fi

    start_logging "${ORIG_ARGS[@]}"

    local config
    if ! config="$(resolve_config)"; then
        cat >&2 <<EOF
$PROG_NAME: no config file found.

Create one with the entries you want, then re-run. Quick start:

    mkdir -p "\$HOME/.config/IT_SysadminTools"
    cp mounts.conf.example "\$HOME/.config/IT_SysadminTools/mounts.conf"
    \$EDITOR "\$HOME/.config/IT_SysadminTools/mounts.conf"

See '$PROG_NAME --help' for full search order and entry format.
EOF
        exit 1
    fi

    echo "Using config: $config"

    local rc=0
    local lineno=0
    while IFS= read -r raw_line || [[ -n "$raw_line" ]]; do
        lineno=$((lineno + 1))
        # Strip leading/trailing whitespace and inline comments.
        local line="${raw_line%%#*}"
        line="${line#"${line%%[![:space:]]*}"}"
        line="${line%"${line##*[![:space:]]}"}"
        [[ -z "$line" ]] && continue

        # shellcheck disable=SC2206
        local fields=($line)
        local kind="${fields[0]:-}"
        local identifier="${fields[1]:-}"
        local mountpoint="${fields[2]:-}"
        local fstype="${fields[3]:-}"
        local options="${fields[4]:-}"

        if ! mount_one "$kind" "$identifier" "$mountpoint" "$fstype" "$options"; then
            rc=1
            echo "  (config line $lineno: $raw_line)" >&2
        fi
    done <"$config"

    exit "$rc"
}

main "$@"

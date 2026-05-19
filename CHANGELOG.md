# Changelog

All notable changes to this project are documented here.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- `IT_MountMyDrives.sh`: replace `findmnt -T "$mountpoint"` with
  `findmnt -M "$mountpoint"`. `-T` returns the filesystem containing the path
  (so any subdirectory of an already-mounted FS looked "already mounted"),
  while `-M` only matches when `$mountpoint` is exactly a mount target. Cured
  the false-positive `[skip]` on configs like `label 5_TB /mnt/5_TB` when
  `/mnt/5_TB` was a plain directory on the root filesystem.
- `IT_MountMyDrives.sh`: pass `-c /dev/null` to `blkid -L` so label lookup
  bypasses the on-disk cache (`/run/blkid/blkid.tab`). A drive that was
  previously labeled `5_TB` and later relabeled (e.g., to `KALI_DATA`) could
  still be returned for `blkid -L 5_TB` from the stale cache, causing the
  script to report the wrong device as "already mounted at $other_target".

## [0.2.0] - 2026-05-19

### Added
- `--dry-run` flag on `IT_MountMyDrives.sh`. Previews what would be mounted
  without touching the system. Skips sudo elevation so it can be run unprivileged.
- `--dry-run` flag on `IT_Backupmanager.py`. Prints each command with a
  `[DRY-RUN]` prefix instead of executing it. Skips sudo elevation and makes
  the sha256 + rotation helpers no-ops to avoid acting on files that were
  never written.
- Timestamped per-run logs at `$XDG_STATE_HOME/IT_SysadminTools/logs/`
  (default `~/.local/state/IT_SysadminTools/logs/`). Log files are owned by
  the real user even when the scripts auto-elevate via sudo.
- `install.sh` one-shot installer.

## [0.1.0] - 2026-05-19

### Added
- Initial public release.
- `IT_Backupmanager.py`: zenity-driven backup and restore utility supporting
  dpkg/apt package state, $HOME, root filesystem snapshot via rsync, full disk
  image via dd+zstd, /etc and selected configs, custom tar.zst, and restore
  from any tar.zst archive with optional sha256 verification.
- `IT_MountMyDrives.sh`: config-driven drive mounter supporting LABEL and
  DEVICE entries with optional fstype and mount options. Auto-elevates via
  sudo and uses an XDG-aware config search order.
- GitHub Actions CI: `bash -n`, `shellcheck`, `python -m py_compile`, `ruff`.
- MIT licensed. PyInstaller onefile binary published as release asset.

[Unreleased]: https://github.com/v1ral-ITS/IT_SysadminTools/compare/v0.2.0...HEAD
[0.2.0]: https://github.com/v1ral-ITS/IT_SysadminTools/compare/v0.1.0...v0.2.0
[0.1.0]: https://github.com/v1ral-ITS/IT_SysadminTools/releases/tag/v0.1.0

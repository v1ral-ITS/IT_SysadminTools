# IT_SysadminTools

Personal sysadmin utilities for Linux workstations. Two standalone scripts, no shared dependencies.

## Scripts

### `IT_Backupmanager.py`
Zenity-driven interactive backup and restore tool. Auto-elevates with `sudo`.

Modes:
- Backup `dpkg --get-selections` and `apt-mark showmanual`
- Backup `$HOME` (tar + zstd, optional xattrs/ACLs)
- Root filesystem snapshot via `rsync -aAXHv --delete` with excludes
- Full disk image (`dd | pv | zstd`)
- Backup `/etc` and selected critical configs
- Custom `tar.zst` of arbitrary paths
- Restore from any `.tar.zst` archive in a folder (with optional sha256 verification)

All archives get a sidecar `.sha256` file and a 2-deep rotation per prefix.

**Requirements:** `zenity`, `tar`, `pv`, `zstd`, `rsync`, `dd`, `blockdev`, `dpkg`, `apt-mark`.

### `IT_MountMyDrives.sh`
Mounts a user-defined set of drives -- by filesystem `LABEL` or by `DEVICE` path -- from a config file. Each mount is independent; one failure does not abort the others. Auto-elevates with `sudo`.

**Quick start:**
```bash
mkdir -p ~/.config/IT_SysadminTools
cp mounts.conf.example ~/.config/IT_SysadminTools/mounts.conf
$EDITOR ~/.config/IT_SysadminTools/mounts.conf
./IT_MountMyDrives.sh
```

**Config search order** (first match wins):
1. `$IT_MOUNT_CONFIG` environment variable
2. `--config PATH` command-line argument
3. `$XDG_CONFIG_HOME/IT_SysadminTools/mounts.conf` (or `~/.config/IT_SysadminTools/mounts.conf`)
4. `/etc/IT_SysadminTools/mounts.conf`
5. `./mounts.conf` next to the script

**Entry format** (one per line):
```
label  <FS_LABEL>   <MOUNTPOINT>  [fstype]  [mount_options]
device <DEVICE>     <MOUNTPOINT>  [fstype]  [mount_options]
```

See [`mounts.conf.example`](mounts.conf.example) for samples. Run with `--help` for usage.

## Install

### One-liner (recommended)

```bash
curl -fsSL https://raw.githubusercontent.com/v1ral-ITS/IT_SysadminTools/main/install.sh | bash
```

Pin a specific version, or install into your home directory:
```bash
curl -fsSL https://raw.githubusercontent.com/v1ral-ITS/IT_SysadminTools/main/install.sh | bash -s -- --version v0.2.0
curl -fsSL https://raw.githubusercontent.com/v1ral-ITS/IT_SysadminTools/main/install.sh | bash -s -- --prefix ~/.local
```

The installer downloads the latest `IT_Backupmanager` release binary, verifies its sha256, installs both scripts to `$PREFIX/bin`, and drops `mounts.conf.example` into `$XDG_CONFIG_HOME/IT_SysadminTools/`. Run with `--dry-run` to preview.

### From source

```bash
# Optional: build a self-contained binary with PyInstaller
pip install pyinstaller
pyinstaller --onefile --name IT_Backupmanager --strip IT_Backupmanager.py
sudo install -m 0755 dist/IT_Backupmanager /usr/local/bin/IT_Backupmanager

# Mount helper
sudo install -m 0755 IT_MountMyDrives.sh /usr/local/bin/IT_MountMyDrives
```

## CI

GitHub Actions runs on every push and PR:
- `shellcheck` on the Bash script
- `bash -n` syntax check
- `ruff` lint on the Python script
- `python -m py_compile` syntax check

## License

MIT -- see [LICENSE](LICENSE).

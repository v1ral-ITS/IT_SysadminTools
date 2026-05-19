#!/usr/bin/env python3

import os
import sys
import shlex
import glob
import shutil
import hashlib
import subprocess
from datetime import datetime

def _real_user_home():
    sudo_user = os.environ.get("SUDO_USER")
    if sudo_user:
        try:
            import pwd
            return pwd.getpwnam(sudo_user).pw_dir
        except (KeyError, ImportError):
            pass
    return os.path.expanduser("~")


_DRY_RUN_ON_ARGV = any(arg in ("--dry-run", "-n") for arg in sys.argv[1:])

# Auto elevate to root like: [ "$UID" -eq 0 ] || exec sudo "$0" "$@"
# Skip elevation in dry-run so the user can preview commands without sudo.
if os.geteuid() != 0 and not _DRY_RUN_ON_ARGV:
    if not shutil.which("sudo"):
        print("Error: sudo not found and not running as root.", file=sys.stderr)
        sys.exit(1)
    os.execvp("sudo", ["sudo", "-E", sys.executable] + sys.argv)
    sys.exit(1)

class BackupUI:
    def run_zenity(self, args, *, input_text=None, check=False):
        """Run zenity safely and return CompletedProcess or None on missing binary."""
        try:
            return subprocess.run(
                ["zenity", *args],
                input=input_text,
                capture_output=True,
                text=True,
                check=check,
            )
        except FileNotFoundError:
            print("Error: zenity is not installed or not in PATH.", file=sys.stderr)
            return None
        except subprocess.CalledProcessError as exc:
            return exc

    def show_error(self, text):
        if shutil.which("zenity"):
            self.run_zenity(["--error", "--width=500", f"--text={text}"])
        else:
            print(f"ERROR: {text}", file=sys.stderr)

    def show_info(self, text):
        if shutil.which("zenity"):
            self.run_zenity(["--info", "--width=500", f"--text={text}"])
        else:
            print(text)

    def ask_question(self, title, text):
        result = self.run_zenity(
            ["--question", f"--title={title}", "--width=500", f"--text={text}"]
        )
        return result is not None and result.returncode == 0

    def ask_entry(self, title, text, width=500):
        result = self.run_zenity(
            ["--entry", f"--title={title}", f"--width={width}", f"--text={text}"]
        )
        if result is None or result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    def ask_list(self, title, text, columns, rows, *, width=500, height=300):
        args = [
            "--list",
            f"--title={title}",
            f"--width={width}",
            f"--height={height}",
            f"--text={text}",
        ]
        for column in columns:
            args.append(f"--column={column}")
        args.extend(rows)
        result = self.run_zenity(args)
        if result is None or result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    def ask_directory(self, title, width=650, height=400):
        result = self.run_zenity(
            [
                "--file-selection",
                "--directory",
                f"--title={title}",
                f"--width={width}",
                f"--height={height}",
            ]
        )
        if result is None or result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    def ask_checklist(self, title, text, columns, rows, *, width=750, height=450):
        args = [
            "--list",
            "--checklist",
            "--separator=|",
            f"--title={title}",
            f"--width={width}",
            f"--height={height}",
            f"--text={text}",
        ]
        for column in columns:
            args.append(f"--column={column}")
        args.extend(rows)
        result = self.run_zenity(args)
        if result is None or result.returncode != 0:
            return []
        output = (result.stdout or "").strip()
        return output.split("|") if output else []

    def ask_radiolist(self, title, text, columns, rows, *, width=700, height=350):
        args = [
            "--list",
            "--radiolist",
            f"--title={title}",
            f"--width={width}",
            f"--height={height}",
            f"--text={text}",
        ]
        for column in columns:
            args.append(f"--column={column}")
        args.extend(rows)
        result = self.run_zenity(args)
        if result is None or result.returncode != 0:
            return ""
        return (result.stdout or "").strip()

    def ask_restore_picker(self, archive_paths):
        if not archive_paths:
            return ""

        rows = []
        for path in archive_paths:
            try:
                size = os.path.getsize(path)
            except OSError:
                size = 0
            rows.extend([path, self.human_size(size)])

        return self.ask_list(
            "Restore Archive",
            "Select an archive to restore:",
            ["Archive", "Size"],
            rows,
            width=900,
            height=500,
        )

    def human_size(self, size):
        units = ["B", "KB", "MB", "GB", "TB"]
        n = float(size)
        for unit in units:
            if n < 1024.0 or unit == units[-1]:
                return f"{n:.2f} {unit}"
            n /= 1024.0
        return f"{n:.2f} TB"

    def get_user_input(self):
        config = {}

        main_choice = self.ask_list(
            "ImPerial TeK Solutions Backup and Restore Like a real sysAdmin:",
            "Select Action:",
            ["Option"],
            [
                "Backup dpkg-selections and manual-packages",
                "Backup Home",
                "Root filesystem Snapshot",
                "Full Disk Image Backup",
                "Backup /etc and critical configs",
                "Custom tar.zst Backup",
                "Restore Archive",
                "Exit",
            ],
            width=700,
            height=450,
        )

        if not main_choice or main_choice == "Exit":
            config["action"] = "exit"
            return config

        if main_choice == "Backup dpkg-selections and manual-packages":
            config["action"] = "backup_packages"
            config["output_dir"] = self.ask_directory(
                "Choose destination folder for package backup"
            )
            if not config["output_dir"]:
                config["action"] = "cancelled"
                return config

        elif main_choice == "Backup Home":
            config["action"] = "backup_home"
            config["source_dir"] = self.ask_entry(
                "Home Backup",
                "Enter source directory:",
                width=600,
            ) or _real_user_home()

            config["output_dir"] = self.ask_directory(
                "Choose destination folder for home backup"
            )
            if not config["output_dir"]:
                config["action"] = "cancelled"
                return config

            config["compression_level"] = self.ask_radiolist(
                "Compression Level",
                "Select zstd compression level:",
                ["Pick", "Level"],
                [
                    "TRUE", "Fast, -3",
                    "FALSE", "Balanced, -6",
                    "FALSE", "Strong, -19",
                ],
            ) or "Balanced, -6"

            config["preserve_xattrs"] = self.ask_question(
                "Extended Attributes",
                "Preserve xattrs and ACLs?",
            )

        elif main_choice == "Root filesystem Snapshot":
            config["action"] = "snapshot_root"
            config["output_dir"] = self.ask_directory(
                "Choose base folder for root snapshots"
            )
            if not config["output_dir"]:
                config["action"] = "cancelled"
                return config

            config["exclude_paths"] = [
                "/dev/*",
                "/proc/*",
                "/sys/*",
                "/tmp/*",
                "/run/*",
                "/mnt/*",
                "/media/*",
                "/lost+found",
            ]

            extra_excludes = self.ask_entry(
                "Extra Excludes",
                "Enter any extra exclude paths separated by commas, or leave blank:",
                width=700,
            )
            if extra_excludes:
                for item in extra_excludes.split(","):
                    item = item.strip()
                    if item:
                        config["exclude_paths"].append(item)

        elif main_choice == "Full Disk Image Backup":
            config["action"] = "disk_image"

            config["device"] = self.ask_entry(
                "Disk Image Backup",
                "Enter source block device, example, /dev/nvme0n1 or /dev/sda:",
                width=650,
            )
            if not config["device"]:
                config["action"] = "cancelled"
                return config

            config["output_dir"] = self.ask_directory(
                "Choose destination folder for disk image"
            )
            if not config["output_dir"]:
                config["action"] = "cancelled"
                return config

            config["block_size"] = self.ask_radiolist(
                "Block Size",
                "Select dd block size:",
                ["Pick", "Block Size"],
                [
                    "FALSE", "4M",
                    "FALSE", "8M",
                    "TRUE", "16M",
                    "FALSE", "64M",
                ],
            ) or "16M"

        elif main_choice == "Backup /etc and critical configs":
            config["action"] = "backup_configs"

            selected_items = self.ask_checklist(
                "Select Config Items",
                "Choose which config items to back up:",
                ["Pick", "Path"],
                [
                    "TRUE", "/etc",
                    "TRUE", "/usr/local/bin",
                    "TRUE", os.path.join(_real_user_home(), ".config"),
                    "TRUE", os.path.join(_real_user_home(), ".bashrc"),
                    "TRUE", os.path.join(_real_user_home(), ".zshrc"),
                    "FALSE", "/boot/grub",
                ],
            )

            if not selected_items:
                config["action"] = "cancelled"
                return config

            config["paths"] = selected_items
            config["output_dir"] = self.ask_directory(
                "Choose destination folder for config backup"
            )
            if not config["output_dir"]:
                config["action"] = "cancelled"
                return config

        elif main_choice == "Custom tar.zst Backup":
            config["action"] = "custom_tar"

            selected_items = self.ask_checklist(
                "Custom Backup",
                "Choose files or directories to include:",
                ["Pick", "Path"],
                [
                    "TRUE", _real_user_home(),
                    "FALSE", "/etc",
                    "FALSE", "/usr/local/bin",
                    "FALSE", "/var/log",
                    "FALSE", "/opt",
                    "FALSE", "/boot",
                ],
            )

            if not selected_items:
                config["action"] = "cancelled"
                return config

            config["paths"] = selected_items
            config["output_dir"] = self.ask_directory(
                "Choose destination folder for custom archive"
            )
            if not config["output_dir"]:
                config["action"] = "cancelled"
                return config

            config["compression_level"] = self.ask_radiolist(
                "Compression Level",
                "Select zstd compression level:",
                ["Pick", "Level"],
                [
                    "TRUE", "Fast, -3",
                    "FALSE", "Balanced, -6",
                    "FALSE", "Strong, -19",
                ],
            ) or "Balanced, -6"

        elif main_choice == "Restore Archive":
            config["action"] = "restore_archive"

            config["search_dir"] = self.ask_directory(
                "Choose folder that contains your backup archives"
            )
            if not config["search_dir"]:
                config["action"] = "cancelled"
                return config

            config["restore_target"] = self.ask_entry(
                "Restore Target",
                "Enter restore target directory, example, / or /tmp/restore-test:",
                width=700,
            )
            if not config["restore_target"]:
                config["action"] = "cancelled"
                return config

        return config


class BackupManager:
    def __init__(self, ui, dry_run=False):
        self.ui = ui
        self.dry_run = dry_run
        self.timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")

    def require_root(self):
        if os.geteuid() != 0:
            self.ui.show_error("Please run this script as root.")
            sys.exit(1)

    def require_tools(self, *needed_tools):
        not_avail = ""

        for tool in needed_tools:
            if not shutil.which(tool):
                not_avail += f" {tool}"

        if not_avail:
            self.ui.show_error(
                f"ERROR: The following required tool(s) cannot be found:{not_avail}"
            )
            return False

        return True

    def ensure_dir(self, path):
        os.makedirs(path, exist_ok=True)

    def ensure_writable_dir(self, path):
        self.ensure_dir(path)
        if not os.path.isdir(path):
            self.ui.show_error(f"Destination is not a directory:\n{path}")
            return False
        if not os.access(path, os.W_OK):
            self.ui.show_error(f"Destination is not writable:\n{path}")
            return False
        return True

    def run_command(self, cmd, shell=False):
        rendered = cmd if isinstance(cmd, str) else " ".join(shlex.quote(x) for x in cmd)
        label = "[DRY-RUN] would run" if self.dry_run else "Running command"
        print(f"\n{label}:\n")
        print(rendered)
        print()
        if self.dry_run:
            return True
        if shell and isinstance(cmd, str):
            # Use bash with pipefail so failures in any pipeline stage propagate.
            result = subprocess.run(["bash", "-o", "pipefail", "-c", cmd])
        else:
            result = subprocess.run(cmd, shell=shell)
        return result.returncode == 0

    def parse_zstd_level(self, level_text):
        if "-19" in level_text:
            return "-19"
        if "-3" in level_text:
            return "-3"
        return "-6"

    def make_dated_filename(self, output_dir, prefix, extension):
        self.ensure_dir(output_dir)
        return os.path.join(output_dir, f"{prefix}-{self.timestamp}.{extension}")

    def sha256_file(self, filepath):
        if self.dry_run or not os.path.exists(filepath):
            return f"{filepath}.sha256 (skipped: dry-run or missing source)"

        sha256 = hashlib.sha256()
        with open(filepath, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha256.update(chunk)

        digest = sha256.hexdigest()
        checksum_path = f"{filepath}.sha256"

        with open(checksum_path, "w", encoding="utf-8") as f:
            f.write(f"{digest}  {os.path.basename(filepath)}\n")

        return checksum_path

    def rotate_backups(self, output_dir, prefix, extension):
        if self.dry_run:
            return [], []
        pattern = os.path.join(output_dir, f"{prefix}-*.{extension}")
        files = sorted(glob.glob(pattern), key=os.path.getmtime, reverse=True)

        keep = files[:2]
        remove = files[2:]

        for old_file in remove:
            try:
                os.remove(old_file)
            except FileNotFoundError:
                pass

            checksum_file = f"{old_file}.sha256"
            if os.path.exists(checksum_file):
                try:
                    os.remove(checksum_file)
                except FileNotFoundError:
                    pass

        return keep, remove

    def rotate_snapshot_directories(self, base_dir, prefix):
        if self.dry_run:
            return [], []
        pattern = os.path.join(base_dir, f"{prefix}-*")
        dirs = [p for p in glob.glob(pattern) if os.path.isdir(p)]
        dirs.sort(key=os.path.getmtime, reverse=True)

        keep = dirs[:2]
        remove = dirs[2:]

        for old_dir in remove:
            try:
                shutil.rmtree(old_dir)
            except FileNotFoundError:
                pass

        return keep, remove

    def build_tar_command(self, paths, zstd_level, output_file, preserve_xattrs=True):
        quoted_paths = " ".join(shlex.quote(path) for path in paths)
        tar_flags = "--numeric-owner -cpf -"

        if preserve_xattrs:
            tar_flags = "--xattrs --acls --numeric-owner -cpf -"

        return (
            f"tar {tar_flags} {quoted_paths} "
            f"| pv -ptebar "
            f"| zstd -T0 {zstd_level} "
            f"> {shlex.quote(output_file)}"
        )

    def backup_packages(self, config):
        if not self.require_tools("dpkg", "apt-mark"):
            return False

        output_dir = config["output_dir"]
        if not self.ensure_writable_dir(output_dir):
            return False

        dpkg_file = self.make_dated_filename(output_dir, "dpkg-selections", "txt")
        manual_file = self.make_dated_filename(output_dir, "manual-packages", "txt")

        ok1 = self.run_command(
            f"dpkg --get-selections > {shlex.quote(dpkg_file)}",
            shell=True,
        )
        ok2 = self.run_command(
            f"apt-mark showmanual > {shlex.quote(manual_file)}",
            shell=True,
        )

        if ok1 and ok2:
            dpkg_sha = self.sha256_file(dpkg_file)
            manual_sha = self.sha256_file(manual_file)

            self.rotate_backups(output_dir, "dpkg-selections", "txt")
            self.rotate_backups(output_dir, "manual-packages", "txt")

            self.ui.show_info(
                "Package backup complete.\n\n"
                f"Saved:\n{dpkg_file}\n{manual_file}\n\n"
                f"Checksums:\n{dpkg_sha}\n{manual_sha}"
            )
            return True

        self.ui.show_error("Package backup failed.")
        return False

    def backup_home(self, config):
        if not self.require_tools("tar", "pv", "zstd"):
            return False

        source_dir = config["source_dir"]
        output_dir = config["output_dir"]
        zstd_level = self.parse_zstd_level(config["compression_level"])
        preserve_xattrs = config.get("preserve_xattrs", True)

        if not os.path.exists(source_dir):
            self.ui.show_error(f"Source directory does not exist:\n{source_dir}")
            return False

        if not self.ensure_writable_dir(output_dir):
            return False

        output_file = self.make_dated_filename(output_dir, "home-backup", "tar.zst")
        cmd = self.build_tar_command(
            [source_dir], zstd_level, output_file, preserve_xattrs=preserve_xattrs
        )

        if self.run_command(cmd, shell=True):
            checksum_file = self.sha256_file(output_file)
            self.rotate_backups(output_dir, "home-backup", "tar.zst")
            self.ui.show_info(
                f"Home backup complete.\n\nSaved to:\n{output_file}\n\nChecksum:\n{checksum_file}"
            )
            return True

        self.ui.show_error("Home backup failed.")
        return False

    def snapshot_root(self, config):
        if not self.require_tools("rsync"):
            return False

        base_dir = config["output_dir"]
        exclude_paths = config.get("exclude_paths", [])

        if not self.ensure_writable_dir(base_dir):
            return False

        snapshot_dir = os.path.join(base_dir, f"root-snapshot-{self.timestamp}")
        self.ensure_dir(snapshot_dir)

        cmd = ["rsync", "-aAXHv", "--delete"]
        for pattern in exclude_paths:
            cmd.append(f"--exclude={pattern}")
        cmd.extend(["/", snapshot_dir])

        if self.run_command(cmd):
            marker_file = os.path.join(snapshot_dir, "SNAPSHOT_INFO.txt")
            with open(marker_file, "w", encoding="utf-8") as f:
                f.write(f"Root snapshot completed at {self.timestamp}\n")
                f.write(f"Snapshot directory: {snapshot_dir}\n")

            checksum_file = self.sha256_file(marker_file)
            self.rotate_snapshot_directories(base_dir, "root-snapshot")

            self.ui.show_info(
                f"Root snapshot complete.\n\n"
                f"Saved to:\n{snapshot_dir}\n\n"
                f"Marker:\n{marker_file}\n\n"
                f"Checksum:\n{checksum_file}"
            )
            return True

        try:
            shutil.rmtree(snapshot_dir)
        except FileNotFoundError:
            pass

        self.ui.show_error("Root snapshot failed.")
        return False

    def disk_image(self, config):
        if not self.require_tools("dd", "pv", "zstd", "blockdev"):
            return False

        device = config["device"]
        output_dir = config["output_dir"]
        block_size = config.get("block_size", "16M")

        if not os.path.exists(device):
            self.ui.show_error(f"Block device does not exist:\n{device}")
            return False

        if not self.ensure_writable_dir(output_dir):
            return False

        output_file = self.make_dated_filename(output_dir, "disk-image", "img.zst")

        size_proc = subprocess.run(
            ["blockdev", "--getsize64", device],
            capture_output=True,
            text=True,
        )
        device_size = (size_proc.stdout or "").strip()

        if device_size.isdigit():
            pv_part = f"pv -ptebar -s {device_size}"
        else:
            pv_part = "pv -ptebar"

        cmd = (
            f"dd if={shlex.quote(device)} bs={shlex.quote(block_size)} status=none "
            f"| {pv_part} "
            f"| zstd -T0 "
            f"> {shlex.quote(output_file)}"
        )

        if self.run_command(cmd, shell=True):
            checksum_file = self.sha256_file(output_file)
            self.rotate_backups(output_dir, "disk-image", "img.zst")
            self.ui.show_info(
                f"Disk image backup complete.\n\nSaved to:\n{output_file}\n\nChecksum:\n{checksum_file}"
            )
            return True

        self.ui.show_error("Disk image backup failed.")
        return False

    def backup_configs(self, config):
        if not self.require_tools("tar", "pv", "zstd"):
            return False

        paths = [path for path in config["paths"] if os.path.exists(path)]
        output_dir = config["output_dir"]

        if not paths:
            self.ui.show_error("No valid config paths selected.")
            return False

        if not self.ensure_writable_dir(output_dir):
            return False

        output_file = self.make_dated_filename(output_dir, "config-backup", "tar.zst")
        cmd = self.build_tar_command(paths, "-6", output_file, preserve_xattrs=True)

        if self.run_command(cmd, shell=True):
            checksum_file = self.sha256_file(output_file)
            self.rotate_backups(output_dir, "config-backup", "tar.zst")
            self.ui.show_info(
                f"Config backup complete.\n\nSaved to:\n{output_file}\n\nChecksum:\n{checksum_file}"
            )
            return True

        self.ui.show_error("Config backup failed.")
        return False

    def custom_tar(self, config):
        if not self.require_tools("tar", "pv", "zstd"):
            return False

        paths = [path for path in config["paths"] if os.path.exists(path)]
        output_dir = config["output_dir"]
        zstd_level = self.parse_zstd_level(config["compression_level"])

        if not paths:
            self.ui.show_error("No valid paths selected.")
            return False

        if not self.ensure_writable_dir(output_dir):
            return False

        output_file = self.make_dated_filename(output_dir, "custom-backup", "tar.zst")
        cmd = self.build_tar_command(paths, zstd_level, output_file, preserve_xattrs=True)

        if self.run_command(cmd, shell=True):
            checksum_file = self.sha256_file(output_file)
            self.rotate_backups(output_dir, "custom-backup", "tar.zst")
            self.ui.show_info(
                f"Custom archive complete.\n\nSaved to:\n{output_file}\n\nChecksum:\n{checksum_file}"
            )
            return True

        self.ui.show_error("Custom archive failed.")
        return False

    def find_restore_archives(self, search_dir):
        pattern = os.path.join(search_dir, "*.tar.zst")
        results = glob.glob(pattern)
        results.sort(key=os.path.getmtime, reverse=True)
        return results

    def verify_checksum_if_present(self, archive_file):
        checksum_file = f"{archive_file}.sha256"

        if not os.path.exists(checksum_file):
            return True, "No checksum file found, continuing without verification."

        expected = ""
        with open(checksum_file, "r", encoding="utf-8") as f:
            first_line = f.readline().strip()
            if first_line:
                expected = first_line.split()[0]

        if not expected:
            return False, "Checksum file exists but could not be parsed."

        sha256 = hashlib.sha256()
        with open(archive_file, "rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha256.update(chunk)
        actual = sha256.hexdigest()

        if actual == expected:
            return True, "Checksum verified successfully."

        return False, "Checksum mismatch. Archive may be corrupt."

    def restore_archive(self, config):
        if not self.require_tools("tar", "zstd"):
            return False

        search_dir = config["search_dir"]
        restore_target = config["restore_target"]

        if not os.path.isdir(search_dir):
            self.ui.show_error(f"Search directory does not exist:\n{search_dir}")
            return False

        self.ensure_dir(restore_target)
        if not os.path.isdir(restore_target):
            self.ui.show_error(f"Restore target is not a directory:\n{restore_target}")
            return False
        if not os.access(restore_target, os.W_OK):
            self.ui.show_error(f"Restore target is not writable:\n{restore_target}")
            return False

        archives = self.find_restore_archives(search_dir)
        archive_file = self.ui.ask_restore_picker(archives)

        if not archive_file:
            self.ui.show_info("Restore cancelled.")
            return False

        ok, message = self.verify_checksum_if_present(archive_file)
        if not ok:
            self.ui.show_error(message)
            return False

        cmd = (
            f"tar -I zstd -xpf {shlex.quote(archive_file)} "
            f"-C {shlex.quote(restore_target)}"
        )

        if self.run_command(cmd, shell=True):
            self.ui.show_info(
                f"Archive restored successfully.\n\nTarget:\n{restore_target}\n\n{message}"
            )
            return True

        self.ui.show_error("Archive restore failed.")
        return False

    def execute(self, config):
        action = config.get("action", "")

        if action == "exit":
            print("User exited.")
            return

        if action == "cancelled":
            self.ui.show_info("Action cancelled.")
            return

        if action == "backup_packages":
            self.backup_packages(config)
        elif action == "backup_home":
            self.backup_home(config)
        elif action == "snapshot_root":
            self.snapshot_root(config)
        elif action == "disk_image":
            self.disk_image(config)
        elif action == "backup_configs":
            self.backup_configs(config)
        elif action == "custom_tar":
            self.custom_tar(config)
        elif action == "restore_archive":
            self.restore_archive(config)
        else:
            self.ui.show_error(f"Unknown action: {action}")


def main():
    import argparse

    parser = argparse.ArgumentParser(
        prog="IT_Backupmanager",
        description="Interactive backup and restore tool (zenity-driven).",
        add_help=True,
    )
    parser.add_argument(
        "--dry-run",
        "-n",
        action="store_true",
        help="Show the commands that would run without executing them.",
    )
    args, _unknown = parser.parse_known_args()

    ui = BackupUI()
    if args.dry_run:
        print("=" * 60)
        print("DRY-RUN MODE: no files will be written, no commands executed.")
        print("=" * 60)
        ui.show_info(
            "DRY-RUN MODE\n\nNo files will be written and no commands will be executed.\n"
            "The terminal will show the commands that would run."
        )

    manager = BackupManager(ui, dry_run=args.dry_run)
    if not args.dry_run:
        manager.require_root()

    config = ui.get_user_input()
    manager.execute(config)


if __name__ == "__main__":
    main()

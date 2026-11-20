#!/usr/bin/env python3
"""tidydl - sort a messy Downloads folder into tidy subfolders.

Safe by default: it only shows what it would do. Add --apply to move files,
--watch to keep sorting new downloads, --install to start automatically at
login, and --undo to put things back. No dependencies, Python 3.8+.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

__version__ = "1.1.0"

TASK_NAME = "tidydl"
LOG_NAME = ".tidydl-log.json"      # undo log
WATCH_LOG = ".tidydl.log"          # activity log used by --watch
MAX_UNDO_ENTRIES = 500
SKIP_SUFFIXES = {".crdownload", ".part", ".partial", ".tmp", ".download", ".opdownload"}

CATEGORIES = {
    "Images": {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp", ".svg", ".heic", ".tiff", ".ico"},
    "Documents": {".pdf", ".doc", ".docx", ".odt", ".txt", ".rtf", ".md", ".epub", ".ppt", ".pptx", ".odp"},
    "Spreadsheets": {".xls", ".xlsx", ".csv", ".ods", ".tsv"},
    "Videos": {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".flv"},
    "Audio": {".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac"},
    "Archives": {".zip", ".rar", ".7z", ".tar", ".gz", ".bz2", ".xz", ".tgz"},
    "Installers": {".exe", ".msi", ".dmg", ".pkg", ".deb", ".rpm", ".appimage", ".apk", ".iso"},
    "Code": {".py", ".js", ".ts", ".html", ".css", ".json", ".xml", ".yml", ".yaml", ".sh", ".ps1", ".bat", ".sql"},
}
OTHER = "Other"


def category_for(path):
    """Return the folder name a file belongs in, or None if it should be skipped."""
    suffix = path.suffix.lower()
    if path.name.startswith(".") or suffix in SKIP_SUFFIXES:
        return None
    for category, exts in CATEGORIES.items():
        if suffix in exts:
            return category
    return OTHER


def unique_target(target):
    """If target exists, return 'name (1).ext', 'name (2).ext', ... instead."""
    if not target.exists():
        return target
    n = 1
    while True:
        candidate = target.with_name(f"{target.stem} ({n}){target.suffix}")
        if not candidate.exists():
            return candidate
        n += 1


def plan_moves(folder, older_than_days=0, min_age_seconds=0, now=None):
    """Return a list of (source, destination) for every file that should move.

    older_than_days: only files not modified in that many days.
    min_age_seconds: skip files modified more recently than this (still being written).
    """
    now = time.time() if now is None else now
    day_cutoff = now - older_than_days * 86400
    moves = []
    for item in sorted(folder.iterdir()):
        if not item.is_file():
            continue
        category = category_for(item)
        if category is None:
            continue
        mtime = item.stat().st_mtime
        if older_than_days and mtime > day_cutoff:
            continue
        if now - mtime < min_age_seconds:
            continue
        moves.append((item, unique_target(folder / category / item.name)))
    return moves


def _write_undo_log(folder, new_entries, append):
    log = folder / LOG_NAME
    entries = []
    if append and log.exists():
        try:
            entries = json.loads(log.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            entries = []
    entries = (entries + new_entries)[-MAX_UNDO_ENTRIES:]
    log.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def apply_moves(folder, moves, append=False, on_error=None):
    """Move files. Files that cannot be moved (e.g. still locked) are skipped."""
    done = []
    for src, dst in moves:
        try:
            dst.parent.mkdir(exist_ok=True)
            dst = unique_target(dst)
            shutil.move(str(src), str(dst))
        except OSError as exc:
            if on_error:
                on_error(f"skipped {src.name}: {exc}")
            continue
        done.append({"from": str(src), "to": str(dst)})
    if done:
        _write_undo_log(folder, done, append)
    return done


def undo(folder):
    log = folder / LOG_NAME
    if not log.exists():
        print("Nothing to undo (no log found).")
        return 0
    entries = json.loads(log.read_text(encoding="utf-8"))
    restored = 0
    for e in reversed(entries):
        src, dst = Path(e["to"]), Path(e["from"])
        if src.exists():
            shutil.move(str(src), str(unique_target(dst)))
            restored += 1
    log.unlink()
    for sub in list(CATEGORIES) + [OTHER]:
        d = folder / sub
        if d.is_dir() and not any(d.iterdir()):
            d.rmdir()
    print(f"Restored {restored} file(s).")
    return 0


# ------------------------------------------------------------------- watch

def watch_once(folder, settle=10, log=None):
    """One sorting pass for watch mode. Returns the list of moved files."""
    moves = plan_moves(folder, min_age_seconds=settle)
    done = apply_moves(folder, moves, append=True, on_error=log)
    if log:
        for d in done:
            log(f"moved {Path(d['from']).name} -> {Path(d['to']).parent.name}/")
    return done


def watch(folder, interval=5, settle=10):
    logfile = folder / WATCH_LOG

    def log(msg):
        try:
            with open(logfile, "a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')}  {msg}\n")
            if logfile.stat().st_size > 1_000_000:   # keep the log small
                lines = logfile.read_text(encoding="utf-8").splitlines()[-500:]
                logfile.write_text("\n".join(lines) + "\n", encoding="utf-8")
        except OSError:
            pass

    log(f"watching {folder} every {interval}s")
    while True:
        try:
            watch_once(folder, settle, log)
        except Exception as exc:      # never let the background job die
            log(f"error: {exc}")
        time.sleep(interval)


# ----------------------------------------------------------------- autostart

def pythonw_path():
    exe = Path(sys.executable)
    candidate = exe.with_name("pythonw.exe")
    return candidate if candidate.exists() else exe


def build_schtasks_create(folder, script=None, python=None):
    """Arguments for schtasks that start tidydl --watch at every login."""
    script = Path(script or __file__).resolve()
    python = python or pythonw_path()
    command = f'"{python}" "{script}" "{folder}" --watch'
    return ["schtasks", "/create", "/tn", TASK_NAME, "/tr", command,
            "/sc", "onlogon", "/rl", "limited", "/f"]


def build_systemd_unit(folder, script=None, python=None):
    script = Path(script or __file__).resolve()
    python = python or sys.executable
    return (
        "[Unit]\nDescription=tidydl - sort the Downloads folder\n\n"
        "[Service]\n"
        f'ExecStart="{python}" "{script}" "{folder}" --watch\n'
        "Restart=on-failure\n\n"
        "[Install]\nWantedBy=default.target\n"
    )


def install(folder):
    if os.name == "nt":
        subprocess.run(build_schtasks_create(folder), check=True)
        subprocess.run(["schtasks", "/run", "/tn", TASK_NAME], check=False)
        print(f"Installed. tidydl now starts at login and watches {folder}.")
        print("It is running already. Check with: schtasks /query /tn tidydl")
    else:
        unit_dir = Path.home() / ".config" / "systemd" / "user"
        unit_dir.mkdir(parents=True, exist_ok=True)
        (unit_dir / "tidydl.service").write_text(build_systemd_unit(folder))
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now", "tidydl.service"], check=True)
        print(f"Installed. tidydl now starts at login and watches {folder}.")
    return 0


def uninstall():
    if os.name == "nt":
        subprocess.run(["schtasks", "/end", "/tn", TASK_NAME], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        subprocess.run(["schtasks", "/delete", "/tn", TASK_NAME, "/f"], check=False)
    else:
        subprocess.run(["systemctl", "--user", "disable", "--now", "tidydl.service"], check=False)
        (Path.home() / ".config" / "systemd" / "user" / "tidydl.service").unlink(missing_ok=True)
    print("Autostart removed.")
    return 0


# ---------------------------------------------------------------------- cli

def main(argv=None):
    # pythonw has no console; make print() harmless there.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    p = argparse.ArgumentParser(prog="tidydl", description=__doc__.splitlines()[0])
    p.add_argument("folder", nargs="?", default=str(Path.home() / "Downloads"),
                   help="folder to tidy (default: ~/Downloads)")
    p.add_argument("--apply", action="store_true", help="actually move the files")
    p.add_argument("--undo", action="store_true", help="undo the moves recorded in the log")
    p.add_argument("--older-than", type=int, default=0, metavar="DAYS",
                   help="only move files not modified in the last DAYS days")
    p.add_argument("--watch", action="store_true",
                   help="keep running and sort new files as they appear")
    p.add_argument("--interval", type=int, default=5, metavar="SEC",
                   help="--watch: how often to check (default 5)")
    p.add_argument("--settle", type=int, default=10, metavar="SEC",
                   help="--watch: wait until a file has not changed for SEC seconds (default 10)")
    p.add_argument("--install", action="store_true",
                   help="start 'tidydl --watch' automatically at login")
    p.add_argument("--uninstall", action="store_true", help="remove the autostart")
    p.add_argument("--version", action="version", version=f"tidydl {__version__}")
    args = p.parse_args(argv)

    if args.uninstall:
        return uninstall()

    folder = Path(args.folder).expanduser().resolve()
    if not folder.is_dir():
        print(f"Not a folder: {folder}", file=sys.stderr)
        return 2

    if args.install:
        return install(folder)
    if args.undo:
        return undo(folder)
    if args.watch:
        watch(folder, args.interval, args.settle)
        return 0

    moves = plan_moves(folder, args.older_than)
    if not moves:
        print("Nothing to tidy.")
        return 0

    for src, dst in moves:
        print(f"{src.name}  ->  {dst.parent.name}/{dst.name}")
    print(f"\n{len(moves)} file(s).", end=" ")

    if args.apply:
        apply_moves(folder, moves, on_error=lambda m: print(m, file=sys.stderr))
        print("Moved. Run with --undo to put them back.")
    else:
        print("Preview only. Add --apply to move them.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

"""Backup / reset / restore / server-management operations shared by the
Tkinter GUI launcher (launcher.py) and the batch-file fallback
(scripts/toolbox_cli.py, QA Toolbox Launcher.bat) — kept in one place so the
two entry points can't drift out of sync on how data is handled.
"""
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import zipfile
from datetime import datetime

HOST = "127.0.0.1"
PORT = 8000
NO_WINDOW = subprocess.CREATE_NO_WINDOW

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    # This file lives at <repo root>/app/toolbox_ops.py.
    BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VENV_DIR = os.path.join(BASE_DIR, ".venv")
VENV_PYTHON = os.path.join(VENV_DIR, "Scripts", "python.exe")
REQUIREMENTS = os.path.join(BASE_DIR, "requirements.txt")
DB_PATH = os.path.join(BASE_DIR, "qa_toolbox.db")
UPLOADS_DIR = os.path.join(BASE_DIR, "app", "uploads")
BACKUPS_DIR = os.path.join(BASE_DIR, "backups")


def find_system_python():
    """Locate a real Python interpreter on PATH (not this exe itself)."""
    for candidate in (["py", "-3"], ["python"], ["python3"]):
        if shutil.which(candidate[0]):
            return candidate
    return None


def get_python():
    """Interpreter to run uvicorn with: prefer the project venv."""
    if os.path.exists(VENV_PYTHON):
        return VENV_PYTHON
    if not getattr(sys, "frozen", False):
        return sys.executable
    return None


def _find_stray_server_pids():
    """PIDs of any python process serving this app's uvicorn — including
    ones not tracked by whichever entry point called this (e.g. a
    terminal-started dev server, or a server started by the other entry
    point). Needed so Reset/Import don't fail with qa_toolbox.db locked."""
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-CimInstance Win32_Process -Filter \"Name='python.exe' OR Name='pythonw.exe'\" "
                "| Where-Object { $_.CommandLine -like '*app.main:app*' } "
                "| Select-Object -ExpandProperty ProcessId",
            ],
            capture_output=True, text=True, creationflags=NO_WINDOW, timeout=10,
        )
        return [int(pid) for pid in result.stdout.split() if pid.strip().isdigit()]
    except Exception:
        return []


def kill_stray_servers():
    for pid in _find_stray_server_pids():
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            creationflags=NO_WINDOW, capture_output=True,
        )


def _retry(action, attempts=10, delay=0.3):
    """Run `action`, retrying on OSError (e.g. WinError 32 - file still in
    use for a moment after the process holding it was just killed)."""
    last_err = None
    for _ in range(attempts):
        try:
            return action()
        except OSError as e:
            last_err = e
            time.sleep(delay)
    raise last_err


def _clear_uploads():
    """Empty screenshots/exports in place, keeping each folder's .gitkeep."""
    for sub in ("screenshots", "exports"):
        d = os.path.join(UPLOADS_DIR, sub)
        if not os.path.isdir(d):
            continue
        for entry_name in os.listdir(d):
            if entry_name == ".gitkeep":
                continue
            full = os.path.join(d, entry_name)
            if os.path.isdir(full):
                shutil.rmtree(full)
            else:
                os.remove(full)


def backup() -> str:
    """Zip qa_toolbox.db + app/uploads into backups/. Returns the zip path."""
    os.makedirs(BACKUPS_DIR, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    dest = os.path.join(BACKUPS_DIR, f"qa_toolbox_backup_{ts}.zip")
    tmp_db = os.path.join(BACKUPS_DIR, f"_tmp_{ts}.db")
    try:
        if os.path.exists(DB_PATH):
            src = sqlite3.connect(DB_PATH)
            dst = sqlite3.connect(tmp_db)
            with dst:
                src.backup(dst)
            src.close()
            dst.close()
        with zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as zf:
            if os.path.exists(tmp_db):
                zf.write(tmp_db, arcname="qa_toolbox.db")
            if os.path.isdir(UPLOADS_DIR):
                for root_dir, _, files in os.walk(UPLOADS_DIR):
                    for f in files:
                        full = os.path.join(root_dir, f)
                        arc = os.path.join("uploads", os.path.relpath(full, UPLOADS_DIR))
                        zf.write(full, arcname=arc)
    finally:
        if os.path.exists(tmp_db):
            os.remove(tmp_db)
    return dest


def reset():
    """Delete the database and clear uploads. Stops any running server first."""
    kill_stray_servers()
    if os.path.exists(DB_PATH):
        _retry(lambda: os.remove(DB_PATH))
    _clear_uploads()


def restore(path: str):
    """Replace the database and uploads with the contents of a backup zip."""
    kill_stray_servers()
    with zipfile.ZipFile(path) as zf:
        names = zf.namelist()
        if "qa_toolbox.db" not in names:
            raise ValueError("Not a QA Toolbox backup (missing qa_toolbox.db).")
        _clear_uploads()
        if os.path.exists(DB_PATH):
            _retry(lambda: os.remove(DB_PATH))
        with zf.open("qa_toolbox.db") as src, open(DB_PATH, "wb") as dst:
            shutil.copyfileobj(src, dst)
        for name in names:
            if not name.startswith("uploads/") or name.endswith("/"):
                continue
            dest = os.path.join(BASE_DIR, "app", *name.split("/"))
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with zf.open(name) as src, open(dest, "wb") as dst:
                shutil.copyfileobj(src, dst)

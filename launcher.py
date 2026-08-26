"""Simple GUI to start/stop the QA Toolbox web service (no console window)."""
import os
import shutil
import sqlite3
import subprocess
import sys
import threading
import webbrowser
import zipfile
from datetime import datetime
import tkinter as tk
from tkinter import ttk, messagebox
import urllib.request

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"
NO_WINDOW = subprocess.CREATE_NO_WINDOW

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

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


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.proc = None
        self.setup_running = False

        root.title("QA Toolbox Launcher")
        root.geometry("320x340")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)

        self.status_var = tk.StringVar(value="Stopped")
        ttk.Label(root, text="QA Toolbox web service", font=("Segoe UI", 11, "bold")).pack(pady=(16, 4))

        self.status_label = ttk.Label(root, textvariable=self.status_var, foreground="red")
        self.status_label.pack(pady=(0, 12))

        btn_frame = ttk.Frame(root)
        btn_frame.pack()
        self.start_btn = ttk.Button(btn_frame, text="Start", width=12, command=self.start)
        self.start_btn.grid(row=0, column=0, padx=6)
        self.stop_btn = ttk.Button(btn_frame, text="Stop", width=12, command=self.stop, state="disabled")
        self.stop_btn.grid(row=0, column=1, padx=6)

        self.open_btn = ttk.Button(root, text="Open in browser", command=self.open_browser, state="disabled")
        self.open_btn.pack(pady=(12, 0))

        ttk.Separator(root, orient="horizontal").pack(fill="x", pady=16, padx=20)

        self.setup_btn = ttk.Button(root, text="Setup / Install Dependencies", command=self.setup)
        self.setup_btn.pack(pady=(0, 8))

        self.backup_btn = ttk.Button(root, text="Backup Data (db + images)", command=self.backup)
        self.backup_btn.pack(pady=(0, 8))

        self.reset_btn = ttk.Button(root, text="Reset / Clear All Data", command=self.reset_data)
        self.reset_btn.pack()

    # -- service control -------------------------------------------------

    def start(self):
        if self.proc is not None:
            return
        python = get_python()
        if python is None:
            messagebox.showwarning(
                "Setup required",
                "No environment found yet. Click 'Setup / Install Dependencies' first.",
            )
            return
        self.proc = subprocess.Popen(
            [python, "-m", "uvicorn", "app.main:app", "--host", HOST, "--port", str(PORT)],
            cwd=BASE_DIR,
            creationflags=NO_WINDOW,
        )
        self.start_btn.config(state="disabled")
        self.stop_btn.config(state="normal")
        self.open_btn.config(state="normal")
        self.status_var.set("Starting...")
        self.status_label.config(foreground="orange")
        self.root.after(300, self.poll_ready)

    def poll_ready(self, attempts=0):
        if self.proc is None:
            return
        if self.proc.poll() is not None:
            self.status_var.set("Failed to start")
            self.status_label.config(foreground="red")
            self.proc = None
            self.start_btn.config(state="normal")
            self.stop_btn.config(state="disabled")
            self.open_btn.config(state="disabled")
            return
        try:
            urllib.request.urlopen(URL, timeout=0.5)
            self.status_var.set(f"Running on {URL}")
            self.status_label.config(foreground="green")
            return
        except Exception:
            pass
        if attempts > 40:
            self.status_var.set("Still starting...")
            return
        self.root.after(300, lambda: self.poll_ready(attempts + 1))

    def stop(self):
        if self.proc is None:
            return
        subprocess.run(
            ["taskkill", "/PID", str(self.proc.pid), "/T", "/F"],
            creationflags=NO_WINDOW,
            capture_output=True,
        )
        self.proc = None
        self.status_var.set("Stopped")
        self.status_label.config(foreground="red")
        self.start_btn.config(state="normal")
        self.stop_btn.config(state="disabled")
        self.open_btn.config(state="disabled")

    def open_browser(self):
        webbrowser.open(URL)

    # -- setup / install ---------------------------------------------------

    def setup(self):
        if self.setup_running:
            return
        base_python = find_system_python()
        if base_python is None:
            messagebox.showerror(
                "Setup",
                "No Python interpreter found on this machine (PATH). "
                "Install Python 3 first, then click Setup again.",
            )
            return
        self.setup_running = True
        self.setup_btn.config(state="disabled")
        self.status_var.set("Installing dependencies...")
        self.status_label.config(foreground="orange")
        threading.Thread(target=self._run_setup, args=(base_python,), daemon=True).start()

    def _run_setup(self, base_python):
        try:
            if not os.path.exists(VENV_PYTHON):
                r = subprocess.run(
                    base_python + ["-m", "venv", VENV_DIR],
                    cwd=BASE_DIR, creationflags=NO_WINDOW, capture_output=True, text=True,
                )
                if r.returncode != 0:
                    raise RuntimeError(r.stderr or "venv creation failed")
            r = subprocess.run(
                [VENV_PYTHON, "-m", "pip", "install", "--upgrade", "pip"],
                cwd=BASE_DIR, creationflags=NO_WINDOW, capture_output=True, text=True,
            )
            r = subprocess.run(
                [VENV_PYTHON, "-m", "pip", "install", "-r", REQUIREMENTS],
                cwd=BASE_DIR, creationflags=NO_WINDOW, capture_output=True, text=True,
            )
            if r.returncode != 0:
                raise RuntimeError(r.stderr or "pip install failed")
            self.root.after(0, self._setup_done, True, "")
        except Exception as e:
            self.root.after(0, self._setup_done, False, str(e))

    def _setup_done(self, ok, err):
        self.setup_running = False
        self.setup_btn.config(state="normal")
        if ok:
            self.status_var.set("Setup complete")
            self.status_label.config(foreground="green")
            messagebox.showinfo("Setup", "Dependencies installed. You can Start the service now.")
        else:
            self.status_var.set("Setup failed")
            self.status_label.config(foreground="red")
            messagebox.showerror("Setup failed", err[-1500:])

    # -- backup ---------------------------------------------------------

    def backup(self):
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
        except Exception as e:
            messagebox.showerror("Backup failed", str(e))
            return
        finally:
            if os.path.exists(tmp_db):
                os.remove(tmp_db)
        messagebox.showinfo("Backup complete", f"Saved to:\n{dest}")
        try:
            os.startfile(BACKUPS_DIR)
        except Exception:
            pass

    # -- reset ------------------------------------------------------------

    def reset_data(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Confirm Reset")
        dialog.resizable(False, False)
        dialog.transient(self.root)
        dialog.grab_set()

        ttk.Label(
            dialog,
            text="This permanently deletes the database and all\nscreenshots/exports. This cannot be undone.",
            foreground="red",
            justify="center",
        ).pack(padx=24, pady=(16, 8))
        ttk.Label(dialog, text='Type DELETE ALL to confirm:').pack(pady=(0, 4))

        entry_var = tk.StringVar()
        entry = ttk.Entry(dialog, textvariable=entry_var, width=20, justify="center")
        entry.pack(pady=(0, 12))
        entry.focus_set()

        btn_frame = ttk.Frame(dialog)
        btn_frame.pack(pady=(0, 16))
        confirm_btn = ttk.Button(
            btn_frame, text="Delete Everything", state="disabled",
            command=lambda: self._do_reset(dialog),
        )
        confirm_btn.grid(row=0, column=0, padx=6)
        ttk.Button(btn_frame, text="Cancel", command=dialog.destroy).grid(row=0, column=1, padx=6)

        def on_change(*_):
            confirm_btn.config(state="normal" if entry_var.get() == "DELETE ALL" else "disabled")

        entry_var.trace_add("write", on_change)
        entry.bind("<Return>", lambda e: confirm_btn.invoke() if str(confirm_btn["state"]) == "normal" else None)

    def _do_reset(self, dialog):
        dialog.destroy()
        was_running = self.proc is not None
        if was_running:
            self.stop()
        try:
            if os.path.exists(DB_PATH):
                os.remove(DB_PATH)
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
        except Exception as e:
            messagebox.showerror("Reset failed", str(e))
            return
        messagebox.showinfo("Reset complete", "All data cleared. Database and uploads are empty.")
        if was_running:
            self.start()

    def on_close(self):
        self.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()

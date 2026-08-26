"""Simple GUI to start/stop the QA Toolbox web service (no console window)."""
import os
import subprocess
import sys
import time
import urllib.request
import webbrowser
import tkinter as tk
from tkinter import ttk

HOST = "127.0.0.1"
PORT = 8000
URL = f"http://{HOST}:{PORT}"

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))

PYTHON = sys.executable


class LauncherApp:
    def __init__(self, root):
        self.root = root
        self.proc = None

        root.title("QA Toolbox Launcher")
        root.geometry("320x160")
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
        self.open_btn.pack(pady=(16, 0))

    def start(self):
        if self.proc is not None:
            return
        self.proc = subprocess.Popen(
            [PYTHON, "-m", "uvicorn", "app.main:app", "--host", HOST, "--port", str(PORT)],
            cwd=BASE_DIR,
            creationflags=subprocess.CREATE_NO_WINDOW,
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
            creationflags=subprocess.CREATE_NO_WINDOW,
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

    def on_close(self):
        self.stop()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    LauncherApp(root)
    root.mainloop()

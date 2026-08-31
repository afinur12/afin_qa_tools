"""Command-line entry point for the QA Toolbox data operations
(backup/reset/restore). Used by QA Toolbox Launcher.bat as a fallback for
the packaged GUI exe when it's unavailable (e.g. quarantined by endpoint
security software) — see app/toolbox_ops.py for the actual logic, shared
with the GUI launcher.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from app import toolbox_ops as ops


def main():
    if len(sys.argv) < 2:
        print("Usage: toolbox_cli.py <backup|reset|restore|stop-server> [args]")
        sys.exit(1)

    command = sys.argv[1]

    if command == "backup":
        dest = ops.backup()
        print(f"Backup saved to: {dest}")

    elif command == "reset":
        if "--yes" not in sys.argv:
            print("Refusing to reset without --yes (the .bat menu asks for confirmation before passing it).")
            sys.exit(1)
        ops.reset()
        print("Reset complete. Database and uploads are empty.")

    elif command == "restore":
        if len(sys.argv) < 3:
            print("Usage: toolbox_cli.py restore <path-to-backup.zip>")
            sys.exit(1)
        ops.restore(sys.argv[2])
        print("Backup restored.")

    elif command == "stop-server":
        ops.kill_stray_servers()
        print("Stopped any running QA Toolbox server.")

    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

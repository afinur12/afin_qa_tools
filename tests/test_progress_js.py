"""progress.js pure helpers, executed under Node (skipped without node)."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

PROGRESS = Path(__file__).resolve().parent.parent / "app" / "static" / "js" / "progress.js"
NODE = shutil.which("node")
pytestmark = pytest.mark.skipif(NODE is None, reason="node is not on PATH")


def call(fn, *args):
    script = (
        f"const P = require({json.dumps(str(PROGRESS))});"
        f"process.stdout.write(JSON.stringify(P.{fn}(...{json.dumps(list(args))})));"
    )
    result = subprocess.run([NODE, "-e", script], capture_output=True, text=True, encoding="utf-8", check=True)
    return json.loads(result.stdout)


def test_format_bytes_reads_like_a_file_size():
    assert call("formatBytes", 512) == "512 B"
    assert call("formatBytes", 2048) == "2 KB"
    assert call("formatBytes", 3.4 * 1048576) == "3.4 MB"


def test_clock_shows_elapsed_minutes_and_seconds():
    assert call("clock", 0) == "0:00"
    assert call("clock", 7.9) == "0:07"
    assert call("clock", 125) == "2:05"


def test_filename_comes_from_the_download_header():
    header = "attachment; filename=\"BM-16275 - docx.zip\"; filename*=UTF-8''BM-16275%20-%20docx.zip"
    assert call("filenameFromDisposition", header) == "BM-16275 - docx.zip"
    # the UTF-8 name wins over the ASCII fallback
    assert call("filenameFromDisposition", "attachment; filename=\"Kaf.json\"; filename*=UTF-8''Kaf%C3%A9.json") == "Kafé.json"
    assert call("filenameFromDisposition", 'attachment; filename="settings.json"') == "settings.json"
    assert call("filenameFromDisposition", None, "export.zip") == "export.zip"


def test_percent_is_whole_and_capped_or_unknown():
    assert call("percent", 1, 3) == 33
    assert call("percent", 5, 4) == 100
    assert call("percent", 10, 0) is None

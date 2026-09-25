import io
import re
import struct
import zlib

import pytest

from app import image_compress
from tests.test_screenshots import _create_testcase

pytest.importorskip("oxipng")


def _bloated_png(w=200, h=200):
    """A valid PNG stored with zlib level 0 — like a browser's lightly
    compressed screenshot, only more so, so there's plenty to win."""
    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    rows = b"".join(b"\x00" + b"".join(bytes(((x // 20) * 20, 120, 200)) for x in range(w)) for _ in range(h))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(rows, 0))
        + chunk(b"IEND", b"")
    )


def test_compress_png_shrinks_file_without_changing_pixels(tmp_path):
    Image = pytest.importorskip("PIL.Image")
    path = tmp_path / "shot.png"
    original = _bloated_png()
    path.write_bytes(original)

    saved = image_compress.compress_png(path)

    compressed = path.read_bytes()
    assert saved == len(original) - len(compressed) > 0
    before = Image.open(io.BytesIO(original)).convert("RGBA")
    after = Image.open(io.BytesIO(compressed)).convert("RGBA")
    assert before.size == after.size
    assert before.tobytes() == after.tobytes()


def test_compress_png_leaves_non_png_and_missing_files_alone(tmp_path):
    jpg = tmp_path / "shot.jpg"
    jpg.write_bytes(b"not really a jpeg")
    assert image_compress.compress_png(jpg) == 0
    assert jpg.read_bytes() == b"not really a jpeg"
    assert image_compress.compress_png(tmp_path / "gone.png") == 0


def test_uploaded_screenshot_is_queued_for_compression(client, monkeypatch):
    queued = []
    monkeypatch.setattr("app.routers.screenshots.compress_in_background", queued.append)
    testcase_id = _create_testcase(client, "CMP-1")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "s", "expected_result": "e", "actual_result": "a"})
    step_id = re.search(r"/steps/(\d+)/edit", client.get(f"/testcases/{testcase_id}/execute").text).group(1)

    client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/screenshot",
        files={"file": ("paste.png", _bloated_png(), "image/png")},
        follow_redirects=False,
    )

    assert len(queued) == 1 and str(queued[0]).endswith(".png")
    queued[0].unlink(missing_ok=True)  # uploads is the real shared dir

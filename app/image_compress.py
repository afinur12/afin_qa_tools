"""Lossless PNG compression for stored screenshots.

Browser-made PNGs (a pasted screenshot, the API client's html2canvas
export) are written with fast, light compression. oxipng re-encodes them
far more tightly without touching a single pixel — typically ~45% smaller
on this app's screenshots. That keeps app/uploads small and makes every
download that bundles them (the "download all images" zips, the docx
exports) proportionally smaller too.

It's slow on very large images (tens of seconds for a 6000x20000 export),
so uploads hand files to a single background worker instead of waiting:
the upload responds immediately and the file is swapped for its
compressed copy a moment later. Run `python -m app.image_compress` once
to compress screenshots that were stored before this existed.
"""

import logging
import os
import sys
from concurrent.futures import Future, ThreadPoolExecutor
from pathlib import Path

try:
    import oxipng
except ImportError:  # compression is an optimization, never a requirement
    oxipng = None

logger = logging.getLogger(__name__)

# oxipng's slowest-but-smallest preset that's still practical: level 2 took
# the biggest stored export from 9.7MB to 5.3MB; levels 0/1 only reach ~6.3MB.
OXIPNG_LEVEL = 2

# One worker: oxipng already uses several cores per image, and a burst of
# pasted screenshots shouldn't compete for CPU with the app itself.
_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="png-compress")


def compress_png(path: str | Path) -> int:
    """Losslessly recompress a PNG in place; returns the bytes saved.

    Anything that isn't a PNG, or that oxipng can't make smaller, is left
    untouched. Never raises — a failed compression just keeps the original.
    """
    path = Path(path)
    if oxipng is None or path.suffix.lower() != ".png":
        return 0
    try:
        raw = path.read_bytes()
        optimized = oxipng.optimize_from_memory(raw, level=OXIPNG_LEVEL)
        if len(optimized) >= len(raw):
            return 0
        # The screenshot may have been deleted while this ran — don't
        # resurrect it.
        if not path.exists():
            return 0
        tmp_path = path.with_name(path.name + ".tmp")
        tmp_path.write_bytes(optimized)
        os.replace(tmp_path, path)  # atomic: a concurrent download sees old or new, never half
        return len(raw) - len(optimized)
    except Exception:
        logger.exception("PNG compression failed for %s", path)
        return 0


def compress_in_background(path: str | Path) -> Future:
    """Queue compress_png for `path` on the background worker."""
    return _executor.submit(compress_png, path)


def compress_existing(root: str | Path = "app/uploads/screenshots") -> None:
    """One-time pass over every stored PNG under `root`, printing progress."""
    files = sorted(Path(root).rglob("*.png"))
    total_saved = 0
    for index, file in enumerate(files, 1):
        before = file.stat().st_size
        saved = compress_png(file)
        total_saved += saved
        if saved:
            print(f"[{index}/{len(files)}] {file}: {before / 1e6:.2f}MB -> {(before - saved) / 1e6:.2f}MB", flush=True)
    print(f"Done: {len(files)} PNGs checked, {total_saved / 1e6:.1f}MB saved.")


if __name__ == "__main__":
    if oxipng is None:
        sys.exit("pyoxipng isn't installed — run: pip install pyoxipng")
    compress_existing(*sys.argv[1:])

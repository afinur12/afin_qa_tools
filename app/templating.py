"""Shared Jinja environment.

Every router used to build its own ``Jinja2Templates``, which meant a
helper registered on one environment was invisible to the others. One
instance keeps them in step — and gives static assets a cache-busting
stamp, so an edited stylesheet or script is picked up on an ordinary
refresh instead of needing a hard reload.
"""

from pathlib import Path

from fastapi.templating import Jinja2Templates

TEMPLATES_DIR = "app/templates"
STATIC_DIR = Path("app/static")

templates = Jinja2Templates(directory=TEMPLATES_DIR)


def static_url(path: str) -> str:
    """URL for a static file, stamped with its last-modified time."""
    try:
        stamp = int((STATIC_DIR / path).stat().st_mtime)
    except OSError:
        stamp = 0
    return f"/static/{path}?v={stamp}"


templates.env.globals["static_url"] = static_url

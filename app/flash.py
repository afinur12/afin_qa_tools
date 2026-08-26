"""One-shot "success" toast messages carried across a redirect.

Uses a short-lived cookie rather than a query param so the redirect target's
URL is untouched — tests and bookmarks that parse it (``.../subtasks/{id}``)
aren't affected by an appended ``?flash=...``.
"""
from urllib.parse import quote

from fastapi.responses import RedirectResponse


def redirect_with_flash(url: str, message: str, category: str = "success", status_code: int = 303) -> RedirectResponse:
    response = RedirectResponse(url=url, status_code=status_code)
    response.set_cookie("flash", quote(message), max_age=10, path="/")
    response.set_cookie("flash_type", category, max_age=10, path="/")
    return response

"""Server-side cleaning of Knowledge Management rich text.

Text blocks and table cells hold HTML typed or pasted in the browser, and a
paste from a web page can carry scripts, event handlers and styles. Every
save runs through these allowlists, and the page renders through them again
(the km_text / km_cell template filters), so only plain formatting and
http(s)/mailto links survive. Code blocks and captions are plain text and
never come through here — they are HTML-escaped when rendered.
"""

import json

import nh3

TEXT_TAGS = {"p", "br", "div", "b", "strong", "i", "em", "u", "s", "h2", "h3", "ul", "ol", "li", "a", "code"}
CELL_TAGS = {"b", "strong", "i", "em", "u", "s", "a", "code", "br"}
_ATTRIBUTES = {"a": {"href"}}
_URL_SCHEMES = {"http", "https", "mailto"}

EMPTY_TABLE_JSON = json.dumps({"head_row": True, "head_col": False, "rows": [["", "", ""], ["", "", ""], ["", "", ""]]})


def _clean(html: str | None, tags: set[str]) -> str:
    return nh3.clean(html or "", tags=tags, attributes=_ATTRIBUTES, url_schemes=_URL_SCHEMES, link_rel="noopener noreferrer")


def sanitize_text_html(html: str | None) -> str:
    return _clean(html, TEXT_TAGS)


def sanitize_cell_html(html: str | None) -> str:
    return _clean(html, CELL_TAGS)


def parse_table(raw: str | None) -> dict:
    """Table JSON -> {"head_row", "head_col", "rows"} with every row padded to
    the same width and every cell sanitised. Anything unreadable becomes a
    single empty cell rather than an error."""
    try:
        data = json.loads(raw or "")
    except (TypeError, ValueError):
        data = {}
    if not isinstance(data, dict):
        data = {}
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows or not all(isinstance(r, list) and r for r in rows):
        rows = [[""]]
    width = max(len(r) for r in rows)
    return {
        "head_row": bool(data.get("head_row")),
        "head_col": bool(data.get("head_col")),
        "rows": [[sanitize_cell_html("" if c is None else str(c)) for c in r] + [""] * (width - len(r)) for r in rows],
    }


def sanitize_table_json(raw: str | None) -> str:
    return json.dumps(parse_table(raw))

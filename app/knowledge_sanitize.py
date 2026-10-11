"""Server-side cleaning of Knowledge Management rich text.

Text blocks and table cells hold HTML typed or pasted in the browser, and a
paste from a web page can carry scripts, event handlers and styles. Every
save runs through these allowlists, and the page renders through them again
(the km_text / km_cell template filters), so only plain formatting and
http(s)/mailto links survive. Code blocks and captions are plain text and
never come through here — they are HTML-escaped when rendered.
"""

import json
import math

import nh3

TEXT_TAGS = {"p", "br", "div", "b", "strong", "i", "em", "u", "s", "h2", "h3", "ul", "ol", "li", "a", "code"}
CELL_TAGS = {"b", "strong", "i", "em", "u", "s", "a", "code", "br"}
_ATTRIBUTES = {"a": {"href"}}
_URL_SCHEMES = {"http", "https", "mailto"}

# Table sizes, in whole pixels: (smallest, largest) a drag can set.
COL_WIDTH = (40, 2000)
ROW_HEIGHT = (20, 2000)
# A column with no width of its own in a table whose widths are set.
DEFAULT_COL_WIDTH = 120

EMPTY_TABLE_JSON = json.dumps({"head_row": True, "head_col": False, "rows": [["", "", ""], ["", "", ""], ["", "", ""]]})


def _clean(html: str | None, tags: set[str]) -> str:
    return nh3.clean(html or "", tags=tags, attributes=_ATTRIBUTES, url_schemes=_URL_SCHEMES, link_rel="noopener noreferrer")


def sanitize_text_html(html: str | None) -> str:
    return _clean(html, TEXT_TAGS)


def sanitize_cell_html(html: str | None) -> str:
    return _clean(html, CELL_TAGS)


def _px(value, low: int, high: int) -> int | None:
    """A size as whole pixels clamped to [low, high]; None if it isn't a number."""
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        return None
    return min(high, max(low, round(value)))


def parse_table(raw: str | None) -> dict:
    """Table JSON -> {"head_row", "head_col", "rows"} with every row padded to
    the same width and every cell sanitised. Anything unreadable becomes a
    single empty cell rather than an error.

    Dragged sizes come along when there are any: "col_widths" holds one width
    per column (all or nothing: a table with widths is laid out fixed, so a
    column missing one gets the default) and "row_heights" one height or None
    per row."""
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
    table = {
        "head_row": bool(data.get("head_row")),
        "head_col": bool(data.get("head_col")),
        "rows": [[sanitize_cell_html("" if c is None else str(c)) for c in r] + [""] * (width - len(r)) for r in rows],
    }
    widths = data.get("col_widths")
    if isinstance(widths, list):
        widths = [_px(w, *COL_WIDTH) for w in widths[:width]]
        if any(w is not None for w in widths):
            widths += [None] * (width - len(widths))
            table["col_widths"] = [w or DEFAULT_COL_WIDTH for w in widths]
    heights = data.get("row_heights")
    if isinstance(heights, list):
        heights = [_px(h, *ROW_HEIGHT) for h in heights[:len(rows)]]
        if any(h is not None for h in heights):
            table["row_heights"] = heights + [None] * (len(rows) - len(heights))
    return table


def sanitize_table_json(raw: str | None) -> str:
    return json.dumps(parse_table(raw))

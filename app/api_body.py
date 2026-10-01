"""Request body modes for the API Client — the Body dropdown's choices.

A request's ``body_mode`` decides how its ``body`` text is read:

- ``json`` / ``text`` / ``xml`` / ``html`` — raw text, sent as typed.
- ``urlencoded`` / ``formdata`` — ``body`` holds the key/value table as
  JSON rows (``[{key, value, description, enabled}]``), encoded only at
  send time, after {{variable}} substitution, so a resolved value
  containing "&" or a space can't break the encoding.
- ``none`` — no body at all, whatever text the editor still holds.
- ``""`` — a request saved before body modes existed. Sent verbatim with
  no Content-Type added (the old behavior); the builder page infers a
  real mode for it the first time it's opened.
"""

import json
import uuid
from urllib.parse import unquote_plus, urlencode

RAW_CONTENT_TYPES = {
    "json": "application/json",
    "text": "text/plain",
    "xml": "application/xml",
    "html": "text/html",
}
FORM_MODES = {"urlencoded", "formdata"}
BODY_MODES = {"none", *RAW_CONTENT_TYPES, *FORM_MODES}


def normalize_mode(mode: str | None) -> str:
    mode = (mode or "").strip().lower()
    return mode if mode in BODY_MODES else ""


def parse_form_rows(body: str) -> list[dict]:
    try:
        data = json.loads(body or "[]")
    except (json.JSONDecodeError, TypeError, ValueError):
        return []
    if not isinstance(data, list):
        return []
    rows = []
    for item in data:
        if not isinstance(item, dict):
            continue
        rows.append({
            "key": str(item.get("key") or ""),
            "value": str(item.get("value") or ""),
            "description": str(item.get("description") or ""),
            "enabled": item.get("enabled", True) is not False,
        })
    return rows


def dump_form_rows(rows: list[dict]) -> str:
    return json.dumps(rows, indent=2)


def enabled_pairs(rows: list[dict]) -> list[tuple[str, str]]:
    return [(r["key"], r["value"]) for r in rows if r["enabled"] and r["key"]]


def encode_urlencoded(pairs: list[tuple[str, str]]) -> str:
    return urlencode(pairs)


def urlencoded_text_to_rows(text: str) -> list[dict]:
    """``a=1&b=x+y`` -> rows, decoded the way a server would read them."""
    rows = []
    for pair in (text or "").split("&"):
        if not pair:
            continue
        key, _, value = pair.partition("=")
        rows.append({"key": unquote_plus(key), "value": unquote_plus(value), "description": "", "enabled": True})
    return rows


def _multipart_name(name: str) -> str:
    # Same escaping browsers use for a form field name in Content-Disposition.
    return name.replace('"', "%22").replace("\r", "%0D").replace("\n", "%0A")


def encode_multipart(pairs: list[tuple[str, str]], boundary: str | None = None) -> tuple[bytes, str]:
    boundary = boundary or f"----QAToolbox{uuid.uuid4().hex}"
    parts = [
        f'--{boundary}\r\nContent-Disposition: form-data; name="{_multipart_name(k)}"\r\n\r\n{v}\r\n'
        for k, v in pairs
    ]
    content = ("".join(parts) + f"--{boundary}--\r\n").encode("utf-8")
    return content, f"multipart/form-data; boundary={boundary}"


def with_content_type(headers: list[list[str]], content_type: str, replace: bool = False) -> list[list[str]]:
    """Add a Content-Type unless the user already set one. With
    ``replace``, any existing one is dropped first — form-data needs its
    own generated boundary, so a hand-typed multipart header can't win."""
    has_one = any(k.lower() == "content-type" for k, _v in headers)
    if has_one and not replace:
        return headers
    kept = [[k, v] for k, v in headers if k.lower() != "content-type"]
    return kept + [["Content-Type", content_type]]


def without_content_type(headers: list[list[str]]) -> list[list[str]]:
    return [[k, v] for k, v in headers if k.lower() != "content-type"]

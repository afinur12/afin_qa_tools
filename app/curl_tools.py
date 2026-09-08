"""Parse a pasted curl command into request fields, and build one back.

Hand-rolled rather than a vendored parser, same philosophy as the Note
Section paste-language-detector in app.js: this only ever needs to handle
what a browser's "Copy as cURL" or a person's own typing produces, not the
full curl CLI grammar.
"""

import re
import shlex
from urllib.parse import quote_plus


def looks_like_curl(text: str) -> bool:
    return bool(re.match(r"^\s*curl\b", text or "", re.IGNORECASE))


def parse_curl(text: str) -> dict:
    """Return {"method": str, "url": str, "headers": [[k, v], ...], "body": str}.

    Best-effort: unrecognized flags are silently skipped rather than raising,
    since a pasted command is likely to carry curl options (-k, --compressed,
    -sS, ...) that don't map onto anything in the request builder.
    """
    # Browser "Copy as cURL" commonly line-continues with a trailing "\" (or
    # "^" on Windows) before a newline — join those back into one line first.
    joined = re.sub(r"[\\^]\s*\r?\n", " ", text or "")
    try:
        tokens = shlex.split(joined, posix=True)
    except ValueError:
        tokens = joined.split()

    method = None
    url = ""
    headers: list[list[str]] = []
    data_parts: list[str] = []
    has_data = False
    used_urlencode = False

    i = 0
    while i < len(tokens):
        tok = tokens[i]

        def _next() -> str:
            nonlocal i
            i += 1
            return tokens[i] if i < len(tokens) else ""

        if tok in ("-X", "--request"):
            method = _next().upper()
        elif tok in ("-H", "--header"):
            raw = _next()
            if ":" in raw:
                k, v = raw.split(":", 1)
                headers.append([k.strip(), v.strip()])
        elif tok in ("-d", "--data", "--data-raw", "--data-binary", "--data-ascii"):
            # curl accumulates every -d/--data(-raw|-binary|-ascii) occurrence
            # into one body, joined with "&" — a command can (and for
            # multi-field forms, usually does) pass several.
            data_parts.append(_next())
            has_data = True
        elif tok == "--data-urlencode":
            # name=value -> name kept as-is, value percent-encoded (curl's
            # own rule — the name is assumed already safe). A bare value or
            # a leading "=value" has no name, so the whole value is encoded
            # with no "=" in the output. name@file/@file (read from disk)
            # isn't supported for a pasted command — skipped, best-effort.
            raw = _next()
            has_data = True
            used_urlencode = True
            if "@" in raw.split("=", 1)[0]:
                pass
            elif raw.startswith("="):
                data_parts.append(quote_plus(raw[1:]))
            elif "=" in raw:
                name, value = raw.split("=", 1)
                data_parts.append(f"{name}={quote_plus(value)}")
            else:
                data_parts.append(quote_plus(raw))
        elif tok == "-u" or tok == "--user":
            import base64

            creds = _next()
            token = base64.b64encode(creds.encode("utf-8")).decode("ascii")
            headers.append(["Authorization", f"Basic {token}"])
        elif tok in ("--url",):
            url = _next()
        elif tok == "curl":
            pass
        elif tok.startswith("-"):
            # Unrecognized flag. If it plausibly takes a value (single dash,
            # short option, not a known no-arg switch) skip that too — better
            # to lose one flag's argument than to mis-parse it as the URL.
            NO_ARG = {"-s", "-S", "-k", "-i", "-I", "-L", "-v", "-#", "--silent", "--show-error",
                      "--insecure", "--include", "--head", "--location", "--verbose", "--compressed"}
            if tok not in NO_ARG and not tok.startswith("--"):
                i += 1
        else:
            if not url:
                url = tok
        i += 1

    if method is None:
        method = "POST" if has_data else "GET"

    body = "&".join(data_parts)

    # curl itself defaults to application/x-www-form-urlencoded whenever
    # --data-urlencode builds the body, unless the command already sets its
    # own Content-Type — match that so a replayed request behaves the same.
    if used_urlencode and not any(k.strip().lower() == "content-type" for k, _v in headers):
        headers.append(["Content-Type", "application/x-www-form-urlencoded"])

    return {"method": method, "url": url, "headers": headers, "body": body}


def build_curl(method: str, url: str, headers: list[list[str]], body: str) -> str:
    parts = ["curl", "-X", method, shlex.quote(url or "")]
    for k, v in headers or []:
        if not k:
            continue
        parts.append("-H")
        parts.append(shlex.quote(f"{k}: {v}"))
    if body:
        parts.append("-d")
        parts.append(shlex.quote(body))
    return " ".join(parts)

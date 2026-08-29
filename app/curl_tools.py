"""Parse a pasted curl command into request fields, and build one back.

Hand-rolled rather than a vendored parser, same philosophy as the Note
Section paste-language-detector in app.js: this only ever needs to handle
what a browser's "Copy as cURL" or a person's own typing produces, not the
full curl CLI grammar.
"""

import re
import shlex


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
    body = ""
    has_data = False

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
            body = _next()
            has_data = True
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

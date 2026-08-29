"""Resolve ``{{name}}`` placeholders in a request's URL/headers/body.

Precedence at send time: COLLECTION > GLOBAL > BUILTIN — a variable saved
on the current collection shadows a same-named global one, which in turn
shadows a same-named built-in. A VALUE variable is a plain string; a
SCRIPT variable is a short Python snippet re-run fresh on every call (so
e.g. {{uuid}} is a new UUID each time), executed in a restricted namespace
under a soft timeout via a background thread — the request handler never
blocks forever on a runaway script, though (Windows has no SIGALRM, so
there's no way to hard-kill a Python thread) an abandoned script keeps
running until it finishes on its own.
"""

import base64
import hashlib
import random
import re
import threading
import time
import uuid
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models import ApiVariable, ApiVariableKind, ApiVariableScope

VAR_PATTERN = re.compile(r"\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\}\}")

SCRIPT_TIMEOUT_SECONDS = 1.0

_SAFE_BUILTIN_NAMES = (
    "str", "int", "float", "bool", "len", "range", "list", "dict", "tuple", "set",
    "abs", "min", "max", "sum", "round", "sorted", "enumerate", "zip", "map", "filter",
    "True", "False", "None", "ValueError", "TypeError",
)


def _safe_namespace() -> dict:
    import builtins

    safe_builtins = {name: getattr(builtins, name) for name in _SAFE_BUILTIN_NAMES if hasattr(builtins, name)}
    return {
        "__builtins__": safe_builtins,
        "uuid": uuid,
        "time": time,
        "timezone": timezone,
        "datetime": datetime,
        "random": random,
        "hashlib": hashlib,
        "base64": base64,
    }


class ScriptError(Exception):
    pass


def run_script(script: str) -> str:
    """Run a variable's script (the body of an implicit function — the
    author writes `return <expr>` same as inside any Python function) and
    return its result as a string."""
    indented = "\n".join("    " + line for line in (script or "").splitlines()) or "    pass"
    source = f"def __variable_script__():\n{indented}\n"

    result_box: dict = {}

    def _run():
        try:
            local_ns: dict = {}
            exec(compile(source, "<variable-script>", "exec"), _safe_namespace(), local_ns)
            result_box["value"] = local_ns["__variable_script__"]()
        except Exception as exc:  # noqa: BLE001 - surfaced to the caller, never a 500
            result_box["error"] = f"{type(exc).__name__}: {exc}"

    thread = threading.Thread(target=_run, daemon=True)
    thread.start()
    thread.join(SCRIPT_TIMEOUT_SECONDS)
    if thread.is_alive():
        raise ScriptError("Script timed out")
    if "error" in result_box:
        raise ScriptError(result_box["error"])
    return str(result_box.get("value", ""))


# Seeded once (see database.seed_builtin_variables); still just ordinary
# ApiVariable rows from there on — fully editable/deletable like any other.
DEFAULT_BUILTIN_VARIABLES = [
    {"key": "guid", "script": "return str(uuid.uuid4())", "description": "Random UUID v4"},
    {"key": "timestamp", "script": "return str(int(time.time()))", "description": "Unix time, seconds"},
    {"key": "timestamp_ms", "script": "return str(int(time.time() * 1000))", "description": "Unix time, milliseconds"},
    {"key": "iso_date", "script": "return datetime.now(timezone.utc).isoformat()", "description": "Current time, ISO 8601"},
    {"key": "random_int", "script": "return str(random.randint(0, 999999))", "description": "Random integer, 0-999999"},
]


def seed_builtin_variables(db: Session) -> None:
    """Insert the 5 default built-ins once, on an empty table. From then on
    they're ordinary rows — the user can edit, delete, or add to them
    freely, so this never runs again once at least one BUILTIN row exists."""
    if db.query(ApiVariable).filter(ApiVariable.scope == ApiVariableScope.BUILTIN).first():
        return
    for item in DEFAULT_BUILTIN_VARIABLES:
        db.add(ApiVariable(
            scope=ApiVariableScope.BUILTIN, kind=ApiVariableKind.SCRIPT,
            key=item["key"], script=item["script"], description=item["description"],
        ))
    db.commit()


def load_variables(db: Session, collection_id: int | None) -> dict[str, ApiVariable]:
    """key -> the ApiVariable that should win, respecting scope precedence."""
    resolved: dict[str, ApiVariable] = {}
    for row in db.query(ApiVariable).filter(ApiVariable.scope == ApiVariableScope.BUILTIN):
        resolved[row.key] = row
    for row in db.query(ApiVariable).filter(ApiVariable.scope == ApiVariableScope.GLOBAL):
        resolved[row.key] = row
    if collection_id is not None:
        for row in db.query(ApiVariable).filter(
            ApiVariable.scope == ApiVariableScope.COLLECTION, ApiVariable.collection_id == collection_id
        ):
            resolved[row.key] = row
    return resolved


def resolve_value(variable: ApiVariable) -> str:
    if variable.kind == ApiVariableKind.SCRIPT:
        return run_script(variable.script or "")
    return variable.value or ""


def resolve_text(text: str, variables: dict[str, ApiVariable], sensitive_values: set[str]) -> tuple[str, list[str]]:
    """Replace every {{name}} in `text`. Returns (resolved_text, errors) —
    an unresolved or errored placeholder is left literal, never silently
    dropped, and its name is added to `errors`. Any sensitive variable's
    resolved value is recorded into `sensitive_values` so the frontend can
    mask it later when rendering an export image."""
    errors: list[str] = []

    def _sub(match: re.Match) -> str:
        name = match.group(1)
        variable = variables.get(name)
        if variable is None:
            errors.append(name)
            return match.group(0)
        try:
            value = resolve_value(variable)
        except ScriptError as exc:
            errors.append(f"{name} ({exc})")
            return match.group(0)
        if variable.is_sensitive and value:
            sensitive_values.add(value)
        return value

    return VAR_PATTERN.sub(_sub, text or ""), errors


SENSITIVE_HEADER_PATTERN = re.compile(
    r"authorization|cookie|api[-_]?key|token|secret|password", re.IGNORECASE
)


def header_looks_sensitive(header_key: str) -> bool:
    return bool(SENSITIVE_HEADER_PATTERN.search(header_key or ""))

"""API Client: a local Postman/Insomnia-style request builder.

Runs every request through this server (httpx), never straight from the
browser, so it rides whatever network/VPN this machine is on and never
hits browser CORS. See PLAN.md for the full feature spec this implements.
"""

import json
import time as time_module
import uuid
from collections import defaultdict

import httpx
from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import JSONResponse, Response
from sqlalchemy.orm import Session

from app.curl_tools import build_curl, looks_like_curl, parse_curl
from app.database import get_db
from app.flash import redirect_with_flash
from app.models import (
    ApiCollection, ApiFolder, ApiHistory, ApiRequest, ApiVariable,
    ApiVariableKind, ApiVariableScope,
)
from app.templating import templates
from app.variables import header_looks_sensitive, load_variables, resolve_text

router = APIRouter(prefix="/api-client")

MAX_HISTORY_ROWS = 500


def _headers_to_json(headers: list[list[str]]) -> str:
    return json.dumps([[k, v] for k, v in headers if k])


def _headers_from_json(raw: str) -> list[list[str]]:
    try:
        return [[str(k), str(v)] for k, v in json.loads(raw or "[]")]
    except (json.JSONDecodeError, TypeError, ValueError):
        return []


def _beautify(text: str) -> str:
    """Pretty-print a body for storage/display when it's JSON; anything
    else (XML, form-encoded, plain text, or just not valid JSON) is left
    exactly as it was. Only touches what gets saved/shown — the bytes
    actually sent over the wire in send_request are never run through
    this, so a signature-checked webhook body isn't silently reformatted."""
    stripped = (text or "").strip()
    if not stripped:
        return text or ""
    try:
        return json.dumps(json.loads(stripped), indent=2)
    except (json.JSONDecodeError, TypeError, ValueError):
        return text


def _history_to_response_dict(hist: ApiHistory) -> dict:
    """Same shape /send returns, so the builder page can hand a past hit
    straight to the same renderResponse() JS used for a live Send."""
    if hist.error:
        return {"error": hist.error, "unresolved": []}
    return {
        "status": hist.response_status, "headers": _headers_from_json(hist.response_headers_json),
        "body": hist.response_body, "duration_ms": hist.duration_ms, "size_bytes": hist.response_size_bytes,
        "unresolved": [], "sensitive_values": [],
    }


def _unique_collection_name(db: Session, name: str) -> str:
    base = name or "Imported Collection"
    candidate = base
    n = 2
    while db.query(ApiCollection).filter(ApiCollection.name == candidate).first():
        candidate = f"{base} ({n})"
        n += 1
    return candidate


# ── Builder page ────────────────────────────────────────────────────────

@router.get("")
def builder(
    request: Request,
    request_id: int | None = None,
    restore_history_id: int | None = None,
    collection_id: int | None = None,
    db: Session = Depends(get_db),
):
    collections = db.query(ApiCollection).order_by(ApiCollection.name).all()

    current = {"id": None, "name": "New Request", "method": "GET", "url": "", "headers": [], "body": "", "collection_id": collection_id}
    last_response = None
    if request_id is not None:
        saved = db.get(ApiRequest, request_id)
        if saved is not None:
            current = {
                "id": saved.id, "name": saved.name, "method": saved.method, "url": saved.url,
                "headers": _headers_from_json(saved.headers_json), "body": saved.body,
                "collection_id": saved.collection_id, "folder_id": saved.folder_id,
            }
            last_hit = (
                db.query(ApiHistory)
                .filter(ApiHistory.request_id == saved.id)
                .order_by(ApiHistory.id.desc())
                .first()
            )
            if last_hit is not None:
                last_response = _history_to_response_dict(last_hit)
    elif restore_history_id is not None:
        hist = db.get(ApiHistory, restore_history_id)
        if hist is not None:
            current = {
                "id": None, "name": "Restored from History", "method": hist.method, "url": hist.url,
                "headers": _headers_from_json(hist.request_headers_json), "body": hist.request_body,
                "collection_id": None,
            }

    builtin_vars = db.query(ApiVariable).filter(ApiVariable.scope == ApiVariableScope.BUILTIN).order_by(ApiVariable.key).all()
    global_vars = db.query(ApiVariable).filter(ApiVariable.scope == ApiVariableScope.GLOBAL).order_by(ApiVariable.key).all()
    collection_vars = []
    if current.get("collection_id"):
        collection_vars = (
            db.query(ApiVariable)
            .filter(ApiVariable.scope == ApiVariableScope.COLLECTION, ApiVariable.collection_id == current["collection_id"])
            .order_by(ApiVariable.key)
            .all()
        )

    # For the {{ }} autocomplete dropdown — collection-scope listed first so
    # a same-named shadow of a global/built-in shows as the one that'll
    # actually win (matches the real resolution precedence).
    all_variables = [
        {"name": v.key, "scope": "collection", "description": v.description or ""} for v in collection_vars
    ] + [
        {"name": v.key, "scope": "global", "description": v.description or ""} for v in global_vars
    ] + [
        {"name": v.key, "scope": "builtin", "description": v.description or ""} for v in builtin_vars
    ]

    return templates.TemplateResponse(
        request,
        "api_client/builder.html",
        {
            "collections": collections,
            "current": current,
            "all_variables": all_variables,
            "last_response": last_response,
        },
    )


# ── Send / resolve ──────────────────────────────────────────────────────

def _resolve_request(db: Session, payload: dict) -> dict:
    collection_id = payload.get("collection_id")
    variables = load_variables(db, collection_id)
    sensitive_values: set[str] = set()

    url, url_errors = resolve_text(payload.get("url", ""), variables, sensitive_values)
    body, body_errors = resolve_text(payload.get("body", ""), variables, sensitive_values)

    headers: list[list[str]] = []
    header_errors: list[str] = []
    for key, value in payload.get("headers", []):
        r_key, k_err = resolve_text(key, variables, sensitive_values)
        r_val, v_err = resolve_text(value, variables, sensitive_values)
        header_errors += k_err + v_err
        if r_key:
            headers.append([r_key, r_val])
            if header_looks_sensitive(r_key) and r_val:
                sensitive_values.add(r_val)

    errors = sorted(set(url_errors + body_errors + header_errors))
    return {
        "method": (payload.get("method") or "GET").upper(),
        "url": url, "headers": headers, "body": body,
        "errors": errors, "sensitive_values": sorted(sensitive_values),
    }


@router.post("/resolve")
async def resolve_request(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    resolved = _resolve_request(db, payload)
    resolved["curl"] = build_curl(resolved["method"], resolved["url"], resolved["headers"], resolved["body"])
    return JSONResponse(resolved)


@router.post("/parse-curl")
async def parse_curl_route(request: Request):
    payload = await request.json()
    text = payload.get("text", "")
    if not looks_like_curl(text):
        return JSONResponse({"matched": False})
    parsed = parse_curl(text)
    return JSONResponse({"matched": True, **parsed})


@router.post("/send")
async def send_request(request: Request, db: Session = Depends(get_db)):
    payload = await request.json()
    resolved = _resolve_request(db, payload)

    history = ApiHistory(
        request_id=payload.get("request_id"),
        method=resolved["method"], url=resolved["url"],
        request_headers_json=_headers_to_json(resolved["headers"]), request_body=_beautify(resolved["body"]),
    )

    if resolved["errors"] and not resolved["url"]:
        history.error = f"Unresolved variables: {', '.join(resolved['errors'])}"
        db.add(history)
        _prune_history(db)
        db.commit()
        return JSONResponse({"error": history.error, "unresolved": resolved["errors"]}, status_code=200)

    started = time_module.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=30.0, follow_redirects=True) as client:
            resp = await client.request(
                resolved["method"], resolved["url"],
                headers={k: v for k, v in resolved["headers"]},
                content=resolved["body"].encode("utf-8") if resolved["body"] else None,
            )
        duration_ms = int((time_module.perf_counter() - started) * 1000)
        # Beautified for storage/display only — response_size_bytes below
        # still reflects the real wire size, not this reformatted text.
        body_text = _beautify(resp.text)
        history.response_status = resp.status_code
        history.response_headers_json = _headers_to_json(list(resp.headers.items()))
        history.response_body = body_text
        history.duration_ms = duration_ms
        history.response_size_bytes = len(resp.content)
        db.add(history)
        _prune_history(db)
        db.commit()
        return JSONResponse({
            "status": resp.status_code, "headers": list(resp.headers.items()),
            "body": body_text, "duration_ms": duration_ms, "size_bytes": len(resp.content),
            "unresolved": resolved["errors"], "sensitive_values": resolved["sensitive_values"],
        })
    except httpx.HTTPError as exc:
        history.error = f"{type(exc).__name__}: {exc}"
        db.add(history)
        _prune_history(db)
        db.commit()
        return JSONResponse({"error": history.error, "unresolved": resolved["errors"]}, status_code=200)


def _prune_history(db: Session) -> None:
    total = db.query(ApiHistory).count()
    if total > MAX_HISTORY_ROWS:
        stale_ids = [
            row.id for row in
            db.query(ApiHistory.id).order_by(ApiHistory.id.asc()).limit(total - MAX_HISTORY_ROWS)
        ]
        db.query(ApiHistory).filter(ApiHistory.id.in_(stale_ids)).delete(synchronize_session=False)


# ── Collections ─────────────────────────────────────────────────────────

@router.post("/collections")
def create_collection(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    name = name.strip() or "Untitled Collection"
    collection = ApiCollection(name=name)
    db.add(collection)
    db.commit()
    db.refresh(collection)
    return redirect_with_flash(f"/api-client?collection_id={collection.id}", f'Collection "{collection.name}" created.')


@router.post("/collections/{collection_id}/edit")
def rename_collection(request: Request, collection_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    collection = db.get(ApiCollection, collection_id)
    if collection is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    collection.name = name.strip() or collection.name
    db.commit()
    return redirect_with_flash("/api-client", f'Collection renamed to "{collection.name}".')


@router.post("/collections/{collection_id}/delete")
def delete_collection(request: Request, collection_id: int, db: Session = Depends(get_db)):
    collection = db.get(ApiCollection, collection_id)
    if collection is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    name = collection.name
    db.query(ApiVariable).filter(ApiVariable.collection_id == collection_id).delete(synchronize_session=False)
    db.query(ApiRequest).filter(ApiRequest.collection_id == collection_id).delete(synchronize_session=False)
    db.query(ApiFolder).filter(ApiFolder.collection_id == collection_id).delete(synchronize_session=False)
    db.delete(collection)
    db.commit()
    return redirect_with_flash("/api-client", f'Collection "{name}" deleted.', category="danger")


def _request_to_postman_item(r: ApiRequest) -> dict:
    item: dict = {
        "name": r.name,
        "request": {
            "method": r.method,
            "header": [{"key": k, "value": v, "type": "text"} for k, v in _headers_from_json(r.headers_json)],
            "url": r.url,
        },
        "response": [],
    }
    if r.body:
        item["request"]["body"] = {"mode": "raw", "raw": r.body, "options": {"raw": {"language": "json"}}}
    return item


def _folder_to_postman_item(folder: ApiFolder, children_by_parent: dict, requests_by_folder: dict) -> dict:
    return {
        "name": folder.name,
        "item": [
            *[_folder_to_postman_item(child, children_by_parent, requests_by_folder) for child in children_by_parent.get(folder.id, [])],
            *[_request_to_postman_item(r) for r in requests_by_folder.get(folder.id, [])],
        ],
    }


@router.get("/collections/{collection_id}/export")
def export_collection(collection_id: int, db: Session = Depends(get_db)):
    collection = db.get(ApiCollection, collection_id)
    if collection is None:
        return Response(status_code=404)

    children_by_parent: dict = defaultdict(list)
    for f in collection.folders:
        children_by_parent[f.parent_folder_id].append(f)
    requests_by_folder: dict = defaultdict(list)
    for r in collection.requests:
        requests_by_folder[r.folder_id].append(r)

    # A real Postman Collection v2.1 export (not our own schema) — so the
    # file round-trips through Postman itself, not just back into this app.
    data = {
        "info": {
            "_postman_id": str(uuid.uuid4()),
            "name": collection.name,
            "schema": "https://schema.getpostman.com/json/collection/v2.1.0/collection.json",
        },
        "item": [
            *[_folder_to_postman_item(f, children_by_parent, requests_by_folder) for f in children_by_parent.get(None, [])],
            *[_request_to_postman_item(r) for r in requests_by_folder.get(None, [])],
        ],
    }
    filename = "".join(c if c.isalnum() or c in "-_ " else "_" for c in collection.name).strip() or "collection"
    return Response(
        json.dumps(data, indent=2), media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{filename}.postman_collection.json"'},
    )


def _postman_url(url_field) -> str:
    if isinstance(url_field, dict):
        return url_field.get("raw", "") or ""
    return url_field or ""


def _postman_body(body_field: dict) -> str:
    mode = body_field.get("mode")
    if mode == "raw":
        return body_field.get("raw", "")
    if mode == "urlencoded":
        pairs = body_field.get("urlencoded", []) or []
        return "&".join(f"{p.get('key', '')}={p.get('value', '')}" for p in pairs if not p.get("disabled"))
    if mode == "graphql":
        return (body_field.get("graphql") or {}).get("query", "")
    return ""


def _import_postman_items(db: Session, collection_id: int, items: list, folder_id: int | None) -> None:
    """Postman's "item" array mixes folders (nested "item") and requests
    ("request") at every level — walk it recursively, mirroring that shape
    onto our flat ApiFolder/ApiRequest tables."""
    for item in items:
        if "item" in item:
            folder = ApiFolder(collection_id=collection_id, name=item.get("name", "Folder"), parent_folder_id=folder_id)
            db.add(folder)
            db.flush()
            _import_postman_items(db, collection_id, item.get("item", []), folder.id)
        elif "request" in item:
            req = item["request"]
            if isinstance(req, str):
                method, url, headers, body = "GET", req, [], ""
            else:
                method = (req.get("method") or "GET").upper()
                url = _postman_url(req.get("url", ""))
                headers = [[h.get("key", ""), h.get("value", "")] for h in req.get("header", []) or [] if not h.get("disabled")]
                body = _postman_body(req.get("body") or {})
            db.add(ApiRequest(
                collection_id=collection_id, folder_id=folder_id,
                name=item.get("name", "Request"), method=method, url=url,
                headers_json=_headers_to_json(headers), body=_beautify(body),
            ))


@router.post("/collections/import")
async def import_collection(request: Request, file: UploadFile = File(...), db: Session = Depends(get_db)):
    raw = await file.read()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return redirect_with_flash("/api-client", "That file isn't valid JSON.", category="danger")

    if "item" in data and "info" in data:
        # A Postman collection export (v2.0/v2.1) — a different shape
        # entirely from our own export, not just different field names.
        collection = ApiCollection(name=_unique_collection_name(db, (data.get("info") or {}).get("name", "Imported Collection")))
        db.add(collection)
        db.flush()
        _import_postman_items(db, collection.id, data.get("item", []), None)
        db.commit()
        return redirect_with_flash(f"/api-client?collection_id={collection.id}", f'Imported "{collection.name}".')

    collection = ApiCollection(name=_unique_collection_name(db, data.get("name", "Imported Collection")))
    db.add(collection)
    db.flush()

    ref_to_folder_id: dict[int, int] = {}
    for f in data.get("folders", []):
        parent_ref = f.get("parent_id_ref")
        folder = ApiFolder(
            collection_id=collection.id, name=f.get("name", "Folder"),
            parent_folder_id=ref_to_folder_id.get(parent_ref) if parent_ref is not None else None,
        )
        db.add(folder)
        db.flush()
        ref_to_folder_id[f.get("id_ref")] = folder.id

    for r in data.get("requests", []):
        folder_ref = r.get("folder_id_ref")
        db.add(ApiRequest(
            collection_id=collection.id, folder_id=ref_to_folder_id.get(folder_ref) if folder_ref is not None else None,
            name=r.get("name", "Request"), method=r.get("method", "GET"), url=r.get("url", ""),
            headers_json=_headers_to_json(r.get("headers", [])), body=_beautify(r.get("body", "")),
        ))
    db.commit()
    return redirect_with_flash(f"/api-client?collection_id={collection.id}", f'Imported "{collection.name}".')


# ── Folders ─────────────────────────────────────────────────────────────

@router.post("/folders")
def create_folder(
    request: Request, collection_id: int = Form(...), name: str = Form(...),
    parent_folder_id: str = Form(""), db: Session = Depends(get_db),
):
    collection = db.get(ApiCollection, collection_id)
    if collection is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    folder = ApiFolder(
        collection_id=collection_id, name=name.strip() or "Folder",
        parent_folder_id=int(parent_folder_id) if parent_folder_id else None,
    )
    db.add(folder)
    db.commit()
    return redirect_with_flash(f"/api-client?collection_id={collection_id}", f'Folder "{folder.name}" created.')


@router.post("/folders/{folder_id}/edit")
def rename_folder(request: Request, folder_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    folder = db.get(ApiFolder, folder_id)
    if folder is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    folder.name = name.strip() or folder.name
    db.commit()
    return redirect_with_flash(f"/api-client?collection_id={folder.collection_id}", f'Folder renamed to "{folder.name}".')


def _delete_folder_recursive(db: Session, folder: ApiFolder) -> None:
    for child in list(folder.children):
        _delete_folder_recursive(db, child)
    db.query(ApiRequest).filter(ApiRequest.folder_id == folder.id).delete(synchronize_session=False)
    db.delete(folder)


@router.post("/folders/{folder_id}/delete")
def delete_folder(request: Request, folder_id: int, db: Session = Depends(get_db)):
    folder = db.get(ApiFolder, folder_id)
    if folder is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    collection_id = folder.collection_id
    name = folder.name
    _delete_folder_recursive(db, folder)
    db.commit()
    return redirect_with_flash(f"/api-client?collection_id={collection_id}", f'Folder "{name}" deleted.', category="danger")


# ── Requests ────────────────────────────────────────────────────────────

@router.post("/requests")
def create_request(
    request: Request, collection_id: int = Form(...), name: str = Form(...),
    method: str = Form("GET"), url: str = Form(""), headers_json: str = Form("[]"),
    body: str = Form(""), folder_id: str = Form(""), db: Session = Depends(get_db),
):
    collection = db.get(ApiCollection, collection_id)
    if collection is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    saved = ApiRequest(
        collection_id=collection_id, folder_id=int(folder_id) if folder_id else None,
        name=name.strip() or "Untitled Request", method=method.upper(), url=url,
        headers_json=_headers_to_json(_headers_from_json(headers_json)), body=_beautify(body),
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return redirect_with_flash(f"/api-client?request_id={saved.id}", f'"{saved.name}" saved.')


@router.post("/requests/{request_id}/edit")
def update_request(
    request: Request, request_id: int, name: str = Form(...), method: str = Form("GET"),
    url: str = Form(""), headers_json: str = Form("[]"), body: str = Form(""),
    db: Session = Depends(get_db),
):
    saved = db.get(ApiRequest, request_id)
    if saved is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    saved.name = name.strip() or saved.name
    saved.method = method.upper()
    saved.url = url
    saved.headers_json = _headers_to_json(_headers_from_json(headers_json))
    saved.body = _beautify(body)
    db.commit()
    return redirect_with_flash(f"/api-client?request_id={saved.id}", f'"{saved.name}" saved.')


@router.post("/requests/{request_id}/rename")
def rename_request(request: Request, request_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    saved = db.get(ApiRequest, request_id)
    if saved is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    saved.name = name.strip() or saved.name
    db.commit()
    return redirect_with_flash(f"/api-client?request_id={saved.id}", f'Request renamed to "{saved.name}".')


@router.post("/requests/{request_id}/delete")
def delete_request(request: Request, request_id: int, db: Session = Depends(get_db)):
    saved = db.get(ApiRequest, request_id)
    if saved is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    collection_id = saved.collection_id
    name = saved.name
    db.delete(saved)
    db.commit()
    return redirect_with_flash(f"/api-client?collection_id={collection_id}", f'"{name}" deleted.', category="danger")


# ── Variables (dedicated page: global + collection) ─────────────────────

@router.get("/variables")
def variables_page(request: Request, collection_id: int | None = None, db: Session = Depends(get_db)):
    global_vars = db.query(ApiVariable).filter(ApiVariable.scope == ApiVariableScope.GLOBAL).order_by(ApiVariable.key).all()
    collections = db.query(ApiCollection).order_by(ApiCollection.name).all()
    selected_collection = db.get(ApiCollection, collection_id) if collection_id else None
    collection_vars = []
    if selected_collection is not None:
        collection_vars = (
            db.query(ApiVariable)
            .filter(ApiVariable.scope == ApiVariableScope.COLLECTION, ApiVariable.collection_id == selected_collection.id)
            .order_by(ApiVariable.key)
            .all()
        )
    return templates.TemplateResponse(
        request,
        "api_client/variables.html",
        {
            "global_vars": global_vars,
            "collections": collections,
            "selected_collection": selected_collection,
            "collection_vars": collection_vars,
        },
    )


@router.post("/variables")
def create_variable(
    request: Request, scope: str = Form(...), key: str = Form(...), kind: str = Form("VALUE"),
    value: str = Form(""), script: str = Form(""), description: str = Form(""),
    is_sensitive: str = Form(""), collection_id: str = Form(""), db: Session = Depends(get_db),
):
    scope_enum = ApiVariableScope(scope)
    scoped_collection_id = int(collection_id) if collection_id and scope_enum == ApiVariableScope.COLLECTION else None
    key = key.strip()

    # The DB's UniqueConstraint("scope", "collection_id", "key") can't catch
    # this on its own: collection_id is NULL for every GLOBAL/BUILTIN
    # variable, and SQL treats each NULL as distinct from every other NULL,
    # so the constraint silently allows duplicate global/built-in names. A
    # double-submit (e.g. a fast double-click) needs this explicit check.
    existing = (
        db.query(ApiVariable)
        .filter(ApiVariable.scope == scope_enum, ApiVariable.collection_id == scoped_collection_id, ApiVariable.key == key)
        .first()
    )
    if existing is not None:
        return redirect_with_flash(
            "/api-client/variables/builtin" if scope_enum == ApiVariableScope.BUILTIN
            else (f"/api-client/variables?collection_id={scoped_collection_id}" if scoped_collection_id else "/api-client/variables"),
            f'{{{{{key}}}}} already exists in this scope.', category="danger",
        )

    variable = ApiVariable(
        scope=scope_enum, collection_id=scoped_collection_id,
        key=key, kind=ApiVariableKind(kind), value=value or None, script=script or None,
        description=description.strip() or None, is_sensitive=bool(is_sensitive),
    )
    db.add(variable)
    db.commit()
    return _variable_redirect(variable)


@router.post("/variables/{variable_id}/edit")
def update_variable(
    request: Request, variable_id: int, key: str = Form(...), kind: str = Form("VALUE"),
    value: str = Form(""), script: str = Form(""), description: str = Form(""),
    is_sensitive: str = Form(""), db: Session = Depends(get_db),
):
    variable = db.get(ApiVariable, variable_id)
    if variable is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    variable.key = key.strip() or variable.key
    variable.kind = ApiVariableKind(kind)
    variable.value = value or None
    variable.script = script or None
    variable.description = description.strip() or None
    variable.is_sensitive = bool(is_sensitive)
    db.commit()
    return _variable_redirect(variable)


@router.post("/variables/{variable_id}/delete")
def delete_variable(request: Request, variable_id: int, db: Session = Depends(get_db)):
    variable = db.get(ApiVariable, variable_id)
    if variable is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    scope = variable.scope
    collection_id = variable.collection_id
    db.delete(variable)
    db.commit()
    if scope == ApiVariableScope.BUILTIN:
        target = "/api-client/variables/builtin"
    elif collection_id:
        target = f"/api-client/variables?collection_id={collection_id}"
    else:
        target = "/api-client/variables"
    return redirect_with_flash(target, "Variable deleted.", category="danger")


def _variable_redirect(variable: ApiVariable):
    if variable.scope == ApiVariableScope.BUILTIN:
        return redirect_with_flash("/api-client/variables/builtin", f"{{{{{variable.key}}}}} saved.")
    target = f"/api-client/variables?collection_id={variable.collection_id}" if variable.collection_id else "/api-client/variables"
    return redirect_with_flash(target, f"{{{{{variable.key}}}}} saved.")


# ── Built-in Variables page ─────────────────────────────────────────────

@router.get("/variables/builtin")
def builtin_variables(request: Request, db: Session = Depends(get_db)):
    variables = db.query(ApiVariable).filter(ApiVariable.scope == ApiVariableScope.BUILTIN).order_by(ApiVariable.key).all()
    return templates.TemplateResponse(request, "api_client/builtin_variables.html", {"variables": variables})


@router.post("/variables/builtin")
def create_builtin_variable(
    request: Request, key: str = Form(...), kind: str = Form("SCRIPT"), value: str = Form(""),
    script: str = Form(""), description: str = Form(""), db: Session = Depends(get_db),
):
    key = key.strip()
    # Same NULL-collision reason as create_variable: collection_id is always
    # NULL here, so the DB's UniqueConstraint can't be trusted to reject a
    # double-submit on its own.
    if db.query(ApiVariable).filter(ApiVariable.scope == ApiVariableScope.BUILTIN, ApiVariable.key == key).first():
        return redirect_with_flash("/api-client/variables/builtin", f'{{{{{key}}}}} already exists.', category="danger")

    db.add(ApiVariable(
        scope=ApiVariableScope.BUILTIN, key=key, kind=ApiVariableKind(kind),
        value=value or None, script=script or None, description=description.strip() or None,
    ))
    db.commit()
    return redirect_with_flash("/api-client/variables/builtin", f"{{{{{key}}}}} added.")


# ── History ─────────────────────────────────────────────────────────────

@router.get("/history")
def history_list(request: Request, db: Session = Depends(get_db)):
    rows = db.query(ApiHistory).order_by(ApiHistory.id.desc()).limit(200).all()
    return templates.TemplateResponse(request, "api_client/history.html", {"rows": rows})


@router.get("/history/{history_id}")
def history_detail(request: Request, history_id: int, db: Session = Depends(get_db)):
    row = db.get(ApiHistory, history_id)
    if row is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request, "api_client/history_detail.html",
        {"row": row, "headers": _headers_from_json(row.request_headers_json), "response_headers": _headers_from_json(row.response_headers_json)},
    )


@router.post("/history/{history_id}/delete")
def delete_history_row(request: Request, history_id: int, db: Session = Depends(get_db)):
    row = db.get(ApiHistory, history_id)
    if row is not None:
        db.delete(row)
        db.commit()
    return redirect_with_flash("/api-client/history", "Removed from history.", category="danger")


@router.post("/history/clear")
def clear_history(request: Request, db: Session = Depends(get_db)):
    db.query(ApiHistory).delete(synchronize_session=False)
    db.commit()
    return redirect_with_flash("/api-client/history", "History cleared.", category="danger")

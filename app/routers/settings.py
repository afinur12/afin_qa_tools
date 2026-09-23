"""Settings: Service, Simulate, Test Type, and Test Priority master-data
management.

One generic, slug-driven set of routes handles all of these tables
instead of duplicating near-identical CRUD code — see TABLES below. User
does NOT
extend this dict: it has an extra required `type` column and a
delete-block check spanning 12 (model, column) pairs across 4 models,
neither of which fits this dict's one-model-per-slug shape, so it gets
its own router (see app/routers/users.py).
"""

import json

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import redirect_with_flash
from app.models import Label, PrebuiltTestCase, Service, Simulate, TestCase, TestPriority, TestType, User, UserType
from app.routers.docx_export import _json_response
from app.templating import templates

router = APIRouter(prefix="/settings")

SETTINGS_SCHEMA_VERSION = 1

TABLES = {
    "services": {
        "model": Service, "label": "Service", "label_plural": "Services",
        "refs": [(PrebuiltTestCase, "service_id", "prebuilt template")],
    },
    "simulates": {
        "model": Simulate, "label": "Simulate Type", "label_plural": "Simulate Types",
        "refs": [(PrebuiltTestCase, "simulate_id", "prebuilt template")],
    },
    "test-types": {
        "model": TestType, "label": "Test Type", "label_plural": "Test Types",
        "refs": [
            (PrebuiltTestCase, "test_type_id", "prebuilt template"),
            (TestCase, "test_type_id", "test case"),
        ],
    },
    "test-priorities": {
        "model": TestPriority, "label": "Test Priority", "label_plural": "Test Priorities",
        "refs": [(TestCase, "test_priority_id", "test case")],
    },
}


def _export_settings_data(db: Session) -> dict:
    """One JSON-friendly dict covering every settings table — the 4 in
    TABLES plus Label and User, which live outside it (see module docstring)."""
    data: dict = {}
    for slug, cfg in TABLES.items():
        key = slug.replace("-", "_")
        rows = db.query(cfg["model"]).order_by(cfg["model"].name).all()
        data[key] = [row.name for row in rows]
    data["labels"] = [row.name for row in db.query(Label).order_by(Label.name).all()]
    data["users"] = [
        {"name": u.name, "type": u.type.value, "jira_username": u.jira_username}
        for u in db.query(User).order_by(User.name).all()
    ]
    return data


def _import_names(db: Session, model, names) -> int:
    """Adds each new (non-existing, non-blank) name to `model`; existing
    names are left untouched. Returns how many rows were added."""
    if not isinstance(names, list):
        return 0
    existing = {row.name for row in db.query(model).all()}
    added = 0
    for name in names:
        name = name.strip() if isinstance(name, str) else ""
        if name and name not in existing:
            db.add(model(name=name))
            existing.add(name)
            added += 1
    return added


def _import_users(db: Session, users_payload) -> int:
    if not isinstance(users_payload, list):
        return 0
    existing = {row.name for row in db.query(User).all()}
    added = 0
    for entry in users_payload:
        if not isinstance(entry, dict):
            continue
        name = (entry.get("name") or "").strip()
        if not name or name in existing:
            continue
        try:
            user_type = UserType(entry.get("type"))
        except ValueError:
            continue
        jira_username = (entry.get("jira_username") or "").strip() or None
        db.add(User(name=name, type=user_type, jira_username=jira_username))
        existing.add(name)
        added += 1
    return added


@router.get("/export")
def export_settings(db: Session = Depends(get_db)):
    payload = {"kind": "settings", "schema_version": SETTINGS_SCHEMA_VERSION, "settings": _export_settings_data(db)}
    return _json_response(payload, "qa-toolbox-settings.json")


@router.post("/import")
async def import_settings(file: UploadFile = File(...), db: Session = Depends(get_db)):
    try:
        data = json.loads(await file.read())
    except json.JSONDecodeError:
        return redirect_with_flash("/settings/services", "That file isn't valid JSON.", category="danger")
    if not isinstance(data, dict) or data.get("kind") != "settings" or not isinstance(data.get("settings"), dict):
        return redirect_with_flash(
            "/settings/services", "That file isn't a QA Toolbox settings export.", category="danger"
        )
    payload = data["settings"]
    added = 0
    for slug, cfg in TABLES.items():
        added += _import_names(db, cfg["model"], payload.get(slug.replace("-", "_")))
    added += _import_names(db, Label, payload.get("labels"))
    added += _import_users(db, payload.get("users"))
    db.commit()
    return redirect_with_flash(
        "/settings/services", f"Imported {added} row{'' if added == 1 else 's'} (existing names were skipped)."
    )


def _usage_counts(db: Session, cfg: dict) -> dict[int, int]:
    """Row id -> how many records across cfg['refs'] point at it, summed
    across every ref model (e.g. a Service referenced by both prebuilt
    templates and test cases counts both). One grouped query per ref."""
    counts: dict[int, int] = {}
    for ref_model, fk_column, _label in cfg["refs"]:
        column = getattr(ref_model, fk_column)
        rows = db.query(column, func.count(ref_model.id)).filter(column.isnot(None)).group_by(column).all()
        for row_id, count in rows:
            counts[row_id] = counts.get(row_id, 0) + count
    return counts


def _render_table(request: Request, slug: str, db: Session, error: str | None = None, status_code: int = 200):
    cfg = TABLES[slug]
    rows = db.query(cfg["model"]).order_by(cfg["model"].name).all()
    counts = _usage_counts(db, cfg)
    for row in rows:
        row.usage_count = counts.get(row.id, 0)
    return templates.TemplateResponse(
        request,
        "settings/table.html",
        {"slug": slug, "label": cfg["label"], "label_plural": cfg["label_plural"], "rows": rows, "error": error},
        status_code=status_code,
    )


@router.get("/")
def settings_index():
    return RedirectResponse(url="/settings/services", status_code=303)


@router.get("/{slug}")
def list_table(request: Request, slug: str, db: Session = Depends(get_db)):
    if slug not in TABLES:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return _render_table(request, slug, db)


@router.post("/{slug}")
def create_row(request: Request, slug: str, name: str = Form(...), db: Session = Depends(get_db)):
    if slug not in TABLES:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    cfg = TABLES[slug]
    name = name.strip()
    if not name:
        return _render_table(request, slug, db, error="Name is required.", status_code=422)
    if db.query(cfg["model"]).filter(cfg["model"].name == name).first():
        return _render_table(request, slug, db, error=f'"{name}" already exists.', status_code=422)
    db.add(cfg["model"](name=name))
    db.commit()
    return RedirectResponse(url=f"/settings/{slug}", status_code=303)


@router.post("/{slug}/{row_id}/edit")
def rename_row(request: Request, slug: str, row_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    if slug not in TABLES:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    cfg = TABLES[slug]
    row = db.get(cfg["model"], row_id)
    if row is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    name = name.strip()
    if not name:
        return _render_table(request, slug, db, error="Name is required.", status_code=422)
    conflict = db.query(cfg["model"]).filter(cfg["model"].name == name, cfg["model"].id != row_id).first()
    if conflict:
        return _render_table(request, slug, db, error=f'"{name}" already exists.', status_code=422)
    row.name = name
    db.commit()
    return RedirectResponse(url=f"/settings/{slug}", status_code=303)


@router.post("/{slug}/{row_id}/delete")
def delete_row(request: Request, slug: str, row_id: int, db: Session = Depends(get_db)):
    if slug not in TABLES:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    cfg = TABLES[slug]
    row = db.get(cfg["model"], row_id)
    if row is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    for ref_model, fk_column, ref_label in cfg["refs"]:
        count = db.query(func.count(ref_model.id)).filter(getattr(ref_model, fk_column) == row_id).scalar()
        if count:
            return _render_table(
                request, slug, db,
                error=f'"{row.name}" is still used by {count} {ref_label}{"" if count == 1 else "s"}.',
                status_code=422,
            )
    db.delete(row)
    db.commit()
    return RedirectResponse(url=f"/settings/{slug}", status_code=303)

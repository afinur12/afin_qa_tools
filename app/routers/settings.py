"""Settings: Service, Simulate, and Test Type master-data management.

One generic, slug-driven set of routes handles all three tables instead
of tripling near-identical CRUD code — see TABLES below. User does NOT
extend this dict: it has an extra required `type` column and a
delete-block check spanning 12 (model, column) pairs across 4 models,
neither of which fits this dict's one-model-per-slug shape, so it gets
its own router (see app/routers/users.py).
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PrebuiltTestCase, Service, Simulate, TestCase, TestType
from app.templating import templates

router = APIRouter(prefix="/settings")

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
}


def _render_table(request: Request, slug: str, db: Session, error: str | None = None, status_code: int = 200):
    cfg = TABLES[slug]
    rows = db.query(cfg["model"]).order_by(cfg["model"].name).all()
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

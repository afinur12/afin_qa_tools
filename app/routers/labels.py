"""Labels: a shared tag pool for Story/Subtask/TestCase/Bug, assigned
through the polymorphic LabelAssignment join (see app/labels.py).

Not folded into settings.py's generic TABLES-dict router: that router's
delete-block check assumes a scalar FK column on the referencing model
(getattr(ref_model, fk_column) == row_id); a Label is referenced through
the LabelAssignment join table instead, which needs a different count
query.
"""

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Label, LabelAssignment
from app.templating import templates

router = APIRouter()


def _render(request: Request, db: Session, error: str | None = None, status_code: int = 200):
    labels = db.query(Label).order_by(Label.name).all()
    return templates.TemplateResponse(
        request, "settings/labels.html", {"slug": "labels", "labels": labels, "error": error}, status_code=status_code,
    )


@router.get("/settings/labels")
def list_labels(request: Request, db: Session = Depends(get_db)):
    return _render(request, db)


@router.post("/settings/labels")
def create_label(request: Request, name: str = Form(...), db: Session = Depends(get_db)):
    name = name.strip()
    if not name:
        return _render(request, db, error="Name is required.", status_code=422)
    if db.query(Label).filter(Label.name == name).first():
        return _render(request, db, error=f'"{name}" already exists.', status_code=422)
    db.add(Label(name=name))
    db.commit()
    return RedirectResponse(url="/settings/labels", status_code=303)


@router.post("/settings/labels/{label_id}/edit")
def rename_label(request: Request, label_id: int, name: str = Form(...), db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if label is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    name = name.strip()
    if not name:
        return _render(request, db, error="Name is required.", status_code=422)
    conflict = db.query(Label).filter(Label.name == name, Label.id != label_id).first()
    if conflict:
        return _render(request, db, error=f'"{name}" already exists.', status_code=422)
    label.name = name
    db.commit()
    return RedirectResponse(url="/settings/labels", status_code=303)


@router.post("/settings/labels/{label_id}/delete")
def delete_label(request: Request, label_id: int, db: Session = Depends(get_db)):
    label = db.get(Label, label_id)
    if label is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    count = db.query(func.count(LabelAssignment.id)).filter(LabelAssignment.label_id == label_id).scalar()
    if count:
        return _render(request, db, error=f'"{label.name}" is still used by {count} item(s).', status_code=422)
    db.delete(label)
    db.commit()
    return RedirectResponse(url="/settings/labels", status_code=303)

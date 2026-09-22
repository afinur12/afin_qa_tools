"""Knowledge Base: standalone cards holding a markdown document each —
text, images, syntax-highlighted code. Unrelated to the Note model (the
small text box on Story/Subtask pages) despite the similar name; see the
design spec for why they're deliberately kept separate."""

from sqlalchemy import or_
from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from app.database import get_db
from app.labels import get_labels, set_labels
from app.models import Card, Label, LabelAssignment, LabelAttachType
from app.templating import templates

router = APIRouter()


@router.get("/knowledge-base")
def list_cards(request: Request, q: str = "", tag: str = "", db: Session = Depends(get_db)):
    query = db.query(Card)
    q = q.strip()
    if q:
        like = f"%{q}%"
        query = query.filter(or_(Card.title.ilike(like), Card.content_markdown.ilike(like)))
    tag = tag.strip()
    if tag.isdecimal():
        query = (
            query.join(
                LabelAssignment,
                (LabelAssignment.attach_type == LabelAttachType.CARD) & (LabelAssignment.attach_id == Card.id),
            )
            .filter(LabelAssignment.label_id == int(tag))
        )
    cards = query.order_by(Card.updated_at.desc()).all()
    card_labels = {card.id: get_labels(db, LabelAttachType.CARD, card.id) for card in cards}
    return templates.TemplateResponse(
        request,
        "knowledge_base/list.html",
        {
            "cards": cards,
            "card_labels": card_labels,
            "all_labels": db.query(Label).order_by(Label.name).all(),
            "q": q,
            "selected_tag": tag,
        },
    )


@router.post("/knowledge-base")
def create_card(db: Session = Depends(get_db)):
    card = Card(title="Untitled", content_markdown="")
    db.add(card)
    db.commit()
    db.refresh(card)
    return RedirectResponse(url=f"/knowledge-base/{card.id}", status_code=303)


# NOTE: card_detail (GET) and update_card (POST .../edit) below are the
# routes formally scoped to Task 2 of this plan (see
# .superpowers/sdd/2026-09-22-knowledge-base-cards/task-2-brief.md, whose
# Step 3 defines this exact code and whose Step 4 defines the full
# detail.html editor template). They're pulled forward into Task 1 because
# Task 1's own required test file (Step 1 of task-1-brief.md) already
# exercises both — the create-card test follows the create redirect to
# GET /knowledge-base/{id} expecting 200, and three of the five tests
# save a title/content/tags via POST .../edit before asserting on the
# list page. Without these two routes, Task 1's own tests cannot reach
# GREEN. The detail template below is a minimal, functional placeholder
# (not Task 2's full autosave/preview-toggle editor UI) — Task 2 is
# expected to overwrite app/templates/knowledge_base/detail.html with
# the richer version; this router code is otherwise identical to what
# Task 2 specifies, so Task 2 should find it already in place.
@router.get("/knowledge-base/{card_id}")
def card_detail(request: Request, card_id: int, db: Session = Depends(get_db)):
    card = db.get(Card, card_id)
    if card is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "knowledge_base/detail.html",
        {
            "card": card,
            "all_labels": db.query(Label).order_by(Label.name).all(),
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.CARD, card.id)],
        },
    )


@router.post("/knowledge-base/{card_id}/edit")
def update_card(
    card_id: int,
    title: str = Form("Untitled"),
    content_markdown: str = Form(""),
    label_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    card = db.get(Card, card_id)
    if card is None:
        return RedirectResponse(url="/knowledge-base", status_code=303)
    card.title = title.strip() or "Untitled"
    card.content_markdown = content_markdown
    set_labels(db, LabelAttachType.CARD, card.id, label_ids)
    db.commit()
    return RedirectResponse(url=f"/knowledge-base/{card.id}", status_code=303)

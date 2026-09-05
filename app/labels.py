"""Label helpers: get/set an entity's labels through the polymorphic
LabelAssignment join (app/models.py). Not a normal SQLAlchemy
relationship — a polymorphic (attach_type, attach_id) join isn't one
without extra primaryjoin wiring, and a plain query/insert/delete here
is simpler than that machinery for a two-function surface.
"""

from sqlalchemy.orm import Session

from app.models import Label, LabelAssignment, LabelAttachType


def get_labels(db: Session, attach_type: LabelAttachType, attach_id: int) -> list[Label]:
    return (
        db.query(Label)
        .join(LabelAssignment, LabelAssignment.label_id == Label.id)
        .filter(LabelAssignment.attach_type == attach_type, LabelAssignment.attach_id == attach_id)
        .order_by(Label.name)
        .all()
    )


def set_labels(db: Session, attach_type: LabelAttachType, attach_id: int, label_ids: list[int]) -> None:
    """Replace an entity's full label set in one call: delete every
    LabelAssignment row for this (attach_type, attach_id) not in
    label_ids, insert one for every id in label_ids not already
    present. Simpler and less error-prone than diffing individual
    add/remove calls — a form submit already sends the complete desired
    state as a list of checked checkboxes."""
    existing = (
        db.query(LabelAssignment)
        .filter(LabelAssignment.attach_type == attach_type, LabelAssignment.attach_id == attach_id)
        .all()
    )
    existing_ids = {row.label_id for row in existing}
    wanted_ids = set(label_ids)

    for row in existing:
        if row.label_id not in wanted_ids:
            db.delete(row)
    for label_id in wanted_ids - existing_ids:
        db.add(LabelAssignment(label_id=label_id, attach_type=attach_type, attach_id=attach_id))


def clear_labels(db: Session, attach_type: LabelAttachType, attach_id: int) -> None:
    """Remove every LabelAssignment row for one entity. Call this as part of
    permanently deleting a Story/Subtask/TestCase/Bug (or a child removed via
    a parent's cascade) — otherwise a deleted entity's label rows linger
    forever: they key on (attach_type, attach_id) with no FK constraint, so
    nothing else ever clears them, which both makes an assigned Label
    permanently undeletable and lets a future entity that reuses the same id
    silently inherit the old label chips."""
    set_labels(db, attach_type, attach_id, [])

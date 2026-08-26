"""Note Section: freeform snippets (curl, SQL, JSON, or any other text)
attached to a story or subtask, stored verbatim — nothing is executed."""

from fastapi import APIRouter, Depends, Form, Request
from sqlalchemy.orm import Session

from app.database import get_db
from app.flash import redirect_with_flash
from app.models import Note, NoteAttachType

router = APIRouter()


def _redirect_target(attach_type: NoteAttachType, attach_id: int) -> str:
    if attach_type == NoteAttachType.STORY:
        return f"/stories/{attach_id}"
    return f"/subtasks/{attach_id}"


@router.post("/notes")
def create_note(
    request: Request,
    attach_type: str = Form(...),
    attach_id: int = Form(...),
    language: str = Form("TEXT"),
    content: str = Form(...),
    remark: str = Form(""),
    db: Session = Depends(get_db),
):
    attach_type_enum = NoteAttachType(attach_type)
    db.add(
        Note(
            attach_type=attach_type_enum, attach_id=attach_id,
            language=language.strip() or "TEXT", content=content, remark=remark.strip() or None,
        )
    )
    db.commit()
    return redirect_with_flash(_redirect_target(attach_type_enum, attach_id), "Note added.")


@router.post("/notes/{note_id}/delete")
def delete_note(
    request: Request,
    note_id: int,
    attach_type: str = Form(...),
    attach_id: int = Form(...),
    db: Session = Depends(get_db),
):
    note = db.get(Note, note_id)
    if note is not None:
        db.delete(note)
        db.commit()
    return redirect_with_flash(
        _redirect_target(NoteAttachType(attach_type), attach_id), "Note deleted.", category="danger"
    )

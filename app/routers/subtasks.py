import json
import re

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile
from fastapi.responses import RedirectResponse, Response
from sqlalchemy import case, exists, func
from sqlalchemy.orm import Session, selectinload

from app import deletion
from app.database import get_db
from app.flash import redirect_with_flash
from app.templating import templates
from app.models import LabelAttachType, Note, NoteAttachType, Phase, PhaseType, PrebuiltTestCase, Screenshot, Subtask, SubtaskType, TaskStatus, TestCase, TestCaseSection, TestCaseStep, TestCaseStepData, generate_internal_key
from app.labels import get_labels, set_labels
from app.models import KnowledgeLinkTarget
from app.routers.knowledge import knowledge_card_context
from app.routers.stories import _parse_id, _user_dropdowns
from app.testcase_io import dict_to_subtask

router = APIRouter()


def _allowed_subtask_types(phase: Phase) -> list[SubtaskType]:
    return phase.allowed_subtask_types


def _next_subtask_position(phase: Phase) -> int:
    return max((subtask.position for subtask in phase.subtasks), default=-1) + 1


@router.get("/phases/{phase_id}/subtasks/new")
def new_subtask_form(request: Request, phase_id: int, db: Session = Depends(get_db)):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "subtasks/form.html",
        {
            "subtask": None,
            "phase": phase,
            "allowed_types": _allowed_subtask_types(phase),
            "error": None,
            "values": {
                "display_code": "", "title": "", "subtask_type": "",
                "assignee_id": "", "tester_id": "", "developer_id": "",
            },
            "current_label_ids": [],
            **_user_dropdowns(db),
        },
    )


@router.post("/phases/{phase_id}/subtasks")
def create_subtask(
    request: Request,
    phase_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    subtask_type: str = Form(...),
    assignee_id: str = Form(""),
    tester_id: str = Form(""),
    developer_id: str = Form(""),
    label_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    allowed = _allowed_subtask_types(phase)
    try:
        st_type = SubtaskType(subtask_type)
    except ValueError:
        st_type = None

    error = None
    if st_type is None or st_type not in allowed:
        error = "That subtask type isn't allowed for this phase."
    elif db.query(Subtask).filter(Subtask.phase_id == phase.id, Subtask.display_code == display_code).first():
        error = f'Code "{display_code}" is already used in this phase.'

    if error:
        return templates.TemplateResponse(
            request,
            "subtasks/form.html",
            {
                "subtask": None,
                "phase": phase,
                "allowed_types": allowed,
                "error": error,
                "values": {
                    "display_code": display_code, "title": title, "subtask_type": subtask_type,
                    "assignee_id": assignee_id, "tester_id": tester_id, "developer_id": developer_id,
                },
                "current_label_ids": label_ids,
                **_user_dropdowns(db),
            },
            status_code=422,
        )

    subtask = Subtask(
        phase_id=phase.id,
        display_code=display_code,
        title=title,
        internal_key=generate_internal_key(),
        subtask_type=st_type,
        position=_next_subtask_position(phase),
        assignee_id=_parse_id(assignee_id), tester_id=_parse_id(tester_id), developer_id=_parse_id(developer_id),
    )
    db.add(subtask)
    db.flush()
    set_labels(db, LabelAttachType.SUBTASK, subtask.id, label_ids)
    db.commit()
    db.refresh(subtask)
    return redirect_with_flash(f"/subtasks/{subtask.id}", f"Subtask {subtask.display_code} created.")


@router.post("/phases/{phase_id}/subtasks/reorder")
def reorder_subtasks(request: Request, phase_id: int, order: str = Form(...), db: Session = Depends(get_db)):
    """Persist a new subtask order within a phase.

    ``order`` is a comma-separated list of subtask ids in their new order.
    Ids that don't belong to this phase are rejected outright rather than
    partially applied.
    """
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

    by_id = {subtask.id: subtask for subtask in phase.subtasks}
    try:
        requested = [int(value) for value in order.split(",") if value.strip()]
    except ValueError:
        return Response("Invalid subtask order.", status_code=422)

    if sorted(requested) != sorted(by_id):
        return Response("Subtask order does not match this phase.", status_code=422)

    for position, subtask_id in enumerate(requested):
        by_id[subtask_id].position = position
    db.commit()
    return RedirectResponse(url=f"/stories/{phase.story_id}", status_code=303)


@router.post("/phases/{phase_id}/subtasks/import")
async def import_subtask(request: Request, phase_id: int, file: UploadFile = File(...), db: Session = Depends(get_db)):
    phase = db.get(Phase, phase_id)
    if phase is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    try:
        data = json.loads(await file.read())
    except json.JSONDecodeError:
        return redirect_with_flash(f"/stories/{phase.story_id}", "That file isn't valid JSON.", category="danger")
    try:
        subtask = dict_to_subtask(db, phase_id, data)
    except ValueError as exc:
        db.rollback()
        return redirect_with_flash(f"/stories/{phase.story_id}", str(exc), category="danger")
    db.commit()
    return redirect_with_flash(f"/subtasks/{subtask.id}", f"Subtask {subtask.display_code} imported.")


def _screenshot_coverage(db: Session, testcase_ids: list[int]) -> dict[int, tuple[int, int]]:
    """testcase_id -> (steps, steps with at least one screenshot), in one
    query for the whole table. A test case with no steps is absent here and
    reads as (0, 0) — shown as incomplete."""
    if not testcase_ids:
        return {}
    has_shot = exists().where(Screenshot.step_id == TestCaseStep.id)
    rows = (
        db.query(TestCaseSection.testcase_id, func.count(TestCaseStep.id), func.sum(case((has_shot, 1), else_=0)))
        .join(TestCaseStep, TestCaseStep.section_id == TestCaseSection.id)
        .filter(TestCaseSection.testcase_id.in_(testcase_ids))
        .group_by(TestCaseSection.testcase_id)
        .all()
    )
    return {tc_id: (int(total), int(with_shot or 0)) for tc_id, total, with_shot in rows}


# A step that checks the state *after* the run (e.g. "check balance after")
# mirrors a "before" step that already carries the Test Data.
AFTER_STEP = re.compile(r"\bafter\b", re.IGNORECASE)


def needs_test_data(step_text: str | None) -> bool:
    """Every step needs Test Data, except one whose text has the word "after"."""
    return not AFTER_STEP.search(step_text or "")


def _test_data_coverage(db: Session, testcase_ids: list[int]) -> dict[int, tuple[int, int, int, int]]:
    """testcase_id -> (steps needing Test Data, how many of those have it,
    "after" steps not counted, all steps), in one query for the whole table.
    A step has Test Data when one of its items has a non-blank value. A test
    case with no steps is absent here (reads as all zeros: incomplete)."""
    if not testcase_ids:
        return {}
    has_data = exists().where(
        TestCaseStepData.step_id == TestCaseStep.id,
        func.trim(func.coalesce(TestCaseStepData.value, "")) != "",
    )
    rows = (
        db.query(TestCaseSection.testcase_id, TestCaseStep.step_text, case((has_data, 1), else_=0))
        .join(TestCaseStep, TestCaseStep.section_id == TestCaseSection.id)
        .filter(TestCaseSection.testcase_id.in_(testcase_ids))
        .all()
    )
    coverage: dict[int, tuple[int, int, int, int]] = {}
    for testcase_id, step_text, with_data in rows:
        needed, have, exempt, total = coverage.get(testcase_id, (0, 0, 0, 0))
        if needs_test_data(step_text):
            needed, have = needed + 1, have + (1 if with_data else 0)
        else:
            exempt += 1
        coverage[testcase_id] = (needed, have, exempt, total + 1)
    return coverage


@router.get("/subtasks/{subtask_id}")
def subtask_detail(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(
        Subtask, subtask_id,
        options=[
            selectinload(Subtask.testcases).selectinload(TestCase.test_priority_ref),
            selectinload(Subtask.testcases).selectinload(TestCase.test_type_ref),
        ],
    )
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    notes = db.query(Note).filter(
        Note.attach_type == NoteAttachType.SUBTASK, Note.attach_id == subtask_id
    ).all()
    prebuilts = db.query(PrebuiltTestCase).order_by(PrebuiltTestCase.name).all()
    # A test case is flagged "in Prebuilt" when some prebuilt's name is
    # exactly its title (case-sensitive; surrounding spaces ignored). With
    # several same-named prebuilts the badge links to the oldest one.
    prebuilt_id_by_name: dict[str, int] = {}
    for p in sorted(prebuilts, key=lambda p: p.id):
        prebuilt_id_by_name.setdefault((p.name or "").strip(), p.id)
    prebuilt_id_by_testcase_id = {
        tc.id: prebuilt_id_by_name[title]
        for tc in subtask.testcases
        if (title := (tc.title or "").strip()) in prebuilt_id_by_name
    }
    return templates.TemplateResponse(
        request,
        "subtasks/detail.html",
        {
            "subtask": subtask, "error": None, "notes": notes,
            "prebuilts": prebuilts,
            "prebuilt_id_by_testcase_id": prebuilt_id_by_testcase_id,
            "screenshot_coverage": _screenshot_coverage(db, [tc.id for tc in subtask.testcases]),
            "test_data_coverage": _test_data_coverage(db, [tc.id for tc in subtask.testcases]),
            "statuses": list(TaskStatus),
            "subtask_labels": get_labels(db, LabelAttachType.SUBTASK, subtask_id),
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.SUBTASK, subtask_id)],
            **_user_dropdowns(db),
            **knowledge_card_context(db, KnowledgeLinkTarget.SUBTASK, subtask_id),
        },
    )


@router.get("/subtasks/{subtask_id}/edit")
def edit_subtask_form(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    return templates.TemplateResponse(
        request,
        "subtasks/form.html",
        {
            "subtask": subtask,
            "phase": subtask.phase,
            "allowed_types": _allowed_subtask_types(subtask.phase) or [subtask.subtask_type],
            "error": None,
            "statuses": list(TaskStatus),
            "values": {
                "display_code": subtask.display_code,
                "title": subtask.title,
                "subtask_type": subtask.subtask_type.value,
                "notes": subtask.notes or "",
                "status": subtask.status.value,
                "assignee_id": str(subtask.assignee_id or ""), "tester_id": str(subtask.tester_id or ""),
                "developer_id": str(subtask.developer_id or ""),
            },
            "current_label_ids": [l.id for l in get_labels(db, LabelAttachType.SUBTASK, subtask_id)],
            **_user_dropdowns(db),
        },
    )


@router.post("/subtasks/{subtask_id}/edit")
def update_subtask(
    request: Request,
    subtask_id: int,
    display_code: str = Form(...),
    title: str = Form(...),
    notes: str = Form(""),
    status: str = Form(...),
    assignee_id: str = Form(""),
    tester_id: str = Form(""),
    developer_id: str = Form(""),
    label_ids: list[int] = Form([]),
    db: Session = Depends(get_db),
):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    display_code = display_code.strip()
    title = title.strip()
    conflict = (
        db.query(Subtask)
        .filter(Subtask.phase_id == subtask.phase_id, Subtask.display_code == display_code, Subtask.id != subtask_id)
        .first()
    )
    try:
        status_enum = TaskStatus(status)
    except ValueError:
        conflict = True  # reuse the same error branch below for any invalid enum value

    if conflict:
        return templates.TemplateResponse(
            request,
            "subtasks/form.html",
            {
                "subtask": subtask,
                "phase": subtask.phase,
                "allowed_types": [subtask.subtask_type],
                "error": f'Code "{display_code}" is already used in this phase, or the status was invalid.',
                "values": {
                    "display_code": display_code, "title": title, "subtask_type": subtask.subtask_type.value,
                    "notes": notes, "status": status,
                    "assignee_id": assignee_id, "tester_id": tester_id, "developer_id": developer_id,
                },
                "current_label_ids": label_ids,
                **_user_dropdowns(db),
            },
            status_code=422,
        )
    subtask.display_code = display_code
    subtask.title = title
    subtask.notes = notes
    subtask.status = status_enum
    subtask.assignee_id = _parse_id(assignee_id)
    subtask.tester_id = _parse_id(tester_id)
    subtask.developer_id = _parse_id(developer_id)
    set_labels(db, LabelAttachType.SUBTASK, subtask.id, label_ids)
    db.commit()
    return redirect_with_flash(f"/subtasks/{subtask.id}", f"Subtask {subtask.display_code} updated.")


@router.post("/subtasks/{subtask_id}/delete")
def delete_subtask(request: Request, subtask_id: int, db: Session = Depends(get_db)):
    subtask = db.get(Subtask, subtask_id)
    if subtask is None:
        return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)
    story_id = subtask.phase.story_id
    code = subtask.display_code
    # Cascades to its test cases (and their steps/screenshots) and bugs, so
    # the subtask can be removed without emptying it first.
    deletion.delete_subtask(db, subtask)
    db.commit()
    return redirect_with_flash(f"/stories/{story_id}", f"Subtask {code} deleted.", category="danger")

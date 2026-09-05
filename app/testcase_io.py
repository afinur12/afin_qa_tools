"""Task / Subtask / Test Case <-> JSON, for the export/import feature.

One shape reused at three nesting depths: a testcase dict embeds directly
into a subtask dict's "testcases" list, which embeds directly into a task
dict's "phases[].subtasks" list. No id-ref indirection is needed (unlike the
API Client's self-referencing folder tree in app/routers/api_client.py) since
Phase -> Subtask -> TestCase -> Section -> Step has no recursion.

Every dict_to_* raises a plain ValueError with a human-readable message on a
wrong "kind", an unknown enum value, or a missing required field — callers
(the import routes) catch this and turn it into a flashed error instead of a
500, the same way app.routers.api_client.import_collection already handles a
malformed upload.
"""

import base64
import mimetypes
import uuid
from pathlib import Path

from sqlalchemy.orm import Session

from app.master_data import get_or_create
from app.models import (
    Bug,
    BugSeverity,
    BugStatus,
    Phase,
    PhaseType,
    Screenshot,
    Story,
    StepSection,
    Subtask,
    SubtaskType,
    TaskStatus,
    TestCase,
    TestCaseSection,
    TestCaseStatus,
    TestCaseStep,
    TestPriority,
    TestType,
    User,
    UserType,
    generate_internal_key,
)

SCHEMA_VERSION = 1
UPLOADS_DIR = Path("app/uploads")


def _unique_code(db: Session, model, base_code: str, **scope_filters) -> str:
    """base_code, or base_code with " (2)", " (3)", ... appended until no row
    in `model` matching scope_filters (plus display_code) exists. Generalizes
    api_client.py's _unique_collection_name to any (model, scope) pair."""
    candidate = base_code
    n = 2
    while db.query(model).filter_by(display_code=candidate, **scope_filters).first():
        candidate = f"{base_code} ({n})"
        n += 1
    return candidate


# ── Export: model -> dict ───────────────────────────────────────────────

def _screenshot_to_dict(screenshot: Screenshot) -> dict | None:
    disk_path = UPLOADS_DIR / screenshot.file_path
    if not disk_path.exists():
        return None
    content_type = mimetypes.guess_type(disk_path.name)[0] or "application/octet-stream"
    return {
        "filename": disk_path.name,
        "content_type": content_type,
        "data_base64": base64.b64encode(disk_path.read_bytes()).decode("ascii"),
    }


def testcase_to_dict(tc: TestCase, include_screenshots: bool = False) -> dict:
    return {
        "kind": "testcase",
        "schema_version": SCHEMA_VERSION,
        "testcase": _testcase_fields(tc, include_screenshots),
    }


def _testcase_fields(tc: TestCase, include_screenshots: bool) -> dict:
    return {
        "display_code": tc.display_code,
        "title": tc.title,
        "status": tc.status.value,
        "tester": tc.tester_user.name if tc.tester_user else None,
        "test_date": tc.test_date,
        "test_priority": tc.test_priority_ref.name if tc.test_priority_ref else None,
        "test_type": tc.test_type_ref.name if tc.test_type_ref else None,
        "channel": tc.channel,
        "iteration": tc.iteration,
        "balance_before": tc.balance_before,
        "balance_after": tc.balance_after,
        "usage": tc.usage,
        "remark": tc.remark,
        "data_test": tc.data_test,
        "sections": [
            {
                "kind": section.kind.value,
                "position": section.position,
                "steps": [
                    {
                        "step_no": step.step_no,
                        "step_text": step.step_text,
                        "expected_result": step.expected_result,
                        "actual_result": step.actual_result,
                        **(
                            {"screenshots": [s for s in (_screenshot_to_dict(shot) for shot in step.screenshots) if s]}
                            if include_screenshots
                            else {}
                        ),
                    }
                    for step in section.steps
                ],
            }
            for section in tc.sections
        ],
    }


def subtask_to_dict(subtask: Subtask, include_screenshots: bool = False) -> dict:
    return {
        "kind": "subtask",
        "schema_version": SCHEMA_VERSION,
        "subtask": _subtask_fields(subtask, include_screenshots),
    }


def testcases_to_dict(testcases: list[TestCase], include_screenshots: bool = False) -> dict:
    """A selected subset of test cases (e.g. checkbox-picked in the UI), as
    opposed to testcase_to_dict (one) or subtask_to_dict (all, plus bugs)."""
    return {
        "kind": "testcases",
        "schema_version": SCHEMA_VERSION,
        "testcases": [_testcase_fields(tc, include_screenshots) for tc in testcases],
    }


def _bug_fields(bug: Bug) -> dict:
    return {
        "display_code": bug.display_code,
        "title": bug.title,
        "description": bug.description,
        "severity": bug.severity.value,
        "status": bug.status.value,
    }


def _subtask_fields(subtask: Subtask, include_screenshots: bool) -> dict:
    return {
        "display_code": subtask.display_code,
        "title": subtask.title,
        "subtask_type": subtask.subtask_type.value,
        "notes": subtask.notes,
        "status": subtask.status.value,
        "testcases": [_testcase_fields(tc, include_screenshots) for tc in subtask.testcases],
        "bugs": [_bug_fields(bug) for bug in subtask.bugs],
    }


def task_to_dict(story: Story, include_screenshots: bool = False) -> dict:
    return {
        "kind": "task",
        "schema_version": SCHEMA_VERSION,
        "task": {
            "display_code": story.display_code,
            "title": story.title,
            "status": story.status.value,
            "phases": [
                {
                    "type": phase.type.value,
                    "subtasks": [_subtask_fields(st, include_screenshots) for st in phase.subtasks],
                }
                for phase in story.phases
            ],
        },
    }


# ── Import: dict -> model ───────────────────────────────────────────────

def _require(data: dict, key: str, label: str):
    value = data.get(key)
    if value in (None, ""):
        raise ValueError(f'Missing required field "{key}" on {label}.')
    return value


def _parse_enum(enum_cls, raw: str, label: str):
    try:
        return enum_cls(raw)
    except ValueError:
        valid = ", ".join(e.value for e in enum_cls)
        raise ValueError(f'Unknown {label} "{raw}" — expected one of: {valid}.')


def _write_screenshot(testcase_id: int, step_id: int, shot: dict) -> Screenshot:
    try:
        raw = base64.b64decode(shot["data_base64"], validate=True)
    except Exception as exc:
        raise ValueError(f"Couldn't decode screenshot data: {exc}")
    extension = Path(shot.get("filename", "")).suffix or mimetypes.guess_extension(shot.get("content_type", "")) or ".bin"
    filename = f"{uuid.uuid4().hex}{extension}"
    relative_path = f"screenshots/{testcase_id}/{step_id}/{filename}"
    disk_path = UPLOADS_DIR / relative_path
    disk_path.parent.mkdir(parents=True, exist_ok=True)
    disk_path.write_bytes(raw)
    return Screenshot(step_id=step_id, file_path=relative_path)


def extract_testcase_candidates(data: dict) -> list[dict]:
    """Pull a list of raw testcase field-dicts out of an uploaded file for the
    import-preview flow, regardless of which export shape it came from: a
    single testcase, a "testcases" list (testcases_to_dict), or a whole
    subtask export (only its nested testcases — bugs/notes/etc are ignored,
    this flow is testcase-only). Each dict is exactly what dict_to_testcase
    expects under a {"kind": "testcase", "testcase": ...} wrapper."""
    kind = data.get("kind")
    if kind == "testcase":
        fields = data.get("testcase")
        if not isinstance(fields, dict):
            raise ValueError('Missing "testcase" object.')
        return [fields]
    if kind == "testcases":
        items = data.get("testcases")
        if not isinstance(items, list):
            raise ValueError('Missing "testcases" list.')
        return items
    if kind == "subtask":
        fields = data.get("subtask")
        if not isinstance(fields, dict):
            raise ValueError('Missing "subtask" object.')
        return fields.get("testcases") or []
    raise ValueError(f'Unsupported file kind "{kind}" for test case import — expected "testcase", "testcases", or "subtask".')


def dict_to_testcase(db: Session, subtask_id: int, data: dict) -> TestCase:
    if data.get("kind") != "testcase":
        raise ValueError('Expected a test case export (kind: "testcase").')
    fields = data.get("testcase")
    if not isinstance(fields, dict):
        raise ValueError('Missing "testcase" object.')

    display_code = _unique_code(db, TestCase, _require(fields, "display_code", "test case"), subtask_id=subtask_id)
    title = _require(fields, "title", "test case")
    status = _parse_enum(TestCaseStatus, fields.get("status") or TestCaseStatus.TO_DO.value, "test case status")
    test_type_row = get_or_create(db, TestType, fields.get("test_type"))
    test_priority_row = get_or_create(db, TestPriority, fields.get("test_priority"))
    tester_row = get_or_create(db, User, fields.get("tester"), type=UserType.TESTER)

    testcase = TestCase(
        subtask_id=subtask_id, display_code=display_code, title=title, internal_key=generate_internal_key(),
        status=status,
        tester_id=tester_row.id if tester_row else None,
        test_date=fields.get("test_date"),
        test_priority=fields.get("test_priority"), test_priority_id=test_priority_row.id if test_priority_row else None,
        test_type=fields.get("test_type"), test_type_id=test_type_row.id if test_type_row else None,
        channel=fields.get("channel"),
        iteration=fields.get("iteration") or "1",
        balance_before=fields.get("balance_before") or "Rp. -",
        balance_after=fields.get("balance_after") or "Rp. -",
        usage=fields.get("usage") or "Rp. -",
        remark=fields.get("remark"), data_test=fields.get("data_test"),
    )
    db.add(testcase)
    db.flush()

    for section_data in fields.get("sections") or []:
        section_kind = _parse_enum(StepSection, _require(section_data, "kind", "section"), "section kind")
        section = TestCaseSection(
            testcase_id=testcase.id, kind=section_kind, position=int(section_data.get("position") or 0),
        )
        db.add(section)
        db.flush()
        for step_data in section_data.get("steps") or []:
            step = TestCaseStep(
                section_id=section.id, step_no=int(step_data.get("step_no") or 1),
                step_text=step_data.get("step_text") or "", expected_result=step_data.get("expected_result") or "",
                actual_result=step_data.get("actual_result") or "",
            )
            db.add(step)
            db.flush()
            for shot_data in step_data.get("screenshots") or []:
                db.add(_write_screenshot(testcase.id, step.id, shot_data))

    return testcase


def dict_to_subtask(db: Session, phase_id: int, data: dict) -> Subtask:
    if data.get("kind") != "subtask":
        raise ValueError('Expected a subtask export (kind: "subtask").')
    fields = data.get("subtask")
    if not isinstance(fields, dict):
        raise ValueError('Missing "subtask" object.')

    phase = db.get(Phase, phase_id)
    if phase is None:
        raise ValueError("Target phase no longer exists.")

    subtask_type = _parse_enum(SubtaskType, _require(fields, "subtask_type", "subtask"), "subtask type")
    if subtask_type not in phase.allowed_subtask_types:
        raise ValueError(f'Subtask type "{subtask_type.value}" isn\'t allowed on a {phase.type.value} phase.')

    status = _parse_enum(TaskStatus, fields.get("status") or TaskStatus.TO_DO.value, "subtask status")
    display_code = _unique_code(db, Subtask, _require(fields, "display_code", "subtask"), phase_id=phase_id)
    subtask = Subtask(
        phase_id=phase_id, display_code=display_code, title=_require(fields, "title", "subtask"),
        internal_key=generate_internal_key(), subtask_type=subtask_type, notes=fields.get("notes"),
        status=status,
    )
    db.add(subtask)
    db.flush()

    for tc_data in fields.get("testcases") or []:
        dict_to_testcase(db, subtask.id, {"kind": "testcase", "testcase": tc_data})

    for bug_data in fields.get("bugs") or []:
        _dict_to_bug(db, subtask.id, bug_data)

    return subtask


def _dict_to_bug(db: Session, subtask_id: int, data: dict) -> Bug:
    display_code = _unique_code(db, Bug, _require(data, "display_code", "bug"), subtask_id=subtask_id)
    severity = _parse_enum(BugSeverity, data.get("severity") or BugSeverity.MEDIUM.value, "bug severity")
    status = _parse_enum(BugStatus, data.get("status") or BugStatus.OPEN.value, "bug status")
    bug = Bug(
        subtask_id=subtask_id, display_code=display_code, title=_require(data, "title", "bug"),
        internal_key=generate_internal_key(), description=data.get("description") or "",
        severity=severity, status=status,
    )
    db.add(bug)
    db.flush()
    return bug


def dict_to_task(db: Session, data: dict) -> Story:
    if data.get("kind") != "task":
        raise ValueError('Expected a task export (kind: "task").')
    fields = data.get("task")
    if not isinstance(fields, dict):
        raise ValueError('Missing "task" object.')

    phases_data = fields.get("phases") or []
    seen_types: set[str] = set()
    for phase_data in phases_data:
        raw_type = _require(phase_data, "type", "phase")
        if raw_type in seen_types:
            raise ValueError(f'Duplicate phase type "{raw_type}" in import file — a task can only have one of each.')
        seen_types.add(raw_type)

    status = _parse_enum(TaskStatus, fields.get("status") or TaskStatus.TO_DO.value, "task status")
    display_code = _unique_code(db, Story, _require(fields, "display_code", "task"))
    story = Story(
        display_code=display_code, title=_require(fields, "title", "task"),
        internal_key=generate_internal_key(), status=status,
    )
    db.add(story)
    db.flush()

    for phase_data in phases_data:
        phase_type = _parse_enum(PhaseType, phase_data["type"], "phase type")
        phase = Phase(story_id=story.id, type=phase_type)
        db.add(phase)
        db.flush()
        for subtask_data in phase_data.get("subtasks") or []:
            dict_to_subtask(db, phase.id, {"kind": "subtask", "subtask": subtask_data})

    return story

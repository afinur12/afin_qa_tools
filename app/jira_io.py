"""Subtask + Test Cases <-> Jira/Zephyr-shaped JSON, for the Jira Sync
feature.

Distinct from app/testcase_io.py: that module round-trips this app's own
internal schema (used for QA-Toolbox-to-QA-Toolbox transfer/backup). This
module's shapes match Jira/Zephyr fields instead, so a Subtask's test
cases can be synced with a real Jira workspace via an external tool
("CodeBuddy") that reads/writes these same JSON shapes — this app never
calls a Jira or Zephyr API itself.

Every field this app has no real value for is exported as the literal
string "{{placeholder_<name>}}" (matching update-template.json's own
placeholder names exactly), so CodeBuddy's existing "contains
{{placeholder" skip-detection (see field-mapping-update.md) works
unchanged on this app's output. The same string is how import direction
(see the bottom of this file) recognizes "nothing real here — don't
overwrite the existing value".
"""

import re

from sqlalchemy.orm import Session

from app import deletion
from app.labels import get_labels, set_labels
from app.master_data import get_or_create
from app.models import (
    DEFAULT_SECTION_KINDS, Label, LabelAttachType, StepSection, Subtask, TestCase,
    TestCaseCategory, TestCaseSection, TestCaseStatus, TestCaseStep, User, UserType,
    generate_internal_key,
)

_SECTION_LABEL = {
    StepSection.PRECONDITION: "PRE CONDITION",
    StepSection.MAIN: "MAIN TEST",
    StepSection.POSTCONDITION: "POST CONDITION",
}
_SECTION_ORDER_ID = {
    StepSection.PRECONDITION: 1,
    StepSection.MAIN: 2,
    StepSection.POSTCONDITION: 3,
}
_STATUS_TO_JIRA = {
    TestCaseStatus.PASS: "PASS",
    TestCaseStatus.FAIL: "FAIL",
    TestCaseStatus.IN_PROGRESS: "WIP",
    TestCaseStatus.BLOCKED: "BLOCKED",
    TestCaseStatus.TO_DO: "UNEXECUTED",
    TestCaseStatus.BACK_LOG: "UNEXECUTED",
    TestCaseStatus.CANCELLED: "UNEXECUTED",
    TestCaseStatus.POSTPONED: "UNEXECUTED",
}
_JIRA_TO_STATUS = {
    "PASS": TestCaseStatus.PASS,
    "FAIL": TestCaseStatus.FAIL,
    "WIP": TestCaseStatus.IN_PROGRESS,
    "BLOCKED": TestCaseStatus.BLOCKED,
    "UNEXECUTED": TestCaseStatus.TO_DO,
}


def _placeholder(field_name: str) -> str:
    return "{{placeholder_" + field_name + "}}"


def _is_placeholder(value) -> bool:
    return isinstance(value, str) and "{{placeholder" in value


def _numbered_block(lines: list[str]) -> str:
    return "\r\n".join(f"{i}. {text}" for i, text in enumerate(lines, start=1))


def _person(user: "User | None", field: str) -> dict:
    """Always an object — never null — matching the reference template's
    shape for assignee/developer/tester exactly (each is `{name, username}`
    with placeholder markers standing in for whatever this app has no real
    value for, same as every other field in this export)."""
    if user is None:
        return {"name": _placeholder(f"{field}_display_name"), "username": _placeholder(f"{field}_username")}
    return {"name": user.name, "username": user.jira_username or _placeholder(f"{field}_username")}


# Jira's data model has exactly one Pre/Main/Post section each, unlike this
# app where a TestCase can hold multiple sections of the same `kind` (see
# TestCaseSection's own docstring in app/models.py). So Jira Sync — in both
# directions — only ever looks at the FIRST section of each kind, in
# testcase.sections' existing position order. Any additional section of a
# kind already seen is local-only: never exported, never touched on import.
def _zephyr_entry(section: "TestCaseSection") -> dict:
    label = _SECTION_LABEL[section.kind]
    steps = section.steps
    if steps:
        step_text = label + "\r\n" + _numbered_block([s.step_text for s in steps])
        expected_text = _numbered_block([s.expected_result for s in steps])
    else:
        key = section.kind.value.lower()
        step_text = _placeholder(f"{key}_step")
        expected_text = _placeholder(f"{key}_expected")
    return {
        "order_id": _SECTION_ORDER_ID[section.kind],
        "step_type": label,
        "step": step_text,
        "expected_result": expected_text,
    }


def _first_section_per_kind(sections: list["TestCaseSection"]) -> list["TestCaseSection"]:
    """First section of each kind, in position order — see the comment above
    _zephyr_entry for why repeats beyond the first are excluded."""
    seen = set()
    result = []
    for section in sections:
        if section.kind in seen:
            continue
        seen.add(section.kind)
        result.append(section)
    return result


def testcase_to_jira_dict(testcase: "TestCase", db: Session) -> dict:
    labels = [l.name for l in get_labels(db, LabelAttachType.TESTCASE, testcase.id)]
    return {
        "issue_key": testcase.display_code,
        "summary": testcase.title,
        "category": testcase.category.value if testcase.category else _placeholder("category"),
        "planned_cost": testcase.planned_cost or _placeholder("planned_cost_value"),
        "actual_cost": testcase.actual_cost or _placeholder("actual_cost_value"),
        "number_of_iteration": (
            testcase.number_of_iteration if testcase.number_of_iteration is not None
            else _placeholder("number_of_iteration_value")
        ),
        "msisdn": testcase.msisdn or _placeholder("msisdn_value"),
        "assignee": _person(testcase.assignee, "assignee"),
        "developer": _person(testcase.developer, "developer"),
        "tester": _person(testcase.tester_user, "tester"),
        "zephyr_steps": [_zephyr_entry(section) for section in _first_section_per_kind(testcase.sections)],
        "execution": {
            "execution_id": testcase.jira_execution_id or _placeholder("execution_id_numeric_or_placeholder"),
            "status": _STATUS_TO_JIRA[testcase.status],
            "executed_on": None,
            "executed_by": None,
            "cycle_name": testcase.subtask.title,
        },
        "fields": {
            "description": testcase.remark or _placeholder("description_text_or_placeholder"),
            "priority": {"name": testcase.test_priority or _placeholder("priority_name")},
            "labels": labels,
        },
    }


def subtask_to_jira_json(subtask: "Subtask", db: Session) -> dict:
    test_cases = [testcase_to_jira_dict(tc, db) for tc in subtask.testcases]
    return {
        "parent_ticket": subtask.display_code,
        "test_suite": subtask.title,
        "total_test_cases": len(test_cases),
        "parent_ticket_info": {
            "assignee": _person(subtask.assignee, "assignee"),
            "developer": _person(subtask.developer, "developer"),
            "tester": _person(subtask.tester_user, "tester"),
            "labels": [l.name for l in get_labels(db, LabelAttachType.SUBTASK, subtask.id)],
        },
        "test_cases": test_cases,
    }


# ── Import: Jira JSON -> model ──────────────────────────────────────────


def _split_numbered_block(text: str) -> list[str]:
    """Reverse of _numbered_block: "1. a\\r\\n2. b" -> ["a", "b"]."""
    if not text:
        return []
    lines = [line for line in text.split("\r\n") if line.strip()]
    return [re.sub(r"^\d+\.\s*", "", line) for line in lines]


def _resolve(entry: dict, key: str, current):
    """Placeholder-skip resolution for one flat field: `current` unchanged
    if entry[key] is a {{placeholder_...}} marker or the key is absent,
    else the JSON's own value — even if that value is empty/blank, since
    only a placeholder marker means "nothing real here, don't touch"."""
    if key not in entry:
        return current
    value = entry[key]
    return current if _is_placeholder(value) else value


def _resolve_person_id(db: Session, entry: dict, key: str, user_type: "UserType", current_id: int | None) -> int | None:
    if key not in entry:
        return current_id
    person = entry[key]
    if person is None:
        return None  # explicitly cleared — null is not a placeholder
    name = person.get("name") if isinstance(person, dict) else None
    if not name or _is_placeholder(name):
        return current_id
    user = get_or_create(db, User, name, type=user_type)
    username = person.get("username") if isinstance(person, dict) else None
    if user is not None and username and not _is_placeholder(username):
        user.jira_username = username
    return user.id if user else current_id


def _apply_zephyr_entry(db: Session, section: "TestCaseSection", entry: dict) -> None:
    """Replace a section's steps from one Jira zephyr_steps entry.

    Jira never supplies actual_result at all, and either side (step text or
    expected result) may be a placeholder marker meaning "nothing real here".
    In both cases the OLD row's value at that same position is preserved
    rather than blanked to "" — matching this module's own placeholder rule
    (see the module docstring): a placeholder must never overwrite real data
    already recorded locally, and a field Jira has no concept of at all
    (actual_result) must never be touched by an import.
    """
    step_text = entry.get("step", "")
    expected_text = entry.get("expected_result", "")
    if _is_placeholder(step_text) and _is_placeholder(expected_text):
        return  # nothing real in this section's entry — leave existing steps alone

    old_steps = list(section.steps)

    if _is_placeholder(step_text):
        step_lines = None  # no real step data supplied — preserve old step_text by position
    else:
        body = step_text.split("\r\n", 1)[1] if "\r\n" in step_text else ""
        step_lines = _split_numbered_block(body)

    expected_lines = None if _is_placeholder(expected_text) else _split_numbered_block(expected_text)

    step_count = len(step_lines) if step_lines is not None else len(old_steps)
    expected_count = len(expected_lines) if expected_lines is not None else len(old_steps)
    count = max(step_count, expected_count)

    new_rows = []
    for i in range(count):
        old = old_steps[i] if i < len(old_steps) else None
        if step_lines is not None:
            step_value = step_lines[i] if i < len(step_lines) else ""
        else:
            step_value = old.step_text if old else ""
        if expected_lines is not None:
            expected_value = expected_lines[i] if i < len(expected_lines) else ""
        else:
            expected_value = old.expected_result if old else ""
        actual_value = old.actual_result if old else ""
        new_rows.append((step_value, expected_value, actual_value))

    for step in old_steps:
        deletion.delete_step(db, step)
    db.flush()
    for i, (step_value, expected_value, actual_value) in enumerate(new_rows):
        db.add(
            TestCaseStep(
                section_id=section.id, step_no=i + 1,
                step_text=step_value, expected_result=expected_value, actual_result=actual_value,
            )
        )


def _apply_labels(db: Session, attach_type: "LabelAttachType", attach_id: int, names: list[str]) -> None:
    label_ids = [get_or_create(db, Label, name).id for name in names if name]
    set_labels(db, attach_type, attach_id, label_ids)


def _apply_testcase_from_jira(db: Session, testcase: "TestCase", entry: dict) -> None:
    testcase.title = _resolve(entry, "summary", testcase.title) or testcase.title

    category_raw = entry.get("category")
    if "category" in entry and not _is_placeholder(category_raw):
        try:
            testcase.category = TestCaseCategory(category_raw)
        except ValueError:
            pass  # unknown category value — leave whatever was there

    testcase.msisdn = _resolve(entry, "msisdn", testcase.msisdn)
    testcase.planned_cost = _resolve(entry, "planned_cost", testcase.planned_cost)
    testcase.actual_cost = _resolve(entry, "actual_cost", testcase.actual_cost)
    testcase.number_of_iteration = _resolve(entry, "number_of_iteration", testcase.number_of_iteration)

    testcase.assignee_id = _resolve_person_id(db, entry, "assignee", UserType.TESTER, testcase.assignee_id)
    testcase.developer_id = _resolve_person_id(db, entry, "developer", UserType.DEVELOPER, testcase.developer_id)
    testcase.tester_id = _resolve_person_id(db, entry, "tester", UserType.TESTER, testcase.tester_id)

    zephyr_steps = entry.get("zephyr_steps") or []
    if not isinstance(zephyr_steps, list):
        raise ValueError('"zephyr_steps" must be a list.')
    # Only the FIRST section of each kind is ever touched by an import — see
    # the comment above _zephyr_entry for why (Jira has no equivalent of a
    # repeated section kind). Sections beyond the first of their kind are
    # skipped entirely and left completely untouched.
    applied_kinds = set()
    for section in testcase.sections:
        if section.kind in applied_kinds:
            continue
        applied_kinds.add(section.kind)
        matching = next(
            (
                z for z in zephyr_steps
                if isinstance(z, dict) and z.get("step_type") == _SECTION_LABEL[section.kind]
            ),
            None,
        )
        if matching is not None:
            _apply_zephyr_entry(db, section, matching)

    execution = entry.get("execution") or {}
    if not isinstance(execution, dict):
        raise ValueError('"execution" must be a JSON object.')
    status_raw = execution.get("status")
    if status_raw and not _is_placeholder(status_raw) and status_raw in _JIRA_TO_STATUS:
        testcase.status = _JIRA_TO_STATUS[status_raw]
    if "execution_id" in execution:
        exec_id = execution["execution_id"]
        testcase.jira_execution_id = None if exec_id is None else str(exec_id)

    fields = entry.get("fields") or {}
    if not isinstance(fields, dict):
        raise ValueError('"fields" must be a JSON object.')
    testcase.remark = _resolve(fields, "description", testcase.remark)
    priority = fields.get("priority") or {}
    if not isinstance(priority, dict):
        raise ValueError('"fields.priority" must be a JSON object.')
    testcase.test_priority = _resolve(priority, "name", testcase.test_priority)

    if "labels" in fields:
        _apply_labels(db, LabelAttachType.TESTCASE, testcase.id, fields.get("labels") or [])


def apply_jira_json_to_subtask(db: Session, subtask: "Subtask", data: dict) -> "Subtask":
    if not isinstance(data, dict):
        raise ValueError('Expected a JSON object with a "test_cases" list.')
    test_cases = data.get("test_cases")
    if not isinstance(test_cases, list):
        raise ValueError('Missing "test_cases" list.')

    parent_info = data.get("parent_ticket_info") or {}
    if not isinstance(parent_info, dict):
        raise ValueError('"parent_ticket_info" must be a JSON object.')
    subtask.assignee_id = _resolve_person_id(db, parent_info, "assignee", UserType.TESTER, subtask.assignee_id)
    subtask.developer_id = _resolve_person_id(db, parent_info, "developer", UserType.DEVELOPER, subtask.developer_id)
    subtask.tester_id = _resolve_person_id(db, parent_info, "tester", UserType.TESTER, subtask.tester_id)
    if "labels" in parent_info:
        _apply_labels(db, LabelAttachType.SUBTASK, subtask.id, parent_info.get("labels") or [])

    for entry in test_cases:
        if not isinstance(entry, dict):
            raise ValueError("Each test case entry must be a JSON object.")
        issue_key = entry.get("issue_key")
        if not issue_key:
            raise ValueError('Each test case entry needs an "issue_key".')
        testcase = next((tc for tc in subtask.testcases if tc.display_code == issue_key), None)
        if testcase is None:
            testcase = TestCase(
                subtask_id=subtask.id, display_code=issue_key,
                title=entry.get("summary") or issue_key, internal_key=generate_internal_key(),
            )
            db.add(testcase)
            db.flush()
            for position, kind in enumerate(DEFAULT_SECTION_KINDS):
                db.add(TestCaseSection(testcase_id=testcase.id, kind=kind, position=position))
            db.flush()
        _apply_testcase_from_jira(db, testcase, entry)

    return subtask

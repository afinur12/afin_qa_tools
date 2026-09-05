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

from sqlalchemy.orm import Session

from app.labels import get_labels
from app.models import (
    LabelAttachType, StepSection, Subtask, TestCase, TestCaseSection, TestCaseStatus, User,
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


def _person(user: "User | None") -> dict | None:
    if user is None:
        return None
    return {"name": user.name, "username": user.jira_username or _placeholder("username")}


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
        "assignee": _person(testcase.assignee),
        "developer": _person(testcase.developer),
        "tester": _person(testcase.tester_user),
        "zephyr_steps": [_zephyr_entry(section) for section in testcase.sections],
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


def subtask_to_jira_json(subtask: "Subtask", db: Session) -> list[dict]:
    return [testcase_to_jira_dict(tc, db) for tc in subtask.testcases]

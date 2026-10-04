"""Copy test steps — with their Test Data items and screenshots — into a
section of another (or the same) test case.

Used by "Copy steps to…" on the test case page: an already-executed case's
steps can seed another case, evidence included. Everything is duplicated,
screenshots as new files, so deleting a step or screenshot on either side
never affects the other.
"""

import uuid
from pathlib import Path

from sqlalchemy.orm import Session

import app.routers.screenshots as screenshots_module
from app.image_compress import compress_in_background
from app.models import Screenshot, TestCaseSection, TestCaseStep, TestCaseStepData


def _copy_screenshot(shot: Screenshot, testcase_id: int, step_id: int) -> Screenshot | None:
    # Resolved at call time so tests can point uploads at a temp folder.
    uploads = screenshots_module.UPLOADS_DIR
    source = uploads / shot.file_path
    if not source.exists():
        return None  # file already gone — nothing to duplicate
    relative_path = f"screenshots/{testcase_id}/{step_id}/{uuid.uuid4().hex}{Path(shot.file_path).suffix}"
    target = uploads / relative_path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    compress_in_background(target)
    return Screenshot(step_id=step_id, file_path=relative_path)


def copy_steps(db: Session, steps: list[TestCaseStep], target: TestCaseSection) -> list[TestCaseStep]:
    """Append copies of `steps` (in the given order) after `target`'s
    existing steps; returns the new steps."""
    next_no = max((s.step_no for s in target.steps), default=0) + 1
    created = []
    for offset, source in enumerate(steps):
        step = TestCaseStep(
            section_id=target.id, step_no=next_no + offset, step_text=source.step_text,
            expected_result=source.expected_result, actual_result=source.actual_result,
        )
        db.add(step)
        db.flush()
        for item in source.data_items:
            db.add(TestCaseStepData(
                step_id=step.id, order_no=item.order_no, title=item.title, value=item.value, language=item.language,
            ))
        for shot in source.screenshots:
            copy = _copy_screenshot(shot, target.testcase_id, step.id)
            if copy is not None:
                db.add(copy)
        created.append(step)
    db.flush()
    return created

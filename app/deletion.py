"""Cascading deletes for the test-case tree.

Deleting a test case or a subtask takes its children with it, so a tester
never has to clear steps or cases out by hand first. Screenshot rows are
always removed together with their file on disk — that pairing lives here so
it cannot drift between the routers that trigger a delete.

Callers commit; these helpers only stage the deletions.
"""

from sqlalchemy.orm import Session


def _remove_screenshot(db: Session, screenshot) -> None:
    from app.routers.screenshots import UPLOADS_DIR

    disk_path = UPLOADS_DIR / screenshot.file_path
    if disk_path.exists():
        disk_path.unlink()
    db.delete(screenshot)


def delete_step(db: Session, step) -> None:
    for screenshot in list(step.screenshots):
        _remove_screenshot(db, screenshot)
    db.delete(step)


def delete_section(db: Session, section) -> None:
    for step in list(section.steps):
        delete_step(db, step)
    db.delete(section)


def delete_testcase(db: Session, testcase) -> None:
    for section in list(testcase.sections):
        delete_section(db, section)
    db.delete(testcase)


def delete_subtask(db: Session, subtask) -> None:
    for testcase in list(subtask.testcases):
        delete_testcase(db, testcase)
    for bug in list(subtask.bugs):
        db.delete(bug)
    db.delete(subtask)

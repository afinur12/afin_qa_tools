"""Cascading deletes for the test-case tree.

Deleting a test case or a subtask takes its children with it, so a tester
never has to clear steps or cases out by hand first. Screenshot rows are
always removed together with their file on disk — that pairing lives here so
it cannot drift between the routers that trigger a delete.

Callers commit; these helpers only stage the deletions.
"""

from sqlalchemy.orm import Session

from app.labels import clear_labels
from app.models import KnowledgePageLink, LabelAttachType


def _remove_screenshot(db: Session, screenshot) -> None:
    from app.routers.screenshots import UPLOADS_DIR

    disk_path = UPLOADS_DIR / screenshot.file_path
    if disk_path.exists():
        disk_path.unlink()
    db.delete(screenshot)


def delete_step(db: Session, step) -> None:
    for screenshot in list(step.screenshots):
        _remove_screenshot(db, screenshot)
    for data_item in list(step.data_items):
        db.delete(data_item)
    db.delete(step)


def delete_section(db: Session, section) -> None:
    for step in list(section.steps):
        delete_step(db, step)
    db.delete(section)


def delete_testcase(db: Session, testcase) -> None:
    for section in list(testcase.sections):
        delete_section(db, section)
    clear_labels(db, LabelAttachType.TESTCASE, testcase.id)
    db.delete(testcase)


def delete_subtask(db: Session, subtask) -> None:
    for testcase in list(subtask.testcases):
        delete_testcase(db, testcase)
    for bug in list(subtask.bugs):
        clear_labels(db, LabelAttachType.BUG, bug.id)
        db.delete(bug)
    clear_labels(db, LabelAttachType.SUBTASK, subtask.id)
    db.delete(subtask)


def _remove_upload(relative_path: str | None) -> None:
    if not relative_path:
        return
    from app.routers.screenshots import UPLOADS_DIR

    disk_path = UPLOADS_DIR / relative_path
    if disk_path.exists():
        disk_path.unlink()


def delete_knowledge_block(db: Session, block) -> None:
    _remove_upload(block.file_path)
    db.delete(block)


def delete_knowledge_board(db: Session, board) -> None:
    for block in list(board.blocks):
        delete_knowledge_block(db, block)
    db.delete(board)


def delete_knowledge_page(db: Session, page) -> None:
    for board in list(page.boards):
        delete_knowledge_board(db, board)
    for link in list(page.links):
        db.delete(link)
    db.delete(page)


def delete_knowledge_section(db: Session, section) -> None:
    for page in list(section.pages):
        delete_knowledge_page(db, page)
    db.delete(section)


def delete_knowledge_links_to(db: Session, target_type, target_id: int) -> None:
    """A story or subtask is going away: drop the links pointing at it (never the pages)."""
    db.query(KnowledgePageLink).filter(
        KnowledgePageLink.target_type == target_type, KnowledgePageLink.target_id == target_id
    ).delete(synchronize_session=False)

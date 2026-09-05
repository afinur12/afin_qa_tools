"""Deleting a Story/Subtask/TestCase/Bug must also clear its
LabelAssignment rows (and those of any children removed by cascade) —
otherwise a Label assigned to a now-deleted entity becomes permanently
undeletable, and a future entity that reuses the same id can silently
inherit the old label chips (see app/deletion.py, app/labels.py's
clear_labels, and the delete routes in app/routers/stories.py, subtasks.py,
bugs.py, testcases.py).

Verification reads open and close their own session per call (via the same
app.dependency_overrides[get_db] the app itself uses) rather than holding
one session across the whole test — a session held open across several
`client.post()` calls can keep an old transaction snapshot and appear not
to see commits made by those requests' own sessions.
"""

import re

from app.database import get_db
from app.main import app as fastapi_app
from app.models import LabelAssignment, LabelAttachType, TestCase


def _create_label(client, name):
    # Anchored on the label's own name, not just the first delete link on the
    # page: the list is rendered ordered by name (settings/labels.html), so
    # with more than one label present the first "/delete" match need not be
    # the one just created.
    client.post("/settings/labels", data={"name": name})
    page = client.get("/settings/labels").text
    match = re.search(rf'value="{re.escape(name)}"[\s\S]*?/settings/labels/(\d+)/delete', page)
    return int(match.group(1))


def _create_phase_and_subtask(client, story_id, code, label_id):
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split("/subtasks/new")[0].split("/phases/")[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": code, "title": "Exec", "subtask_type": "EXECUTION", "label_ids": [label_id]},
        follow_redirects=False,
    )
    return int(sub_resp.headers["location"].rstrip("/").split("/")[-1])


def _label_count(attach_type, attach_id):
    override = fastapi_app.dependency_overrides[get_db]
    gen = override()
    db = next(gen)
    try:
        return (
            db.query(LabelAssignment)
            .filter(LabelAssignment.attach_type == attach_type, LabelAssignment.attach_id == attach_id)
            .count()
        )
    finally:
        gen.close()


def _add_testcase_row(testcase_id, subtask_id, display_code):
    override = fastapi_app.dependency_overrides[get_db]
    gen = override()
    db = next(gen)
    try:
        db.add(TestCase(id=testcase_id, subtask_id=subtask_id, display_code=display_code, title="B",
                         internal_key=f"reused-{testcase_id}"))
        db.commit()
    finally:
        gen.close()


def _delete_label_should_succeed(client, label_id):
    response = client.post(f"/settings/labels/{label_id}/delete", follow_redirects=False)
    assert response.status_code == 303, "label should be deletable once nothing references it any more"


def test_delete_story_clears_its_label_assignment_and_frees_the_label(client):
    label_id = _create_label(client, "story-tag")
    create = client.post(
        "/stories", data={"display_code": "EX-900", "title": "A", "label_ids": [label_id]}, follow_redirects=False
    )
    story_id = int(create.headers["location"].rstrip("/").split("/")[-1])
    assert _label_count(LabelAttachType.STORY, story_id) == 1

    response = client.post(f"/stories/{story_id}/delete", follow_redirects=False)
    assert response.status_code == 303

    assert _label_count(LabelAttachType.STORY, story_id) == 0
    _delete_label_should_succeed(client, label_id)


def test_delete_bug_directly_clears_its_labels(client):
    label_id = _create_label(client, "bug-tag")
    create = client.post("/stories", data={"display_code": "EX-901", "title": "A"}, follow_redirects=False)
    story_id = int(create.headers["location"].rstrip("/").split("/")[-1])
    subtask_id = _create_phase_and_subtask(client, story_id, "S-1", label_id=_create_label(client, "unused"))

    bug_resp = client.post(
        f"/subtasks/{subtask_id}/bugs",
        data={"display_code": "B-1", "title": "[ISSUE] a", "label_ids": [label_id]},
        follow_redirects=False,
    )
    bug_id = int(bug_resp.headers["location"].rstrip("/").split("/")[-1])
    assert _label_count(LabelAttachType.BUG, bug_id) == 1

    response = client.post(f"/bugs/{bug_id}/delete", follow_redirects=False)
    assert response.status_code == 303

    assert _label_count(LabelAttachType.BUG, bug_id) == 0
    _delete_label_should_succeed(client, label_id)


def test_delete_testcase_directly_clears_its_labels(client):
    label_id = _create_label(client, "tc-tag")
    create = client.post("/stories", data={"display_code": "EX-902", "title": "A"}, follow_redirects=False)
    story_id = int(create.headers["location"].rstrip("/").split("/")[-1])
    subtask_id = _create_phase_and_subtask(client, story_id, "S-1", label_id=_create_label(client, "unused2"))

    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"}, follow_redirects=False
    )
    testcase_id = int(tc_resp.headers["location"].rstrip("/").split("/")[-1])

    # TestCase labels are set through Section 1's autosave endpoint, not the create form.
    client.post(
        f"/testcases/{testcase_id}/section1",
        data={"status": "TO_DO", "label_ids": [label_id]},
        follow_redirects=False,
    )
    assert _label_count(LabelAttachType.TESTCASE, testcase_id) == 1

    response = client.post(f"/testcases/{testcase_id}/delete", follow_redirects=False)
    assert response.status_code == 303

    assert _label_count(LabelAttachType.TESTCASE, testcase_id) == 0
    _delete_label_should_succeed(client, label_id)


def test_delete_subtask_cascades_label_cleanup_to_child_testcase_and_bug(client):
    subtask_label = _create_label(client, "subtask-tag")
    testcase_label = _create_label(client, "testcase-tag")
    bug_label = _create_label(client, "bug-tag-2")

    create = client.post("/stories", data={"display_code": "EX-903", "title": "A"}, follow_redirects=False)
    story_id = int(create.headers["location"].rstrip("/").split("/")[-1])
    subtask_id = _create_phase_and_subtask(client, story_id, "S-1", label_id=subtask_label)

    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"}, follow_redirects=False
    )
    testcase_id = int(tc_resp.headers["location"].rstrip("/").split("/")[-1])
    client.post(
        f"/testcases/{testcase_id}/section1",
        data={"status": "TO_DO", "label_ids": [testcase_label]},
        follow_redirects=False,
    )

    bug_resp = client.post(
        f"/subtasks/{subtask_id}/bugs",
        data={"display_code": "B-1", "title": "[ISSUE] a", "label_ids": [bug_label]},
        follow_redirects=False,
    )
    bug_id = int(bug_resp.headers["location"].rstrip("/").split("/")[-1])

    assert _label_count(LabelAttachType.SUBTASK, subtask_id) == 1
    assert _label_count(LabelAttachType.TESTCASE, testcase_id) == 1
    assert _label_count(LabelAttachType.BUG, bug_id) == 1

    # Deleting the subtask cascades to the test case and the bug — none of
    # them should leave a dangling LabelAssignment row behind.
    response = client.post(f"/subtasks/{subtask_id}/delete", follow_redirects=False)
    assert response.status_code == 303

    assert _label_count(LabelAttachType.SUBTASK, subtask_id) == 0
    assert _label_count(LabelAttachType.TESTCASE, testcase_id) == 0
    assert _label_count(LabelAttachType.BUG, bug_id) == 0

    _delete_label_should_succeed(client, subtask_label)
    _delete_label_should_succeed(client, testcase_label)
    _delete_label_should_succeed(client, bug_label)


def test_a_new_entity_reusing_a_deleted_ids_row_does_not_inherit_old_labels(client):
    """SQLite reuses the highest available rowid. If a deleted TestCase's
    LabelAssignment rows were left behind, a fresh TestCase that lands on
    the same id would silently show the old case's label chips."""
    label_id = _create_label(client, "sticky-tag")
    create = client.post("/stories", data={"display_code": "EX-904", "title": "A"}, follow_redirects=False)
    story_id = int(create.headers["location"].rstrip("/").split("/")[-1])
    subtask_id = _create_phase_and_subtask(client, story_id, "S-1", label_id=_create_label(client, "unused3"))

    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"}, follow_redirects=False
    )
    testcase_id = int(tc_resp.headers["location"].rstrip("/").split("/")[-1])
    client.post(
        f"/testcases/{testcase_id}/section1",
        data={"status": "TO_DO", "label_ids": [label_id]},
        follow_redirects=False,
    )
    client.post(f"/testcases/{testcase_id}/delete", follow_redirects=False)

    # A brand-new TestCase row created directly at the same id (simulating
    # SQLite's rowid reuse) must not inherit the deleted one's labels.
    _add_testcase_row(testcase_id, subtask_id, "TC-2")

    assert _label_count(LabelAttachType.TESTCASE, testcase_id) == 0

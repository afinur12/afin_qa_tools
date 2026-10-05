"""Labels are picked with toggle chips (one shared macro), not a long checklist."""
import re

import app.models as m

CHIP = re.compile(
    r'<label class="label-chip">\s*<input type="checkbox" name="label_ids" value="(\d+)"( checked)?>\s*<span>([^<]*)</span>'
)
OLD_ROW = re.compile(r'<label class="choice">\s*<input type="checkbox" name="label_ids"')


def _labels(client, db_session, *names):
    for name in names:
        client.post("/settings/labels", data={"name": name})
    db_session.expire_all()
    return {label.name: label.id for label in db_session.query(m.Label).filter(m.Label.name.in_(names))}


def _chips(html):
    return [(int(label_id), bool(checked), name) for label_id, checked, name in CHIP.findall(html)]


def _story_phase_subtask(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    phase_id = client.get(f"/stories/{story_id}").text.split("/subtasks/new")[0].split("/phases/")[-1]
    sub = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    return story_id, phase_id, sub.headers["location"].rstrip("/").split("/")[-1]


def test_edit_story_modal_shows_labels_as_chips_with_current_ones_ticked(client, db_session):
    ids = _labels(client, db_session, "SITDefect", "Sanity Scenario")
    story_id, _, _ = _story_phase_subtask(client, "EX-950")
    client.post(f"/stories/{story_id}/edit", data={
        "display_code": "EX-950", "title": "A", "status": "TO_DO", "label_ids": [ids["Sanity Scenario"]],
    })

    page = client.get(f"/stories/{story_id}").text
    edit_modal = page.split('id="edit-story"')[1].split('class="modal-backdrop"')[0]
    assert sorted(_chips(edit_modal)) == sorted([
        (ids["SITDefect"], False, "SITDefect"),
        (ids["Sanity Scenario"], True, "Sanity Scenario"),
    ])


def test_edit_subtask_modal_shows_labels_as_chips_with_current_ones_ticked(client, db_session):
    ids = _labels(client, db_session, "SITDefect", "Sanity Scenario")
    _, _, subtask_id = _story_phase_subtask(client, "EX-951")
    client.post(f"/subtasks/{subtask_id}/edit", data={
        "display_code": "S-1", "title": "Exec", "status": "TO_DO", "label_ids": [ids["SITDefect"]],
    })

    page = client.get(f"/subtasks/{subtask_id}").text
    ticked = {name for _, checked, name in _chips(page) if checked}
    assert ticked == {"SITDefect"}


def test_every_label_picker_uses_chips(client, db_session):
    _labels(client, db_session, "smoke")
    story_id, phase_id, subtask_id = _story_phase_subtask(client, "EX-952")
    bug = client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"},
                      follow_redirects=False)
    bug_id = bug.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login"})
    db_session.expire_all()
    testcase_id = db_session.query(m.TestCase).filter_by(subtask_id=int(subtask_id)).one().id

    pages = [
        "/", "/stories", "/stories/new", f"/stories/{story_id}", f"/stories/{story_id}/edit",
        f"/phases/{phase_id}/subtasks/new", f"/subtasks/{subtask_id}", f"/subtasks/{subtask_id}/edit",
        f"/subtasks/{subtask_id}/bugs/new", f"/bugs/{bug_id}", f"/bugs/{bug_id}/edit",
        f"/testcases/{testcase_id}/execute",
    ]
    for url in pages:
        html = client.get(url).text
        assert not OLD_ROW.search(html), f"{url} still has the old label checklist"
        assert any(name == "smoke" for _, _, name in _chips(html)), f"{url} has no label chips"


def test_label_picker_without_labels_points_to_settings(client):
    html = client.get("/stories/new").text
    assert "No labels yet — add some under Settings." in html

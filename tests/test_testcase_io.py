import json

import pytest

from app.models import (
    DEFAULT_SECTION_KINDS,
    Bug,
    Phase,
    PhaseType,
    Story,
    Subtask,
    SubtaskType,
    TestCase,
    TestCaseSection,
    TestCaseStep,
    generate_internal_key,
)
# testcase_to_dict aliased to dump_testcase on import: its name starts with
# "test", which pytest's default collector treats as a test function to
# call — aliasing avoids a spurious collection error without touching
# pytest config.
from app.testcase_io import (
    dict_to_subtask, dict_to_task, dict_to_testcase, extract_testcase_candidates,
    subtask_to_dict, task_to_dict,
)
from app.testcase_io import testcase_to_dict as dump_testcase
from app.testcase_io import testcases_to_dict as dump_testcases


def _make_story(db, code="PROJ-1", phase_type=PhaseType.SIT):
    story = Story(display_code=code, title="A task", internal_key=generate_internal_key())
    db.add(story)
    db.flush()
    phase = Phase(story_id=story.id, type=phase_type)
    db.add(phase)
    db.flush()
    return story, phase


def _make_subtask(db, phase, code="ST-1"):
    subtask = Subtask(
        phase_id=phase.id, display_code=code, title="A subtask",
        internal_key=generate_internal_key(), subtask_type=SubtaskType.EXECUTION,
    )
    db.add(subtask)
    db.flush()
    return subtask


def _make_bug(db, subtask, code="BUG-1"):
    bug = Bug(
        subtask_id=subtask.id, display_code=code, title="A bug", description="Steps to reproduce...",
        internal_key=generate_internal_key(),
    )
    db.add(bug)
    db.flush()
    return bug


def _make_testcase(db, subtask, code="TC-1"):
    tc = TestCase(subtask_id=subtask.id, display_code=code, title="A test case", internal_key=generate_internal_key())
    db.add(tc)
    db.flush()
    for position, kind in enumerate(DEFAULT_SECTION_KINDS):
        section = TestCaseSection(testcase_id=tc.id, kind=kind, position=position)
        db.add(section)
        db.flush()
        db.add(TestCaseStep(
            section_id=section.id, step_no=1, step_text="Do the thing",
            expected_result="It works", actual_result="It worked",
        ))
    db.commit()
    db.refresh(tc)
    return tc


def test_testcase_round_trip(db_session):
    story, phase = _make_story(db_session)
    subtask_a = _make_subtask(db_session, phase, "ST-A")
    subtask_b = _make_subtask(db_session, phase, "ST-B")
    tc = _make_testcase(db_session, subtask_a, "TC-1")
    db_session.commit()

    data = dump_testcase(tc)
    assert data["kind"] == "testcase"
    assert data["testcase"]["display_code"] == "TC-1"
    assert len(data["testcase"]["sections"]) == 3
    assert data["testcase"]["sections"][0]["steps"][0]["step_text"] == "Do the thing"
    # No include_screenshots requested — the key shouldn't appear at all.
    assert "screenshots" not in data["testcase"]["sections"][0]["steps"][0]

    imported = dict_to_testcase(db_session, subtask_b.id, data)
    db_session.commit()
    assert imported.subtask_id == subtask_b.id
    assert imported.display_code == "TC-1"  # different subtask, no collision
    assert len(imported.sections) == 3
    assert imported.sections[0].steps[0].step_text == "Do the thing"
    assert imported.sections[0].steps[0].expected_result == "It works"


def test_testcase_import_auto_renames_on_collision(db_session):
    story, phase = _make_story(db_session)
    subtask = _make_subtask(db_session, phase)
    tc = _make_testcase(db_session, subtask, "TC-1")
    db_session.commit()

    data = dump_testcase(tc)
    imported = dict_to_testcase(db_session, subtask.id, data)  # same subtask as the original
    db_session.commit()
    assert imported.display_code == "TC-1 (2)"


def test_testcase_import_rejects_wrong_kind(db_session):
    story, phase = _make_story(db_session)
    subtask = _make_subtask(db_session, phase)
    with pytest.raises(ValueError):
        dict_to_testcase(db_session, subtask.id, {"kind": "subtask", "subtask": {}})


def test_subtask_round_trip(db_session):
    story, phase_a = _make_story(db_session, phase_type=PhaseType.SIT)
    phase_b = Phase(story_id=story.id, type=PhaseType.STAGING)
    db_session.add(phase_b)
    db_session.flush()

    subtask = _make_subtask(db_session, phase_a, "ST-1")
    _make_testcase(db_session, subtask, "TC-1")
    _make_testcase(db_session, subtask, "TC-2")
    _make_bug(db_session, subtask, "BUG-1")
    db_session.commit()

    data = subtask_to_dict(subtask)
    assert data["kind"] == "subtask"
    assert len(data["subtask"]["testcases"]) == 2
    assert len(data["subtask"]["bugs"]) == 1
    assert data["subtask"]["bugs"][0]["display_code"] == "BUG-1"

    imported = dict_to_subtask(db_session, phase_b.id, data)
    db_session.commit()
    assert imported.phase_id == phase_b.id
    assert imported.display_code == "ST-1"
    assert len(imported.testcases) == 2
    assert {tc.display_code for tc in imported.testcases} == {"TC-1", "TC-2"}
    assert len(imported.bugs) == 1
    assert imported.bugs[0].display_code == "BUG-1"
    assert imported.bugs[0].description == "Steps to reproduce..."


def test_subtask_import_rejects_disallowed_type_for_target_phase(db_session):
    story, phase_a = _make_story(db_session, phase_type=PhaseType.SIT)
    rollback_phase = Phase(story_id=story.id, type=PhaseType.STAGING_AFTER_ROLLBACK)
    db_session.add(rollback_phase)
    db_session.flush()
    # Give the rollback phase its one allowed EXECUTION subtask already —
    # allowed_subtask_types becomes empty, so nothing else can go in.
    db_session.add(Subtask(
        phase_id=rollback_phase.id, display_code="ST-X", title="x",
        internal_key=generate_internal_key(), subtask_type=SubtaskType.EXECUTION,
    ))
    db_session.commit()

    subtask = _make_subtask(db_session, phase_a, "ST-1")
    data = subtask_to_dict(subtask)
    with pytest.raises(ValueError):
        dict_to_subtask(db_session, rollback_phase.id, data)


def test_subtask_import_auto_renames_colliding_bug(db_session):
    story, phase = _make_story(db_session)
    subtask = _make_subtask(db_session, phase, "ST-1")
    _make_bug(db_session, subtask, "BUG-1")
    db_session.commit()

    data = subtask_to_dict(subtask)
    # Import the SAME subtask export back into the SAME phase — both the
    # subtask's own display_code and its nested bug's collide with what's
    # already there.
    imported = dict_to_subtask(db_session, phase.id, data)
    db_session.commit()
    assert imported.display_code == "ST-1 (2)"
    assert imported.bugs[0].display_code == "BUG-1"  # different subtask now, no collision within it


def test_task_round_trip(db_session):
    story, phase = _make_story(db_session, code="PROJ-1")
    subtask = _make_subtask(db_session, phase)
    _make_testcase(db_session, subtask)
    _make_bug(db_session, subtask)
    db_session.commit()

    data = task_to_dict(story)
    assert data["kind"] == "task"
    assert data["task"]["display_code"] == "PROJ-1"
    assert len(data["task"]["phases"]) == 1
    assert data["task"]["phases"][0]["type"] == "SIT"
    assert len(data["task"]["phases"][0]["subtasks"][0]["bugs"]) == 1

    imported = dict_to_task(db_session, data)
    db_session.commit()
    assert imported.id != story.id
    assert imported.display_code == "PROJ-1 (2)"  # collides with the original
    assert len(imported.phases) == 1
    assert len(imported.phases[0].subtasks) == 1
    assert len(imported.phases[0].subtasks[0].bugs) == 1
    assert len(imported.phases[0].subtasks[0].testcases) == 1


def test_task_import_rejects_duplicate_phase_type(db_session):
    data = {
        "kind": "task", "schema_version": 1,
        "task": {
            "display_code": "DUP-1", "title": "x",
            "phases": [{"type": "SIT", "subtasks": []}, {"type": "SIT", "subtasks": []}],
        },
    }
    with pytest.raises(ValueError):
        dict_to_task(db_session, data)


def test_export_json_endpoint_returns_valid_shape(client, db_session):
    story, phase = _make_story(db_session, code="HTTPX-1")
    subtask = _make_subtask(db_session, phase)
    tc = _make_testcase(db_session, subtask)
    db_session.commit()

    response = client.get(f"/testcases/{tc.id}/export-json")
    assert response.status_code == 200
    assert response.json()["kind"] == "testcase"
    assert response.json()["testcase"]["display_code"] == tc.display_code


def test_import_subtask_endpoint_flashes_error_on_bad_json(client, db_session):
    story, phase = _make_story(db_session, code="HTTPX-2")
    db_session.commit()

    response = client.post(
        f"/phases/{phase.id}/subtasks/import",
        files={"file": ("bad.json", b"not json", "application/json")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/stories/{story.id}"


def test_import_testcase_endpoint_happy_path(client, db_session):
    import json

    story, phase = _make_story(db_session, code="HTTPX-3")
    source_subtask = _make_subtask(db_session, phase, "ST-SRC")
    target_subtask = _make_subtask(db_session, phase, "ST-DST")
    tc = _make_testcase(db_session, source_subtask, "TC-1")
    db_session.commit()

    payload = json.dumps(dump_testcase(tc)).encode("utf-8")
    response = client.post(
        f"/subtasks/{target_subtask.id}/testcases/import",
        files={"file": ("export.json", payload, "application/json")},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/subtasks/{target_subtask.id}"

    db_session.expire_all()
    imported = [t for t in target_subtask.testcases if t.display_code == "TC-1"]
    assert len(imported) == 1
    assert len(imported[0].sections) == 3


# ── Selected-testcases export/import (extract_testcase_candidates + routes) ─

def test_testcases_to_dict_and_extract_round_trip(db_session):
    story, phase = _make_story(db_session, code="SEL-1")
    subtask = _make_subtask(db_session, phase)
    tc1 = _make_testcase(db_session, subtask, "TC-1")
    tc2 = _make_testcase(db_session, subtask, "TC-2")
    db_session.commit()

    data = dump_testcases([tc1, tc2])
    assert data["kind"] == "testcases"
    assert [t["display_code"] for t in data["testcases"]] == ["TC-1", "TC-2"]

    candidates = extract_testcase_candidates(data)
    assert [c["display_code"] for c in candidates] == ["TC-1", "TC-2"]


def test_extract_testcase_candidates_from_single_testcase(db_session):
    story, phase = _make_story(db_session, code="SEL-2")
    subtask = _make_subtask(db_session, phase)
    tc = _make_testcase(db_session, subtask, "TC-1")
    db_session.commit()

    candidates = extract_testcase_candidates(dump_testcase(tc))
    assert len(candidates) == 1
    assert candidates[0]["display_code"] == "TC-1"


def test_extract_testcase_candidates_from_subtask_ignores_bugs(db_session):
    story, phase = _make_story(db_session, code="SEL-3")
    subtask = _make_subtask(db_session, phase)
    _make_testcase(db_session, subtask, "TC-1")
    _make_bug(db_session, subtask, "BUG-1")
    db_session.commit()

    candidates = extract_testcase_candidates(subtask_to_dict(subtask))
    assert len(candidates) == 1
    assert candidates[0]["display_code"] == "TC-1"


def test_extract_testcase_candidates_rejects_unknown_kind():
    with pytest.raises(ValueError):
        extract_testcase_candidates({"kind": "bug", "bug": {}})


def test_export_selected_testcases_endpoint_only_includes_checked_ids(client, db_session):
    story, phase = _make_story(db_session, code="SELHTTP-1")
    subtask = _make_subtask(db_session, phase)
    tc1 = _make_testcase(db_session, subtask, "TC-1")
    _make_testcase(db_session, subtask, "TC-2")  # not selected
    db_session.commit()

    response = client.post(
        f"/subtasks/{subtask.id}/testcases/export-selected",
        data={"testcase_ids": [str(tc1.id)]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["kind"] == "testcases"
    assert [t["display_code"] for t in body["testcases"]] == ["TC-1"]


def test_export_selected_testcases_endpoint_flashes_when_none_selected(client, db_session):
    story, phase = _make_story(db_session, code="SELHTTP-2")
    subtask = _make_subtask(db_session, phase)
    db_session.commit()

    response = client.post(
        f"/subtasks/{subtask.id}/testcases/export-selected",
        data={"testcase_ids": ["999999"]},  # doesn't belong to this subtask
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/subtasks/{subtask.id}"


def test_import_preview_endpoint_lists_every_candidate(client, db_session):
    story, phase = _make_story(db_session, code="SELHTTP-3")
    source_subtask = _make_subtask(db_session, phase, "ST-SRC")
    target_subtask = _make_subtask(db_session, phase, "ST-DST")
    tc1 = _make_testcase(db_session, source_subtask, "TC-1")
    tc2 = _make_testcase(db_session, source_subtask, "TC-2")
    db_session.commit()

    payload = json.dumps(dump_testcases([tc1, tc2])).encode("utf-8")
    response = client.post(
        f"/subtasks/{target_subtask.id}/testcases/import-preview",
        files={"file": ("selected.json", payload, "application/json")},
    )
    assert response.status_code == 200
    assert "TC-1" in response.text
    assert "TC-2" in response.text


def test_import_confirm_endpoint_only_creates_selected_rows(client, db_session):
    story, phase = _make_story(db_session, code="SELHTTP-4")
    source_subtask = _make_subtask(db_session, phase, "ST-SRC")
    target_subtask = _make_subtask(db_session, phase, "ST-DST")
    tc1 = _make_testcase(db_session, source_subtask, "TC-1")
    tc2 = _make_testcase(db_session, source_subtask, "TC-2")
    db_session.commit()

    candidates = [dump_testcase(tc1)["testcase"], dump_testcase(tc2)["testcase"]]
    response = client.post(
        f"/subtasks/{target_subtask.id}/testcases/import-confirm",
        data={
            "candidates": [json.dumps(c) for c in candidates],
            "selected": ["0"],  # only TC-1
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/subtasks/{target_subtask.id}"

    db_session.expire_all()
    codes = {t.display_code for t in target_subtask.testcases}
    assert codes == {"TC-1"}


def test_import_confirm_endpoint_flashes_when_nothing_selected(client, db_session):
    story, phase = _make_story(db_session, code="SELHTTP-5")
    source_subtask = _make_subtask(db_session, phase, "ST-SRC")
    target_subtask = _make_subtask(db_session, phase, "ST-DST")
    tc = _make_testcase(db_session, source_subtask, "TC-1")
    db_session.commit()

    response = client.post(
        f"/subtasks/{target_subtask.id}/testcases/import-confirm",
        data={"candidates": [json.dumps(dump_testcase(tc)["testcase"])]},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/subtasks/{target_subtask.id}"

    db_session.expire_all()
    assert len(target_subtask.testcases) == 0

"""Copying selected test steps (with Test Data and screenshots) into a
section of another test case — app/step_copy.py and its route."""

import pytest

import app.routers.screenshots as screenshots_module
from app.models import (
    Phase, PhaseType, Screenshot, StepSection, Story, Subtask, SubtaskType, TestCase,
    TestCaseSection, TestCaseStep, TestCaseStepData, generate_internal_key,
)


@pytest.fixture(autouse=True)
def uploads(monkeypatch, tmp_path):
    monkeypatch.setattr(screenshots_module, "UPLOADS_DIR", tmp_path)
    return tmp_path


def _testcase(db, code):
    story = Story(display_code=f"{code}-S", title="S", internal_key=generate_internal_key())
    db.add(story)
    db.flush()
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db.add(phase)
    db.flush()
    subtask = Subtask(phase_id=phase.id, display_code=f"{code}-ST", title="ST",
                      internal_key=generate_internal_key(), subtask_type=SubtaskType.EXECUTION)
    db.add(subtask)
    db.flush()
    tc = TestCase(subtask_id=subtask.id, display_code=code, title=f"{code} title", internal_key=generate_internal_key())
    db.add(tc)
    db.flush()
    sections = {}
    for pos, kind in enumerate((StepSection.PRECONDITION, StepSection.MAIN, StepSection.POSTCONDITION)):
        sections[kind] = TestCaseSection(testcase_id=tc.id, kind=kind, position=pos)
        db.add(sections[kind])
    db.flush()
    return tc, sections


def _step(db, uploads, tc, section, no, text, data=(), shots=()):
    step = TestCaseStep(section_id=section.id, step_no=no, step_text=text,
                        expected_result=f"{text} expected", actual_result=f"{text} actual")
    db.add(step)
    db.flush()
    for order, (title, value, lang) in enumerate(data, start=1):
        db.add(TestCaseStepData(step_id=step.id, order_no=order, title=title, value=value, language=lang))
    for i, content in enumerate(shots):
        rel = f"screenshots/{tc.id}/{step.id}/shot{i}.png"
        (uploads / rel).parent.mkdir(parents=True, exist_ok=True)
        (uploads / rel).write_bytes(content)
        db.add(Screenshot(step_id=step.id, file_path=rel))
    db.flush()
    return step


def _rows(section):
    return [(s.step_no, s.step_text, s.expected_result, s.actual_result,
             [(d.order_no, d.title, d.value, d.language) for d in s.data_items], len(s.screenshots))
            for s in section.steps]


def test_copy_appends_selected_steps_with_data_and_screenshot_files(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-1")
    dst, dst_sections = _testcase(db_session, "DST-1")
    pre = src_sections[StepSection.PRECONDITION]
    s1 = _step(db_session, uploads, src, pre, 1, "check profile msisdn",
               data=[("query", "SELECT 1", "SQL"), ("curl", "curl x", "CURL")], shots=[b"img-1"])
    _step(db_session, uploads, src, pre, 2, "not selected")
    s3 = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "do token call", shots=[b"img-3a", b"img-3b"])
    target = dst_sections[StepSection.PRECONDITION]
    _step(db_session, uploads, dst, target, 1, "existing step")
    db_session.commit()

    resp = client.post(f"/testcases/{src.id}/steps/copy-to",
                       data={"section_id": str(target.id), "step_ids": [str(s3.id), str(s1.id)]},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert resp.headers["location"] == f"/testcases/{src.id}/execute"
    assert "Copied%202%20steps%20to%20DST-1" in resp.cookies.get("flash", "")

    db_session.expire_all()
    rows = _rows(db_session.get(TestCaseSection, target.id))
    # appended after the existing step, in the SOURCE page order (Pre Condition before Main)
    assert [r[:4] for r in rows] == [
        (1, "existing step", "existing step expected", "existing step actual"),
        (2, "check profile msisdn", "check profile msisdn expected", "check profile msisdn actual"),
        (3, "do token call", "do token call expected", "do token call actual"),
    ]
    assert rows[1][4] == [(1, "query", "SELECT 1", "SQL"), (2, "curl", "curl x", "CURL")]
    assert rows[2][5] == 2

    # screenshots are separate, byte-identical files under the destination
    copied = db_session.get(TestCaseSection, target.id).steps[2].screenshots
    assert [(uploads / s.file_path).read_bytes() for s in copied] == [b"img-3a", b"img-3b"]
    assert all(s.file_path.startswith(f"screenshots/{dst.id}/") for s in copied)


def test_copy_leaves_the_source_untouched(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-2")
    dst, dst_sections = _testcase(db_session, "DST-2")
    pre = src_sections[StepSection.PRECONDITION]
    s1 = _step(db_session, uploads, src, pre, 1, "a", data=[("t", "v", "TEXT")], shots=[b"x"])
    db_session.commit()
    before = _rows(pre)
    src_file = uploads / s1.screenshots[0].file_path

    client.post(f"/testcases/{src.id}/steps/copy-to",
                data={"section_id": str(dst_sections[StepSection.MAIN].id), "step_ids": [str(s1.id)]})

    db_session.expire_all()
    assert _rows(db_session.get(TestCaseSection, pre.id)) == before
    assert src_file.read_bytes() == b"x"


def test_copy_into_the_same_test_case_works(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-3")
    pre = src_sections[StepSection.PRECONDITION]
    s1 = _step(db_session, uploads, src, pre, 1, "a")
    db_session.commit()
    client.post(f"/testcases/{src.id}/steps/copy-to",
                data={"section_id": str(src_sections[StepSection.POSTCONDITION].id), "step_ids": [str(s1.id)]})
    db_session.expire_all()
    assert [s.step_text for s in db_session.get(TestCaseSection, src_sections[StepSection.POSTCONDITION].id).steps] == ["a"]


def test_copy_ignores_steps_that_are_not_on_the_source_page(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-4")
    other, other_sections = _testcase(db_session, "OTH-4")
    dst, dst_sections = _testcase(db_session, "DST-4")
    mine = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "mine")
    foreign = _step(db_session, uploads, other, other_sections[StepSection.MAIN], 1, "foreign")
    db_session.commit()

    client.post(f"/testcases/{src.id}/steps/copy-to",
                data={"section_id": str(dst_sections[StepSection.MAIN].id),
                      "step_ids": [str(mine.id), str(foreign.id), "999999"]})
    db_session.expire_all()
    assert [s.step_text for s in db_session.get(TestCaseSection, dst_sections[StepSection.MAIN].id).steps] == ["mine"]


def test_copy_with_unknown_section_or_nothing_selected_changes_nothing(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-5")
    s1 = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "a")
    db_session.commit()
    count = db_session.query(TestCaseStep).count()

    resp = client.post(f"/testcases/{src.id}/steps/copy-to", data={"section_id": "999999", "step_ids": [str(s1.id)]},
                       follow_redirects=False)
    assert resp.status_code == 303
    resp = client.post(f"/testcases/{src.id}/steps/copy-to",
                       data={"section_id": str(src_sections[StepSection.MAIN].id)}, follow_redirects=False)
    assert resp.status_code == 303
    db_session.expire_all()
    assert db_session.query(TestCaseStep).count() == count


def test_copy_skips_a_screenshot_whose_file_is_missing(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-6")
    dst, dst_sections = _testcase(db_session, "DST-6")
    s1 = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "a", shots=[b"keep", b"gone"])
    (uploads / s1.screenshots[1].file_path).unlink()
    db_session.commit()

    client.post(f"/testcases/{src.id}/steps/copy-to",
                data={"section_id": str(dst_sections[StepSection.MAIN].id), "step_ids": [str(s1.id)]})
    db_session.expire_all()
    copied = db_session.get(TestCaseSection, dst_sections[StepSection.MAIN].id).steps[0].screenshots
    assert [(uploads / s.file_path).read_bytes() for s in copied] == [b"keep"]


def test_sections_endpoint_lists_destination_sections(client, db_session, uploads):
    dst, dst_sections = _testcase(db_session, "DST-7")
    _step(db_session, uploads, dst, dst_sections[StepSection.PRECONDITION], 1, "x")
    db_session.commit()
    data = client.get(f"/testcases/{dst.id}/sections.json").json()
    assert [(s["id"], s["label"], s["step_count"]) for s in data["sections"]] == [
        (dst_sections[StepSection.PRECONDITION].id, "2. Pre Condition", 1),
        (dst_sections[StepSection.MAIN].id, "3. Main Test", 0),
        (dst_sections[StepSection.POSTCONDITION].id, "4. Post Condition", 0),
    ]


def test_execute_page_has_step_checkboxes_and_copy_dialog(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-8")
    s1 = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "a")
    db_session.commit()
    page = client.get(f"/testcases/{src.id}/execute").text
    assert f'data-step-select data-selection-name="step_ids" value="{s1.id}"' in page
    assert 'data-selection-actions="step_ids" hidden' in page
    assert f'action="/testcases/{src.id}/steps/copy-to"' in page

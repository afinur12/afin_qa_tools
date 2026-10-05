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


def _section(db, tc, kind, position):
    section = TestCaseSection(testcase_id=tc.id, kind=kind, position=position)
    db.add(section)
    db.flush()
    return section


def _texts(db, tc_id):
    """[(kind, [step texts])] per section of a test case, in page order."""
    db.expire_all()
    return [(s.kind, [st.step_text for st in s.steps]) for s in db.get(TestCase, tc_id).sections]


def test_copy_into_matching_sections_keeps_each_step_in_its_kind(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-11")
    dst, dst_sections = _testcase(db_session, "DST-11")
    p1 = _step(db_session, uploads, src, src_sections[StepSection.PRECONDITION], 1, "pre one",
               data=[("query", "SELECT 1", "SQL")], shots=[b"img-p1"])
    m1 = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "main one")
    m2 = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 2, "main two")
    q1 = _step(db_session, uploads, src, src_sections[StepSection.POSTCONDITION], 1, "post one")
    _step(db_session, uploads, dst, dst_sections[StepSection.MAIN], 1, "existing main")
    db_session.commit()

    resp = client.post(f"/testcases/{src.id}/steps/copy-to", data={
        "mode": "match", "dest_testcase_id": str(dst.id),
        "step_ids": [str(q1.id), str(m2.id), str(p1.id), str(m1.id)],
    }, follow_redirects=False)
    assert resp.status_code == 303
    assert "Copied%204%20steps%20to%20DST-11%20into%20matching%20sections" in resp.cookies.get("flash", "")

    assert _texts(db_session, dst.id) == [
        (StepSection.PRECONDITION, ["pre one"]),
        (StepSection.MAIN, ["existing main", "main one", "main two"]),
        (StepSection.POSTCONDITION, ["post one"]),
    ]
    copied = db_session.get(TestCaseSection, dst_sections[StepSection.PRECONDITION].id).steps[0]
    assert [(d.title, d.value) for d in copied.data_items] == [("query", "SELECT 1")]
    assert [(uploads / s.file_path).read_bytes() for s in copied.screenshots] == [b"img-p1"]


def test_matching_puts_the_second_main_into_the_second_main_and_adds_missing_sections(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-12")
    dst, dst_sections = _testcase(db_session, "DST-12")
    src_main2 = _section(db_session, src, StepSection.MAIN, 3)
    src_post2 = _section(db_session, src, StepSection.POSTCONDITION, 4)
    dst_main2 = _section(db_session, dst, StepSection.MAIN, 3)          # DST-12 has a 2nd Main but no 2nd Post
    a = _step(db_session, uploads, src, src_main2, 1, "second main step")
    b = _step(db_session, uploads, src, src_post2, 1, "second post step")
    db_session.commit()

    resp = client.post(f"/testcases/{src.id}/steps/copy-to", data={
        "mode": "match", "dest_testcase_id": str(dst.id), "step_ids": [str(a.id), str(b.id)],
    }, follow_redirects=False)
    assert "adding%201%20new%20section" in resp.cookies.get("flash", "")

    assert _texts(db_session, dst.id) == [
        (StepSection.PRECONDITION, []),
        (StepSection.MAIN, []),
        (StepSection.POSTCONDITION, []),
        (StepSection.MAIN, ["second main step"]),
        (StepSection.POSTCONDITION, ["second post step"]),   # added at the end
    ]
    assert db_session.get(TestCaseSection, dst_main2.id).steps[0].step_text == "second main step"


def _bare_testcase(db, code, *kinds):
    """A test case holding only the given sections, in that order."""
    tc, sections = _testcase(db, code)
    for section in sections.values():
        db.delete(section)
    db.flush()
    for position, kind in enumerate(kinds):
        _section(db, tc, kind, position)
    db.commit()
    return tc


def test_matching_into_a_blank_test_case_creates_the_sections_in_order(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-15")
    dst = _bare_testcase(db_session, "DST-15")
    ids = [
        _step(db_session, uploads, src, src_sections[kind], 1, f"{kind.value.lower()} step").id
        for kind in (StepSection.PRECONDITION, StepSection.MAIN, StepSection.POSTCONDITION)
    ]
    db_session.commit()
    resp = client.post(f"/testcases/{src.id}/steps/copy-to", data={
        "mode": "match", "dest_testcase_id": str(dst.id), "step_ids": [str(i) for i in ids],
    }, follow_redirects=False)
    assert "adding%203%20new%20sections" in resp.cookies.get("flash", "")
    assert _texts(db_session, dst.id) == [
        (StepSection.PRECONDITION, ["precondition step"]),
        (StepSection.MAIN, ["main step"]),
        (StepSection.POSTCONDITION, ["postcondition step"]),
    ]


def test_a_missing_section_is_added_where_it_belongs(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-16")
    dst = _bare_testcase(db_session, "DST-16", StepSection.MAIN, StepSection.POSTCONDITION)
    pre = _step(db_session, uploads, src, src_sections[StepSection.PRECONDITION], 1, "pre step")
    main = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "main step")
    db_session.commit()
    client.post(f"/testcases/{src.id}/steps/copy-to", data={
        "mode": "match", "dest_testcase_id": str(dst.id), "step_ids": [str(pre.id), str(main.id)],
    })
    assert _texts(db_session, dst.id) == [
        (StepSection.PRECONDITION, ["pre step"]),   # first, not after the Post Condition
        (StepSection.MAIN, ["main step"]),
        (StepSection.POSTCONDITION, []),
    ]


def test_delete_screenshots_of_the_selected_steps(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-17")
    other, other_sections = _testcase(db_session, "OTH-17")
    main = src_sections[StepSection.MAIN]
    a = _step(db_session, uploads, src, main, 1, "a", data=[("query", "SELECT 1", "SQL")], shots=[b"a1", b"a2"])
    b = _step(db_session, uploads, src, main, 2, "b", shots=[b"b1"])
    kept = _step(db_session, uploads, src, main, 3, "not ticked", shots=[b"c1"])
    foreign = _step(db_session, uploads, other, other_sections[StepSection.MAIN], 1, "other case", shots=[b"f1"])
    db_session.commit()
    gone = [uploads / s.file_path for s in a.screenshots + b.screenshots]

    resp = client.post(f"/testcases/{src.id}/steps/screenshots/delete",
                       data={"step_ids": [str(a.id), str(b.id), str(foreign.id)]}, follow_redirects=False)
    assert resp.status_code == 303 and resp.headers["location"] == f"/testcases/{src.id}/execute"
    assert "Deleted%203%20screenshots%20from%202%20steps" in resp.cookies.get("flash", "")

    db_session.expire_all()
    assert [len(db_session.get(TestCaseStep, s.id).screenshots) for s in (a, b, kept, foreign)] == [0, 0, 1, 1]
    assert not any(path.exists() for path in gone)
    assert [(d.title, d.value) for d in db_session.get(TestCaseStep, a.id).data_items] == [("query", "SELECT 1")]
    assert db_session.query(TestCaseStep).filter_by(section_id=main.id).count() == 3


def test_delete_screenshots_when_the_selected_steps_have_none(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-18")
    a = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "a")
    db_session.commit()
    resp = client.post(f"/testcases/{src.id}/steps/screenshots/delete", data={"step_ids": [str(a.id)]},
                       follow_redirects=False)
    assert resp.status_code == 303
    assert "have%20no%20screenshots" in resp.cookies.get("flash", "")


def test_execute_page_has_the_delete_screenshots_action(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-19")
    _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "a")
    db_session.commit()
    page = client.get(f"/testcases/{src.id}/execute").text
    assert f'action="/testcases/{src.id}/steps/screenshots/delete"' in page
    assert 'data-submit-selected="delete-step-screenshots" data-selection-name="step_ids"' in page


def test_matching_with_an_unknown_destination_changes_nothing(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-13")
    s1 = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "a")
    db_session.commit()
    count = db_session.query(TestCaseStep).count()
    resp = client.post(f"/testcases/{src.id}/steps/copy-to",
                       data={"mode": "match", "dest_testcase_id": "999999", "step_ids": [str(s1.id)]},
                       follow_redirects=False)
    assert resp.status_code == 303
    db_session.expire_all()
    assert db_session.query(TestCaseStep).count() == count
    assert db_session.query(TestCaseSection).filter_by(testcase_id=src.id).count() == 3


def test_copy_dialog_offers_matching_sections(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-14")
    _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "a")
    db_session.commit()
    page = client.get(f"/testcases/{src.id}/execute").text
    assert 'name="mode" value="match"' in page and 'name="mode" value="section"' in page
    assert 'name="dest_testcase_id"' in page


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


def test_execute_page_has_section_and_select_all_step_boxes(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-9")
    pre = src_sections[StepSection.PRECONDITION]
    _step(db_session, uploads, src, pre, 1, "a")
    _step(db_session, uploads, src, pre, 2, "b")
    db_session.commit()
    page = client.get(f"/testcases/{src.id}/execute").text
    assert f'data-section-select="{pre.id}"' in page
    assert f'data-section-select="{src_sections[StepSection.MAIN].id}"' not in page  # no steps, no box
    assert "data-select-all-steps" in page


def test_execute_page_without_steps_has_no_select_all_box(client, db_session, uploads):
    src, _ = _testcase(db_session, "SRC-10")
    db_session.commit()
    assert "data-select-all-steps" not in client.get(f"/testcases/{src.id}/execute").text


def test_execute_page_has_step_checkboxes_and_copy_dialog(client, db_session, uploads):
    src, src_sections = _testcase(db_session, "SRC-8")
    s1 = _step(db_session, uploads, src, src_sections[StepSection.MAIN], 1, "a")
    db_session.commit()
    page = client.get(f"/testcases/{src.id}/execute").text
    assert f'data-step-select data-selection-name="step_ids" value="{s1.id}"' in page
    assert 'data-selection-actions="step_ids" hidden' in page
    assert f'action="/testcases/{src.id}/steps/copy-to"' in page

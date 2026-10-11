def _create_execution_subtask(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    return sub_resp.headers["location"].rstrip("/").split("/")[-1]


def test_create_testcase_defaults_to_to_do(client):
    subtask_id = _create_execution_subtask(client, "EX-300")
    response = client.post(
        f"/subtasks/{subtask_id}/testcases",
        data={"display_code": "TC-1", "title": "Login works"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/subtasks/{subtask_id}")
    assert "TC-1" in detail.text
    assert "TO DO" in detail.text


def test_create_testcase_duplicate_code_within_subtask(client):
    subtask_id = _create_execution_subtask(client, "EX-301")
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    response = client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "B"})
    assert response.status_code == 422
    assert "already used" in response.text


def test_edit_testcase_code_and_title(client):
    subtask_id = _create_execution_subtask(client, "EX-303")
    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Old title"}, follow_redirects=False
    )
    testcase_id = tc_resp.headers["location"].rstrip("/").split("/")[-1]
    response = client.post(
        f"/testcases/{testcase_id}/edit", data={"display_code": "TC-1", "title": "New title"}, follow_redirects=False
    )
    assert response.status_code == 303
    assert response.headers["location"] == f"/testcases/{testcase_id}/execute"
    detail = client.get(f"/subtasks/{subtask_id}")
    assert "New title" in detail.text


def test_delete_testcase_cascades_to_its_steps(client):
    subtask_id = _create_execution_subtask(client, "EX-302")
    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"}, follow_redirects=False
    )
    testcase_id = tc_resp.headers["location"].rstrip("/").split("/")[-1]
    from app.database import SessionLocal  # noqa: F401 (import kept minimal; step insert below uses raw SQL-free ORM via app import)
    import app.models as m
    from app.database import get_db
    from app.main import app as fastapi_app
    override = fastapi_app.dependency_overrides[get_db]
    gen = override()
    db = next(gen)
    section = m.TestCaseSection(testcase_id=int(testcase_id), kind=m.StepSection.MAIN, position=0)
    db.add(section)
    db.commit()
    section_id = section.id
    db.add(m.TestCaseStep(section_id=section_id, step_no=1, step_text="x"))
    db.commit()
    gen.close()

    # Deleting a case takes its steps with it -- no need to clear them first.
    response = client.post(f"/testcases/{testcase_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert client.get(f"/testcases/{testcase_id}/execute").status_code == 404

    gen = override()
    db = next(gen)
    assert db.query(m.TestCaseSection).filter_by(testcase_id=int(testcase_id)).count() == 0
    assert db.query(m.TestCaseStep).filter_by(section_id=section_id).count() == 0
    gen.close()


def test_selection_toolbar_rendered_hidden_and_only_when_testcases_exist(client):
    subtask_id = _create_execution_subtask(client, "EX-304")
    empty_page = client.get(f"/subtasks/{subtask_id}").text
    assert "/testcases/delete-selected" not in empty_page
    assert "/testcases/clear-all" not in empty_page

    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    populated_page = client.get(f"/subtasks/{subtask_id}").text
    assert f'action="/subtasks/{subtask_id}/testcases/delete-selected"' in populated_page
    assert '<div class="selection-actions" data-selection-actions="testcase_ids" hidden>' in populated_page
    assert "/testcases/clear-all" not in populated_page  # replaced by delete-selected
    # New and Import stay outside the selection-only group
    toolbar_start = populated_page.index('data-selection-actions="testcase_ids"')
    assert populated_page.index('data-modal-open="import-testcase"') > populated_page.index("</div>", toolbar_start)


def _add_testcase(client, db_session, subtask_id, code):
    import app.models as m

    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": code, "title": code})
    db_session.expire_all()
    return db_session.query(m.TestCase).filter_by(subtask_id=int(subtask_id), display_code=code).one().id


def test_delete_selected_removes_only_ticked_cases_and_cascades_to_steps(client, db_session):
    import app.models as m

    subtask_id = _create_execution_subtask(client, "EX-305")
    tc1 = _add_testcase(client, db_session, subtask_id, "TC-1")
    tc2 = _add_testcase(client, db_session, subtask_id, "TC-2")
    tc3 = _add_testcase(client, db_session, subtask_id, "TC-3")
    section = m.TestCaseSection(testcase_id=tc1, kind=m.StepSection.MAIN, position=0)
    db_session.add(section)
    db_session.commit()
    db_session.add(m.TestCaseStep(section_id=section.id, step_no=1, step_text="x"))
    db_session.commit()

    response = client.post(
        f"/subtasks/{subtask_id}/testcases/delete-selected",
        data={"testcase_ids": [str(tc1), str(tc3)]}, follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"].rstrip("/") == f"/subtasks/{subtask_id}"
    assert "Deleted%202%20test%20cases" in response.cookies.get("flash", "")

    db_session.expire_all()
    remaining = {t.id for t in db_session.query(m.TestCase).filter_by(subtask_id=int(subtask_id))}
    assert remaining == {tc2}
    assert db_session.query(m.TestCaseSection).filter_by(testcase_id=tc1).count() == 0


def test_delete_selected_ignores_ids_from_another_subtask(client, db_session):
    import app.models as m

    subtask_a = _create_execution_subtask(client, "EX-306")
    subtask_b = _create_execution_subtask(client, "EX-307")
    own = _add_testcase(client, db_session, subtask_a, "TC-1")
    other = _add_testcase(client, db_session, subtask_b, "TC-1")

    client.post(f"/subtasks/{subtask_a}/testcases/delete-selected", data={"testcase_ids": [str(own), str(other)]})

    db_session.expire_all()
    assert db_session.get(m.TestCase, own) is None
    assert db_session.get(m.TestCase, other) is not None


def test_delete_selected_with_nothing_ticked_deletes_nothing(client, db_session):
    import app.models as m

    subtask_id = _create_execution_subtask(client, "EX-308")
    tc = _add_testcase(client, db_session, subtask_id, "TC-1")
    response = client.post(f"/subtasks/{subtask_id}/testcases/delete-selected", follow_redirects=False)
    assert response.status_code == 303
    db_session.expire_all()
    assert db_session.get(m.TestCase, tc) is not None


def test_delete_selected_route_404s_for_unknown_subtask(client):
    response = client.post("/subtasks/999999/testcases/delete-selected")
    assert response.status_code == 404


def test_status_dropdown_offers_to_do_and_back_log(client):
    from app.models import TestCaseStatus

    assert [s.value for s in TestCaseStatus] == [
        "TO_DO", "IN_PROGRESS", "BACK_LOG", "PASS", "FAIL", "BLOCKED", "CANCELLED", "POSTPONED",
    ]
    # Underscores are an implementation detail; the UI shows them spaced.
    assert TestCaseStatus.TO_DO.label == "TO DO"
    assert TestCaseStatus.BACK_LOG.label == "BACK LOG"

    subtask_id = _create_execution_subtask(client, "EX-310")
    tc = client.post(
        f"/subtasks/{subtask_id}/testcases",
        data={"display_code": "TC-1", "title": "A"},
        follow_redirects=False,
    )
    import re
    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)

    page = client.get(f"/testcases/{testcase_id}/execute").text
    assert '<option value="TO_DO" selected>TO DO</option>' in page
    assert '<option value="BACK_LOG" >BACK LOG</option>' in page


def test_status_can_be_set_to_back_log(client):
    import re

    subtask_id = _create_execution_subtask(client, "EX-311")
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)

    response = client.post(
        f"/testcases/{testcase_id}/section1",
        data={"status": "BACK_LOG", "iteration": "1"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert "BACK LOG" in client.get(f"/subtasks/{subtask_id}").text


def _bulk_edit(client, subtask_id, ids, **fields):
    return client.post(
        f"/subtasks/{subtask_id}/testcases/bulk-edit",
        data={"testcase_ids": [str(i) for i in ids], **fields}, follow_redirects=False,
    )


def _flash(response):
    from urllib.parse import unquote

    return unquote(response.cookies.get("flash", "")), response.cookies.get("flash_type", "")


def _user(client, db_session, name, kind="TESTER"):
    import app.models as m

    client.post("/settings/users", data={"name": name, "type": kind})
    db_session.expire_all()
    return db_session.query(m.User).filter_by(name=name).one().id


def test_bulk_edit_sets_the_status_of_selected_test_cases(client, db_session):
    import app.models as m

    subtask_id = _create_execution_subtask(client, "EX-340")
    tc1 = _add_testcase(client, db_session, subtask_id, "TC-1")
    tc2 = _add_testcase(client, db_session, subtask_id, "TC-2")
    tc3 = _add_testcase(client, db_session, subtask_id, "TC-3")

    response = _bulk_edit(client, subtask_id, [tc1, tc3], status="PASS")
    assert response.status_code == 303
    assert response.headers["location"].rstrip("/") == f"/subtasks/{subtask_id}"
    assert _flash(response) == ("Updated 2 test cases: status PASS.", "success")

    db_session.expire_all()
    status = {t.id: t.status for t in db_session.query(m.TestCase).filter_by(subtask_id=int(subtask_id))}
    assert status == {tc1: m.TestCaseStatus.PASS, tc2: m.TestCaseStatus.TO_DO, tc3: m.TestCaseStatus.PASS}


def test_bulk_edit_sets_assignee_iteration_and_costs_together(client, db_session):
    import app.models as m

    subtask_id = _create_execution_subtask(client, "EX-341")
    tc1 = _add_testcase(client, db_session, subtask_id, "TC-1")
    tess = _user(client, db_session, "Tess Tester")

    response = _bulk_edit(client, subtask_id, [tc1], assignee_id=str(tess), iteration=" 3 ",
                          planned_cost="15000", actual_cost="12000")
    assert _flash(response) == (
        "Updated 1 test case: assignee Tess Tester, iteration 3, planned cost 15000, actual cost 12000.", "success",
    )
    db_session.expire_all()
    tc = db_session.get(m.TestCase, tc1)
    assert (tc.assignee_id, tc.iteration, tc.number_of_iteration, tc.planned_cost, tc.actual_cost) == (tess, "3", 3, "15000", "12000")
    assert tc.status == m.TestCaseStatus.TO_DO  # left on "keep"


def test_bulk_edit_leaves_every_field_left_on_keep_alone(client, db_session):
    import app.models as m

    subtask_id = _create_execution_subtask(client, "EX-342")
    tc1 = _add_testcase(client, db_session, subtask_id, "TC-1")
    tess = _user(client, db_session, "Tess Tester")
    tc = db_session.get(m.TestCase, tc1)
    tc.assignee_id, tc.iteration, tc.number_of_iteration, tc.planned_cost, tc.actual_cost = tess, "2", 2, "500", "400"
    db_session.commit()

    _bulk_edit(client, subtask_id, [tc1], status="FAIL", assignee_id="", iteration="", planned_cost="  ", actual_cost="")
    db_session.expire_all()
    tc = db_session.get(m.TestCase, tc1)
    assert tc.status == m.TestCaseStatus.FAIL
    assert (tc.assignee_id, tc.iteration, tc.number_of_iteration, tc.planned_cost, tc.actual_cost) == (tess, "2", 2, "500", "400")


def test_bulk_edit_can_clear_the_assignee(client, db_session):
    import app.models as m

    subtask_id = _create_execution_subtask(client, "EX-343")
    tc1 = _add_testcase(client, db_session, subtask_id, "TC-1")
    tc = db_session.get(m.TestCase, tc1)
    tc.assignee_id = _user(client, db_session, "Tess Tester")
    db_session.commit()

    response = _bulk_edit(client, subtask_id, [tc1], assignee_id="none")
    assert _flash(response) == ("Updated 1 test case: assignee nobody.", "success")
    db_session.expire_all()
    assert db_session.get(m.TestCase, tc1).assignee_id is None


def test_bulk_edit_refuses_bad_input_and_changes_nothing(client, db_session):
    import app.models as m

    subtask_id = _create_execution_subtask(client, "EX-344")
    tc1 = _add_testcase(client, db_session, subtask_id, "TC-1")
    cases = [
        ({"status": "PASS", "iteration": "abc"}, "Iteration must be a whole number, 1 or more."),
        ({"status": "PASS", "iteration": "0"}, "Iteration must be a whole number, 1 or more."),
        ({"status": "DONE"}, "Pick a valid status."),
        ({"assignee_id": "999999"}, "That assignee no longer exists."),
        ({"planned_cost": "x" * 65}, "Costs can be at most 64 characters."),
        ({}, "Pick at least one thing to change."),
    ]
    for fields, message in cases:
        response = _bulk_edit(client, subtask_id, [tc1], **fields)
        assert response.status_code == 303
        assert _flash(response) == (message, "danger"), fields
    db_session.expire_all()
    tc = db_session.get(m.TestCase, tc1)
    assert (tc.status, tc.assignee_id, tc.iteration, tc.planned_cost) == (m.TestCaseStatus.TO_DO, None, "1", None)


def test_bulk_edit_ignores_ids_from_another_subtask(client, db_session):
    import app.models as m

    subtask_a = _create_execution_subtask(client, "EX-345")
    subtask_b = _create_execution_subtask(client, "EX-346")
    own = _add_testcase(client, db_session, subtask_a, "TC-1")
    other = _add_testcase(client, db_session, subtask_b, "TC-2")
    _bulk_edit(client, subtask_a, [own, other], status="IN_PROGRESS")
    db_session.expire_all()
    assert db_session.get(m.TestCase, own).status == m.TestCaseStatus.IN_PROGRESS
    assert db_session.get(m.TestCase, other).status == m.TestCaseStatus.TO_DO
    assert _flash(_bulk_edit(client, subtask_a, [other], status="PASS")) == ("No test cases selected.", "danger")


def test_subtask_page_offers_edit_selected(client, db_session):
    import app.models as m

    subtask_id = _create_execution_subtask(client, "EX-347")
    tc1 = _add_testcase(client, db_session, subtask_id, "TC-1")
    tc = db_session.get(m.TestCase, tc1)
    tc.planned_cost, tc.iteration = "15000", "2"
    db_session.commit()

    page = client.get(f"/subtasks/{subtask_id}").text
    assert "data-bulk-edit-open" in page and 'id="bulk-edit"' in page
    assert f'action="/subtasks/{subtask_id}/testcases/bulk-edit"' in page
    assert '<option value="PASS">PASS</option>' in page and '<option value="none">' in page
    # each row carries what the dialog's "Now:" hints summarise
    assert 'data-bulk-status="TO DO"' in page and 'data-bulk-iteration="2"' in page
    assert 'data-bulk-planned="15000"' in page and 'data-bulk-assignee=""' in page
    assert "/testcases/set-status" not in page and "data-bulk-status-value" not in page

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

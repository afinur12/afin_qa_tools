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


def test_create_testcase_defaults_to_not_run(client):
    subtask_id = _create_execution_subtask(client, "EX-300")
    response = client.post(
        f"/subtasks/{subtask_id}/testcases",
        data={"display_code": "TC-1", "title": "Login works"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/subtasks/{subtask_id}")
    assert "TC-1" in detail.text
    assert "NOT_RUN" in detail.text


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


def test_delete_testcase_blocked_when_steps_exist(client):
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
    db.add(m.TestCaseStep(testcase_id=int(testcase_id), section=m.StepSection.MAIN, step_no=1, step_text="x"))
    db.commit()
    gen.close()

    response = client.post(f"/testcases/{testcase_id}/delete")
    assert response.status_code == 422

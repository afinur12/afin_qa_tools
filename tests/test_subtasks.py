def _create_story_and_phase(client, code="EX-200", phase_type="SIT"):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    phase_resp = client.post(f"/stories/{story_id}/phases", data={"type": phase_type}, follow_redirects=False)
    story_page = client.get(f"/stories/{story_id}")
    import re
    phase_id = re.search(r'/phases/(\d+)/subtasks/new', story_page.text)
    return story_id, phase_id


def test_create_subtask(client):
    create = client.post("/stories", data={"display_code": "EX-201", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    from app.database import SessionLocal  # noqa
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    response = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "SIT Planning", "subtask_type": "TEST_PLANNING"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_staging_after_rollback_restricts_to_single_execution_subtask(client):
    create = client.post("/stories", data={"display_code": "EX-202", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "STAGING_AFTER_ROLLBACK"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    rejected = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Planning", "subtask_type": "TEST_PLANNING"},
    )
    assert rejected.status_code == 422

    accepted = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Execution", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    assert accepted.status_code == 303

    second = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-2", "title": "Execution 2", "subtask_type": "EXECUTION"},
    )
    assert second.status_code == 422


def test_delete_subtask_blocked_when_testcase_exists(client):
    create = client.post("/stories", data={"display_code": "EX-203", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    response = client.post(f"/subtasks/{subtask_id}/delete")
    assert response.status_code == 422
    assert "Delete" in response.text

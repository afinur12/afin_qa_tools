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


def test_create_bug_with_defaults(client):
    subtask_id = _create_execution_subtask(client, "EX-600")
    response = client.post(
        f"/subtasks/{subtask_id}/bugs",
        data={"display_code": "B-1", "title": "[ISSUE] OTP fails", "description": "steps..."},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert "MEDIUM" in detail.text
    assert "OPEN" in detail.text


def test_create_bug_duplicate_code_within_subtask(client):
    subtask_id = _create_execution_subtask(client, "EX-601")
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"})
    response = client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] b"})
    assert response.status_code == 422


def test_edit_bug_severity_and_status(client):
    subtask_id = _create_execution_subtask(client, "EX-602")
    create = client.post(
        f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"}, follow_redirects=False
    )
    bug_id = create.headers["location"].rstrip("/").split("/")[-1]
    response = client.post(
        f"/bugs/{bug_id}/edit",
        data={
            "display_code": "B-1", "title": "[ISSUE] a", "description": "updated",
            "severity": "HIGH", "status": "IN_PROGRESS",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/bugs/{bug_id}")
    assert "HIGH" in detail.text
    assert "IN PROGRESS" in detail.text, "status badge should show a space, not the raw enum underscore"


def test_bug_list_route(client):
    subtask_id = _create_execution_subtask(client, "EX-603")
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"})
    response = client.get("/bugs")
    assert response.status_code == 200
    assert "B-1" in response.text


def test_bug_list_shows_tracker_link(client):
    subtask_id = _create_execution_subtask(client, "EX-604")
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-2", "title": "[ISSUE] a"})
    response = client.get("/bugs")
    assert "https://collabs.xlsmart.co.id/browse/B-2" in response.text


def test_create_bug_with_assignee_tester_developer_and_labels(client):
    import re

    subtask_id = _create_execution_subtask(client, "EX-610")
    client.post("/settings/users", data={"name": "Bug Tester", "type": "TESTER"})
    tester_id = re.search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    client.post("/settings/users", data={"name": "Bug Dev", "type": "DEVELOPER"})
    developer_id = re.search(
        r'value="Bug Dev"[\s\S]*?/settings/users/(\d+)/delete', client.get("/settings/users").text
    ).group(1)
    client.post("/settings/labels", data={"name": "crash"})
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    response = client.post(
        f"/subtasks/{subtask_id}/bugs",
        data={
            "display_code": "B-1", "title": "[ISSUE] a",
            "assignee_id": tester_id, "tester_id": tester_id, "developer_id": developer_id,
            "label_ids": [label_id],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert "Bug Tester" in page.text
    assert "Bug Dev" in page.text
    assert "crash" in page.text


def test_edit_bug_updates_assignee_tester_developer_and_labels(client):
    import re

    subtask_id = _create_execution_subtask(client, "EX-611")
    create = client.post(
        f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"}, follow_redirects=False
    )
    bug_id = create.headers["location"].rstrip("/").split("/")[-1]

    client.post("/settings/users", data={"name": "Later Bug Tester", "type": "TESTER"})
    tester_id = re.search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    client.post("/settings/labels", data={"name": "p1"})
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    response = client.post(
        f"/bugs/{bug_id}/edit",
        data={
            "display_code": "B-1", "title": "[ISSUE] a", "description": "",
            "severity": "HIGH", "status": "OPEN",
            "tester_id": tester_id, "label_ids": [label_id],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/bugs/{bug_id}")
    assert "Later Bug Tester" in page.text
    assert "p1" in page.text

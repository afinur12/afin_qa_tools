def test_create_story(client):
    response = client.post("/stories", data={"display_code": "EX-100", "title": "Payments"}, follow_redirects=False)
    assert response.status_code == 303
    detail = client.get(response.headers["location"])
    assert detail.status_code == 200
    assert "EX-100" in detail.text
    assert "Payments" in detail.text


def test_create_story_duplicate_code_shows_inline_error(client):
    client.post("/stories", data={"display_code": "EX-101", "title": "A"})
    response = client.post("/stories", data={"display_code": "EX-101", "title": "B"})
    assert response.status_code == 422
    assert "already used" in response.text
    assert 'value="B"' in response.text


def test_delete_story_blocked_when_phase_exists(client):
    create = client.post("/stories", data={"display_code": "EX-102", "title": "A"}, follow_redirects=False)
    story_url = create.headers["location"]
    story_id = story_url.rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    response = client.post(f"/stories/{story_id}/delete")
    assert response.status_code == 422
    assert "Delete" in response.text


def test_create_phase_rejects_duplicate_type(client):
    create = client.post("/stories", data={"display_code": "EX-103", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    first = client.post(f"/stories/{story_id}/phases", data={"type": "SIT"}, follow_redirects=False)
    assert first.status_code == 303
    second = client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    assert second.status_code == 422


def test_delete_empty_phase_succeeds(client):
    create = client.post("/stories", data={"display_code": "EX-104", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    response = client.post(f"/phases/{phase_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].rstrip("/") == f"/stories/{story_id}"

    story_page_after = client.get(f"/stories/{story_id}")
    assert 'id="SIT"' not in story_page_after.text
    assert f"#SIT" not in story_page_after.text

    # With the phase gone, the story itself can now be deleted.
    delete_story = client.post(f"/stories/{story_id}/delete", follow_redirects=False)
    assert delete_story.status_code == 303


def test_delete_phase_blocked_when_subtasks_exist(client):
    create = client.post("/stories", data={"display_code": "EX-105", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
    )

    response = client.post(f"/phases/{phase_id}/delete")
    assert response.status_code == 422
    assert "Delete" in response.text

    # The phase must still exist (delete was blocked, not silently no-op'd).
    story_page_after = client.get(f"/stories/{story_id}")
    assert "SIT" in story_page_after.text


def test_delete_phase_not_found_returns_404(client):
    response = client.post("/phases/999999/delete")
    assert response.status_code == 404


def test_edit_story_status(client):
    create = client.post("/stories", data={"display_code": "EX-106", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]

    response = client.post(
        f"/stories/{story_id}/edit",
        data={"display_code": "EX-106", "title": "A", "status": "DONE"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/stories/{story_id}")
    assert "DONE" in detail.text

    listing = client.get("/stories")
    assert "DONE" in listing.text


def test_edit_story_status_in_progress(client):
    create = client.post("/stories", data={"display_code": "EX-107", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]

    response = client.post(
        f"/stories/{story_id}/edit",
        data={"display_code": "EX-107", "title": "A", "status": "IN_PROGRESS"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/stories/{story_id}")
    assert "IN PROGRESS" in detail.text

    listing = client.get("/stories")
    assert "IN PROGRESS" in listing.text


def test_story_list_shows_tracker_link(client):
    client.post("/stories", data={"display_code": "EX-108", "title": "A"})
    response = client.get("/stories")
    assert "https://collabs.xlsmart.co.id/browse/EX-108" in response.text


def test_story_detail_shows_tracker_link_for_subtask(client):
    create = client.post("/stories", data={"display_code": "EX-109", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
    )
    detail = client.get(f"/stories/{story_id}")
    assert "https://collabs.xlsmart.co.id/browse/S-1" in detail.text


def test_edit_story_rejects_invalid_status(client):
    create = client.post("/stories", data={"display_code": "EX-107", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]

    response = client.post(
        f"/stories/{story_id}/edit",
        data={"display_code": "EX-107", "title": "A", "status": "NOT_A_STATUS"},
    )
    assert response.status_code == 422


def test_create_story_with_assignee_tester_developer_and_labels(client):
    client.post("/settings/users", data={"name": "Tess Tester", "type": "TESTER"})
    tester_id = __import__("re").search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    client.post("/settings/users", data={"name": "Dave Dev", "type": "DEVELOPER"})
    developer_id = __import__("re").search(
        r'value="Dave Dev"[\s\S]*?/settings/users/(\d+)/delete', client.get("/settings/users").text
    ).group(1)
    client.post("/settings/labels", data={"name": "regression"})
    label_id = __import__("re").search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    response = client.post(
        "/stories",
        data={
            "display_code": "EX-110", "title": "A",
            "assignee_id": tester_id, "tester_id": tester_id, "developer_id": developer_id,
            "label_ids": [label_id],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert "Tess Tester" in page.text
    assert "Dave Dev" in page.text
    assert "regression" in page.text


def test_edit_story_updates_assignee_tester_developer_and_labels(client):
    import re

    create = client.post("/stories", data={"display_code": "EX-111", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]

    client.post("/settings/users", data={"name": "Later Tester", "type": "TESTER"})
    tester_id = re.search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    client.post("/settings/labels", data={"name": "smoke"})
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    response = client.post(
        f"/stories/{story_id}/edit",
        data={
            "display_code": "EX-111", "title": "A", "status": "TO_DO",
            "tester_id": tester_id, "label_ids": [label_id],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/stories/{story_id}")
    assert "Later Tester" in page.text
    assert "smoke" in page.text


def test_story_tester_dropdown_excludes_developers(client):
    client.post("/settings/users", data={"name": "Only Dev", "type": "DEVELOPER"})
    page = client.get("/stories/new")
    # The create-form Tester <select> must not offer a Developer-typed user.
    # (Story's create form always shows Tester per this task, unlike Status
    # which stays edit-only — see Task 5's design note.)
    assert 'name="tester_id"' in page.text
    tester_select = page.text.split('name="tester_id"')[1].split("</select>")[0]
    assert "Only Dev" not in tester_select

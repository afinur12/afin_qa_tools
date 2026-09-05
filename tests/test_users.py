"""Settings: managing the User master-data table (Tester/Developer)."""
import re


def test_create_and_list_user(client):
    response = client.post("/settings/users", data={"name": "Jane Doe", "type": "TESTER"}, follow_redirects=False)
    assert response.status_code == 303
    page = client.get("/settings/users")
    assert "Jane Doe" in page.text
    assert "Tester" in page.text


def test_create_rejects_blank_name(client):
    response = client.post("/settings/users", data={"name": "  ", "type": "TESTER"})
    assert response.status_code == 422


def test_create_rejects_invalid_type(client):
    response = client.post("/settings/users", data={"name": "Jane Doe", "type": "MANAGER"})
    assert response.status_code == 422


def test_create_rejects_duplicate_name(client):
    client.post("/settings/users", data={"name": "Jane Doe", "type": "TESTER"})
    response = client.post("/settings/users", data={"name": "Jane Doe", "type": "DEVELOPER"})
    assert response.status_code == 422
    assert "already exists" in response.text


def test_rename_user(client):
    client.post("/settings/users", data={"name": "Jane Doe", "type": "TESTER"})
    page = client.get("/settings/users")
    user_id = re.search(r"/settings/users/(\d+)/edit", page.text).group(1)

    response = client.post(f"/settings/users/{user_id}/edit", data={"name": "Jane D."}, follow_redirects=False)
    assert response.status_code == 303
    page_after = client.get("/settings/users")
    assert "Jane D." in page_after.text
    assert "Jane Doe" not in page_after.text


def test_rename_does_not_change_type(client):
    client.post("/settings/users", data={"name": "Jane Doe", "type": "DEVELOPER"})
    page = client.get("/settings/users")
    user_id = re.search(r"/settings/users/(\d+)/edit", page.text).group(1)

    client.post(f"/settings/users/{user_id}/edit", data={"name": "Jane D."})
    page_after = client.get("/settings/users")
    assert "Developer" in page_after.text


def test_delete_unused_user_succeeds(client):
    client.post("/settings/users", data={"name": "Unused Person", "type": "TESTER"})
    page = client.get("/settings/users")
    user_id = re.search(r"/settings/users/(\d+)/delete", page.text).group(1)

    response = client.post(f"/settings/users/{user_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert "Unused Person" not in client.get("/settings/users").text


def test_delete_blocked_when_referenced_by_story(client, db_session):
    from app.models import Story

    client.post("/settings/users", data={"name": "Busy Person", "type": "TESTER"})
    user_id = re.search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    create = client.post("/stories", data={"display_code": "EX-900", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    story = db_session.get(Story, int(story_id))
    story.tester_id = int(user_id)
    db_session.commit()

    response = client.post(f"/settings/users/{user_id}/delete")
    assert response.status_code == 422
    assert "Busy Person" in client.get("/settings/users").text


def test_nav_and_tabs_show_users(client):
    page = client.get("/settings/services")
    assert 'href="/settings/users"' in page.text
    users_page = client.get("/settings/users")
    assert 'href="/settings/services"' in users_page.text  # tab bar links back the other way too


def test_create_user_with_jira_username(client):
    response = client.post(
        "/settings/users",
        data={"name": "Jane Doe", "type": "TESTER", "jira_username": "ADL.JANED"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get("/settings/users")
    assert "ADL.JANED" in page.text


def test_create_user_without_jira_username_leaves_it_blank(client):
    client.post("/settings/users", data={"name": "No Username", "type": "TESTER"})
    page = client.get("/settings/users")
    assert "No Username" in page.text


def test_rename_user_updates_jira_username(client):
    client.post("/settings/users", data={"name": "Jane Doe", "type": "TESTER", "jira_username": "ADL.OLD"})
    page = client.get("/settings/users")
    user_id = re.search(r"/settings/users/(\d+)/edit", page.text).group(1)

    response = client.post(
        f"/settings/users/{user_id}/edit",
        data={"name": "Jane Doe", "jira_username": "ADL.NEW"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    page_after = client.get("/settings/users")
    assert "ADL.NEW" in page_after.text
    assert "ADL.OLD" not in page_after.text

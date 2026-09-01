"""Note Section: freeform snippets (curl, SQL, JSON, ...) attached to a
story or subtask, stored verbatim."""
import html
import re


def test_create_note_attached_to_story(client):
    create = client.post("/stories", data={"display_code": "EX-700", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    response = client.post(
        "/notes",
        data={
            "attach_type": "STORY", "attach_id": story_id,
            "language": "CURL", "content": "curl https://api.example.com/health", "remark": "Health check",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    story_page = client.get(f"/stories/{story_id}")
    assert "api.example.com/health" in story_page.text
    assert "Health check" in story_page.text
    assert "CURL" in story_page.text


def test_note_panel_displays_content_verbatim(client):
    create = client.post("/stories", data={"display_code": "EX-702", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    content = "SELECT * FROM users WHERE id = 1;"
    client.post("/notes", data={"attach_type": "STORY", "attach_id": story_id, "language": "SQL", "content": content})
    story_page = client.get(f"/stories/{story_id}")
    assert content in story_page.text
    assert "SQL" in story_page.text


def test_note_without_remark_has_no_remark_shown(client):
    create = client.post("/stories", data={"display_code": "EX-705", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post("/notes", data={"attach_type": "STORY", "attach_id": story_id, "language": "JSON", "content": "{}"})
    story_page = client.get(f"/stories/{story_id}")
    assert "JSON" in story_page.text


def test_delete_note(client):
    create = client.post("/stories", data={"display_code": "EX-701", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post("/notes", data={"attach_type": "STORY", "attach_id": story_id, "language": "CURL", "content": "curl https://api.example.com/health"})
    story_page = client.get(f"/stories/{story_id}")
    note_id = re.search(r"/notes/(\d+)/delete", story_page.text).group(1)
    response = client.post(f"/notes/{note_id}/delete", data={"attach_type": "STORY", "attach_id": story_id}, follow_redirects=False)
    assert response.status_code == 303
    story_page2 = client.get(f"/stories/{story_id}")
    assert "api.example.com/health" not in story_page2.text


def test_update_note_saves_content_remark_and_language(client):
    create = client.post("/stories", data={"display_code": "EX-720", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post("/notes", data={"attach_type": "STORY", "attach_id": story_id, "language": "TEXT", "content": "old text"})
    story_page = client.get(f"/stories/{story_id}")
    note_id = re.search(r"/notes/(\d+)/delete", story_page.text).group(1)

    response = client.post(
        f"/notes/{note_id}",
        data={"language": "JSON", "content": '{"key": "value"}', "remark": "Now JSON"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    story_page2 = html.unescape(client.get(f"/stories/{story_id}").text)
    assert '{"key": "value"}' in story_page2
    assert "Now JSON" in story_page2
    assert "old text" not in story_page2


def test_update_note_returns_404_for_unknown_note(client):
    response = client.post("/notes/999999", data={"content": "x"})
    assert response.status_code == 404


def _make_subtask(client, code="EX-710"):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    page = client.get(f"/stories/{story_id}")
    phase_id = page.text.split("/subtasks/new")[0].split("/phases/")[-1]
    sub = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    return sub.headers["location"].rstrip("/").split("/")[-1]


def test_note_attached_to_subtask(client):
    subtask_id = _make_subtask(client)
    client.post(
        "/notes",
        data={"attach_type": "SUBTASK", "attach_id": subtask_id, "language": "YAML", "content": "key: value"},
        follow_redirects=False,
    )
    subtask_page = client.get(f"/subtasks/{subtask_id}")
    assert "key: value" in subtask_page.text
    assert "YAML" in subtask_page.text

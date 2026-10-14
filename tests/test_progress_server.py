"""Server pieces the loading / progress UI relies on: every import ends in a
redirect the browser can follow after a background upload, and zip downloads
say how big they are so a download can show a real percentage."""

import pytest


@pytest.fixture(autouse=True)
def import_stash(monkeypatch, tmp_path):
    """Keep import-preview stash files out of the real app/uploads."""
    import app.routers.testcases as testcases_router

    stash = tmp_path / "import_tmp"
    monkeypatch.setattr(testcases_router, "_import_stash_dir", lambda: stash)
    return stash


def _execution_subtask(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    phase_id = client.get(f"/stories/{story_id}").text.split("/subtasks/new")[0].split("/phases/")[-1]
    sub = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    return story_id, sub.headers["location"].rstrip("/").split("/")[-1]


def _testcases_export(client, subtask_id):
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login"})
    page = client.get(f"/subtasks/{subtask_id}").text
    tc_id = page.split('data-selection-name="testcase_ids" value="')[1].split('"')[0]
    return client.post(f"/subtasks/{subtask_id}/testcases/export-selected", data={"testcase_ids": [tc_id]}).content


def test_import_preview_redirects_to_a_page_that_shows_the_preview(client):
    _, source = _execution_subtask(client, "EX-970")
    _, target = _execution_subtask(client, "EX-971")
    payload = _testcases_export(client, source)

    response = client.post(f"/subtasks/{target}/testcases/import-preview",
                           files={"file": ("selected.json", payload, "application/json")}, follow_redirects=False)
    assert response.status_code == 303
    location = response.headers["location"]
    assert location.startswith(f"/subtasks/{target}/testcases/import-preview/")
    page = client.get(location)
    assert page.status_code == 200 and "TC-1" in page.text
    token = location.rsplit("/", 1)[1]
    assert f'name="token" value="{token}"' in page.text
    # Opening it again (a refresh) still shows the same preview.
    assert "TC-1" in client.get(location).text


def test_an_unknown_or_expired_preview_sends_you_back_with_a_message(client):
    from urllib.parse import unquote

    _, target = _execution_subtask(client, "EX-972")
    for token in ("0" * 32, "not-a-token"):
        response = client.get(f"/subtasks/{target}/testcases/import-preview/{token}", follow_redirects=False)
        assert response.status_code == 303 and response.headers["location"] == f"/subtasks/{target}"
        assert unquote(response.cookies.get("flash", "")) == "That import preview has expired. Upload the file again."
        assert response.cookies.get("flash_type") == "danger"


def test_zip_downloads_say_how_big_they_are(client):
    story_id, subtask_id = _execution_subtask(client, "EX-973")
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login"})
    for url in (f"/subtasks/{subtask_id}/export-docx", f"/stories/{story_id}/export-docx"):
        response = client.get(url)
        assert response.status_code == 200 and response.headers["content-type"] == "application/zip", url
        assert int(response.headers["content-length"]) == len(response.content), url

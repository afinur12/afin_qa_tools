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

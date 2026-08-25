import json

from app.routers.curls import parse_curl


def test_parse_curl_get_with_headers():
    result = parse_curl('curl -H "Authorization: Bearer abc" https://api.example.com/health')
    assert result["method"] == "GET"
    assert result["url"] == "https://api.example.com/health"
    assert json.loads(result["headers"]) == {"Authorization": "Bearer abc"}


def test_parse_curl_post_with_data():
    result = parse_curl("curl -X POST https://api.example.com/users -d '{\"name\":\"a\"}'")
    assert result["method"] == "POST"
    assert result["url"] == "https://api.example.com/users"
    assert result["body"] == '{"name":"a"}'


def test_create_curl_attached_to_story(client):
    create = client.post("/stories", data={"display_code": "EX-700", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    response = client.post(
        "/curls",
        data={"attach_type": "STORY", "attach_id": story_id, "raw_text": "curl https://api.example.com/health"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    story_page = client.get(f"/stories/{story_id}")
    assert "api.example.com/health" in story_page.text


def test_delete_curl(client):
    create = client.post("/stories", data={"display_code": "EX-701", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post("/curls", data={"attach_type": "STORY", "attach_id": story_id, "raw_text": "curl https://api.example.com/health"})
    story_page = client.get(f"/stories/{story_id}")
    curl_id = story_page.text.split('/curls/')[1].split('/delete')[0]
    response = client.post(f"/curls/{curl_id}/delete", data={"attach_type": "STORY", "attach_id": story_id}, follow_redirects=False)
    assert response.status_code == 303
    story_page2 = client.get(f"/stories/{story_id}")
    assert "api.example.com/health" not in story_page2.text

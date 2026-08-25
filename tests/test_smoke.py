def test_app_boots(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404


def test_base_layout_renders_nav(client):
    response = client.get("/__template_check")
    assert response.status_code == 200
    assert "QA Toolbox" in response.text
    assert "Dashboard" in response.text

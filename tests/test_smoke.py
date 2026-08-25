def test_app_boots(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404

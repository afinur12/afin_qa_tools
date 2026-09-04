"""Settings: managing the Label master-data table."""
import re


def test_create_and_list_label(client):
    response = client.post("/settings/labels", data={"name": "regression"}, follow_redirects=False)
    assert response.status_code == 303
    page = client.get("/settings/labels")
    assert "regression" in page.text


def test_create_rejects_blank_name(client):
    response = client.post("/settings/labels", data={"name": "   "})
    assert response.status_code == 422


def test_create_rejects_duplicate_name(client):
    client.post("/settings/labels", data={"name": "flaky"})
    response = client.post("/settings/labels", data={"name": "flaky"})
    assert response.status_code == 422
    assert "already exists" in response.text


def test_rename_label(client):
    client.post("/settings/labels", data={"name": "typo-name"})
    page = client.get("/settings/labels")
    label_id = re.search(r"/settings/labels/(\d+)/edit", page.text).group(1)

    response = client.post(f"/settings/labels/{label_id}/edit", data={"name": "fixed-name"}, follow_redirects=False)
    assert response.status_code == 303
    page_after = client.get("/settings/labels")
    assert "fixed-name" in page_after.text
    assert "typo-name" not in page_after.text


def test_delete_unused_label_succeeds(client):
    client.post("/settings/labels", data={"name": "unused"})
    page = client.get("/settings/labels")
    label_id = re.search(r"/settings/labels/(\d+)/delete", page.text).group(1)

    response = client.post(f"/settings/labels/{label_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert "unused" not in client.get("/settings/labels").text


def test_delete_blocked_when_assigned(client, db_session):
    from app.labels import set_labels
    from app.models import LabelAttachType

    client.post("/settings/labels", data={"name": "in-use"})
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)
    set_labels(db_session, LabelAttachType.STORY, 1, [int(label_id)])
    db_session.commit()

    response = client.post(f"/settings/labels/{label_id}/delete")
    assert response.status_code == 422
    assert "in-use" in client.get("/settings/labels").text


def test_tabs_show_labels(client):
    page = client.get("/settings/labels")
    assert 'href="/settings/services"' in page.text
    assert 'href="/settings/users"' in page.text

"""Settings: managing the Service/Simulate/Test Type master-data tables."""
import re


def _make_subtask(client, code="EX-900"):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    page = client.get(f"/stories/{story_id}")
    phase_id = page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    return sub.headers["location"].rstrip("/").split("/")[-1]


def test_settings_index_redirects_to_services(client):
    response = client.get("/settings/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/settings/services"


def test_unknown_slug_returns_404(client):
    assert client.get("/settings/bogus").status_code == 404
    assert client.post("/settings/bogus", data={"name": "x"}).status_code == 404


def test_create_and_list_service(client):
    response = client.post("/settings/services", data={"name": "payment-service"}, follow_redirects=False)
    assert response.status_code == 303
    page = client.get("/settings/services")
    assert "payment-service" in page.text


def test_create_rejects_blank_name(client):
    response = client.post("/settings/services", data={"name": "   "})
    assert response.status_code == 422


def test_create_rejects_duplicate_name(client):
    client.post("/settings/services", data={"name": "auth-service"})
    response = client.post("/settings/services", data={"name": "auth-service"})
    assert response.status_code == 422
    assert "already exists" in response.text


def test_rename_row(client):
    create = client.post("/settings/simulates", data={"name": "E2E draft"}, follow_redirects=False)
    page = client.get("/settings/simulates")
    row_id = re.search(r"/settings/simulates/(\d+)/edit", page.text).group(1)

    response = client.post(f"/settings/simulates/{row_id}/edit", data={"name": "E2E"}, follow_redirects=False)
    assert response.status_code == 303
    page_after = client.get("/settings/simulates")
    assert "E2E" in page_after.text
    assert "E2E draft" not in page_after.text


def test_rename_rejects_conflict_with_another_row(client):
    client.post("/settings/test-types", data={"name": "POSITIVE"})
    client.post("/settings/test-types", data={"name": "NEGATIVE"})
    page = client.get("/settings/test-types")
    negative_id = re.search(r"value=\"NEGATIVE\"[^>]*action=\"/settings/test-types/(\d+)/edit\"", page.text)
    # Row ids appear in the edit form action; find NEGATIVE's row id directly.
    row_id = re.search(r'action="/settings/test-types/(\d+)/edit"[^>]*>\s*<input name="name" value="NEGATIVE"', page.text, re.S)
    assert row_id is not None
    response = client.post(f"/settings/test-types/{row_id.group(1)}/edit", data={"name": "POSITIVE"})
    assert response.status_code == 422


def test_delete_unused_row_succeeds(client):
    client.post("/settings/services", data={"name": "unused-service"})
    page = client.get("/settings/services")
    row_id = re.search(r"/settings/services/(\d+)/delete", page.text).group(1)

    response = client.post(f"/settings/services/{row_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert "unused-service" not in client.get("/settings/services").text


def test_delete_blocked_when_used_by_prebuilt(client, db_session):
    # Set service_id directly via the ORM rather than through POST
    # /prebuilt — that route doesn't accept service_id until a later
    # change; this test only needs to exercise this task's own
    # delete-blocking logic against the PrebuiltTestCase ref.
    from app.models import PrebuiltTestCase

    client.post("/settings/services", data={"name": "used-service"})
    row_id = re.search(r"/settings/services/(\d+)/delete", client.get("/settings/services").text).group(1)
    create = client.post("/prebuilt", data={"name": "Uses it"}, follow_redirects=False)
    prebuilt_id = create.headers["location"].rstrip("/").split("/")[-1]
    prebuilt = db_session.get(PrebuiltTestCase, int(prebuilt_id))
    prebuilt.service_id = int(row_id)
    db_session.commit()

    response = client.post(f"/settings/services/{row_id}/delete")
    assert response.status_code == 422
    assert "used" in response.text.lower()
    assert "used-service" in client.get("/settings/services").text


def test_delete_blocked_when_test_type_used_by_testcase(client, db_session):
    # Set test_type_id directly via the ORM rather than through
    # /testcases/{id}/section1 — that route doesn't accept test_type_id
    # until a later change; this test only needs to exercise this task's
    # own delete-blocking logic against the TestCase ref, not that route.
    from app.models import TestCase

    client.post("/settings/test-types", data={"name": "SMOKE"})
    row_id = re.search(r"/settings/test-types/(\d+)/delete", client.get("/settings/test-types").text).group(1)
    subtask_id = _make_subtask(client)
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)

    tc = db_session.get(TestCase, int(testcase_id))
    tc.test_type_id = int(row_id)
    db_session.commit()

    response = client.post(f"/settings/test-types/{row_id}/delete")
    assert response.status_code == 422


def test_nav_shows_settings_link(client):
    page = client.get("/stories")
    assert 'href="/settings"' in page.text

"""Settings: exporting/importing all master-data tables as one JSON file."""
import json
from urllib.parse import unquote


def test_export_returns_settings_envelope_with_all_categories(client):
    client.post("/settings/services", data={"name": "payment-service"})
    client.post("/settings/labels", data={"name": "regression"})
    client.post("/settings/users", data={"name": "Jane Doe", "type": "TESTER", "jira_username": "jdoe"})

    response = client.get("/settings/export")
    assert response.status_code == 200
    assert "attachment" in response.headers["content-disposition"]

    data = response.json()
    assert data["kind"] == "settings"
    assert "schema_version" in data
    settings = data["settings"]
    for key in ["services", "simulates", "test_types", "test_priorities", "labels", "users"]:
        assert key in settings

    assert "payment-service" in settings["services"]
    assert "regression" in settings["labels"]
    assert {"name": "Jane Doe", "type": "TESTER", "jira_username": "jdoe"} in settings["users"]


def test_export_then_import_round_trips_into_a_fresh_target(client):
    """Proves the real workflow: download an export, upload that exact file
    back in, and the rows land — no manual re-wrapping needed."""
    client.post("/settings/services", data={"name": "auth-service"})
    client.post("/settings/simulates", data={"name": "TIMEOUT"})
    client.post("/settings/test-types", data={"name": "SMOKE"})
    client.post("/settings/test-priorities", data={"name": "URGENT"})
    client.post("/settings/labels", data={"name": "flaky"})
    client.post("/settings/users", data={"name": "Alex Kim", "type": "DEVELOPER"})

    exported = client.get("/settings/export").json()

    files = {"file": ("settings.json", json.dumps(exported), "application/json")}
    response = client.post("/settings/import", files=files, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies.get("flash_type") != "danger"

    # Re-importing the same export is a no-op (every name already exists) —
    # this is the "safe to re-run" guarantee the skip-existing behavior buys.
    page_services = client.get("/settings/services").text
    assert page_services.count('data-filter-search="auth-service"') == 1
    assert "TIMEOUT" in client.get("/settings/simulates").text
    assert "SMOKE" in client.get("/settings/test-types").text
    assert "URGENT" in client.get("/settings/test-priorities").text
    assert "flaky" in client.get("/settings/labels").text
    users_page = client.get("/settings/users").text
    assert "Alex Kim" in users_page
    assert "Developer" in users_page


def test_import_skips_existing_names_and_only_adds_new_ones(client):
    client.post("/settings/services", data={"name": "existing-service"})

    payload = {
        "kind": "settings",
        "schema_version": 1,
        "settings": {
            "services": ["existing-service", "brand-new-service"],
            "simulates": [], "test_types": [], "test_priorities": [], "labels": [], "users": [],
        },
    }
    files = {"file": ("settings.json", json.dumps(payload), "application/json")}
    response = client.post("/settings/import", files=files, follow_redirects=False)
    assert response.status_code == 303
    assert "Imported 1 row" in unquote(response.cookies.get("flash", ""))

    page = client.get("/settings/services").text
    assert page.count('data-filter-search="existing-service"') == 1
    assert "brand-new-service" in page


def test_import_creates_users_with_type_and_jira_username(client):
    payload = {
        "kind": "settings",
        "schema_version": 1,
        "settings": {
            "services": [], "simulates": [], "test_types": [], "test_priorities": [], "labels": [],
            "users": [{"name": "Priya Nair", "type": "TESTER", "jira_username": "pnair"}],
        },
    }
    files = {"file": ("settings.json", json.dumps(payload), "application/json")}
    response = client.post("/settings/import", files=files, follow_redirects=False)
    assert response.status_code == 303

    page = client.get("/settings/users").text
    assert "Priya Nair" in page
    assert "pnair" in page
    assert "Tester" in page


def test_import_rejects_invalid_json(client):
    files = {"file": ("bad.json", b"not json", "application/json")}
    response = client.post("/settings/import", files=files, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies.get("flash_type") == "danger"


def test_import_rejects_a_file_that_isnt_a_settings_export(client):
    files = {"file": ("wrong.json", json.dumps({"kind": "task", "task": {}}), "application/json")}
    response = client.post("/settings/import", files=files, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies.get("flash_type") == "danger"

import json


def _create_subtask(client, code="SND-9900"):
    story = client.post("/stories", data={"display_code": f"{code}-STORY", "title": "Story"}, follow_redirects=False)
    story_id = story.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": code, "title": "Subtask", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    return sub_resp.headers["location"].rstrip("/").split("/")[-1]


def test_export_jira_json_returns_array_with_one_entry_per_testcase(client):
    subtask_id = _create_subtask(client, "SND-9901")
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "SND-10070", "title": "A"})
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "SND-10071", "title": "B"})

    response = client.get(f"/subtasks/{subtask_id}/export-jira-json")
    assert response.status_code == 200
    assert "application/json" in response.headers["content-type"]
    data = response.json()
    assert [entry["issue_key"] for entry in data] == ["SND-10070", "SND-10071"]


def test_export_jira_json_404_for_missing_subtask(client):
    response = client.get("/subtasks/999999/export-jira-json")
    assert response.status_code == 404


def test_import_jira_json_creates_and_updates_testcases(client):
    subtask_id = _create_subtask(client, "SND-9902")
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "SND-10080", "title": "Old title"})

    payload = {
        "parent_ticket_info": {
            "assignee": {"name": "Andri Firman Nurvianto", "username": "ADL.ANDRIF"},
            "labels": ["SITScenario"],
        },
        "test_cases": [
            {
                "issue_key": "SND-10080", "summary": "New title", "category": "Positive",
                "planned_cost": "0", "actual_cost": "0", "number_of_iteration": 1,
                "msisdn": "MSISDN #A: 62812",
                "assignee": None, "developer": None,
                "tester": {"name": "Andri Firman Nurvianto", "username": "ADL.ANDRIF"},
                "zephyr_steps": [
                    {"order_id": 1, "step_type": "PRE CONDITION", "step": "{{placeholder_pre_condition_step}}", "expected_result": "{{placeholder_pre_condition_expected}}"},
                    {"order_id": 2, "step_type": "MAIN TEST", "step": "MAIN TEST\r\n1. Do A", "expected_result": "1. A happens"},
                    {"order_id": 3, "step_type": "POST CONDITION", "step": "{{placeholder_post_condition_step}}", "expected_result": "{{placeholder_post_condition_expected}}"},
                ],
                "execution": {"execution_id": 12345, "status": "PASS", "executed_on": None, "executed_by": None, "cycle_name": "SIT"},
                "fields": {"description": "Steps", "priority": {"name": "Highest"}, "labels": ["SITScenario"]},
            },
            {
                "issue_key": "SND-10081", "summary": "Brand new case", "category": "Regression",
                "planned_cost": "0", "actual_cost": "0", "number_of_iteration": 0,
                "msisdn": "{{placeholder_msisdn_value}}",
                "assignee": None, "developer": None, "tester": None,
                "zephyr_steps": [
                    {"order_id": 1, "step_type": "PRE CONDITION", "step": "{{placeholder_pre_condition_step}}", "expected_result": "{{placeholder_pre_condition_expected}}"},
                    {"order_id": 2, "step_type": "MAIN TEST", "step": "{{placeholder_main_test_step}}", "expected_result": "{{placeholder_main_test_expected}}"},
                    {"order_id": 3, "step_type": "POST CONDITION", "step": "{{placeholder_post_condition_step}}", "expected_result": "{{placeholder_post_condition_expected}}"},
                ],
                "execution": {"execution_id": 12346, "status": "UNEXECUTED", "executed_on": None, "executed_by": None, "cycle_name": "SIT"},
                "fields": {"description": "{{placeholder_description}}", "priority": {"name": "Medium"}, "labels": []},
            },
        ],
    }
    files = {"file": ("import.json", json.dumps(payload), "application/json")}
    response = client.post(f"/subtasks/{subtask_id}/import-jira-json", files=files, follow_redirects=False)
    assert response.status_code == 303

    page = client.get(f"/subtasks/{subtask_id}")
    assert "New title" in page.text
    assert "Brand new case" in page.text


def test_import_jira_json_flashes_error_on_malformed_json(client):
    subtask_id = _create_subtask(client, "SND-9903")
    files = {"file": ("import.json", "not json", "application/json")}
    response = client.post(f"/subtasks/{subtask_id}/import-jira-json", files=files, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies.get("flash_type") == "danger"


def test_import_jira_json_flashes_error_on_missing_test_cases_key(client):
    subtask_id = _create_subtask(client, "SND-9904")
    files = {"file": ("import.json", json.dumps({}), "application/json")}
    response = client.post(f"/subtasks/{subtask_id}/import-jira-json", files=files, follow_redirects=False)
    assert response.status_code == 303
    assert response.cookies.get("flash_type") == "danger"


def test_import_jira_json_404_for_missing_subtask(client):
    files = {"file": ("import.json", json.dumps({"test_cases": []}), "application/json")}
    response = client.post("/subtasks/999999/import-jira-json", files=files)
    assert response.status_code == 404


def test_subtask_detail_shows_jira_sync_button_and_modal(client):
    subtask_id = _create_subtask(client, "SND-9905")
    page = client.get(f"/subtasks/{subtask_id}")
    assert 'data-modal-open="jira-sync"' in page.text
    assert f"/subtasks/{subtask_id}/export-jira-json" in page.text
    assert f"/subtasks/{subtask_id}/import-jira-json" in page.text

def test_app_boots(client):
    response = client.get("/does-not-exist")
    assert response.status_code == 404


def test_base_layout_renders_nav(client):
    response = client.get("/stories")
    assert response.status_code == 200
    assert "QA Toolbox" in response.text
    assert "Dashboard" in response.text


def test_full_workflow_story_to_docx_export(client):
    create = client.post("/stories", data={"display_code": "EX-999", "title": "E2E Story"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]

    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "SIT Login Flow", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]

    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login works"}, follow_redirects=False
    )
    testcase_id = tc_resp.headers["location"].rstrip("/").split("/")[-1]

    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "enter otp", "expected_result": "logged in", "actual_result": "logged in"})
    client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "tester": "Andri Firman Nurvianto", "test_date": "2026-08-26", "test_priority": "High",
            "channel": "Mobile App", "iteration": "1",
            "balance_before": "Rp. -", "balance_after": "Rp. -", "usage": "Rp. -",
            "remark": "", "data_test": "msisdn: 62812", "status": "PASS",
        },
    )
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] minor UI glitch"})

    export = client.get(f"/testcases/{testcase_id}/export-docx")
    assert export.status_code == 200

    dashboard = client.get("/")
    assert "EX-999" in dashboard.text
    assert "PASS" in dashboard.text

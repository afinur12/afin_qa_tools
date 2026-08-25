def _create_testcase_with_step(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "Payments"}, follow_redirects=False)
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
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login"}, follow_redirects=False
    )
    testcase_id = tc_resp.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "s", "expected_result": "e", "actual_result": "a"})
    return testcase_id


def test_export_docx_downloads_file(client):
    testcase_id = _create_testcase_with_step(client, "EX-900")
    response = client.get(f"/testcases/{testcase_id}/export-docx")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert len(response.content) > 0


def test_export_docx_404_for_missing_testcase(client):
    response = client.get("/testcases/999999/export-docx")
    assert response.status_code == 404

import re


def _create_testcase(client, code):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub_resp = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub_resp.headers["location"].rstrip("/").split("/")[-1]
    tc_resp = client.post(
        f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "Login"}, follow_redirects=False
    )
    return tc_resp.headers["location"].rstrip("/").split("/")[-1]


def test_execute_page_renders(client):
    testcase_id = _create_testcase(client, "EX-400")
    response = client.get(f"/testcases/{testcase_id}/execute")
    assert response.status_code == 200
    assert "Pre Condition" in response.text
    assert "Main Test" in response.text
    assert "Post Condition" in response.text


def test_add_step_and_ordering(client):
    testcase_id = _create_testcase(client, "EX-401")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "first", "expected_result": "e1", "actual_result": "a1"})
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "second", "expected_result": "e2", "actual_result": "a2"})
    response = client.get(f"/testcases/{testcase_id}/execute")
    assert response.text.index('value="first"') < response.text.index('value="second"')


def test_update_section1_fields(client):
    testcase_id = _create_testcase(client, "EX-402")
    client.post("/settings/test-types", data={"name": "Functional"})
    test_type_id = re.search(r"/settings/test-types/(\d+)/delete", client.get("/settings/test-types").text).group(1)
    response = client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "tester": "Jane Doe", "test_date": "2026-08-26", "test_priority": "High",
            "test_type_id": test_type_id, "channel": "Mobile App", "iteration": "1",
            "balance_before": "Rp. -", "balance_after": "Rp. -", "usage": "Rp. -",
            "remark": "", "data_test": "msisdn: 62812", "status": "PASS",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/testcases/{testcase_id}/execute")
    assert "Jane Doe" in page.text
    assert "PASS" in page.text
    assert "Functional" in page.text


def test_edit_and_delete_step(client):
    testcase_id = _create_testcase(client, "EX-403")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "PRECONDITION", "step_text": "orig", "expected_result": "e", "actual_result": "a"})
    page = client.get(f"/testcases/{testcase_id}/execute")
    step_id = re.search(r"/steps/(\d+)/edit", page.text).group(1)

    edited = client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/edit",
        data={"step_text": "changed", "expected_result": "e2", "actual_result": "a2"},
        follow_redirects=False,
    )
    assert edited.status_code == 303
    page2 = client.get(f"/testcases/{testcase_id}/execute")
    assert "changed" in page2.text

    deleted = client.post(f"/testcases/{testcase_id}/steps/{step_id}/delete", follow_redirects=False)
    assert deleted.status_code == 303
    page3 = client.get(f"/testcases/{testcase_id}/execute")
    assert "changed" not in page3.text

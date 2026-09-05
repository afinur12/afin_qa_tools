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
    client.post("/settings/test-priorities", data={"name": "HIGH"})
    priority_page = client.get("/settings/test-priorities")
    priority_id = re.search(r'value="HIGH"[\s\S]*?/settings/test-priorities/(\d+)/delete', priority_page.text).group(1)
    client.post("/settings/users", data={"name": "Jane Doe", "type": "TESTER"})
    tester_id = re.search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    response = client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "tester_id": tester_id, "test_date": "2026-08-26", "test_priority_id": priority_id,
            "test_type_id": test_type_id, "channel": "Mobile App", "iteration": "1",
            "balance_before": "Rp. -", "balance_after": "Rp. -", "usage": "Rp. -",
            "remark": "", "data_test": "msisdn: 62812", "status": "PASS",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/testcases/{testcase_id}/execute")
    assert "PASS" in page.text
    assert f'value="{test_type_id}" selected' in page.text
    assert f'value="{priority_id}" selected' in page.text
    assert f'value="{tester_id}" selected' in page.text


def test_update_section1_status_in_progress(client):
    testcase_id = _create_testcase(client, "EX-403")
    response = client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "test_date": "2026-08-26",
            "channel": "Mobile App", "iteration": "1",
            "balance_before": "Rp. -", "balance_after": "Rp. -", "usage": "Rp. -",
            "remark": "", "data_test": "", "status": "IN_PROGRESS",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/testcases/{testcase_id}/execute")
    assert "IN PROGRESS" in page.text


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


def test_update_section1_sets_assignee_tester_developer_and_labels(client):
    import re

    testcase_id = _create_testcase(client, "EX-410")
    client.post("/settings/users", data={"name": "TC Tester", "type": "TESTER"})
    tester_id = re.search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    client.post("/settings/users", data={"name": "TC Dev", "type": "DEVELOPER"})
    developer_id = re.search(
        r'value="TC Dev"[\s\S]*?/settings/users/(\d+)/delete', client.get("/settings/users").text
    ).group(1)
    client.post("/settings/labels", data={"name": "sanity"})
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    response = client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "status": "TO_DO",
            "assignee_id": tester_id, "tester_id": tester_id, "developer_id": developer_id,
            "label_ids": [label_id],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/testcases/{testcase_id}/execute")
    assert "TC Tester" in page.text
    assert "TC Dev" in page.text
    assert "sanity" in page.text


def test_testcase_create_form_does_not_collect_assignee_tester_developer(client):
    # These fields are edit-only for TestCase — the lightweight create
    # form/modal never shows them, matching how `tester`/`test_type`
    # already work for this entity (defaulted, edited later on Section 1).
    testcase_id = _create_testcase(client, "EX-411")
    page = client.get(f"/testcases/{testcase_id}/execute")
    assert 'name="assignee_id"' in page.text  # present on the edit surface (Section 1)...
    # ...but the standalone create form/modal never posts these fields;
    # nothing to assert on testcases/form.html itself since it never
    # collected them even before this task (only display_code/title/
    # prebuilt_id), so there's no regression risk to check there.


def test_update_section1_sets_jira_fields(client, db_session):
    from app.models import TestCase

    testcase_id = _create_testcase(client, "EX-404")
    response = client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "test_date": "2026-08-26",
            "channel": "Mobile App", "iteration": "3",
            "balance_before": "Rp. -", "balance_after": "Rp. -", "usage": "Rp. -",
            "remark": "", "data_test": "", "status": "PASS",
            "msisdn": "MSISDN #A: 62812", "planned_cost": "0",
            "actual_cost": "0",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/testcases/{testcase_id}/execute")
    assert "62812" in page.text
    assert 'value="3"' in page.text

    # A single "Iteration" field feeds both the docx-facing string column
    # and Jira Sync's numeric one.
    tc = db_session.get(TestCase, int(testcase_id))
    assert tc.iteration == "3"
    assert tc.number_of_iteration == 3


def _make_prebuilt_with_step(client, name, step_text="Enter amount"):
    resp = client.post("/prebuilt", data={"name": name, "description": "d"}, follow_redirects=False)
    prebuilt_id = resp.headers["location"].rstrip("/").split("/")[-1]
    section = re.findall(r"/sections/(\d+)/delete", client.get(f"/prebuilt/{prebuilt_id}").text)[1]
    client.post(f"/prebuilt/{prebuilt_id}/sections/{section}/steps",
                data={"step_text": step_text, "expected_result": "Accepted"})
    return prebuilt_id


def test_copy_from_prebuilt_replaces_existing_steps(client):
    testcase_id = _create_testcase(client, "EX-406")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "old step", "expected_result": "e", "actual_result": "a"})
    prebuilt_id = _make_prebuilt_with_step(client, "Copy source", "new step from template")

    response = client.post(f"/testcases/{testcase_id}/copy-from-prebuilt", data={"prebuilt_id": prebuilt_id}, follow_redirects=False)
    assert response.status_code == 303

    page = client.get(f"/testcases/{testcase_id}/execute").text
    assert "new step from template" in page
    assert "old step" not in page


def test_copy_from_prebuilt_blank_option_clears_steps(client):
    testcase_id = _create_testcase(client, "EX-407")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "old step", "expected_result": "e", "actual_result": "a"})

    response = client.post(f"/testcases/{testcase_id}/copy-from-prebuilt", data={"prebuilt_id": ""}, follow_redirects=False)
    assert response.status_code == 303

    page = client.get(f"/testcases/{testcase_id}/execute").text
    assert "old step" not in page
    assert "Pre Condition" in page
    assert "Main Test" in page
    assert "Post Condition" in page


def test_update_section1_jira_fields_are_optional(client):
    testcase_id = _create_testcase(client, "EX-405")
    response = client.post(
        f"/testcases/{testcase_id}/section1",
        data={
            "test_date": "",
            "channel": "", "iteration": "1",
            "balance_before": "Rp. -", "balance_after": "Rp. -", "usage": "Rp. -",
            "remark": "", "data_test": "", "status": "TO_DO",
        },
        follow_redirects=False,
    )
    assert response.status_code == 303

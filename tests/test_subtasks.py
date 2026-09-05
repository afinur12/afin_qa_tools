def _create_story_and_phase(client, code="EX-200", phase_type="SIT"):
    create = client.post("/stories", data={"display_code": code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    phase_resp = client.post(f"/stories/{story_id}/phases", data={"type": phase_type}, follow_redirects=False)
    story_page = client.get(f"/stories/{story_id}")
    import re
    phase_id = re.search(r'/phases/(\d+)/subtasks/new', story_page.text)
    return story_id, phase_id


def test_create_subtask(client):
    create = client.post("/stories", data={"display_code": "EX-201", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    from app.database import SessionLocal  # noqa
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    response = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "SIT Planning", "subtask_type": "TEST_PLANNING"},
        follow_redirects=False,
    )
    assert response.status_code == 303


def test_staging_after_rollback_restricts_to_single_execution_subtask(client):
    create = client.post("/stories", data={"display_code": "EX-202", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "STAGING_AFTER_ROLLBACK"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    rejected = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Planning", "subtask_type": "TEST_PLANNING"},
    )
    assert rejected.status_code == 422

    accepted = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Execution", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    assert accepted.status_code == 303

    second = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-2", "title": "Execution 2", "subtask_type": "EXECUTION"},
    )
    assert second.status_code == 422


def test_delete_subtask_cascades_to_testcases_and_bugs(client):
    create = client.post("/stories", data={"display_code": "EX-203", "title": "A"}, follow_redirects=False)
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
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"})

    # Deleting a subtask takes its test cases and bugs with it.
    response = client.post(f"/subtasks/{subtask_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert client.get(f"/subtasks/{subtask_id}").status_code == 404
    assert "TC-1" not in client.get(f"/stories/{story_id}").text
    assert "B-1" not in client.get("/bugs").text


def test_edit_subtask_status(client):
    create = client.post("/stories", data={"display_code": "EX-204", "title": "A"}, follow_redirects=False)
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

    response = client.post(
        f"/subtasks/{subtask_id}/edit",
        data={"display_code": "S-1", "title": "Exec", "notes": "", "status": "DONE"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/subtasks/{subtask_id}")
    assert "DONE" in detail.text

    story_page_after = client.get(f"/stories/{story_id}")
    assert "DONE" in story_page_after.text


def test_edit_subtask_status_in_progress(client):
    create = client.post("/stories", data={"display_code": "EX-207", "title": "A"}, follow_redirects=False)
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

    response = client.post(
        f"/subtasks/{subtask_id}/edit",
        data={"display_code": "S-1", "title": "Exec", "notes": "", "status": "IN_PROGRESS"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    detail = client.get(f"/subtasks/{subtask_id}")
    assert "IN PROGRESS" in detail.text

    story_page_after = client.get(f"/stories/{story_id}")
    assert "IN PROGRESS" in story_page_after.text


def test_subtask_detail_shows_tracker_links_for_testcase_and_bug(client):
    create = client.post("/stories", data={"display_code": "EX-206", "title": "A"}, follow_redirects=False)
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
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A"})
    client.post(f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"})

    detail = client.get(f"/subtasks/{subtask_id}")
    assert "https://collabs.xlsmart.co.id/browse/TC-1" in detail.text
    assert "https://collabs.xlsmart.co.id/browse/B-1" in detail.text


def test_subtask_detail_shows_test_priority_badge_and_sort_attributes(client):
    import re

    create = client.post("/stories", data={"display_code": "EX-207", "title": "A"}, follow_redirects=False)
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
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "With priority"})
    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)
    client.post("/settings/test-priorities", data={"name": "HIGHEST"})
    priority_id = re.search(r'value="HIGHEST"[\s\S]*?/settings/test-priorities/(\d+)/delete', client.get("/settings/test-priorities").text).group(1)
    client.post(f"/testcases/{testcase_id}/section1", data={"status": "TO_DO", "test_priority_id": priority_id})

    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-2", "title": "No priority"})

    detail = client.get(f"/subtasks/{subtask_id}")
    assert detail.status_code == 200
    assert 'class="badge priority-highest">' in detail.text
    assert "HIGHEST</span>" in detail.text
    assert f'data-sort-priority="{priority_id}"' in detail.text
    assert 'data-sort-priority="999999"' in detail.text  # TC-2 has no priority set
    assert "data-sortable-table" in detail.text
    assert 'data-sort-key="priority"' in detail.text


def test_edit_subtask_rejects_invalid_status(client):
    create = client.post("/stories", data={"display_code": "EX-205", "title": "A"}, follow_redirects=False)
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

    response = client.post(
        f"/subtasks/{subtask_id}/edit",
        data={"display_code": "S-1", "title": "Exec", "notes": "", "status": "NOT_A_STATUS"},
    )
    assert response.status_code == 422


def test_create_subtask_with_assignee_tester_developer_and_labels(client):
    import re

    create = client.post("/stories", data={"display_code": "EX-210", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    client.post("/settings/users", data={"name": "Sub Tester", "type": "TESTER"})
    tester_id = re.search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    client.post("/settings/users", data={"name": "Sub Dev", "type": "DEVELOPER"})
    developer_id = re.search(
        r'value="Sub Dev"[\s\S]*?/settings/users/(\d+)/delete', client.get("/settings/users").text
    ).group(1)
    client.post("/settings/labels", data={"name": "flaky"})
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    response = client.post(
        f"/phases/{phase_id}/subtasks",
        data={
            "display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION",
            "assignee_id": tester_id, "tester_id": tester_id, "developer_id": developer_id,
            "label_ids": [label_id],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(response.headers["location"])
    assert "Sub Tester" in page.text
    assert "Sub Dev" in page.text
    assert "flaky" in page.text


def test_edit_subtask_updates_assignee_tester_developer_and_labels(client):
    import re

    create = client.post("/stories", data={"display_code": "EX-211", "title": "A"}, follow_redirects=False)
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

    client.post("/settings/users", data={"name": "Later Sub Tester", "type": "TESTER"})
    tester_id = re.search(r"/settings/users/(\d+)/delete", client.get("/settings/users").text).group(1)
    client.post("/settings/labels", data={"name": "smoke"})
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    response = client.post(
        f"/subtasks/{subtask_id}/edit",
        data={
            "display_code": "S-1", "title": "Exec", "notes": "", "status": "TO_DO",
            "tester_id": tester_id, "label_ids": [label_id],
        },
        follow_redirects=False,
    )
    assert response.status_code == 303
    page = client.get(f"/subtasks/{subtask_id}")
    assert "Later Sub Tester" in page.text
    assert "smoke" in page.text


def test_subtasks_can_be_reordered(client):
    import re

    create = client.post("/stories", data={"display_code": "EX-208", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]

    first = client.post(f"/phases/{phase_id}/subtasks", data={"display_code": "S-1", "title": "Planning", "subtask_type": "TEST_PLANNING"}, follow_redirects=False)
    first_id = first.headers["location"].rstrip("/").split("/")[-1]
    second = client.post(f"/phases/{phase_id}/subtasks", data={"display_code": "S-2", "title": "Data Prep", "subtask_type": "TEST_DATA_PREP"}, follow_redirects=False)
    second_id = second.headers["location"].rstrip("/").split("/")[-1]
    third = client.post(f"/phases/{phase_id}/subtasks", data={"display_code": "S-3", "title": "Execution", "subtask_type": "EXECUTION"}, follow_redirects=False)
    third_id = third.headers["location"].rstrip("/").split("/")[-1]

    page = client.get(f"/stories/{story_id}").text
    assert page.index(f'data-subtask-id="{first_id}"') < page.index(f'data-subtask-id="{second_id}"') < page.index(f'data-subtask-id="{third_id}"')

    response = client.post(
        f"/phases/{phase_id}/subtasks/reorder",
        data={"order": f"{third_id},{first_id},{second_id}"},
        follow_redirects=False,
    )
    assert response.status_code == 303

    reordered = client.get(f"/stories/{story_id}").text
    assert reordered.index(f'data-subtask-id="{third_id}"') < reordered.index(f'data-subtask-id="{first_id}"') < reordered.index(f'data-subtask-id="{second_id}"')


def test_subtask_reorder_rejects_ids_from_another_phase(client):
    import re

    create = client.post("/stories", data={"display_code": "EX-209", "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    client.post(f"/stories/{story_id}/phases", data={"type": "STAGING"})
    story_page = client.get(f"/stories/{story_id}").text
    phase_ids = re.findall(r"/phases/(\d+)/subtasks/new", story_page)
    sit_phase_id, staging_phase_id = phase_ids[0], phase_ids[1]

    own = client.post(f"/phases/{sit_phase_id}/subtasks", data={"display_code": "S-1", "title": "Own", "subtask_type": "EXECUTION"}, follow_redirects=False)
    own_id = own.headers["location"].rstrip("/").split("/")[-1]
    intruder = client.post(f"/phases/{staging_phase_id}/subtasks", data={"display_code": "S-1", "title": "Intruder", "subtask_type": "EXECUTION"}, follow_redirects=False)
    intruder_id = intruder.headers["location"].rstrip("/").split("/")[-1]

    response = client.post(f"/phases/{sit_phase_id}/subtasks/reorder", data={"order": f"{intruder_id},{own_id}"})
    assert response.status_code == 422

"""Prebuilt test cases: reusable section/step skeletons."""
import re


def _make_subtask(client, code="EX-800"):
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


def _make_prebuilt(client, name="Standard purchase"):
    resp = client.post("/prebuilt", data={"name": name, "description": "d"}, follow_redirects=False)
    assert resp.status_code == 303
    return resp.headers["location"].rstrip("/").split("/")[-1]


def _section_ids(client, prebuilt_id):
    page = client.get(f"/prebuilt/{prebuilt_id}")
    return re.findall(r"/sections/(\d+)/delete", page.text)


def test_new_prebuilt_starts_with_the_three_default_sections(client):
    prebuilt_id = _make_prebuilt(client)
    assert len(_section_ids(client, prebuilt_id)) == 3


def test_prebuilt_steps_can_be_added_and_listed(client):
    prebuilt_id = _make_prebuilt(client, "With steps")
    section = _section_ids(client, prebuilt_id)[1]
    client.post(f"/prebuilt/{prebuilt_id}/sections/{section}/steps",
                data={"step_text": "Open the app", "expected_result": "Home screen"})

    page = client.get(f"/prebuilt/{prebuilt_id}").text
    assert "Open the app" in page
    assert "Home screen" in page
    assert "1 step" in page


def test_creating_a_testcase_from_a_prebuilt_copies_its_steps(client):
    prebuilt_id = _make_prebuilt(client, "Copy me")
    section = _section_ids(client, prebuilt_id)[1]
    client.post(f"/prebuilt/{prebuilt_id}/sections/{section}/steps",
                data={"step_text": "Enter amount", "expected_result": "Accepted"})

    subtask_id = _make_subtask(client, "EX-801")
    client.post(f"/subtasks/{subtask_id}/testcases",
                data={"display_code": "TC-1", "title": "From template", "prebuilt_id": prebuilt_id})

    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)
    page = client.get(f"/testcases/{testcase_id}/execute").text
    assert "Enter amount" in page
    assert "Accepted" in page
    # Screenshots are never part of a template.
    assert "/uploads/screenshots/" not in page


def test_creating_a_blank_testcase_has_three_empty_sections(client):
    subtask_id = _make_subtask(client, "EX-802")
    client.post(f"/subtasks/{subtask_id}/testcases",
                data={"display_code": "TC-1", "title": "Blank", "prebuilt_id": ""})
    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)

    page = client.get(f"/testcases/{testcase_id}/execute").text
    assert len(re.findall(r"<span data-section-index>", page)) == 3
    assert page.count('name="step_text"') == 0


def test_editing_a_prebuilt_does_not_change_cases_already_created_from_it(client):
    prebuilt_id = _make_prebuilt(client, "Frozen")
    section = _section_ids(client, prebuilt_id)[1]
    client.post(f"/prebuilt/{prebuilt_id}/sections/{section}/steps", data={"step_text": "original text"})

    subtask_id = _make_subtask(client, "EX-803")
    client.post(f"/subtasks/{subtask_id}/testcases",
                data={"display_code": "TC-1", "title": "Copy", "prebuilt_id": prebuilt_id})
    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)

    # Change the template afterwards.
    step_id = re.search(r"/prebuilt/\d+/steps/(\d+)/edit", client.get(f"/prebuilt/{prebuilt_id}").text).group(1)
    client.post(f"/prebuilt/{prebuilt_id}/steps/{step_id}/edit", data={"step_text": "changed text"})

    page = client.get(f"/testcases/{testcase_id}/execute").text
    assert "original text" in page, "an existing case is a copy, not a live reference"
    assert "changed text" not in page


def test_save_an_existing_testcase_as_a_prebuilt(client):
    subtask_id = _make_subtask(client, "EX-804")
    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-9", "title": "Reusable flow"})
    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)
    section = re.findall(r"/sections/(\d+)/steps", client.get(f"/testcases/{testcase_id}/execute").text)[1]
    client.post(f"/testcases/{testcase_id}/sections/{section}/steps", data={"step_text": "captured step"})

    resp = client.post(f"/testcases/{testcase_id}/save-as-prebuilt", follow_redirects=False)
    assert resp.status_code == 303
    page = client.get(resp.headers["location"]).text
    assert "Reusable flow" in page
    assert "captured step" in page

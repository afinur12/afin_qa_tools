"""Every page renders a distinct <title> so browser tabs are tellable apart."""
import re


def _make_story_with_subtask(client, code):
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
    return story_id, subtask_id


def _title(page_text):
    return re.search(r"<title>(.*?)</title>", page_text).group(1)


def test_static_pages_have_distinct_titles(client):
    assert _title(client.get("/").text) == "Dashboard - QA Toolbox"
    assert _title(client.get("/stories").text) == "Tasks - QA Toolbox"
    assert _title(client.get("/bugs").text) == "Bugs - QA Toolbox"
    assert _title(client.get("/prebuilt").text) == "Prebuilt - QA Toolbox"
    assert _title(client.get("/stories/new").text) == "New Task - QA Toolbox"


def test_story_subtask_testcase_bug_titles_carry_their_display_code(client):
    story_id, subtask_id = _make_story_with_subtask(client, "EX-950")
    assert _title(client.get(f"/stories/{story_id}").text) == "EX-950 - QA Toolbox"
    assert _title(client.get(f"/subtasks/{subtask_id}").text) == "S-1 - QA Toolbox"

    client.post(f"/subtasks/{subtask_id}/testcases", data={"display_code": "TC-1", "title": "A test"})
    testcase_id = re.search(r"/testcases/(\d+)/execute", client.get(f"/subtasks/{subtask_id}").text).group(1)
    assert _title(client.get(f"/testcases/{testcase_id}/execute").text) == "TC-1 - QA Toolbox"

    bug_resp = client.post(
        f"/subtasks/{subtask_id}/bugs", data={"display_code": "B-1", "title": "[ISSUE] a"}, follow_redirects=False
    )
    bug_id = bug_resp.headers["location"].rstrip("/").split("/")[-1]
    page = client.get(f"/bugs/{bug_id}").text
    assert _title(page) == "B-1 - QA Toolbox"
    assert _title(client.get(f"/bugs/{bug_id}/edit").text) == "Edit B-1 - QA Toolbox"


def test_utility_and_settings_page_titles(client):
    assert _title(client.get("/utility").text) == "Utility Tools - QA Toolbox"
    assert _title(client.get("/utility/uuid").text) == "UUID Generator - QA Toolbox"
    assert _title(client.get("/settings/labels").text) == "Labels - QA Toolbox"
    assert _title(client.get("/settings/users").text) == "Users - QA Toolbox"

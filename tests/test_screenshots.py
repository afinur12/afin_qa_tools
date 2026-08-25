import base64
from pathlib import Path

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


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


def test_upload_and_delete_screenshot(client):
    testcase_id = _create_testcase(client, "EX-500")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "s", "expected_result": "e", "actual_result": "a"})
    page = client.get(f"/testcases/{testcase_id}/execute")
    step_id = page.text.split('/steps/')[1].split('/edit')[0]

    upload = client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/screenshot",
        files={"file": ("paste.png", PNG_BYTES, "image/png")},
        follow_redirects=False,
    )
    assert upload.status_code == 303
    page2 = client.get(f"/testcases/{testcase_id}/execute")
    assert "/uploads/screenshots/" in page2.text

    import re
    screenshot_id = re.search(r"/screenshots/(\d+)/delete", page2.text).group(1)
    disk_path = next(Path("app/uploads/screenshots").rglob("*.png"))
    assert disk_path.exists()

    delete = client.post(f"/screenshots/{screenshot_id}/delete", follow_redirects=False)
    assert delete.status_code == 303
    assert not disk_path.exists()


def test_deleting_step_removes_screenshot_file(client):
    testcase_id = _create_testcase(client, "EX-501")
    client.post(f"/testcases/{testcase_id}/steps", data={"section": "MAIN", "step_text": "s", "expected_result": "e", "actual_result": "a"})
    page = client.get(f"/testcases/{testcase_id}/execute")
    step_id = page.text.split('/steps/')[1].split('/edit')[0]
    client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/screenshot",
        files={"file": ("paste.png", PNG_BYTES, "image/png")},
    )
    disk_path = next(Path("app/uploads/screenshots").rglob("*.png"))
    assert disk_path.exists()

    client.post(f"/testcases/{testcase_id}/steps/{step_id}/delete")
    assert not disk_path.exists()

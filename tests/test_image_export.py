import base64
import io
import zipfile

PNG_BYTES = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+A8AAQUBAScY42YAAAAASUVORK5CYII="
)


def _create_testcase(client, story_code, tc_code="TC-1", tc_title="Verify top-up"):
    create = client.post("/stories", data={"display_code": story_code, "title": "A"}, follow_redirects=False)
    story_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{story_id}/phases", data={"type": "SIT"})
    story_page = client.get(f"/stories/{story_id}")
    phase_id = story_page.text.split('/subtasks/new')[0].split('/phases/')[-1]
    sub = client.post(
        f"/phases/{phase_id}/subtasks",
        data={"display_code": "S-1", "title": "Exec", "subtask_type": "EXECUTION"},
        follow_redirects=False,
    )
    subtask_id = sub.headers["location"].rstrip("/").split("/")[-1]
    tc = client.post(
        f"/subtasks/{subtask_id}/testcases",
        data={"display_code": tc_code, "title": tc_title},
        follow_redirects=False,
    )
    page = client.get(f"/subtasks/{subtask_id}")
    import re
    return re.search(r"/testcases/(\d+)/execute", page.text).group(1)


def _step_ids(client, testcase_id):
    import re
    page = client.get(f"/testcases/{testcase_id}/execute")
    return set(re.findall(r"/steps/(\d+)/edit", page.text))


def _add_step_with_shot(client, testcase_id, section, text):
    # The execute page renders sections in PRE/MAIN/POST order, so "the last
    # edit link on the page" is not the step just created. Diff the ids
    # instead.
    before = _step_ids(client, testcase_id)
    client.post(
        f"/testcases/{testcase_id}/steps",
        data={"section": section, "step_text": text, "expected_result": "e", "actual_result": "a"},
    )
    step_id = (_step_ids(client, testcase_id) - before).pop()
    client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/screenshot",
        files={"file": ("paste.png", PNG_BYTES, "image/png")},
    )
    return step_id


def test_export_images_zip_names_entries_by_section_step_and_name(client):
    testcase_id = _create_testcase(client, "EX-900")
    _add_step_with_shot(client, testcase_id, "MAIN", "Check Balance")
    _add_step_with_shot(client, testcase_id, "PRECONDITION", "Open app")

    response = client.get(f"/testcases/{testcase_id}/export-images")
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/zip"
    from urllib.parse import unquote
    assert "TC-1 - Verify top-up.zip" in unquote(response.headers["content-disposition"])

    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    # Ordered by section (PRECONDITION before MAIN), then step number.
    assert names == ["PRECONDITION.1_Open app.png", "MAIN.1_Check Balance.png"]


def test_export_images_zip_disambiguates_multiple_shots_on_one_step(client):
    testcase_id = _create_testcase(client, "EX-901", tc_code="TC-2", tc_title="Multi")
    step_id = _add_step_with_shot(client, testcase_id, "MAIN", "Check Balance")
    client.post(
        f"/testcases/{testcase_id}/steps/{step_id}/screenshot",
        files={"file": ("paste.png", PNG_BYTES, "image/png")},
    )

    response = client.get(f"/testcases/{testcase_id}/export-images")
    names = zipfile.ZipFile(io.BytesIO(response.content)).namelist()
    assert names == ["MAIN.1_Check Balance.png", "MAIN.1_Check Balance_2.png"]


def test_export_images_404_for_missing_testcase(client):
    assert client.get("/testcases/999999/export-images").status_code == 404


def test_export_docx_filename_is_code_and_title(client):
    from urllib.parse import unquote

    testcase_id = _create_testcase(client, "EX-902", tc_code="TC-9", tc_title="Top-up flow")
    response = client.get(f"/testcases/{testcase_id}/export-docx")
    assert response.status_code == 200
    # Starlette emits the RFC 5987 percent-encoded form.
    assert "TC-9 - Top-up flow.docx" in unquote(response.headers["content-disposition"])

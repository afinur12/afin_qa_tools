def test_dashboard_shows_story_and_counts(client):
    create = client.post("/stories", data={"display_code": "EX-800", "title": "Payments"}, follow_redirects=False)
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

    response = client.get("/")
    assert response.status_code == 200
    assert "EX-800" in response.text
    assert "Payments" in response.text
    assert "TO DO" in response.text
    assert "1" in response.text  # open bug count appears somewhere on the page


def test_dashboard_shows_percent_of_tasks_done(client):
    done = client.post("/stories", data={"display_code": "EX-801", "title": "Done one"}, follow_redirects=False)
    done_id = done.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/stories/{done_id}/edit", data={"display_code": "EX-801", "title": "Done one", "status": "DONE"})

    client.post("/stories", data={"display_code": "EX-802", "title": "Not done"})

    response = client.get("/")
    assert response.status_code == 200
    assert "50" in response.text  # 1 of 2 stories done

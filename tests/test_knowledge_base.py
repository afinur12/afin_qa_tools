def test_create_card_redirects_to_its_editor(client):
    response = client.post("/knowledge-base", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"].startswith("/knowledge-base/")
    card_id = response.headers["location"].rstrip("/").split("/")[-1]

    page = client.get(f"/knowledge-base/{card_id}")
    assert page.status_code == 200
    assert "Untitled" in page.text


def test_card_list_shows_created_cards(client):
    create = client.post("/knowledge-base", follow_redirects=False)
    card_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/knowledge-base/{card_id}/edit", data={"title": "Deploy runbook", "content_markdown": "steps here"})

    page = client.get("/knowledge-base").text
    assert "Deploy runbook" in page
    assert f"/knowledge-base/{card_id}" in page


def test_card_list_search_filters_by_title_and_content(client):
    a = client.post("/knowledge-base", follow_redirects=False).headers["location"].rstrip("/").split("/")[-1]
    b = client.post("/knowledge-base", follow_redirects=False).headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/knowledge-base/{a}/edit", data={"title": "Deploy runbook", "content_markdown": "kubectl apply"})
    client.post(f"/knowledge-base/{b}/edit", data={"title": "Meeting notes", "content_markdown": "standup recap"})

    by_title = client.get("/knowledge-base?q=runbook").text
    assert "Deploy runbook" in by_title
    assert "Meeting notes" not in by_title

    by_content = client.get("/knowledge-base?q=standup").text
    assert "Meeting notes" in by_content
    assert "Deploy runbook" not in by_content


def test_card_list_tag_filter_narrows_to_matching_cards(client):
    import re

    client.post("/settings/labels", data={"name": "runbook"})
    # This exact regex — matching the label's own delete-form action URL,
    # which always embeds its id regardless of the label's name — is the
    # established pattern already used the same way in tests/test_bugs.py,
    # tests/test_execution.py, and tests/test_deletion_labels.py. Use it
    # verbatim rather than inventing a different extraction.
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    a = client.post("/knowledge-base", follow_redirects=False).headers["location"].rstrip("/").split("/")[-1]
    b = client.post("/knowledge-base", follow_redirects=False).headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/knowledge-base/{a}/edit", data={"title": "Tagged card", "content_markdown": "x", "label_ids": [label_id]})
    client.post(f"/knowledge-base/{b}/edit", data={"title": "Untagged card", "content_markdown": "x"})

    filtered = client.get(f"/knowledge-base?tag={label_id}").text
    assert "Tagged card" in filtered
    assert "Untagged card" not in filtered


def test_knowledge_base_nav_link_present(client):
    page = client.get("/").text
    assert 'href="/knowledge-base"' in page
    assert "Knowledge Base" in page


def test_card_editor_page_renders_current_title_and_content(client):
    create = client.post("/knowledge-base", follow_redirects=False)
    card_id = create.headers["location"].rstrip("/").split("/")[-1]
    client.post(f"/knowledge-base/{card_id}/edit", data={"title": "My card", "content_markdown": "hello world"})

    page = client.get(f"/knowledge-base/{card_id}").text
    assert "My card" in page
    assert "hello world" in page


def _label_ids_by_name(client) -> dict[str, str]:
    """Maps each existing Label's name to its id by reading them back off
    the settings page's own delete-form markup (app/templates/settings/
    labels.html: `action="/settings/labels/{id}/delete" data-confirm="Delete
    &quot;{name}&quot;?"`) — both id and name come from the same <form> tag,
    so this doesn't depend on list ordering the way separately extracting
    ids and names would."""
    import re
    html = client.get("/settings/labels").text
    return {name: id_ for id_, name in re.findall(r'/settings/labels/(\d+)/delete" data-confirm="Delete &quot;([^&]+)&quot;', html)}


def test_card_edit_updates_title_content_and_tags_together(client):
    client.post("/settings/labels", data={"name": "alpha"})
    client.post("/settings/labels", data={"name": "beta"})
    ids = _label_ids_by_name(client)

    create = client.post("/knowledge-base", follow_redirects=False)
    card_id = create.headers["location"].rstrip("/").split("/")[-1]

    client.post(
        f"/knowledge-base/{card_id}/edit",
        data={"title": "Renamed", "content_markdown": "new body", "label_ids": [ids["alpha"], ids["beta"]]},
    )
    page = client.get(f"/knowledge-base/{card_id}").text
    assert "Renamed" in page
    assert "new body" in page

    # Removing a tag: resubmit with only one of the two ids.
    client.post(
        f"/knowledge-base/{card_id}/edit",
        data={"title": "Renamed", "content_markdown": "new body", "label_ids": [ids["alpha"]]},
    )
    # Assert via the list page's tag filter, keeping this test at the HTTP
    # boundary like its neighbors rather than reaching into db_session.
    filtered_alpha = client.get(f"/knowledge-base?tag={ids['alpha']}").text
    filtered_beta = client.get(f"/knowledge-base?tag={ids['beta']}").text
    assert "Renamed" in filtered_alpha
    assert "Renamed" not in filtered_beta


def test_delete_card_removes_it_and_its_label_assignments(client, db_session):
    import re
    from app.models import LabelAssignment, LabelAttachType

    client.post("/settings/labels", data={"name": "to-delete-test"})
    # Same established extraction pattern as tests/test_bugs.py and
    # tests/test_execution.py — the label's own delete-form action URL
    # always embeds its id.
    label_id = re.search(r"/settings/labels/(\d+)/delete", client.get("/settings/labels").text).group(1)

    create = client.post("/knowledge-base", follow_redirects=False)
    card_id = int(create.headers["location"].rstrip("/").split("/")[-1])
    client.post(f"/knowledge-base/{card_id}/edit", data={"title": "Temp", "content_markdown": "x", "label_ids": [label_id]})

    assert db_session.query(LabelAssignment).filter_by(attach_type=LabelAttachType.CARD, attach_id=card_id).count() == 1

    response = client.post(f"/knowledge-base/{card_id}/delete", follow_redirects=False)
    assert response.status_code == 303
    assert client.get(f"/knowledge-base/{card_id}").status_code == 404
    assert db_session.query(LabelAssignment).filter_by(attach_type=LabelAttachType.CARD, attach_id=card_id).count() == 0


def test_delete_card_removes_its_uploads_directory(client, tmp_path, monkeypatch):
    from pathlib import Path
    import app.routers.knowledge_base as kb_module

    monkeypatch.setattr(kb_module, "UPLOADS_DIR", tmp_path)

    create = client.post("/knowledge-base", follow_redirects=False)
    card_id = int(create.headers["location"].rstrip("/").split("/")[-1])
    card_dir = tmp_path / "cards" / str(card_id)
    card_dir.mkdir(parents=True)
    (card_dir / "fake.png").write_bytes(b"not a real png")
    assert card_dir.exists()

    client.post(f"/knowledge-base/{card_id}/delete")
    assert not card_dir.exists()


def test_upload_image_to_a_card_returns_url_and_is_image_true(client):
    from pathlib import Path

    create = client.post("/knowledge-base", follow_redirects=False)
    card_id = create.headers["location"].rstrip("/").split("/")[-1]

    response = client.post(
        f"/knowledge-base/{card_id}/upload",
        files={"file": ("pasted.png", b"\x89PNG\r\n fake but has a content-type", "image/png")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_image"] is True
    assert body["url"].startswith(f"/uploads/cards/{card_id}/")
    assert (Path("app") / "uploads" / body["url"].removeprefix("/uploads/")).exists()


def test_upload_non_image_file_returns_is_image_false(client):
    create = client.post("/knowledge-base", follow_redirects=False)
    card_id = create.headers["location"].rstrip("/").split("/")[-1]

    response = client.post(
        f"/knowledge-base/{card_id}/upload",
        files={"file": ("notes.txt", b"plain text content", "text/plain")},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["is_image"] is False
    assert body["url"].startswith(f"/uploads/cards/{card_id}/")


def test_app_js_markdown_renderer_supports_images_and_language_tagged_code(client):
    resp = client.get("/static/js/app.js")
    assert resp.status_code == 200
    js = resp.text
    # Deletion tripwires: these exact substrings must survive whatever
    # extension Step 3 below makes to renderNoteMarkdown.
    assert "renderNoteMarkdown" in js
    assert "escapeHtmlForMarkdown" in js  # the escape-first invariant this whole function leans on
    assert "<img" in js  # image syntax now renders an <img>, not just a link
    assert "language-" in js  # fenced code with a language tag gets a language-<x> class

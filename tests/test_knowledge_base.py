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

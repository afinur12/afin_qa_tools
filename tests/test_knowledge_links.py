"""Links between Knowledge Management pages and stories/subtasks, both sides."""

from app.models import (
    KnowledgeLinkTarget, KnowledgePage, KnowledgePageLink, KnowledgeSection, Phase, PhaseType, Story, Subtask,
    SubtaskType, generate_internal_key,
)

FETCH = {"X-Requested-With": "fetch"}


def _story(db, code="NK-398", title="Develop new authorization endpoint"):
    story = Story(display_code=code, title=title, internal_key=generate_internal_key())
    db.add(story)
    db.commit()
    db.refresh(story)
    return story


def _subtask(db, story, code="NK-886"):
    phase = Phase(story_id=story.id, type=PhaseType.SIT)
    db.add(phase)
    db.flush()
    subtask = Subtask(phase_id=phase.id, display_code=code, title="Re STAGING", internal_key=generate_internal_key(),
                      subtask_type=SubtaskType.EXECUTION)
    db.add(subtask)
    db.commit()
    db.refresh(subtask)
    return subtask


def _page(db, title="Camara-icm consent page"):
    section = KnowledgeSection(name="Camara icm")
    db.add(section)
    db.flush()
    page = KnowledgePage(section_id=section.id, title=title)
    db.add(page)
    db.commit()
    db.refresh(page)
    return page


def test_link_targets_search_stories_and_subtasks(client, db_session):
    story = _story(db_session)
    _subtask(db_session, story)
    data = client.get("/knowledge/link-targets.json", params={"q": "nk-88"}).json()
    assert data["stories"] == []
    assert [s["code"] for s in data["subtasks"]] == ["NK-886"]
    assert [s["code"] for s in client.get("/knowledge/link-targets.json", params={"q": "authorization"}).json()["stories"]] == ["NK-398"]


def test_link_from_the_page_returns_a_chip_and_is_shown(client, db_session):
    story, page = _story(db_session), _page(db_session)
    link = client.post("/knowledge/links", data={"page_id": page.id, "target_type": "STORY", "target_id": story.id}, headers=FETCH).json()
    assert (link["kind"], link["code"], link["url"]) == ("Task", "NK-398", f"/stories/{story.id}")
    client.post("/knowledge/links", data={"page_id": page.id, "target_type": "STORY", "target_id": story.id}, headers=FETCH)
    assert db_session.query(KnowledgePageLink).count() == 1
    html = client.get(f"/knowledge/pages/{page.id}").text
    assert f'data-link-id="{link["id"]}"' in html and "NK-398" in html


def test_bad_links_are_refused(client, db_session):
    page = _page(db_session)
    assert client.post("/knowledge/links", data={"page_id": page.id, "target_type": "BUG", "target_id": 1}).status_code == 400
    assert client.post("/knowledge/links", data={"page_id": page.id, "target_type": "STORY", "target_id": 999}).status_code == 404
    assert client.post("/knowledge/links", data={"page_id": 999, "target_type": "STORY", "target_id": 1}).status_code == 404


def test_unlink_and_safe_next(client, db_session):
    story, page = _story(db_session), _page(db_session)
    link = KnowledgePageLink(page_id=page.id, target_type=KnowledgeLinkTarget.STORY, target_id=story.id)
    db_session.add(link)
    db_session.commit()
    response = client.post(f"/knowledge/links/{link.id}/delete", data={"next": "//evil.example"}, follow_redirects=False)
    assert response.headers["location"] == f"/knowledge/pages/{page.id}"
    assert db_session.query(KnowledgePageLink).count() == 0


def test_story_and_subtask_pages_list_their_linked_pages(client, db_session):
    story = _story(db_session)
    subtask = _subtask(db_session, story)
    page = _page(db_session)
    response = client.post("/knowledge/links", data={
        "page_id": page.id, "target_type": "SUBTASK", "target_id": subtask.id, "next": f"/subtasks/{subtask.id}",
    }, follow_redirects=False)
    assert response.headers["location"] == f"/subtasks/{subtask.id}"
    subtask_html = client.get(f"/subtasks/{subtask.id}").text
    assert "Linked knowledge pages" in subtask_html and f'href="/knowledge/pages/{page.id}"' in subtask_html
    story_html = client.get(f"/stories/{story.id}").text
    assert "Linked knowledge pages" in story_html and "No pages linked yet." in story_html


def test_deleting_a_subtask_or_story_drops_links_but_keeps_pages(client, db_session):
    from app import deletion

    story = _story(db_session)
    subtask = _subtask(db_session, story)
    page = _page(db_session)
    db_session.add_all([
        KnowledgePageLink(page_id=page.id, target_type=KnowledgeLinkTarget.SUBTASK, target_id=subtask.id),
        KnowledgePageLink(page_id=page.id, target_type=KnowledgeLinkTarget.STORY, target_id=story.id),
    ])
    db_session.commit()
    deletion.delete_subtask(db_session, subtask)
    db_session.commit()
    assert [l.target_type for l in db_session.query(KnowledgePageLink).all()] == [KnowledgeLinkTarget.STORY]
    db_session.delete(db_session.get(Phase, subtask.phase_id))
    db_session.commit()
    client.post(f"/stories/{story.id}/delete")
    assert db_session.query(KnowledgePageLink).count() == 0
    assert db_session.query(KnowledgePage).count() == 1


def test_links_to_deleted_targets_are_not_shown(client, db_session):
    page = _page(db_session)
    db_session.add(KnowledgePageLink(page_id=page.id, target_type=KnowledgeLinkTarget.STORY, target_id=424242))
    db_session.commit()
    assert "data-link-id=" not in client.get(f"/knowledge/pages/{page.id}").text

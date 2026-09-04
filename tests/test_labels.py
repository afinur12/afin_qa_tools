"""app/labels.py: get/set an entity's labels through the polymorphic
LabelAssignment join."""

from app.labels import get_labels, set_labels
from app.models import Label, LabelAssignment, LabelAttachType


def test_get_labels_returns_empty_list_when_none_assigned(db_session):
    assert get_labels(db_session, LabelAttachType.STORY, 1) == []


def test_set_labels_assigns_and_get_labels_returns_them_ordered_by_name(db_session):
    zebra = Label(name="zebra")
    apple = Label(name="apple")
    db_session.add_all([zebra, apple])
    db_session.commit()

    set_labels(db_session, LabelAttachType.STORY, 1, [zebra.id, apple.id])
    db_session.commit()

    names = [l.name for l in get_labels(db_session, LabelAttachType.STORY, 1)]
    assert names == ["apple", "zebra"]


def test_set_labels_is_scoped_to_attach_type_and_id(db_session):
    label = Label(name="shared")
    db_session.add(label)
    db_session.commit()

    set_labels(db_session, LabelAttachType.STORY, 1, [label.id])
    set_labels(db_session, LabelAttachType.SUBTASK, 1, [])  # same id, different attach_type
    db_session.commit()

    assert len(get_labels(db_session, LabelAttachType.STORY, 1)) == 1
    assert len(get_labels(db_session, LabelAttachType.SUBTASK, 1)) == 0


def test_set_labels_replaces_the_full_set(db_session):
    a = Label(name="a")
    b = Label(name="b")
    c = Label(name="c")
    db_session.add_all([a, b, c])
    db_session.commit()

    set_labels(db_session, LabelAttachType.BUG, 5, [a.id, b.id])
    db_session.commit()
    assert {l.name for l in get_labels(db_session, LabelAttachType.BUG, 5)} == {"a", "b"}

    set_labels(db_session, LabelAttachType.BUG, 5, [b.id, c.id])
    db_session.commit()
    assert {l.name for l in get_labels(db_session, LabelAttachType.BUG, 5)} == {"b", "c"}


def test_set_labels_called_twice_with_same_list_is_a_no_op(db_session):
    label = Label(name="stable")
    db_session.add(label)
    db_session.commit()

    set_labels(db_session, LabelAttachType.TESTCASE, 9, [label.id])
    db_session.commit()
    set_labels(db_session, LabelAttachType.TESTCASE, 9, [label.id])
    db_session.commit()

    count = db_session.query(LabelAssignment).filter(
        LabelAssignment.attach_type == LabelAttachType.TESTCASE, LabelAssignment.attach_id == 9
    ).count()
    assert count == 1


def test_set_labels_with_empty_list_removes_everything(db_session):
    label = Label(name="temp")
    db_session.add(label)
    db_session.commit()

    set_labels(db_session, LabelAttachType.STORY, 3, [label.id])
    db_session.commit()
    set_labels(db_session, LabelAttachType.STORY, 3, [])
    db_session.commit()

    assert get_labels(db_session, LabelAttachType.STORY, 3) == []

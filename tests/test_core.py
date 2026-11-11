from __future__ import annotations

from datetime import date, datetime, time

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from nexus.database.models import (
    Base,
    FinanceTransaction,
    Habit,
    HabitLog,
    LearningProgram,
    Lesson,
    Task,
    TaskHistory,
    User,
)
from nexus.database.repositories import delete_owned, list_owned, save_owned
from nexus.database.seed import seed_initial_learning_plan
from nexus.services.dates import local_to_utc, utc_to_local


@pytest.fixture
def session() -> Session:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    db = factory()
    db.add_all([
        User(id="person-a", email="a@example.com", display_name="A"),
        User(id="person-b", email="b@example.com", display_name="B"),
    ])
    db.commit()
    yield db
    db.close()
    engine.dispose()


def test_seed_creates_requested_100_video_plan_once(session: Session) -> None:
    assert seed_initial_learning_plan(session, "person-a") is True
    session.commit()
    assert seed_initial_learning_plan(session, "person-a") is False
    program = session.scalar(select(LearningProgram).where(LearningProgram.owner_id == "person-a"))
    lessons = list(session.scalars(select(Lesson).where(Lesson.owner_id == "person-a")).all())
    assert program is not None
    assert program.start_date == date(2026, 11, 11)
    assert program.target_date == date(2026, 11, 21)
    assert program.total_lessons == 100
    assert len(lessons) == 100
    assert sum(1 for lesson in lessons if lesson.due_date == date(2026, 11, 11)) == 9
    assert sum(1 for lesson in lessons if lesson.due_date == date(2026, 11, 20)) == 9
    assert sum(1 for lesson in lessons if lesson.due_date == date(2026, 11, 21)) == 10
    assert all(lesson.status == "Not started" for lesson in lessons)


def test_repository_reads_updates_and_deletes_are_owner_scoped(session: Session) -> None:
    first = save_owned(session, Task, "person-a", None, {"title": "Private task", "status": "Pending", "tags": []})
    session.commit()
    assert [item.id for item in list_owned(session, Task, "person-a")] == [first.id]
    assert list_owned(session, Task, "person-b") == []
    assert delete_owned(session, Task, "person-b", first.id) is False
    session.commit()
    assert session.get(Task, first.id) is not None
    assert delete_owned(session, Task, "person-a", first.id) is True
    session.commit()
    assert session.get(Task, first.id) is None


def test_owner_scoped_update_cannot_change_another_users_task(session: Session) -> None:
    record = Task(owner_id="person-a", title="Original", status="Pending", tags=[])
    session.add(record)
    session.commit()
    save_owned(session, Task, "person-b", record.id, {"title": "Changed", "status": "Completed", "tags": []})
    session.commit()
    assert session.get(Task, record.id).title == "Original"
    assert len(list_owned(session, Task, "person-b")) == 1  # new row has a distinct id


def test_local_timezone_roundtrip_across_utc_day_boundary() -> None:
    local = datetime(2026, 11, 11, 0, 30)
    stored = local_to_utc(local, "Asia/Kolkata")
    assert stored == datetime(2026, 11, 10, 19, 0)
    assert utc_to_local(stored, "Asia/Kolkata") == local


def test_finance_amount_validation_constraint(session: Session) -> None:
    session.add(FinanceTransaction(owner_id="person-a", kind="Expense", amount=-1, category="Test", transaction_date=date.today()))
    with pytest.raises(Exception):
        session.commit()
    session.rollback()


def test_task_status_history_is_representable_and_owner_scoped(session: Session) -> None:
    task = Task(owner_id="person-a", title="Stateful", status="Pending", tags=[])
    session.add(task)
    session.flush()
    session.add(TaskHistory(owner_id="person-a", task_id=task.id, previous_status="Pending", new_status="Completed", note="check-in"))
    session.commit()
    assert session.scalar(select(TaskHistory).where(TaskHistory.owner_id == "person-a", TaskHistory.task_id == task.id)).new_status == "Completed"


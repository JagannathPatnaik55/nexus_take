from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker

from nexus.database.models import Base, Habit, HabitLog, LearningProgram, Lesson, Task, TaskHistory, User
from nexus.services.metrics import dashboard_metrics, habit_streak, lesson_progress


def make_session() -> Session:
    engine = create_engine("sqlite://", future=True)
    Base.metadata.create_all(engine)
    db = sessionmaker(bind=engine, expire_on_commit=False)()
    db.add_all([User(id="person-a", email="a@example.com"), User(id="person-b", email="b@example.com")])
    db.commit()
    return db


def test_lesson_progress_uses_lesson_status_and_owner() -> None:
    session = make_session()
    program_a = LearningProgram(owner_id="person-a", title="A", total_lessons=2, planned_hours=2, status="Active")
    program_b = LearningProgram(owner_id="person-b", title="B", total_lessons=1, planned_hours=1, status="Active")
    session.add_all([program_a, program_b])
    session.flush()
    session.add_all([
        Lesson(owner_id="person-a", program_id=program_a.id, title="One", duration_minutes=60, status="Completed", sort_order=1),
        Lesson(owner_id="person-a", program_id=program_a.id, title="Two", duration_minutes=60, status="Needs revision", sort_order=2),
        Lesson(owner_id="person-b", program_id=program_b.id, title="Other", duration_minutes=60, status="Completed", sort_order=1),
    ])
    session.commit()
    assert lesson_progress(session, "person-a", program_a.id) == (1, 2, 50.0)
    session.close()


def test_dashboard_preserves_missing_rates_and_converts_local_dates() -> None:
    session = make_session()
    session.add(LearningProgram(owner_id="person-a", title="Active", total_lessons=0, planned_hours=0, status="Active"))
    # 2026-11-10 19:00 UTC is 2026-11-11 00:30 in Asia/Kolkata.
    task = Task(owner_id="person-a", title="Local-day completion", status="Completed", due_at=None, completed_at=datetime(2026, 11, 10, 19, 0), tags=[])
    session.add(task)
    session.flush()
    session.add(TaskHistory(owner_id="person-a", task_id=task.id, previous_status="Pending", new_status="Completed", changed_at=datetime(2026, 11, 10, 19, 0)))
    session.commit()
    metrics = dashboard_metrics(session, "person-a", date(2026, 11, 11), "Asia/Kolkata")
    assert metrics["tasks_completed_today"] == 1
    assert metrics["weekly_completion_pct"] is None
    assert metrics["study_hours_today"] == 0
    assert metrics["active_programs"] == 1
    session.close()


def test_habit_streak_uses_complete_historical_logs_after_archive() -> None:
    session = make_session()
    habit = Habit(owner_id="person-a", name="Read", frequency="Daily", weekdays=[])
    session.add(habit)
    session.flush()
    session.add_all([
        HabitLog(owner_id="person-a", habit_id=habit.id, log_date=date(2026, 11, 9), is_complete=True),
        HabitLog(owner_id="person-a", habit_id=habit.id, log_date=date(2026, 11, 10), is_complete=True),
        HabitLog(owner_id="person-a", habit_id=habit.id, log_date=date(2026, 11, 11), is_complete=True),
    ])
    habit.archived_on = date(2026, 11, 12)
    session.commit()
    assert habit_streak(session, "person-a", habit.id, date(2026, 11, 11)) == 3
    assert session.scalar(select(func.count()).select_from(HabitLog).where(HabitLog.owner_id == "person-a")) == 3
    session.close()

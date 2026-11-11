"""Metrics computed only from stored records; missing observations remain missing."""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date, timedelta

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from nexus.database.models import (
    ActivitySession,
    ApplicationSettings,
    Budget,
    CalendarEvent,
    FinanceTransaction,
    Goal,
    GoalHistory,
    GoalMilestone,
    Habit,
    HabitLog,
    LearningProgram,
    LearningSession,
    Lesson,
    LessonHistory,
    Note,
    RoutineCompletion,
    RoutineItem,
    RoutineTemplate,
    RevisionCard,
    RevisionSession,
    Task,
    TaskHistory,
    WellnessLog,
)
from nexus.services.dates import utc_to_local
from nexus.services.metrics import dashboard_metrics, habit_streak, lesson_progress


def productivity_days(session: Session, owner_id: str, start: date, end: date, timezone_name: str = "UTC") -> pd.DataFrame:
    completed: defaultdict[date, set[tuple[str, str]]] = defaultdict(set)
    for history in session.scalars(select(TaskHistory).where(TaskHistory.owner_id == owner_id, TaskHistory.new_status == "Completed")).all():
        day = utc_to_local(history.changed_at, timezone_name).date()
        if start <= day <= end:
            completed[day].add(("task", history.task_id))
    for history in session.scalars(select(LessonHistory).where(LessonHistory.owner_id == owner_id, LessonHistory.new_status == "Completed")).all():
        day = utc_to_local(history.changed_at, timezone_name).date()
        if start <= day <= end:
            completed[day].add(("lesson", history.lesson_id))
    return pd.DataFrame({"date": pd.date_range(start, end, freq="D").date}).assign(
        completed_items=lambda frame: [len(completed.get(day, set())) for day in frame["date"]]
    )


def habit_heatmap(session: Session, owner_id: str, days: int = 120) -> pd.DataFrame:
    start = date.today() - timedelta(days=days - 1)
    rows = session.scalars(select(HabitLog).where(HabitLog.owner_id == owner_id, HabitLog.is_complete.is_(True), HabitLog.log_date >= start)).all()
    counts = Counter(row.log_date for row in rows)
    dates = pd.date_range(start, date.today(), freq="D").date
    return pd.DataFrame({"date": dates, "completed": [counts.get(d, 0) for d in dates]})


def learning_hours_by_day(session: Session, owner_id: str, start: date, end: date, timezone_name: str) -> pd.DataFrame:
    rows = session.scalars(select(LearningSession).where(LearningSession.owner_id == owner_id)).all()
    totals: defaultdict[date, int] = defaultdict(int)
    for row in rows:
        day = utc_to_local(row.started_at, timezone_name).date()
        if start <= day <= end:
            totals[day] += row.duration_minutes
    return pd.DataFrame({"date": pd.date_range(start, end, freq="D").date}).assign(
        hours=lambda frame: [round(totals.get(day, 0) / 60, 2) for day in frame["date"]]
    )


def scoped_export_rows(session: Session, owner_id: str) -> dict[str, list[dict]]:
    models = {
        "tasks": Task,
        "task_history": TaskHistory,
        "learning_programs": LearningProgram,
        "lessons": Lesson,
        "lesson_history": LessonHistory,
        "goal_history": GoalHistory,
        "learning_sessions": LearningSession,
        "goals": Goal,
        "goal_milestones": GoalMilestone,
        "habits": Habit,
        "habit_logs": HabitLog,
        "routine_templates": RoutineTemplate,
        "routine_items": RoutineItem,
        "routine_completions": RoutineCompletion,
        "revision_cards": RevisionCard,
        "revision_sessions": RevisionSession,
        "activities": ActivitySession,
        "wellness": WellnessLog,
        "calendar_events": CalendarEvent,
        "notes": Note,
        "transactions": FinanceTransaction,
        "budgets": Budget,
        "application_settings": ApplicationSettings,
    }
    output: dict[str, list[dict]] = {}
    for name, model in models.items():
        records = session.scalars(select(model).where(model.owner_id == owner_id)).all()
        output[name] = [
            {column.name: getattr(record, column.name) for column in model.__table__.columns}
            for record in records
        ]
    return output


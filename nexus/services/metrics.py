"""Database-only indicators, separated from dataframe-heavy report transforms."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexus.database.models import Goal, Habit, HabitLog, LearningProgram, LearningSession, Lesson, LessonHistory, Task, TaskHistory
from nexus.services.dates import utc_to_local


def dashboard_metrics(session: Session, owner_id: str, today: date, timezone_name: str = "UTC") -> dict[str, int | float | None]:
    tasks = session.scalars(select(Task).where(Task.owner_id == owner_id)).all()
    due_today = [t for t in tasks if t.due_at and utc_to_local(t.due_at, timezone_name).date() == today and t.status not in {"Cancelled", "Deferred"}]
    completed_today = len({
        row.task_id for row in session.scalars(select(TaskHistory).where(TaskHistory.owner_id == owner_id, TaskHistory.new_status == "Completed")).all()
        if utc_to_local(row.changed_at, timezone_name).date() == today
    })
    sessions = session.scalars(select(LearningSession).where(LearningSession.owner_id == owner_id)).all()
    study_minutes = sum(s.duration_minutes for s in sessions if utc_to_local(s.started_at, timezone_name).date() == today)
    programs = session.scalars(select(LearningProgram).where(LearningProgram.owner_id == owner_id, LearningProgram.status == "Active")).all()
    habits = session.scalars(select(Habit).where(Habit.owner_id == owner_id, Habit.archived_on.is_(None))).all()
    logs = session.scalars(select(HabitLog).where(HabitLog.owner_id == owner_id, HabitLog.log_date == today, HabitLog.is_complete.is_(True))).all()
    due_habits = [h for h in habits if h.frequency == "Daily" or (h.frequency == "Selected weekdays" and today.weekday() in (h.weekdays or []))]
    goals = session.scalars(select(Goal).where(Goal.owner_id == owner_id, Goal.status == "Active")).all()

    day_activity: set[date] = set()
    for row in session.scalars(select(TaskHistory).where(TaskHistory.owner_id == owner_id, TaskHistory.new_status == "Completed")).all():
        day_activity.add(utc_to_local(row.changed_at, timezone_name).date())
    for row in session.scalars(select(LessonHistory).where(LessonHistory.owner_id == owner_id, LessonHistory.new_status == "Completed")).all():
        day_activity.add(utc_to_local(row.changed_at, timezone_name).date())
    for record in session.scalars(select(HabitLog).where(HabitLog.owner_id == owner_id, HabitLog.is_complete.is_(True))).all():
        day_activity.add(record.log_date)
    for record in sessions:
        day_activity.add(utc_to_local(record.started_at, timezone_name).date())
    streak = 0
    cursor = today
    while cursor in day_activity:
        streak += 1
        cursor -= timedelta(days=1)

    week_start = today - timedelta(days=today.weekday())
    week_end = week_start + timedelta(days=6)
    due_week = [t for t in tasks if t.due_at and t.status not in {"Cancelled", "Deferred"} and week_start <= utc_to_local(t.due_at, timezone_name).date() <= week_end]
    week_pct = round(sum(1 for t in due_week if t.status == "Completed") / len(due_week) * 100) if due_week else None
    scheduled_ids = {habit.id for habit in due_habits}
    return {
        "tasks_completed_today": completed_today,
        "tasks_pending": sum(1 for t in tasks if t.status in {"Pending", "In progress"}),
        "study_hours_today": round(study_minutes / 60, 1),
        "active_programs": len(programs),
        "habits_complete": sum(1 for log in logs if log.habit_id in scheduled_ids),
        "habits_due": len(due_habits),
        "active_goals": len(goals),
        "productivity_streak": streak,
        "weekly_completion_pct": week_pct,
        "tasks_due_today": len(due_today),
    }


def lesson_progress(session: Session, owner_id: str, program_id: str) -> tuple[int, int, float]:
    lessons = session.scalars(select(Lesson).where(Lesson.owner_id == owner_id, Lesson.program_id == program_id)).all()
    complete = sum(1 for lesson in lessons if lesson.status == "Completed")
    return complete, len(lessons), round(complete / len(lessons) * 100, 1) if lessons else 0.0


def habit_streak(session: Session, owner_id: str, habit_id: str, today: date) -> int:
    completed_dates = set(session.scalars(
        select(HabitLog.log_date).where(
            HabitLog.owner_id == owner_id,
            HabitLog.habit_id == habit_id,
            HabitLog.is_complete.is_(True),
            HabitLog.log_date <= today,
        )
    ).all())
    streak = 0
    cursor = today
    while cursor in completed_dates:
        streak += 1
        cursor -= timedelta(days=1)
    return streak

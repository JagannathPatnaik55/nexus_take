"""Idempotent first-login data that was explicitly requested by the user."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from nexus.database.models import LearningProgram, Lesson


def seed_initial_learning_plan(session: Session, owner_id: str) -> bool:
    existing = session.scalar(
        select(LearningProgram.id).where(
            LearningProgram.owner_id == owner_id,
            LearningProgram.title == "SAP Full-Stack ABAP Developer",
        )
    )
    if existing:
        return False
    start = date(2026, 11, 11)
    end = date(2026, 11, 21)
    program = LearningProgram(
        owner_id=owner_id,
        title="SAP Full-Stack ABAP Developer",
        description="Configurable 100-video learning plan. Adjust dates, lessons, and targets at any time.",
        subject="SAP ABAP",
        start_date=start,
        target_date=end,
        total_lessons=100,
        planned_hours=100,
        status="Active",
    )
    session.add(program)
    session.flush()
    lesson_index = 1
    for day_offset in range(11):
        due_date = date.fromordinal(start.toordinal() + day_offset)
        daily_target = 9 if day_offset < 10 else 10
        for _ in range(daily_target):
            session.add(
                Lesson(
                    owner_id=owner_id,
                    program_id=program.id,
                    title=f"Video {lesson_index:03d}",
                    lesson_type="Video",
                    duration_minutes=60,
                    status="Not started",
                    due_date=due_date,
                    sort_order=lesson_index,
                )
            )
            lesson_index += 1
    return True


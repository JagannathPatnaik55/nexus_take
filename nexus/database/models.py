"""Normalized SQLAlchemy models for NEXUS."""

from __future__ import annotations

from datetime import date, datetime, time
from typing import Any
from uuid import uuid4

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    Time,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def new_id() -> str:
    return str(uuid4())


class Base(DeclarativeBase):
    pass


class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(), nullable=False
    )


class OwnerMixin:
    owner_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id"), index=True, nullable=False)


class User(Base, TimestampMixin):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(255), primary_key=True)
    email: Mapped[str] = mapped_column(String(320), unique=True, index=True, nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)


class LearningProgram(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "learning_programs"
    __table_args__ = (CheckConstraint("total_lessons >= 0"), CheckConstraint("planned_hours >= 0"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    subject: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    target_date: Mapped[date | None] = mapped_column(Date)
    total_lessons: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    planned_hours: Mapped[float] = mapped_column(Float, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Active", nullable=False)
    reference_materials: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Lesson(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "lessons"
    __table_args__ = (
        CheckConstraint("duration_minutes >= 0"),
        CheckConstraint("understanding_level IS NULL OR (understanding_level BETWEEN 1 AND 5)"),
        Index("ix_lessons_owner_program_order", "owner_id", "program_id", "sort_order"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    program_id: Mapped[str] = mapped_column(ForeignKey("learning_programs.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    lesson_type: Mapped[str] = mapped_column(String(40), default="Video", nullable=False)
    url: Mapped[str] = mapped_column(Text, default="", nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Not started", nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    difficulty: Mapped[str] = mapped_column(String(32), default="Medium", nullable=False)
    understanding_level: Mapped[int | None] = mapped_column(Integer)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class LessonHistory(Base, OwnerMixin):
    __tablename__ = "lesson_history"
    __table_args__ = (Index("ix_lesson_history_owner_changed", "owner_id", "changed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    lesson_id: Mapped[str] = mapped_column(ForeignKey("lessons.id", ondelete="CASCADE"), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    new_status: Mapped[str] = mapped_column(String(32), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class LearningSession(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "learning_sessions"
    __table_args__ = (CheckConstraint("duration_minutes > 0"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    program_id: Mapped[str | None] = mapped_column(ForeignKey("learning_programs.id", ondelete="SET NULL"))
    lesson_id: Mapped[str | None] = mapped_column(ForeignKey("lessons.id", ondelete="SET NULL"))
    started_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class RevisionCard(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "revision_cards"
    __table_args__ = (CheckConstraint("understanding_level IS NULL OR (understanding_level BETWEEN 1 AND 5)"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    program_id: Mapped[str | None] = mapped_column(ForeignKey("learning_programs.id", ondelete="SET NULL"))
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, default="", nullable=False)
    difficult: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    understanding_level: Mapped[int | None] = mapped_column(Integer)
    interval_days: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    last_reviewed_at: Mapped[datetime | None] = mapped_column(DateTime)
    next_review_at: Mapped[datetime | None] = mapped_column(DateTime)


class RevisionSession(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "revision_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    card_id: Mapped[str | None] = mapped_column(ForeignKey("revision_cards.id", ondelete="SET NULL"))
    reviewed_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)
    understood: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class Task(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "tasks"
    __table_args__ = (Index("ix_tasks_owner_status_due", "owner_id", "status", "due_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="General", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="Pending", nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime)
    start_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    is_recurring: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    recurrence_rule: Mapped[str] = mapped_column(String(120), default="", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    parent_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))


class TaskHistory(Base, OwnerMixin):
    __tablename__ = "task_history"
    __table_args__ = (Index("ix_task_history_owner_changed", "owner_id", "changed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id", ondelete="CASCADE"), nullable=False)
    previous_status: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Goal(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "goals"
    __table_args__ = (CheckConstraint("progress BETWEEN 0 AND 100"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="Personal", nullable=False)
    period: Mapped[str] = mapped_column(String(24), default="Monthly", nullable=False)
    start_date: Mapped[date | None] = mapped_column(Date)
    target_date: Mapped[date | None] = mapped_column(Date)
    priority: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False)
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="Active", nullable=False)
    linked_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    linked_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)


class GoalHistory(Base, OwnerMixin):
    __tablename__ = "goal_history"
    __table_args__ = (Index("ix_goal_history_owner_changed", "owner_id", "changed_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    previous_progress: Mapped[int] = mapped_column(Integer, nullable=False)
    new_progress: Mapped[int] = mapped_column(Integer, nullable=False)
    previous_status: Mapped[str] = mapped_column(String(24), default="", nullable=False)
    new_status: Mapped[str] = mapped_column(String(24), nullable=False)
    changed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class GoalMilestone(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "goal_milestones"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    goal_id: Mapped[str] = mapped_column(ForeignKey("goals.id", ondelete="CASCADE"), nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)


class Habit(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "habits"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    frequency: Mapped[str] = mapped_column(String(24), default="Daily", nullable=False)
    weekdays: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)
    archived_on: Mapped[date | None] = mapped_column(Date)


class HabitLog(Base, OwnerMixin):
    __tablename__ = "habit_logs"
    __table_args__ = (UniqueConstraint("owner_id", "habit_id", "log_date", name="uq_habit_log_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    habit_id: Mapped[str] = mapped_column(ForeignKey("habits.id", ondelete="CASCADE"), nullable=False)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    note: Mapped[str] = mapped_column(Text, default="", nullable=False)


class RoutineTemplate(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "routine_templates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class RoutineItem(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "routine_items"
    __table_args__ = (CheckConstraint("end_time > start_time"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    template_id: Mapped[str] = mapped_column(ForeignKey("routine_templates.id", ondelete="CASCADE"), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    activity: Mapped[str] = mapped_column(String(200), nullable=False)
    category: Mapped[str] = mapped_column(String(40), default="Personal time", nullable=False)
    priority: Mapped[str] = mapped_column(String(20), default="Medium", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    weekdays: Mapped[list[int]] = mapped_column(JSON, default=list, nullable=False)


class RoutineCompletion(Base, OwnerMixin):
    __tablename__ = "routine_completions"
    __table_args__ = (UniqueConstraint("owner_id", "routine_item_id", "completion_date", name="uq_routine_completion_day"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    routine_item_id: Mapped[str] = mapped_column(ForeignKey("routine_items.id", ondelete="CASCADE"), nullable=False)
    completion_date: Mapped[date] = mapped_column(Date, nullable=False)
    is_complete: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class ActivitySession(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "activity_sessions"
    __table_args__ = (CheckConstraint("duration_minutes > 0"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    activity_date: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    activity_type: Mapped[str] = mapped_column(String(60), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    observations: Mapped[str] = mapped_column(Text, default="", nullable=False)


class WellnessLog(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "wellness_logs"
    __table_args__ = (
        UniqueConstraint("owner_id", "log_date", name="uq_wellness_log_day"),
        CheckConstraint("sleep_hours IS NULL OR (sleep_hours BETWEEN 0 AND 24)"),
        CheckConstraint("sleep_quality IS NULL OR (sleep_quality BETWEEN 1 AND 5)"),
        CheckConstraint("energy_level IS NULL OR (energy_level BETWEEN 1 AND 5)"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    log_date: Mapped[date] = mapped_column(Date, nullable=False)
    sleep_hours: Mapped[float | None] = mapped_column(Float)
    sleep_quality: Mapped[int | None] = mapped_column(Integer)
    energy_level: Mapped[int | None] = mapped_column(Integer)
    mood: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    notes: Mapped[str] = mapped_column(Text, default="", nullable=False)


class CalendarEvent(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "calendar_events"
    __table_args__ = (CheckConstraint("ends_at > starts_at"), Index("ix_calendar_owner_start", "owner_id", "starts_at"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(60), default="Event", nullable=False)
    starts_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    ends_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    related_type: Mapped[str] = mapped_column(String(32), default="", nullable=False)
    related_id: Mapped[str] = mapped_column(String(36), default="", nullable=False)


class Note(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "notes"
    __table_args__ = (Index("ix_notes_owner_updated", "owner_id", "updated_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    content: Mapped[str] = mapped_column(Text, default="", nullable=False)
    category: Mapped[str] = mapped_column(String(100), default="General Knowledge", nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list, nullable=False)
    program_id: Mapped[str | None] = mapped_column(ForeignKey("learning_programs.id", ondelete="SET NULL"))
    task_id: Mapped[str | None] = mapped_column(ForeignKey("tasks.id", ondelete="SET NULL"))
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_pinned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)


class FinanceTransaction(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "transactions"
    __table_args__ = (CheckConstraint("amount > 0"), Index("ix_transactions_owner_date", "owner_id", "transaction_date"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    payment_method: Mapped[str] = mapped_column(String(60), default="", nullable=False)
    description: Mapped[str] = mapped_column(Text, default="", nullable=False)


class Budget(Base, OwnerMixin, TimestampMixin):
    __tablename__ = "budgets"
    __table_args__ = (UniqueConstraint("owner_id", "month", "category", name="uq_budget_month_category"), CheckConstraint("amount >= 0"))

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=new_id)
    month: Mapped[str] = mapped_column(String(7), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    amount: Mapped[float] = mapped_column(Float, nullable=False)


class ApplicationSettings(Base, TimestampMixin):
    __tablename__ = "application_settings"

    owner_id: Mapped[str] = mapped_column(String(255), ForeignKey("users.id"), primary_key=True)
    settings_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict, nullable=False)


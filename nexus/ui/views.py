"""Composed Streamlit pages. Each page uses shared repository and form components."""

from __future__ import annotations

from collections import Counter
from datetime import date, datetime, time, timedelta
from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st
from sqlalchemy import select

from nexus.config import database_config
from nexus.database.connection import session_scope
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
    RevisionCard,
    RevisionSession,
    RoutineCompletion,
    RoutineItem,
    RoutineTemplate,
    Task,
    TaskHistory,
    WellnessLog,
    new_id,
)
from nexus.database.repositories import list_owned, save_owned
from nexus.services.ai import ask_assistant, configured as ai_configured
from nexus.services.analytics import (
    dashboard_metrics,
    habit_heatmap,
    habit_streak,
    learning_hours_by_day,
    lesson_progress,
    productivity_days,
)
from nexus.services.dates import get_zone, local_to_utc, utc_to_local
from nexus.ui.common import csv_bytes, empty_state, page_header, section_title, show_dataframe, show_plotly
from nexus.ui.crud import Field as F, Resource, render_resource


def _db_url() -> str:
    return st.session_state.get("nexus_db_url") or database_config().url


TASKS = Resource(
    "tasks", "Task Manager", "Capture priorities, due dates, recurring work, and a durable completion history.", Task,
    (
        F("title", "Task title", required=True), F("description", "Description", "textarea"),
        F("category", "Category", default="General"), F("priority", "Priority", "select", ("Critical", "High", "Medium", "Low"), default="Medium"),
        F("status", "Status", "select", ("Pending", "In progress", "Completed", "Deferred", "Cancelled"), default="Pending"),
        F("due_at", "Due date and time", "datetime"), F("start_at", "Start time", "datetime"),
        F("is_recurring", "Recurring task", "bool", default=False), F("recurrence_rule", "Recurrence description"),
        F("parent_id", "Parent task", "reference", reference_model=Task, reference_label="title"),
        F("tags", "Tags", "jsonlist"),
    ),
    (("title", "Task"), ("priority", "Priority"), ("status", "Status"), ("category", "Category"), ("due_at", "Due")),
    "title", order_field="created_at",
)

GOALS = Resource(
    "goals", "Goals", "Turn long-term intentions into measurable milestones and visible progress.", Goal,
    (
        F("title", "Goal title", required=True), F("description", "Description", "textarea"),
        F("category", "Category", default="Personal"), F("period", "Planning period", "select", ("Daily", "Weekly", "Monthly", "Quarterly", "Yearly", "Long-term"), default="Monthly"),
        F("start_date", "Start date", "date"), F("target_date", "Target date", "date"),
        F("priority", "Priority", "select", ("Critical", "High", "Medium", "Low"), default="Medium"),
        F("progress", "Progress (%)", "int", required=True, default=0, minimum=0, maximum=100),
        F("status", "Status", "select", ("Active", "Completed", "Paused", "Cancelled"), default="Active"),
        F("linked_type", "Calculate progress from", "select", ("Manual", "Task", "Learning program"), default="Manual"),
        F("linked_id", "Linked record ID", help="Paste the ID shown in the corresponding module. Linked progress is recalculated when this goal is saved."),
    ),
    (("title", "Goal"), ("category", "Category"), ("period", "Period"), ("progress", "Progress %"), ("status", "Status"), ("target_date", "Target")),
    "title",
)

MILESTONES = Resource(
    "goal-milestones", "Goal milestones", "Track smaller checkpoints while keeping each goal's history.", GoalMilestone,
    (
        F("goal_id", "Goal", "reference", required=True, reference_model=Goal, reference_label="title"),
        F("title", "Milestone", required=True), F("due_date", "Due date", "date"), F("is_complete", "Complete", "bool"),
        F("completed_at", "Completed at", "datetime"),
    ),
    (("goal_id", "Goal ID"), ("title", "Milestone"), ("due_date", "Due"), ("is_complete", "Complete")),
    "title",
)

PROGRAMS = Resource(
    "learning-programs", "Learning programs", "Organize subjects, targets, references, and completion status.", LearningProgram,
    (
        F("title", "Program title", required=True), F("description", "Description", "textarea"), F("subject", "Subject"),
        F("start_date", "Start date", "date"), F("target_date", "Target completion", "date"),
        F("total_lessons", "Total lessons", "int", required=True, default=0), F("planned_hours", "Planned hours", "float", default=0),
        F("status", "Status", "select", ("Active", "Paused", "Completed", "Archived"), default="Active"),
        F("reference_materials", "Reference materials", "textarea"),
    ),
    (("title", "Program"), ("subject", "Subject"), ("start_date", "Start"), ("target_date", "Target"), ("status", "Status"), ("total_lessons", "Lessons")),
    "title",
)

LESSONS = Resource(
    "lessons", "Lessons and videos", "Reorder with sort order, track status, and record understanding separately from completion.", Lesson,
    (
        F("program_id", "Program", "reference", required=True, reference_model=LearningProgram, reference_label="title"),
        F("title", "Lesson title", required=True), F("lesson_type", "Type", "select", ("Video", "Article", "Documentation", "Exercise", "Assignment", "Project"), default="Video"),
        F("url", "Reference URL"), F("duration_minutes", "Duration (minutes)", "int", default=60),
        F("status", "Status", "select", ("Not started", "In progress", "Completed", "Needs revision"), default="Not started"),
        F("due_date", "Planned date", "date"), F("difficulty", "Difficulty", "select", ("Easy", "Medium", "Hard"), default="Medium"),
        F("understanding_level", "Understanding (1–5)", "int", minimum=1, maximum=5), F("sort_order", "Order", "int", default=0), F("notes", "Notes", "textarea"),
    ),
    (("title", "Lesson"), ("program_id", "Program ID"), ("lesson_type", "Type"), ("status", "Status"), ("due_date", "Planned"), ("duration_minutes", "Minutes"), ("understanding_level", "Understanding")),
    "title", order_field="sort_order", ascending=True,
)

LEARNING_SESSIONS = Resource(
    "learning-sessions", "Learning sessions", "Log real study time and attach it to a program or lesson.", LearningSession,
    (
        F("program_id", "Program", "reference", reference_model=LearningProgram, reference_label="title"),
        F("lesson_id", "Lesson", "reference", reference_model=Lesson, reference_label="title"),
        F("started_at", "Session date and time", "datetime", required=True), F("duration_minutes", "Duration (minutes)", "positive_int", required=True, default=60),
        F("notes", "Session notes", "textarea"),
    ),
    (("started_at", "Started"), ("program_id", "Program ID"), ("lesson_id", "Lesson ID"), ("duration_minutes", "Minutes"), ("notes", "Notes")),
    "notes", order_field="started_at",
)

REVISION_CARDS = Resource(
    "revision-cards", "Active recall cards", "Questions, answers, difficulty, understanding, and the next spaced review date.", RevisionCard,
    (
        F("program_id", "Program", "reference", reference_model=LearningProgram, reference_label="title"),
        F("question", "Question", "textarea", required=True), F("answer", "Answer", "textarea"), F("difficult", "Needs extra practice", "bool"),
        F("understanding_level", "Understanding (1–5)", "int", minimum=1, maximum=5), F("interval_days", "Revision interval (days)", "positive_int", default=1),
        F("last_reviewed_at", "Last reviewed", "datetime"), F("next_review_at", "Next review", "datetime"),
    ),
    (("question", "Question"), ("difficult", "Difficult"), ("understanding_level", "Understanding"), ("interval_days", "Interval days"), ("next_review_at", "Next review")),
    "question",
)

REVISION_SESSIONS = Resource(
    "revision-sessions", "Revision sessions", "Keep a dated record of actual recall practice and self-reported understanding.", RevisionSession,
    (
        F("card_id", "Card", "reference", reference_model=RevisionCard, reference_label="question"), F("reviewed_at", "Reviewed at", "datetime", required=True),
        F("understood", "Understood during this review", "bool"), F("notes", "Notes", "textarea"),
    ),
    (("reviewed_at", "Reviewed"), ("card_id", "Card ID"), ("understood", "Understood"), ("notes", "Notes")),
    "notes", order_field="reviewed_at",
)

HABITS = Resource(
    "habits", "Habit definitions", "Add and edit routines without rewriting historical completion logs.", Habit,
    (
        F("name", "Habit", required=True), F("description", "Description", "textarea"),
        F("frequency", "Frequency", "select", ("Daily", "Selected weekdays", "Weekly", "Custom"), default="Daily"),
        F("weekdays", "Scheduled weekdays", "weekdaylist", help="For Selected weekdays, choose one or more days. Weekly and Custom can be logged manually."),
        F("archived_on", "Archive date", "date"),
    ),
    (("name", "Habit"), ("frequency", "Frequency"), ("weekdays", "Weekdays"), ("archived_on", "Archived")), "name",
)

ROUTINE_TEMPLATES = Resource(
    "routine-templates", "Routine templates", "Create editable day plans you can reuse.", RoutineTemplate,
    (F("title", "Template name", required=True), F("is_active", "Active", "bool", default=True)),
    (("title", "Template"), ("is_active", "Active")), "title",
)

ROUTINE_ITEMS = Resource(
    "routine-items", "Time blocks", "Build a reusable timeline and flag overlapping blocks before saving.", RoutineItem,
    (
        F("template_id", "Routine template", "reference", required=True, reference_model=RoutineTemplate, reference_label="title"),
        F("start_time", "Start", "time", required=True, default=time(8, 30)), F("end_time", "End", "time", required=True, default=time(9, 30)),
        F("activity", "Activity", required=True), F("category", "Category", "select", ("Deep work", "Shallow work", "Learning", "Exercise", "Meals", "Breaks", "Personal time", "Sleep"), default="Learning"),
        F("priority", "Priority", "select", ("Critical", "High", "Medium", "Low"), default="Medium"), F("weekdays", "Scheduled weekdays", "weekdaylist"),
        F("description", "Description", "textarea"),
    ),
    (("template_id", "Template ID"), ("start_time", "Start"), ("end_time", "End"), ("activity", "Activity"), ("category", "Category"), ("weekdays", "Weekdays")),
    "activity", order_field="start_time", ascending=True,
)

ACTIVITIES = Resource(
    "activities", "Activity sessions", "Record movement and exercise as personal history.", ActivitySession,
    (F("activity_date", "Date and time", "datetime", required=True), F("activity_type", "Activity", "select", ("Walking", "Running", "Cycling", "Sports", "Strength training", "Stretching", "Other"), default="Walking"),
     F("duration_minutes", "Duration (minutes)", "positive_int", required=True, default=30), F("observations", "Observations", "textarea")),
    (("activity_date", "Date"), ("activity_type", "Activity"), ("duration_minutes", "Minutes"), ("observations", "Notes")), "activity_type", order_field="activity_date",
)

WELLNESS = Resource(
    "wellness", "Sleep and wellness log", "Track subjective sleep, mood, and energy without medical scoring or targets.", WellnessLog,
    (F("log_date", "Log date", "date", required=True), F("sleep_hours", "Sleep duration (hours)", "float", maximum=24), F("sleep_quality", "Sleep quality (1–5)", "int", minimum=1, maximum=5),
     F("energy_level", "Energy (1–5)", "int", minimum=1, maximum=5), F("mood", "Mood"), F("notes", "Notes", "textarea")),
    (("log_date", "Date"), ("sleep_hours", "Sleep hours"), ("sleep_quality", "Sleep quality"), ("energy_level", "Energy"), ("mood", "Mood"), ("notes", "Notes")), "log_date", order_field="log_date",
)

EVENTS = Resource(
    "calendar-events", "Calendar events", "Add personal events and inspect tasks and learning deadlines together.", CalendarEvent,
    (F("title", "Event", required=True), F("description", "Description", "textarea"), F("category", "Category", default="Event"),
     F("starts_at", "Starts", "datetime", required=True), F("ends_at", "Ends", "datetime", required=True),
     F("related_type", "Related module"), F("related_id", "Related record ID")),
    (("title", "Event"), ("category", "Type"), ("starts_at", "Starts"), ("ends_at", "Ends"), ("description", "Description")), "title", order_field="starts_at",
)

NOTES = Resource(
    "notes", "Notes and knowledge base", "Searchable Markdown notes with tags, folders, links, pinning, favorites, and archives.", Note,
    (F("title", "Title", required=True), F("content", "Markdown content", "textarea"),
     F("category", "Folder", "select", ("SAP ABAP", "Python", "Programming", "Professional Development", "Personal Notes", "Ideas", "General Knowledge"), default="General Knowledge"),
     F("tags", "Tags", "jsonlist"), F("program_id", "Related program", "reference", reference_model=LearningProgram, reference_label="title"),
     F("task_id", "Related task", "reference", reference_model=Task, reference_label="title"),
     F("is_favorite", "Favorite", "bool"), F("is_pinned", "Pinned", "bool"), F("is_archived", "Archived", "bool")),
    (("title", "Title"), ("category", "Folder"), ("tags", "Tags"), ("is_pinned", "Pinned"), ("is_favorite", "Favorite"), ("is_archived", "Archived"), ("updated_at", "Updated")), "title",
)

TRANSACTIONS = Resource(
    "transactions", "Finance tracker", "Manually record income and spending. No bank connection or credentials are used.", FinanceTransaction,
    (F("kind", "Type", "select", ("Expense", "Income"), required=True, default="Expense"), F("amount", "Amount", "float", required=True),
     F("category", "Category", required=True), F("transaction_date", "Date", "date", required=True),
     F("payment_method", "Payment method"), F("description", "Description", "textarea")),
    (("transaction_date", "Date"), ("kind", "Type"), ("category", "Category"), ("amount", "Amount"), ("payment_method", "Method"), ("description", "Description")), "description", order_field="transaction_date",
)

BUDGETS = Resource(
    "budgets", "Monthly budgets", "Set monthly category caps and compare actual recorded expenses.", Budget,
    (F("month", "Month (YYYY-MM)", required=True, help="Enter the month in YYYY-MM format."), F("category", "Category", required=True), F("amount", "Budget amount", "float", required=True)),
    (("month", "Month"), ("category", "Category"), ("amount", "Budget")), "category", order_field="month",
)


def overview(owner_id: str) -> None:
    settings = st.session_state.get("nexus_settings", {})
    zone_name = settings.get("timezone", "Asia/Kolkata")
    local_now = datetime.now(get_zone(zone_name))
    today = local_now.date()
    page_header("Overview", "A clear view of your day, learning, and follow-through.")
    with session_scope(_db_url()) as session:
        metrics = dashboard_metrics(session, owner_id, today, zone_name)
        tasks = list_owned(session, Task, owner_id, order_by=Task.due_at)
        programs = list_owned(session, LearningProgram, owner_id, order_by=LearningProgram.created_at.desc())
        lessons = list_owned(session, Lesson, owner_id)
        habits = list_owned(session, Habit, owner_id, order_by=Habit.created_at)
        today_logs = list(session.scalars(select(HabitLog).where(HabitLog.owner_id == owner_id, HabitLog.log_date == today)).all())
        sessions = list_owned(session, LearningSession, owner_id)
        routine_items = list_owned(session, RoutineItem, owner_id, order_by=RoutineItem.start_time)
        events = list_owned(session, CalendarEvent, owner_id, order_by=CalendarEvent.starts_at)
        goals = list_owned(session, Goal, owner_id)
        log_dates = {(row.habit_id, row.log_date): row.is_complete for row in today_logs}
        due_lessons = [lesson for lesson in lessons if lesson.due_date == today]
        local_tasks_today = [task for task in tasks if task.due_at and utc_to_local(task.due_at, zone_name).date() == today and task.status not in {"Cancelled", "Deferred"}]
        active_goals = [goal for goal in goals if goal.status == "Active"]
        upcoming = [("Task", t.title, utc_to_local(t.due_at, zone_name)) for t in tasks if t.due_at and t.status not in {"Completed", "Cancelled", "Deferred"}]
        upcoming += [("Event", e.title, utc_to_local(e.starts_at, zone_name)) for e in events]
        upcoming += [("Learning", lesson.title, datetime.combine(lesson.due_date, time.min)) for lesson in lessons if lesson.due_date and lesson.status != "Completed"]
        upcoming = sorted((row for row in upcoming if row[2] and row[2].date() >= today), key=lambda item: item[2])[:8]
        routine_today = [item for item in routine_items if not item.weekdays or today.weekday() in item.weekdays]
        routine_logs = list(session.scalars(select(RoutineCompletion).where(RoutineCompletion.owner_id == owner_id, RoutineCompletion.completion_date == today, RoutineCompletion.is_complete.is_(True))).all())
        routine_done = {row.routine_item_id for row in routine_logs}
        weekly_prod = productivity_days(session, owner_id, today - timedelta(days=today.weekday()), today, zone_name)
        weekly_learning = learning_hours_by_day(session, owner_id, today - timedelta(days=6), today, zone_name)

    display = settings.get("display_name") or st.session_state.get("nexus_display_name", "there")
    st.markdown(f"### Good {('morning' if local_now.hour < 12 else 'afternoon' if local_now.hour < 18 else 'evening')}, {display}")
    focus = settings.get("focus_text", "") if settings.get("focus_date") == today.isoformat() else ""
    st.caption(f"Today's focus: {focus}" if focus else "Choose one meaningful priority to make today count.")
    st.markdown("One place. Every goal. Complete control.")

    metric_groups = [
        ("Completed today", metrics["tasks_completed_today"], "Tasks"),
        ("Pending tasks", metrics["tasks_pending"], "Across your task list"),
        ("Study time", f'{metrics["study_hours_today"]:.1f}h', "Logged today"),
        ("Active programs", metrics["active_programs"], "Learning plans"),
        ("Habits today", f'{metrics["habits_complete"]}/{metrics["habits_due"]}', "Completed / scheduled"),
        ("Active goals", metrics["active_goals"], "In progress"),
        ("Productivity streak", metrics["productivity_streak"], "Days with activity"),
        ("This week", f'{metrics["weekly_completion_pct"]}%' if metrics["weekly_completion_pct"] is not None else "—", "Tasks with a due date"),
    ]
    visible_widgets = set(settings.get("dashboard_widgets", ["Tasks", "Learning", "Habits", "Goals", "Streak", "Weekly charts", "Upcoming"]))
    widget_for_metric = ["Tasks", "Tasks", "Learning", "Learning", "Habits", "Goals", "Streak", "Tasks"]
    metric_groups = [item for item, widget in zip(metric_groups, widget_for_metric) if widget in visible_widgets]
    cols = st.columns(4)
    for index, (label, value, help_text) in enumerate(metric_groups):
        with cols[index % 4]:
            st.metric(label, value, help=help_text)

    st.divider()
    left, right = st.columns([1.25, 1])
    with left:
        section_title("Today's progress", "Counts update from saved tasks, lessons, habit logs, and routine check-ins.")
        task_completed = sum(1 for task in local_tasks_today if task.status == "Completed")
        st.progress(task_completed / len(local_tasks_today) if local_tasks_today else 0, text=f"Tasks · {task_completed} of {len(local_tasks_today)} planned")
        lesson_completed = sum(1 for lesson in due_lessons if lesson.status == "Completed")
        st.progress(lesson_completed / len(due_lessons) if due_lessons else 0, text=f"Lessons · {lesson_completed} of {len(due_lessons)} planned")
        due_habits = [h for h in habits if h.archived_on is None and (h.frequency == "Daily" or (h.frequency == "Selected weekdays" and today.weekday() in (h.weekdays or [])))]
        habits_done = sum(1 for habit in due_habits if log_dates.get((habit.id, today), False))
        st.progress(habits_done / len(due_habits) if due_habits else 0, text=f"Habits · {habits_done} of {len(due_habits)} scheduled")
        st.progress(len(routine_done & {item.id for item in routine_today}) / len(routine_today) if routine_today else 0, text=f"Routine · {len(routine_done & {item.id for item in routine_today})} of {len(routine_today)} blocks checked in")
        priorities = sorted((t for t in local_tasks_today if t.status not in {"Completed", "Cancelled"}), key=lambda t: (t.priority != "Critical", t.priority != "High", t.due_at or datetime.max))[:5]
        if priorities:
            section_title("Remaining priorities")
            for task in priorities:
                st.write(f"**{task.priority}** · {task.title}")
        else:
            st.caption("No remaining tasks are scheduled for today.")
    with right:
        if "Upcoming" in visible_widgets:
            section_title("Upcoming")
            if upcoming:
                for kind, title, when in upcoming:
                    st.markdown(f"**{when.strftime('%a %d %b · %I:%M %p')}** · {kind}  \n{title}")
            else:
                empty_state("Your schedule is clear", "Upcoming deadlines, tasks, lessons, and events will appear here.")
        if "Goals" in visible_widgets:
            section_title("Goal progress")
            for goal in active_goals[:5]:
                st.progress(max(0, min(100, goal.progress)) / 100, text=f"{goal.title} · {goal.progress}%")
            if not active_goals:
                st.caption("Create a goal to see progress here.")

    if "Weekly charts" in visible_widgets:
        section_title("This week")
        chart_left, chart_right = st.columns(2)
        with chart_left:
            show_plotly(px.bar(weekly_prod, x="date", y="completed_items", title="Completed tasks and lessons", template="plotly_dark", color_discrete_sequence=["#6366f1"]), alt="Task and lesson completions by day this week")
        with chart_right:
            show_plotly(px.bar(weekly_learning, x="date", y="hours", title="Logged learning hours", template="plotly_dark", color_discrete_sequence=["#38bdf8"]), alt="Logged study hours by day this week")
    section_title("Quick actions")
    enabled_modules = set(settings.get("enabled_modules", ["Task Manager", "Study Center", "Notes & Knowledge Base", "Habit Tracker", "Goals", "Activity & Wellness", "Finance Tracker"]))
    quick_links = [
        ("Add a task", "app_pages/task_manager.py", "Task Manager"),
        ("Log study time", "app_pages/study_center.py", "Study Center"),
        ("Write a note", "app_pages/notes.py", "Notes & Knowledge Base"),
        ("Complete a habit", "app_pages/habit_tracker.py", "Habit Tracker"),
        ("Add a goal", "app_pages/goals.py", "Goals"),
        ("Record activity", "app_pages/activity_wellness.py", "Activity & Wellness"),
        ("Record expense", "app_pages/finance.py", "Finance Tracker"),
    ]
    quick_links = [item for item in quick_links if item[2] in enabled_modules]
    quick_rows = [st.columns(4), st.columns(max(1, min(4, len(quick_links) - 4)))]
    for index, (label, page, _module) in enumerate(quick_links):
        row = 0 if index < 4 else 1
        column = index if index < 4 else index - 4
        col = quick_rows[row][column]
        with col:
            st.page_link(page, label=label, icon=":material/add_circle:")


def my_day(owner_id: str) -> None:
    settings = st.session_state.get("nexus_settings", {})
    zone_name = settings.get("timezone", "Asia/Kolkata")
    now = datetime.now(get_zone(zone_name))
    today = now.date()
    page_header("My Day", "A focused checklist for the date you select. Unfinished items stay in your records.")
    selected_day = st.date_input("Plan date", value=today, key="my-day-date")
    with session_scope(_db_url()) as session:
        tasks = list_owned(session, Task, owner_id, order_by=Task.due_at)
        habits = list_owned(session, Habit, owner_id, order_by=Habit.name)
        habit_logs = list(session.scalars(select(HabitLog).where(HabitLog.owner_id == owner_id, HabitLog.log_date == selected_day)).all())
        routine = list_owned(session, RoutineItem, owner_id, order_by=RoutineItem.start_time)
        routine_logs = list(session.scalars(select(RoutineCompletion).where(RoutineCompletion.owner_id == owner_id, RoutineCompletion.completion_date == selected_day)).all())
    tasks_for_day = [t for t in tasks if t.due_at and utc_to_local(t.due_at, zone_name).date() == selected_day]
    habit_by_id = {log.habit_id: log for log in habit_logs}
    due_habits = [h for h in habits if h.archived_on is None and (h.frequency == "Daily" or (h.frequency == "Selected weekdays" and selected_day.weekday() in (h.weekdays or [])))]
    routine_for_day = [item for item in routine if not item.weekdays or selected_day.weekday() in item.weekdays]
    routine_by_id = {log.routine_item_id: log for log in routine_logs}

    tab_tasks, tab_habits, tab_routine = st.tabs(["Tasks", "Habits", "Routine"])
    with tab_tasks:
        if not tasks_for_day:
            empty_state("No dated tasks for this day", "Tasks without due dates remain in Task Manager.")
        else:
            with st.form("my-day-task-checklist"):
                state = {}
                for task in tasks_for_day:
                    state[task.id] = st.checkbox(f"{task.title} · {task.priority}", value=task.status == "Completed", key=f"myday-task-{task.id}")
                if st.form_submit_button("Save task checklist", type="primary"):
                    with session_scope(_db_url()) as session:
                        for task in tasks_for_day:
                            current = session.scalar(select(Task).where(Task.id == task.id, Task.owner_id == owner_id))
                            complete = state[task.id]
                            if current and complete != (current.status == "Completed"):
                                previous = current.status
                                current.status = "Completed" if complete else "Pending"
                                current.completed_at = local_to_utc(datetime.now(get_zone(zone_name)).replace(tzinfo=None), zone_name) if complete else None
                            session.add(TaskHistory(owner_id=owner_id, task_id=current.id, previous_status=previous, new_status=current.status, note="My Day checklist"))
                    st.rerun()
    with tab_habits:
        if not due_habits:
            empty_state("No habits are scheduled", "Create a habit in Habit Tracker to start logging consistency.")
        else:
            with st.form("my-day-habit-checklist"):
                state = {habit.id: st.checkbox(habit.name, value=bool(habit_by_id.get(habit.id) and habit_by_id[habit.id].is_complete), key=f"myday-habit-{habit.id}") for habit in due_habits}
                if st.form_submit_button("Save habit check-ins", type="primary"):
                    with session_scope(_db_url()) as session:
                        for habit in due_habits:
                            log = session.scalar(select(HabitLog).where(HabitLog.owner_id == owner_id, HabitLog.habit_id == habit.id, HabitLog.log_date == selected_day))
                            if log:
                                log.is_complete = state[habit.id]
                            elif state[habit.id]:
                                session.add(HabitLog(owner_id=owner_id, habit_id=habit.id, log_date=selected_day, is_complete=True))
                    st.rerun()
    with tab_routine:
        if not routine_for_day:
            empty_state("No routine blocks yet", "Create a routine template and add time blocks in Routine Planner.")
        else:
            with st.form("my-day-routine-checklist"):
                state = {item.id: st.checkbox(f"{item.start_time.strftime('%H:%M')}–{item.end_time.strftime('%H:%M')} · {item.activity}", value=bool(routine_by_id.get(item.id) and routine_by_id[item.id].is_complete), key=f"myday-routine-{item.id}") for item in routine_for_day}
                if st.form_submit_button("Save routine check-ins", type="primary"):
                    with session_scope(_db_url()) as session:
                        for item in routine_for_day:
                            log = session.scalar(select(RoutineCompletion).where(RoutineCompletion.owner_id == owner_id, RoutineCompletion.routine_item_id == item.id, RoutineCompletion.completion_date == selected_day))
                            if log:
                                log.is_complete = state[item.id]
                            elif state[item.id]:
                                session.add(RoutineCompletion(owner_id=owner_id, routine_item_id=item.id, completion_date=selected_day, is_complete=True))
                    st.rerun()


def task_manager(owner_id: str) -> None:
    render_resource(TASKS, owner_id)
    zone_name = st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata")
    with session_scope(_db_url()) as session:
        history = list(session.scalars(select(TaskHistory).where(TaskHistory.owner_id == owner_id).order_by(TaskHistory.changed_at.desc()).limit(50)).all())
        tasks = list_owned(session, Task, owner_id, order_by=Task.due_at)
    overdue = [task for task in tasks if task.due_at and utc_to_local(task.due_at, zone_name).date() < datetime.now(get_zone(zone_name)).date() and task.status not in {"Completed", "Cancelled", "Deferred"}]
    section_title("Carry unfinished tasks forward")
    if overdue:
        labels = {task.id: f"{task.title} · due {utc_to_local(task.due_at, zone_name):%d %b} · {task.status}" for task in overdue}
        with st.form("task-carry-forward"):
            selected = st.multiselect("Choose overdue tasks", list(labels), format_func=lambda ident: labels[ident])
            new_due_day = st.date_input("New due date", value=datetime.now(get_zone(zone_name)).date() + timedelta(days=1))
            carry = st.form_submit_button("Carry selected tasks forward")
        if carry:
            if not selected:
                st.warning("Select at least one task.")
            else:
                with session_scope(_db_url()) as session:
                    for task_id in selected:
                        current = session.scalar(select(Task).where(Task.id == task_id, Task.owner_id == owner_id))
                        if current and current.due_at:
                            previous_day = utc_to_local(current.due_at, zone_name)
                            current.due_at = local_to_utc(datetime.combine(new_due_day, previous_day.time()), zone_name)
                            session.add(TaskHistory(owner_id=owner_id, task_id=current.id, previous_status=current.status, new_status=current.status, changed_at=local_to_utc(datetime.now(get_zone(zone_name)).replace(tzinfo=None), zone_name), note=f"Carried forward to {new_due_day.isoformat()}"))
                st.success("Selected task dates updated. Their statuses and history were retained.")
                st.rerun()
    else:
        st.caption("No unfinished overdue tasks are available to carry forward.")
    section_title("Recent completion history")
    if history:
        task_ids = {row.task_id for row in history}
        with session_scope(_db_url()) as session:
            task_names = {row.id: row.title for row in session.scalars(select(Task).where(Task.owner_id == owner_id, Task.id.in_(task_ids))).all()}
        show_dataframe(pd.DataFrame([{"Task": task_names.get(row.task_id, "Deleted task"), "Previous": row.previous_status, "New status": row.new_status, "Changed": row.changed_at, "Note": row.note} for row in history]), alt="Recent task status history")
    else:
        st.caption("Status changes will appear here.")


def goals_page(owner_id: str) -> None:
    page_header("Goals", "Keep long-term outcomes visible, measurable, and connected to milestones.")
    goals_tab, milestones_tab = st.tabs(["Goals", "Milestones"])
    with goals_tab:
        render_resource(GOALS, owner_id, show_header=False)
    with milestones_tab:
        render_resource(MILESTONES, owner_id, show_header=False)
    with session_scope(_db_url()) as session:
        goals = list_owned(session, Goal, owner_id, order_by=Goal.target_date)
    section_title("Progress overview")
    if goals:
        for goal in goals:
            st.progress(goal.progress / 100, text=f"{goal.title} · {goal.progress}% · {goal.status}")
    else:
        empty_state("No goals yet", "Create a goal and update progress as you make progress.")


def study_center(owner_id: str) -> None:
    page_header("Study Center", "Courses, ordered lessons, actual learning time, active recall, and spaced revision.")
    programs_tab, lessons_tab, sessions_tab, recall_tab = st.tabs(["Programs", "Lessons", "Learning sessions", "Active recall & revision"])
    with programs_tab:
        render_resource(PROGRAMS, owner_id, show_header=False)
    with lessons_tab:
        render_resource(LESSONS, owner_id, show_header=False)
    with sessions_tab:
        render_resource(LEARNING_SESSIONS, owner_id, show_header=False)
    with recall_tab:
        card_tab, review_tab = st.tabs(["Cards", "Revision sessions"])
        with card_tab:
            render_resource(REVISION_CARDS, owner_id, show_header=False)
        with review_tab:
            render_resource(REVISION_SESSIONS, owner_id, show_header=False)

    with session_scope(_db_url()) as session:
        programs = list_owned(session, LearningProgram, owner_id, order_by=LearningProgram.created_at)
        sessions = list_owned(session, LearningSession, owner_id)
        lessons = list_owned(session, Lesson, owner_id)
    section_title("Learning analytics")
    if not programs:
        empty_state("No learning programs", "Create a program to see lesson progress and study time.")
        return
    selected_id = st.selectbox("Program", [program.id for program in programs], format_func=lambda ident: next((p.title for p in programs if p.id == ident), ident), key="study-analytics-program")
    selected = next(p for p in programs if p.id == selected_id)
    program_lessons = [lesson for lesson in lessons if lesson.program_id == selected_id]
    done = sum(1 for lesson in program_lessons if lesson.status == "Completed")
    total = len(program_lessons)
    percent = round(done / total * 100, 1) if total else 0.0
    st.progress(percent / 100, text=f"{done} of {total} lessons · {percent:.1f}%")
    associated = [item for item in sessions if item.program_id == selected_id]
    actual_hours = sum(item.duration_minutes for item in associated) / 60
    planned_hours = selected.planned_hours
    average = sum(item.duration_minutes for item in associated) / 60 / max(1, len({item.started_at.date() for item in associated})) if associated else 0
    local_today = datetime.now(get_zone(st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata"))).date()
    week_start = local_today - timedelta(days=6)
    weekly_minutes = sum(item.duration_minutes for item in associated if week_start <= utc_to_local(item.started_at, st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata")).date() <= local_today)
    completed_dates = {utc_to_local(lesson.completed_at, st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata")).date() for lesson in program_lessons if lesson.completed_at}
    daily_pace = done / len(completed_dates) if completed_dates else 0
    remaining = max(0, total - done)
    estimated = (local_today + timedelta(days=int((remaining + daily_pace - 1) // daily_pace))) if daily_pace else None
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Lessons complete", done)
    c2.metric("Actual study hours", f"{actual_hours:.1f}")
    c3.metric("Daily average", f"{average:.1f}h" if associated else "—")
    c4.metric("Planned hours", f"{planned_hours:.1f}h")
    c1, c2, c3 = st.columns(3)
    c1.metric("Learning time this week", f"{weekly_minutes / 60:.1f}h" if weekly_minutes else "—")
    c2.metric("Lessons remaining", remaining)
    c3.metric("Estimated completion", estimated.strftime("%d %b %Y") if estimated else "—", help="Based on your mean completed lessons per active study day." if estimated else "Log completed lessons on at least one day to estimate.")
    lesson_rows = [lesson for lesson in lessons if lesson.program_id == selected_id and lesson.due_date]
    if lesson_rows:
        frame = pd.DataFrame([{"date": lesson.due_date, "status": lesson.status, "lessons": 1} for lesson in lesson_rows])
        chart = frame.groupby(["date", "status"], as_index=False)["lessons"].sum()
        show_plotly(px.bar(chart, x="date", y="lessons", color="status", barmode="stack", title="Planned lesson pacing", template="plotly_dark"), alt="Lesson counts by planned date and status")
    else:
        st.caption("Lesson pacing chart appears when lessons have planned dates.")
    completed_by_day = Counter(
        utc_to_local(lesson.completed_at, st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata")).date()
        for lesson in program_lessons if lesson.completed_at
    )
    if completed_by_day:
        lesson_history = pd.DataFrame([{"Date": day, "Lessons completed": count} for day, count in sorted(completed_by_day.items())])
        show_plotly(px.line(lesson_history, x="Date", y="Lessons completed", markers=True, title="Lessons completed per day", template="plotly_dark"), alt="Completed lessons per day")
    with session_scope(_db_url()) as session:
        cards = list_owned(session, RevisionCard, owner_id, order_by=RevisionCard.next_review_at)
    if cards:
        section_title("Review a card", "Self-rating drives the next interval; a watched lesson alone never marks understanding.")
        card_id = st.selectbox("Card to review", [item.id for item in cards], format_func=lambda ident: next((item.question[:100] for item in cards if item.id == ident), ident), key="spaced-review-card")
        rating = st.select_slider("How well could you recall it?", options=[1, 2, 3, 4, 5], value=3, key="spaced-review-rating")
        if st.button("Save review and schedule next recall", type="primary"):
            current_local = datetime.now(get_zone(st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata"))).replace(tzinfo=None)
            current_utc = local_to_utc(current_local, st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata"))
            with session_scope(_db_url()) as session:
                card = session.scalar(select(RevisionCard).where(RevisionCard.id == card_id, RevisionCard.owner_id == owner_id))
                if card:
                    previous_interval = max(1, card.interval_days)
                    interval = 1 if rating <= 2 else previous_interval if rating == 3 else max(2, previous_interval * 2)
                    card.interval_days = interval
                    card.last_reviewed_at = current_utc
                    card.next_review_at = current_utc + timedelta(days=interval)
                    card.understanding_level = rating
                    card.difficult = rating <= 2
                    session.add(RevisionSession(owner_id=owner_id, card_id=card.id, reviewed_at=current_utc, understood=rating >= 4, notes=f"Self-rating {rating}/5 · next review in {interval} day(s)"))
            st.success(f"Review saved. Next recall is scheduled in {interval} day(s).")
            st.rerun()


def habit_tracker(owner_id: str) -> None:
    page_header("Habit Tracker", "Build consistency with scheduled check-ins and a history that survives habit edits.")
    definitions_tab, checkin_tab, history_tab = st.tabs(["Habits", "Daily check-in", "History"])
    with definitions_tab:
        render_resource(HABITS, owner_id, show_header=False)

    selected_day = st.date_input("Check-in date", value=date.today(), key="habit-checkin-date")
    with session_scope(_db_url()) as session:
        habits = list_owned(session, Habit, owner_id, order_by=Habit.name)
        logs = list(session.scalars(select(HabitLog).where(HabitLog.owner_id == owner_id, HabitLog.log_date == selected_day)).all())
        all_logs = list_owned(session, HabitLog, owner_id, order_by=HabitLog.log_date)
    active = [habit for habit in habits if habit.archived_on is None]
    due = [h for h in active if h.frequency == "Daily" or (h.frequency == "Selected weekdays" and selected_day.weekday() in (h.weekdays or [])) or h.frequency in {"Weekly", "Custom"}]
    log_by_habit = {row.habit_id: row for row in logs}
    with checkin_tab:
        if not due:
            empty_state("No habits are scheduled for this day", "Add a daily or selected weekday habit above.")
        else:
            with st.form("habit-tracker-daily-log"):
                values = {habit.id: st.checkbox(habit.name, value=bool(log_by_habit.get(habit.id) and log_by_habit[habit.id].is_complete), key=f"habit-log-{selected_day}-{habit.id}") for habit in due}
                note = st.text_input("Optional check-in note")
                if st.form_submit_button("Save check-ins", type="primary"):
                    with session_scope(_db_url()) as session:
                        for habit in due:
                            row = session.scalar(select(HabitLog).where(HabitLog.owner_id == owner_id, HabitLog.habit_id == habit.id, HabitLog.log_date == selected_day))
                            if row:
                                row.is_complete = values[habit.id]
                                row.note = note
                            else:
                                session.add(HabitLog(owner_id=owner_id, habit_id=habit.id, log_date=selected_day, is_complete=values[habit.id], note=note))
                    st.success("Habit history saved.")
                    st.rerun()
    with history_tab:
        heatmap_data = pd.DataFrame([{"Date": row.log_date, "Habit ID": row.habit_id, "Complete": row.is_complete, "Note": row.note} for row in all_logs])
        if not heatmap_data.empty:
            heatmap_data = heatmap_data.merge(pd.DataFrame([{"Habit ID": h.id, "Habit": h.name} for h in habits]), on="Habit ID", how="left")
            show_dataframe(heatmap_data.sort_values("Date", ascending=False), alt="Habit check-in history")
            st.download_button("Export habit history", csv_bytes(heatmap_data), file_name="nexus-habit-history.csv", mime="text/csv")
        else:
            empty_state("No habit history yet", "Save a check-in to start the heatmap.")

    section_title("Consistency heatmap", "Each cell is one day; color depth reflects the number of completed habits.")
    counts = Counter(row.log_date for row in all_logs if row.is_complete)
    heat_start = selected_day - timedelta(days=119)
    dates = [heat_start + timedelta(days=i) for i in range(120)]
    weeks = sorted({day - timedelta(days=day.weekday()) for day in dates})
    matrix = [[None for _ in weeks] for _ in range(7)]
    for day in dates:
        matrix[day.weekday()][weeks.index(day - timedelta(days=day.weekday()))] = counts.get(day, 0)
    figure = go.Figure(data=go.Heatmap(
        z=matrix, x=[week.strftime("%d %b") for week in weeks], y=["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
        colorscale=[[0, "#182233"], [0.35, "#334b79"], [0.7, "#6366f1"], [1, "#38bdf8"]],
        hovertemplate="Week of %{x}<br>%{y}: %{z} completed<extra></extra>", showscale=False,
    ))
    figure.update_layout(template="plotly_dark", height=240, margin=dict(l=5, r=5, t=5, b=5), xaxis_title=None, yaxis_title=None)
    show_plotly(figure, alt="Calendar heatmap of completed habits over the selected 120 days")
    streak_cols = st.columns(min(max(len(active), 1), 4))
    for index, habit in enumerate(active):
        streak = habit_streak_from_logs(all_logs, habit.id, selected_day)
        with streak_cols[index % len(streak_cols)]:
            st.metric(f"{habit.name} streak", f"{streak} days")


def habit_streak_from_logs(logs: list[HabitLog], habit_id: str, selected_day: date) -> int:
    completed = {row.log_date for row in logs if row.habit_id == habit_id and row.is_complete and row.log_date <= selected_day}
    streak = 0
    current = selected_day
    while current in completed:
        streak += 1
        current -= timedelta(days=1)
    return streak


def routine_planner(owner_id: str) -> None:
    page_header("Routine Planner", "Design reusable schedules, inspect overlaps, and check off today's time blocks.")
    templates_tab, blocks_tab, timeline_tab = st.tabs(["Templates", "Time blocks", "Daily timeline"])
    with templates_tab:
        render_resource(ROUTINE_TEMPLATES, owner_id, show_header=False)
    with blocks_tab:
        render_resource(ROUTINE_ITEMS, owner_id, show_header=False)

    selected_day = st.date_input("Timeline date", value=date.today(), key="routine-selected-day")
    with session_scope(_db_url()) as session:
        items = list_owned(session, RoutineItem, owner_id, order_by=RoutineItem.start_time)
        templates = list_owned(session, RoutineTemplate, owner_id)
        completions = list(session.scalars(select(RoutineCompletion).where(RoutineCompletion.owner_id == owner_id, RoutineCompletion.completion_date == selected_day)).all())
    names = {template.id: template.title for template in templates}
    applicable = [item for item in items if not item.weekdays or selected_day.weekday() in item.weekdays]
    with timeline_tab:
        if not applicable:
            empty_state("No time blocks for this day", "Create a template and add editable time blocks.")
        else:
            starts = [item.start_time.hour + item.start_time.minute / 60 for item in applicable]
            durations = [(item.end_time.hour * 60 + item.end_time.minute - item.start_time.hour * 60 - item.start_time.minute) / 60 for item in applicable]
            figure = go.Figure()
            figure.add_trace(go.Bar(
                x=durations, base=starts, y=[f"{names.get(item.template_id, 'Routine')} · {item.activity}" for item in applicable],
                orientation="h", marker_color="#6366f1", text=[item.category for item in applicable],
                hovertemplate="%{y}<br>%{base:.2f}h · %{x:.2f}h<extra></extra>",
            ))
            figure.update_layout(template="plotly_dark", height=max(260, 42 * len(applicable)), xaxis=dict(range=[0, 24], tickvals=list(range(0, 25, 2)), title="Local time"), yaxis=dict(autorange="reversed"), margin=dict(l=5, r=5, t=5, b=5), showlegend=False)
            show_plotly(figure, alt="Daily routine time blocks on a 24-hour timeline")
            completion_map = {row.routine_item_id: row for row in completions}
            with st.form("routine-completion-checklist"):
                states = {item.id: st.checkbox(f"{item.start_time.strftime('%H:%M')}–{item.end_time.strftime('%H:%M')} · {item.activity}", value=bool(completion_map.get(item.id) and completion_map[item.id].is_complete), key=f"routine-complete-{selected_day}-{item.id}") for item in applicable}
                if st.form_submit_button("Save routine check-ins"):
                    with session_scope(_db_url()) as session:
                        for item in applicable:
                            row = session.scalar(select(RoutineCompletion).where(RoutineCompletion.owner_id == owner_id, RoutineCompletion.routine_item_id == item.id, RoutineCompletion.completion_date == selected_day))
                            if row:
                                row.is_complete = states[item.id]
                            elif states[item.id]:
                                session.add(RoutineCompletion(owner_id=owner_id, routine_item_id=item.id, completion_date=selected_day))
                    st.rerun()

    section_title("Overlap check")
    overlaps = []
    for index, first in enumerate(items):
        for second in items[index + 1:]:
            days_a = set(first.weekdays or range(7))
            days_b = set(second.weekdays or range(7))
            if days_a.intersection(days_b) and first.start_time < second.end_time and second.start_time < first.end_time:
                overlaps.append((first, second))
    if overlaps:
        for first, second in overlaps:
            st.warning(f"{first.activity} ({first.start_time:%H:%M}–{first.end_time:%H:%M}) overlaps {second.activity} ({second.start_time:%H:%M}–{second.end_time:%H:%M}).")
    else:
        st.success("No overlapping routine blocks were found.")


def activity_wellness(owner_id: str) -> None:
    page_header("Activity & Wellness", "Keep personal records of movement, sleep, mood, and energy.")
    activities_tab, wellness_tab = st.tabs(["Activity sessions", "Sleep & wellness"])
    with activities_tab:
        render_resource(ACTIVITIES, owner_id, show_header=False)
    with wellness_tab:
        render_resource(WELLNESS, owner_id, show_header=False)
    with session_scope(_db_url()) as session:
        activities = list_owned(session, ActivitySession, owner_id, order_by=ActivitySession.activity_date)
        wellness = list_owned(session, WellnessLog, owner_id, order_by=WellnessLog.log_date)
    section_title("Recent personal records")
    left, right = st.columns(2)
    with left:
        if activities:
            frame = pd.DataFrame([{"Activity": row.activity_type, "Minutes": row.duration_minutes, "Date": row.activity_date.date()} for row in activities[-30:]])
            show_plotly(px.bar(frame, x="Date", y="Minutes", color="Activity", title="Recorded movement", template="plotly_dark"), alt="Recorded activity minutes by date and type")
        else:
            st.caption("Activity history will appear after you log a session.")
    with right:
        observed = [row for row in wellness if row.sleep_hours is not None]
        if observed:
            frame = pd.DataFrame([{"Date": row.log_date, "Sleep hours": row.sleep_hours} for row in observed[-30:]])
            show_plotly(px.line(frame, x="Date", y="Sleep hours", markers=True, title="Recorded sleep duration", template="plotly_dark"), alt="Recorded sleep duration by date")
        else:
            st.caption("Sleep trend appears only for dates with a recorded value.")


def calendar_page(owner_id: str) -> None:
    page_header("Calendar", "Review personal events alongside tasks and planned lessons.")
    render_resource(EVENTS, owner_id)
    zone_name = st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata")
    view = st.selectbox("Calendar view", ["Day", "Week", "Month", "Upcoming"], key="calendar-mode")
    anchor = st.date_input("Date", value=date.today(), key="calendar-anchor")
    if view == "Day":
        start, end = anchor, anchor
    elif view == "Week":
        start, end = anchor - timedelta(days=anchor.weekday()), anchor + timedelta(days=6 - anchor.weekday())
    elif view == "Month":
        start = anchor.replace(day=1)
        end = (anchor.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
    else:
        start, end = anchor, anchor + timedelta(days=30)
    with session_scope(_db_url()) as session:
        events = list_owned(session, CalendarEvent, owner_id, order_by=CalendarEvent.starts_at)
        tasks = list_owned(session, Task, owner_id, order_by=Task.due_at)
        lessons = list_owned(session, Lesson, owner_id, order_by=Lesson.due_date)
        cards = list_owned(session, RevisionCard, owner_id, order_by=RevisionCard.next_review_at)
        habits = list_owned(session, Habit, owner_id)
        routine_items = list_owned(session, RoutineItem, owner_id)
    rows = []
    for item in events:
        local = utc_to_local(item.starts_at, zone_name)
        if local.date() <= end and utc_to_local(item.ends_at, zone_name).date() >= start:
            rows.append({"Date": local.strftime("%Y-%m-%d %H:%M"), "Type": item.category, "Title": item.title, "Status": "Scheduled"})
    for task in tasks:
        if task.due_at and start <= utc_to_local(task.due_at, zone_name).date() <= end and task.status not in {"Completed", "Cancelled"}:
            rows.append({"Date": utc_to_local(task.due_at, zone_name).strftime("%Y-%m-%d %H:%M"), "Type": "Task", "Title": task.title, "Status": task.status})
    for lesson in lessons:
        if lesson.due_date and start <= lesson.due_date <= end and lesson.status != "Completed":
            rows.append({"Date": lesson.due_date.strftime("%Y-%m-%d"), "Type": "Learning", "Title": lesson.title, "Status": lesson.status})
    for card in cards:
        if card.next_review_at and start <= utc_to_local(card.next_review_at, zone_name).date() <= end:
            rows.append({"Date": utc_to_local(card.next_review_at, zone_name).strftime("%Y-%m-%d %H:%M"), "Type": "Revision", "Title": card.question[:120], "Status": "Due"})
    for day_offset in range((end - start).days + 1):
        day = start + timedelta(days=day_offset)
        for habit in habits:
            if habit.archived_on is None and (habit.frequency == "Daily" or (habit.frequency == "Selected weekdays" and day.weekday() in (habit.weekdays or []))):
                rows.append({"Date": day.strftime("%Y-%m-%d"), "Type": "Habit", "Title": habit.name, "Status": "Scheduled"})
        for item in routine_items:
            if not item.weekdays or day.weekday() in item.weekdays:
                rows.append({"Date": f"{day:%Y-%m-%d} {item.start_time:%H:%M}", "Type": "Routine", "Title": item.activity, "Status": "Scheduled"})
    section_title(f"{view} · {start:%d %b} – {end:%d %b %Y}")
    if rows:
        frame = pd.DataFrame(rows).sort_values("Date")
        show_dataframe(frame, alt="Combined calendar events, tasks, lessons, habits, routines, and revisions")
    else:
        empty_state("Nothing scheduled in this period", "Events, task due dates, lessons, and revision dates are combined here.")


def notes_page(owner_id: str) -> None:
    page_header("Notes & Knowledge Base", "Capture searchable Markdown notes and connect them to study or work.")
    render_resource(NOTES, owner_id)
    include_archived = st.toggle("Include archived notes", value=False, key="notes-include-archived")
    with session_scope(_db_url()) as session:
        notes = list_owned(session, Note, owner_id, order_by=Note.updated_at.desc())
    visible = [note for note in notes if include_archived or not note.is_archived]
    if not visible:
        empty_state("No notes available", "Create a note above or include archived notes.")
        return
    selected_id = st.selectbox("Preview note", [item.id for item in visible], format_func=lambda ident: next((f"{'★ ' if n.is_pinned else ''}{n.title}" for n in visible if n.id == ident), ident), key="note-preview-choice")
    note = next(item for item in visible if item.id == selected_id)
    st.markdown(f"### {note.title}")
    st.caption(f"{note.category} · Updated {note.updated_at:%d %b %Y %H:%M} · {', '.join(note.tags or [])}")
    st.markdown(note.content or "_This note has no content yet._")


def finance_page(owner_id: str) -> None:
    page_header("Finance Tracker", "A private manual ledger with budgets and monthly summaries.")
    transactions_tab, budgets_tab = st.tabs(["Transactions", "Budgets"])
    with transactions_tab:
        render_resource(TRANSACTIONS, owner_id, show_header=False)
    with budgets_tab:
        render_resource(BUDGETS, owner_id, show_header=False)
    with session_scope(_db_url()) as session:
        transactions = list_owned(session, FinanceTransaction, owner_id, order_by=FinanceTransaction.transaction_date)
        budgets = list_owned(session, Budget, owner_id, order_by=Budget.month)
    month = st.date_input("Summary month", value=date.today().replace(day=1), key="finance-month").strftime("%Y-%m")
    current = [row for row in transactions if row.transaction_date.strftime("%Y-%m") == month]
    expenses = sum(row.amount for row in current if row.kind == "Expense")
    income = sum(row.amount for row in current if row.kind == "Income")
    c1, c2, c3 = st.columns(3)
    c1.metric("Income recorded", f"{income:,.2f}")
    c2.metric("Expenses recorded", f"{expenses:,.2f}")
    c3.metric("Net recorded", f"{income - expenses:,.2f}" if current else "—")
    if current:
        expense_frame = pd.DataFrame([{"Category": row.category, "Amount": row.amount} for row in current if row.kind == "Expense"])
        if not expense_frame.empty:
            category_totals = expense_frame.groupby("Category", as_index=False)["Amount"].sum()
            show_plotly(px.pie(category_totals, names="Category", values="Amount", hole=0.6, title="Recorded expenses by category", template="plotly_dark"), alt="Recorded expense totals by category")
        month_budgets = [budget for budget in budgets if budget.month == month]
        if month_budgets:
            actual = Counter()
            for row in current:
                if row.kind == "Expense":
                    actual[row.category] += row.amount
            budget_frame = pd.DataFrame([{"Category": item.category, "Budget": item.amount, "Spent": actual[item.category]} for item in month_budgets])
            show_plotly(px.bar(budget_frame, x="Category", y=["Budget", "Spent"], barmode="group", title="Budget versus recorded spending by category", template="plotly_dark"), alt="Monthly category budgets compared with recorded expense totals")
    else:
        st.caption("No transactions recorded in this month; no spending estimate is inferred.")


def analytics_page(owner_id: str) -> None:
    page_header("Analytics & Reports", "Explore trends calculated from your records; an empty period is shown as no data.")
    zone_name = st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata")
    today = datetime.now(get_zone(zone_name)).date()
    period = st.segmented_control("Review period", ["Custom", "This week", "This month", "Previous week", "Previous month"], default="Custom", key="analytics-period")
    if period == "Custom":
        start_col, end_col = st.columns(2)
        start = start_col.date_input("From", value=today - timedelta(days=29), key="analytics-start")
        end = end_col.date_input("Through", value=today, key="analytics-end")
    elif period in {"This week", "Previous week"}:
        this_week_start = today - timedelta(days=today.weekday())
        start, end = (this_week_start, today) if period == "This week" else (this_week_start - timedelta(days=7), this_week_start - timedelta(days=1))
    elif period in {"This month", "Previous month"}:
        this_month_start = today.replace(day=1)
        if period == "This month":
            start, end = this_month_start, today
        else:
            end = this_month_start - timedelta(days=1)
            start = end.replace(day=1)
    else:
        start, end = today - timedelta(days=29), today
    if start > end:
        st.error("The start date must be on or before the end date.")
        return
    with session_scope(_db_url()) as session:
        tasks = list_owned(session, Task, owner_id)
        programs = list_owned(session, LearningProgram, owner_id)
        lessons = list_owned(session, Lesson, owner_id)
        habits = list_owned(session, Habit, owner_id)
        habit_logs = list_owned(session, HabitLog, owner_id)
        learning = list_owned(session, LearningSession, owner_id)
        goals = list_owned(session, Goal, owner_id)
        task_history = list_owned(session, TaskHistory, owner_id)
        goal_history = list_owned(session, GoalHistory, owner_id)
        lesson_history = list_owned(session, LessonHistory, owner_id)
        milestones = list_owned(session, GoalMilestone, owner_id)
        days = productivity_days(session, owner_id, start, end, zone_name)
        study_days = learning_hours_by_day(session, owner_id, start, end, zone_name)

    scoped_tasks = [task for task in tasks if task.due_at and start <= utc_to_local(task.due_at, zone_name).date() <= end]
    completed_in_period = {row.task_id for row in task_history if row.new_status == "Completed" and start <= utc_to_local(row.changed_at, zone_name).date() <= end}
    completed_lessons_in_period = {row.lesson_id for row in lesson_history if row.new_status == "Completed" and start <= utc_to_local(row.changed_at, zone_name).date() <= end}
    task_rate = round(sum(1 for item in scoped_tasks if item.status == "Completed") / len(scoped_tasks) * 100, 1) if scoped_tasks else None
    period_learning = [row for row in learning if start <= utc_to_local(row.started_at, zone_name).date() <= end]
    total_hours = sum(row.duration_minutes for row in period_learning) / 60
    period_days = (end - start).days + 1
    previous_start, previous_end = start - timedelta(days=period_days), start - timedelta(days=1)
    previous_tasks = {row.task_id for row in task_history if row.new_status == "Completed" and previous_start <= utc_to_local(row.changed_at, zone_name).date() <= previous_end}
    previous_learning_hours = sum(row.duration_minutes for row in learning if previous_start <= utc_to_local(row.started_at, zone_name).date() <= previous_end) / 60
    st.caption(f"Report window: {start:%d %b %Y} – {end:%d %b %Y}")
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Completed tasks", len(completed_in_period), delta=len(completed_in_period) - len(previous_tasks), help="Compared with the previous period of equal length")
    c2.metric("Task completion rate", f"{task_rate}%" if task_rate is not None else "—", help="No dated tasks in this window" if task_rate is None else None)
    c3.metric("Learning hours", f"{total_hours:.1f}h" if period_learning else "—", delta=round(total_hours - previous_learning_hours, 1) if period_learning else None, help="Compared with the previous period of equal length")
    c4.metric("Lesson completions", len(completed_lessons_in_period))

    chart_a, chart_b = st.columns(2)
    with chart_a:
        show_plotly(px.bar(days, x="date", y="completed_items", title="Completed tasks and lessons", template="plotly_dark", color_discrete_sequence=["#6366f1"]), alt="Completed tasks and lessons by day in the selected report window")
    with chart_b:
        show_plotly(px.area(study_days, x="date", y="hours", title="Logged learning time", template="plotly_dark", color_discrete_sequence=["#38bdf8"]), alt="Logged learning hours by day in the selected report window")

    section_title("Learning progress by program")
    if programs:
        rows = []
        for program in programs:
            program_lessons = [lesson for lesson in lessons if lesson.program_id == program.id]
            completed = sum(1 for lesson in program_lessons if lesson.status == "Completed")
            hours = sum(row.duration_minutes for row in learning if row.program_id == program.id) / 60
            rows.append({"Program": program.title, "Completed": completed, "Total lessons": len(program_lessons), "Progress %": round(completed / len(program_lessons) * 100, 1) if program_lessons else None, "Logged hours": round(hours, 1)})
        program_frame = pd.DataFrame(rows)
        show_dataframe(program_frame, alt="Progress and recorded hours by learning program")
        if program_frame["Total lessons"].sum():
            show_plotly(px.bar(program_frame, x="Program", y="Progress %", title="Program completion", template="plotly_dark", range_y=[0, 100], color_discrete_sequence=["#6366f1"]), alt="Completion percentage for each learning program")
    else:
        st.caption("No learning programs are stored in this period.")

    section_title("Habit consistency")
    habits_by_id = {item.id: item.name for item in habits}
    window_logs = [row for row in habit_logs if start <= row.log_date <= end]
    if window_logs:
        habit_frame = pd.DataFrame([{"Habit": habits_by_id.get(row.habit_id, "Archived habit"), "Date": row.log_date, "Completed": row.is_complete} for row in window_logs])
        daily_habits = habit_frame.groupby("Habit", as_index=False)["Completed"].mean()
        daily_habits["Completion %"] = (daily_habits.pop("Completed") * 100).round(1)
        show_plotly(px.bar(daily_habits, x="Habit", y="Completion %", title="Recorded check-ins that were completed", template="plotly_dark", range_y=[0, 100]), alt="Share of recorded habit check-ins completed for each habit")
    else:
        st.caption("No habit logs were recorded during this period.")

    section_title("Goals and task history")
    goal_frame = pd.DataFrame([{"Goal": goal.title, "Status": goal.status, "Progress %": goal.progress, "Target": goal.target_date} for goal in goals])
    if not goal_frame.empty:
        show_dataframe(goal_frame, alt="Goal status, progress, and target dates")
    st.caption(f"{len(task_history)} task status changes, {len(lesson_history)} lesson status changes, and {len(goal_history)} goal progress updates are retained.")
    if goal_history:
        goal_names = {goal.id: goal.title for goal in goals}
        history_frame = pd.DataFrame([{"Goal": goal_names.get(row.goal_id, "Deleted goal"), "Progress": f"{row.previous_progress}% → {row.new_progress}%", "Status": f"{row.previous_status or 'New'} → {row.new_status}", "Changed": row.changed_at, "Note": row.note} for row in sorted(goal_history, key=lambda item: item.changed_at, reverse=True)[:50]])
        show_dataframe(history_frame, alt="Recent goal progress and status history")

    section_title("Weekly review")
    overdue_now = [task for task in tasks if task.due_at and utc_to_local(task.due_at, zone_name).date() < today and task.status not in {"Completed", "Cancelled", "Deferred"}]
    overdue_in_window = [task for task in overdue_now if start <= utc_to_local(task.due_at, zone_name).date() <= end]
    if overdue_in_window:
        overdue_frame = pd.DataFrame([{"Due date": utc_to_local(task.due_at, zone_name).date(), "Task": task.title} for task in overdue_in_window]).groupby("Due date", as_index=False).size().rename(columns={"size": "Currently overdue tasks"})
        show_plotly(px.line(overdue_frame, x="Due date", y="Currently overdue tasks", markers=True, title="Current overdue tasks by due date", template="plotly_dark"), alt="Currently overdue task counts grouped by their due date")
    else:
        st.caption("No currently overdue tasks are due within this report window.")
    delayed = [row for row in milestones if row.due_date and row.due_date < today and not row.is_complete]
    st.caption(f"{len(delayed)} goal milestones are currently past due.")
    st.markdown(f"During this window, you recorded **{len(completed_in_period)} completed tasks**, **{total_hours:.1f} learning hours**, and **{len(completed_lessons_in_period)} lesson completions**. These totals describe saved records; missing logs are not counted as failures.")

    # Complete data export remains scoped to this signed-in account.
    with session_scope(_db_url()) as session:
        export_models = {
            "tasks": Task, "task_history": TaskHistory, "programs": LearningProgram, "lessons": Lesson, "lesson_history": LessonHistory, "learning_sessions": LearningSession,
            "goals": Goal, "goal_history": GoalHistory, "goal_milestones": GoalMilestone, "habits": Habit, "habit_logs": HabitLog,
            "routines": RoutineTemplate, "routine_items": RoutineItem, "routine_completions": RoutineCompletion,
            "revision_cards": RevisionCard, "revision_sessions": RevisionSession, "activities": ActivitySession,
            "transactions": FinanceTransaction, "budgets": Budget, "wellness": WellnessLog,
            "events": CalendarEvent, "notes": Note, "settings": ApplicationSettings,
        }
        export_frames = {}
        for name, model in export_models.items():
            records = list_owned(session, model, owner_id)
            export_frames[name] = pd.DataFrame([{column.name: getattr(record, column.name) for column in model.__table__.columns} for record in records])
    csv_bundle = pd.concat([frame.assign(_section=name) for name, frame in export_frames.items() if not frame.empty], ignore_index=True) if any(not frame.empty for frame in export_frames.values()) else pd.DataFrame()
    export_cols = st.columns(3)
    with export_cols[0]:
        st.download_button("Download combined CSV", csv_bytes(csv_bundle), file_name="nexus-export.csv", mime="text/csv", disabled=csv_bundle.empty)
    with export_cols[1]:
        xlsx = _excel_export(export_frames)
        st.download_button("Download Excel workbook", xlsx, file_name="nexus-export.xlsx", mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    with export_cols[2]:
        report = _pdf_report(start, end, len(completed_in_period), total_hours, len(programs), len(goals))
        st.download_button("Download review PDF", report, file_name="nexus-review.pdf", mime="application/pdf")


def _excel_export(frames: dict[str, pd.DataFrame]) -> bytes:
    from io import BytesIO

    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        for name, frame in frames.items():
            (frame if not frame.empty else pd.DataFrame({"No records": []})).to_excel(writer, sheet_name=name[:31], index=False)
    return output.getvalue()


def _pdf_report(start: date, end: date, task_count: int, learning_hours: float, program_count: int, goal_count: int) -> bytes:
    from io import BytesIO
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import letter
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

    output = BytesIO()
    document = SimpleDocTemplate(output, pagesize=letter, title="NEXUS personal review")
    styles = getSampleStyleSheet()
    content = [Paragraph("NEXUS · Personal review", styles["Title"]), Spacer(1, 12), Paragraph(f"{start:%d %B %Y} – {end:%d %B %Y}", styles["Normal"]), Spacer(1, 18)]
    table = Table([["Measure", "Saved records"], ["Completed tasks", str(task_count)], ["Learning hours", f"{learning_hours:.1f}"], ["Learning programs", str(program_count)], ["Goals", str(goal_count)]], colWidths=[250, 180])
    table.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1C2638")), ("TEXTCOLOR", (0, 0), (-1, 0), colors.white), ("GRID", (0, 0), (-1, -1), 0.5, colors.grey), ("PADDING", (0, 0), (-1, -1), 8)]))
    content.extend([table, Spacer(1, 18), Paragraph("This report summarizes records saved in NEXUS. Missing entries are not interpreted as zero performance.", styles["BodyText"])])
    document.build(content)
    return output.getvalue()


def ai_assistant(owner_id: str) -> None:
    page_header("AI Assistant", "Optional read-only suggestions based on the records you choose to send.")
    if not ai_configured():
        st.info("AI is disabled. Add `OPENAI_API_KEY` to Streamlit secrets to enable suggestions. The rest of NEXUS works without it.")
        st.code('[ai]\napi_key = "your-server-side-api-key"\nmodel = "gpt-4.1-mini"')
        return
    with session_scope(_db_url()) as session:
        open_tasks = [task for task in list_owned(session, Task, owner_id) if task.status in {"Pending", "In progress"}]
        programs = list_owned(session, LearningProgram, owner_id)
        learning = list_owned(session, LearningSession, owner_id)
        notes = list_owned(session, Note, owner_id)
        habits = list_owned(session, Habit, owner_id)
    context_lines = [
        "Open tasks: " + ("; ".join(f"{task.title} [{task.priority}]" for task in open_tasks[:40]) or "none recorded"),
        "Learning programs: " + ("; ".join(f"{item.title} ({item.status})" for item in programs[:20]) or "none recorded"),
        f"Learning sessions stored: {len(learning)}; total minutes: {sum(row.duration_minutes for row in learning)}.",
        "Habits: " + ("; ".join(item.name for item in habits if item.archived_on is None) or "none recorded"),
        "Available note titles: " + ("; ".join(item.title for item in notes[:30]) or "none recorded"),
    ]
    st.caption("Your prompt and this compact summary are sent to the configured AI provider. Suggestions do not update stored records.")
    selected_notes = st.multiselect("Include note content", [item.id for item in notes if not item.is_archived], format_func=lambda ident: next((item.title for item in notes if item.id == ident), ident), key="assistant-selected-notes", help="Only selected note content is sent with your prompt.")
    for note in notes:
        if note.id in selected_notes:
            context_lines.append(f"Selected note — {note.title}:\n{note.content[:5000]}")
    context = "\n".join(context_lines)
    prompt = st.chat_input("Ask for a schedule, progress review, or study questions")
    if "nexus_ai_messages" not in st.session_state:
        st.session_state["nexus_ai_messages"] = []
    for message in st.session_state["nexus_ai_messages"]:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
    if prompt:
        st.session_state["nexus_ai_messages"].append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("Reviewing the selected context…"):
                try:
                    answer = ask_assistant(prompt, context)
                except Exception as exc:
                    answer = str(exc)
                    st.error(answer)
                else:
                    st.markdown(answer)
                st.session_state["nexus_ai_messages"].append({"role": "assistant", "content": answer})


def settings_page(owner_id: str) -> None:
    page_header("Settings", "Personalize NEXUS and review the active security and persistence configuration.")
    with session_scope(_db_url()) as session:
        settings_row = session.get(ApplicationSettings, owner_id)
        values = dict(settings_row.settings_json or {}) if settings_row else {}
    current_name = values.get("display_name", st.session_state.get("nexus_display_name", "NEXUS User"))
    available_pages = {
        "My Day": "my_day", "Study Center": "study_center", "Task Manager": "task_manager", "Goals": "goals",
        "Habit Tracker": "habit_tracker", "Routine Planner": "routine_planner", "Activity & Wellness": "activity_wellness",
        "Calendar": "calendar", "Notes & Knowledge Base": "notes", "Finance Tracker": "finance", "Analytics & Reports": "analytics", "AI Assistant": "ai_assistant",
    }
    with st.form("personal-settings"):
        display_name = st.text_input("Display name", value=current_name)
        timezone_options = ["Asia/Kolkata", "UTC", "America/New_York", "America/Los_Angeles", "Europe/London", "Europe/Berlin", "Asia/Singapore", "Australia/Sydney"]
        current_zone = values.get("timezone", "Asia/Kolkata")
        timezone_name = st.selectbox("Timezone", timezone_options, index=timezone_options.index(current_zone) if current_zone in timezone_options else 0)
        date_format = st.selectbox("Date format", ["DD MMM YYYY", "YYYY-MM-DD", "MM/DD/YYYY"], index=["DD MMM YYYY", "YYYY-MM-DD", "MM/DD/YYYY"].index(values.get("date_format", "DD MMM YYYY")))
        theme = st.selectbox("Theme", ["Premium dark", "Midnight"], index=["Premium dark", "Midnight"].index(values.get("theme", "Premium dark")))
        focus = st.text_input("Today's focus", value=values.get("focus_text", ""))
        widgets = st.multiselect("Overview widgets", ["Tasks", "Learning", "Habits", "Goals", "Streak", "Weekly charts", "Upcoming"], default=values.get("dashboard_widgets", ["Tasks", "Learning", "Habits", "Goals", "Streak", "Weekly charts", "Upcoming"]))
        enabled = st.multiselect("Enabled modules", list(available_pages), default=values.get("enabled_modules", list(available_pages)))
        daily_target = st.number_input("Default daily learning target (minutes)", min_value=0, max_value=1440, value=int(values.get("daily_learning_target_minutes", 60)), step=15)
        st.caption("The initial SAP ABAP plan can be edited in Study Center; this default does not alter existing course targets.")
        saved = st.form_submit_button("Save preferences", type="primary")
    if saved:
        new_values = {
            **values,
            "display_name": display_name.strip() or current_name,
            "timezone": timezone_name,
            "date_format": date_format,
            "theme": theme,
            "focus_text": focus.strip(),
            "focus_date": date.today().isoformat(),
            "dashboard_widgets": widgets,
            "enabled_modules": enabled,
            "daily_learning_target_minutes": int(daily_target),
        }
        with session_scope(_db_url()) as session:
            row = session.get(ApplicationSettings, owner_id)
            if row:
                row.settings_json = new_values
            else:
                session.add(ApplicationSettings(owner_id=owner_id, settings_json=new_values))
        st.session_state["nexus_settings"] = new_values
        st.session_state["nexus_display_name"] = new_values["display_name"]
        st.success("Preferences saved.")
        st.rerun()

    st.divider()
    section_title("Database and account security")
    db_config = database_config()
    db_col, auth_col = st.columns(2)
    with db_col:
        st.markdown("**Database connection**")
        st.write("Local SQLite · development only" if db_config.is_local else "Configured PostgreSQL")
        if db_config.is_local:
            st.warning("Local SQLite data is stored on this device and is not suitable for Streamlit Community Cloud persistence.")
        else:
            st.success("Database URL is configured server-side. The value is not displayed.")
        st.caption("Run `alembic upgrade head` before deploying schema changes. Supabase backups must be configured separately; this app does not claim an automatic backup.")
    with auth_col:
        st.markdown("**Authentication**")
        st.write("OIDC with an email allowlist" if st.session_state.get("nexus_auth_mode") == "oidc" else "Local development bypass")
        st.caption("Passwords are never stored by NEXUS. Sign-in tokens remain managed by Streamlit and the configured OIDC provider.")
    st.markdown("**Data export and restore**")
    st.write("Use Analytics & Reports to export CSV, Excel, or PDF. For full PostgreSQL restoration, restore a Supabase backup to the database, run Alembic migrations, and confirm the user account remains on the allowlist.")




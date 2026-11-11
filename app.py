"""NEXUS Streamlit entry point and authenticated multipage router."""

from __future__ import annotations

import streamlit as st
from sqlalchemy import inspect

from nexus.auth import require_identity
from nexus.config import ROOT, database_config, is_dev_auth_bypass
from nexus.database.connection import database_health, get_engine, initialize_local_schema, session_scope
from nexus.database.models import ApplicationSettings
from nexus.database.repositories import upsert_user
from nexus.database.seed import seed_initial_learning_plan
from nexus.ui.common import apply_theme


st.set_page_config(page_title="NEXUS · Personal Command Center", page_icon="◈", layout="wide", initial_sidebar_state="expanded")
st.logo("assets/icons/nexus.svg")
apply_theme()

identity = require_identity()
if identity is None:
    st.stop()

db_config = database_config()
st.session_state["nexus_db_url"] = db_config.url
st.session_state["nexus_owner_id"] = identity.owner_id
st.session_state["nexus_display_name"] = identity.display_name
st.session_state["nexus_auth_mode"] = "development" if identity.is_development else "oidc"

if identity.is_development and not is_dev_auth_bypass():
    st.error("Development authentication bypass cannot be used in this environment.")
    st.stop()

healthy, health_message = database_health(db_config.url)
if not healthy:
    st.title("NEXUS")
    st.error("NEXUS could not connect to its database. Check the server-side database configuration.")
    st.caption(health_message)
    st.stop()

try:
    initialize_local_schema(db_config.url)
    has_schema = inspect(get_engine(db_config.url)).has_table("users")
except Exception:
    has_schema = False
if not has_schema:
    st.title("NEXUS")
    st.error("The database is reachable, but its schema has not been initialized.")
    st.code("alembic upgrade head")
    st.caption("Run this once against the configured PostgreSQL database, then reload the app.")
    st.stop()

try:
    with session_scope(db_config.url) as session:
        upsert_user(session, identity.owner_id, identity.email, identity.display_name)
        seed_initial_learning_plan(session, identity.owner_id)
        settings_row = session.get(ApplicationSettings, identity.owner_id)
        saved_settings = dict(settings_row.settings_json or {}) if settings_row else {}
except Exception as exc:
    st.title("NEXUS")
    st.error("NEXUS could not prepare your private workspace.")
    st.caption(f"Details: {exc.__class__.__name__}")
    st.stop()

st.session_state["nexus_settings"] = saved_settings
if saved_settings.get("display_name"):
    st.session_state["nexus_display_name"] = saved_settings["display_name"]

if not db_config.is_local and not saved_settings:
    # Current user profile is shown in page chrome; persisted preferences can replace it.
    st.session_state["nexus_settings"] = {"timezone": "Asia/Kolkata"}

with st.sidebar:
    st.markdown("## ◈ NEXUS")
    st.caption("One place. Every goal. Complete control.")
    st.markdown(f"**{st.session_state['nexus_display_name']}**")
    if not identity.is_development:
        st.button("Sign out", on_click=st.logout, width="stretch")
    st.divider()

module_pages = {
    "My Day": ("app_pages/my_day.py", "my_day", ":material/today:"),
    "Study Center": ("app_pages/study_center.py", "study_center", ":material/school:"),
    "Task Manager": ("app_pages/task_manager.py", "task_manager", ":material/checklist:"),
    "Goals": ("app_pages/goals.py", "goals", ":material/flag:"),
    "Habit Tracker": ("app_pages/habit_tracker.py", "habit_tracker", ":material/local_fire_department:"),
    "Routine Planner": ("app_pages/routine_planner.py", "routine_planner", ":material/calendar_view_day:"),
    "Activity & Wellness": ("app_pages/activity_wellness.py", "activity_wellness", ":material/directions_run:"),
    "Calendar": ("app_pages/calendar.py", "calendar", ":material/calendar_month:"),
    "Notes & Knowledge Base": ("app_pages/notes.py", "notes", ":material/sticky_note_2:"),
    "Finance Tracker": ("app_pages/finance.py", "finance", ":material/account_balance_wallet:"),
    "Analytics & Reports": ("app_pages/analytics.py", "analytics", ":material/monitoring:"),
    "AI Assistant": ("app_pages/ai_assistant.py", "ai_assistant", ":material/auto_awesome:"),
}
enabled_modules = set(saved_settings.get("enabled_modules", list(module_pages)))
sections = {
    "COMMAND": [st.Page("app_pages/overview.py", title="Overview", icon=":material/dashboard:", help="Your saved tasks, learning progress, habit logs, goals, and upcoming schedule in one view.", default=True)],
    "PLAN & DO": [],
    "PERSONAL": [],
    "INSIGHTS": [],
    "PREFERENCES": [st.Page("app_pages/settings.py", title="Settings", icon=":material/settings:", help="Configure your profile, timezone, dashboard, modules, and review database and sign-in setup.")],
}
section_for = {
    "My Day": "PLAN & DO", "Study Center": "PLAN & DO", "Task Manager": "PLAN & DO", "Goals": "PLAN & DO",
    "Habit Tracker": "PERSONAL", "Routine Planner": "PERSONAL", "Activity & Wellness": "PERSONAL", "Calendar": "PERSONAL", "Notes & Knowledge Base": "PERSONAL",
    "Finance Tracker": "INSIGHTS", "Analytics & Reports": "INSIGHTS", "AI Assistant": "INSIGHTS",
}
for title, (path, url, icon) in module_pages.items():
    if title in enabled_modules:
        page_help = {
            "My Day": "Focus on a date's tasks, scheduled habits, and routine blocks without dropping unfinished work.",
            "Study Center": "Manage programs, lessons, logged study sessions, active recall cards, and spaced reviews.",
            "Task Manager": "Create and update tasks, filter by date and status, and retain a completion history.",
            "Goals": "Set time-bound goals, update progress, and maintain milestones.",
            "Habit Tracker": "Set habit schedules, log check-ins, and review historical consistency.",
            "Routine Planner": "Build reusable time-block templates, detect overlaps, and mark daily completion.",
            "Activity & Wellness": "Record personal activity, sleep duration, mood, energy, and observations.",
            "Calendar": "Combine events, tasks, lessons, revision dates, habit schedules, and routine blocks.",
            "Notes & Knowledge Base": "Search, organize, connect, and preview Markdown notes.",
            "Finance Tracker": "Maintain a manual income and expense ledger with monthly budget comparisons.",
            "Analytics & Reports": "Filter saved records by date and export summaries to CSV, Excel, or PDF.",
            "AI Assistant": "Ask for read-only productivity suggestions using only selected stored context.",
        }[title]
        sections[section_for[title]].append(st.Page(path, title=title, icon=icon, help=page_help, url_path=url))
sections = {name: pages for name, pages in sections.items() if pages}
page = st.navigation(sections, position="sidebar", expanded=False)
page.run()

"""Owner-scoped create, edit, filter, export, and confirmed-delete renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, time
from typing import Any

import pandas as pd
import streamlit as st
from sqlalchemy import select

from nexus.database.connection import session_scope
from nexus.database.models import Goal, GoalHistory, GoalMilestone, LearningProgram, LearningSession, Lesson, LessonHistory, Task, TaskHistory
from nexus.database.repositories import delete_owned, list_owned, save_owned
from nexus.services.dates import get_zone, local_to_utc, utc_now_naive, utc_to_local
from nexus.ui.common import csv_bytes, empty_state, page_header, section_title, show_dataframe


@dataclass(frozen=True)
class Field:
    name: str
    label: str
    kind: str = "text"
    options: tuple[str, ...] = ()
    required: bool = False
    default: Any = None
    help: str | None = None
    reference_model: type | None = None
    reference_label: str = "title"
    minimum: int | float | None = None
    maximum: int | float | None = None


@dataclass(frozen=True)
class Resource:
    key: str
    title: str
    subtitle: str
    model: type
    fields: tuple[Field, ...]
    display_fields: tuple[tuple[str, str], ...]
    label_field: str
    order_field: str = "created_at"
    ascending: bool = False
    extra: str | None = None


def _form_field(field: Field, value: Any, key: str, zone_name: str, owner_id: str) -> Any:
    if field.kind == "select":
        options = list(field.options)
        if not field.required and "" not in options:
            options = [""] + options
        current = value if value in options else (field.default if field.default in options else options[0])
        return st.selectbox(field.label, options, index=options.index(current), key=key, help=field.help)
    if field.kind == "reference":
        if field.reference_model is None:
            return None
        options = []
        labels = {}
        with session_scope(st.session_state["nexus_db_url"]) as session:
            rows = list_owned(session, field.reference_model, owner_id, order_by=getattr(field.reference_model, field.reference_label))
            for row in rows:
                options.append(row.id)
                labels[row.id] = str(getattr(row, field.reference_label, row.id))
        choices = ([""] if not field.required else []) + options
        if not choices:
            choices = [""]
        current = value if value in choices else ("" if "" in choices else choices[0])
        return st.selectbox(field.label, choices, index=choices.index(current), format_func=lambda item: "— None —" if item == "" else labels.get(item, item), key=key, help=field.help, disabled=not options)
    if field.kind == "textarea":
        return st.text_area(field.label, value=str(value or ""), key=key, help=field.help, height=100)
    if field.kind == "jsonlist":
        return st.text_input(field.label, value=", ".join(map(str, value or [])), key=key, help=field.help or "Separate values with commas.")
    if field.kind == "weekdaylist":
        return st.multiselect(field.label, options=list(range(7)), default=[int(day) for day in (value or [])], format_func=lambda day: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"][day], key=key, help=field.help)
    if field.kind == "bool":
        return st.checkbox(field.label, value=bool(value if value is not None else field.default), key=key, help=field.help)
    if field.kind == "int":
        if not field.required and field.default is None:
            enabled = st.checkbox(f"Set {field.label.lower()}", value=value is not None, key=f"{key}-enabled")
            if not enabled:
                return None
        base = value if value is not None else (field.default if field.default is not None else 0)
        return st.number_input(field.label, min_value=field.minimum if field.minimum is not None else 0, max_value=field.maximum, step=1, value=int(base), key=key, help=field.help)
    if field.kind == "positive_int":
        base = value if value is not None else (field.default if field.default is not None else 1)
        return st.number_input(field.label, min_value=1, step=1, value=max(1, int(base)), key=key, help=field.help)
    if field.kind == "float":
        if not field.required and field.default is None:
            enabled = st.checkbox(f"Set {field.label.lower()}", value=value is not None, key=f"{key}-enabled")
            if not enabled:
                return None
        base = value if value is not None else (field.default if field.default is not None else 0.0)
        return st.number_input(field.label, min_value=field.minimum if field.minimum is not None else 0.0, max_value=field.maximum, step=0.5, value=float(base), key=key, help=field.help)
    if field.kind == "date":
        enabled = st.checkbox(f"Set {field.label.lower()}", value=value is not None or field.required, key=f"{key}-enabled")
        if not enabled:
            return None
        initial = value or field.default or date.today()
        return st.date_input(field.label, value=initial, key=key, help=field.help)
    if field.kind == "datetime":
        enabled = st.checkbox(f"Set {field.label.lower()}", value=value is not None or field.required, key=f"{key}-enabled")
        if not enabled:
            return None
        initial = utc_to_local(value, zone_name) if value else field.default
        initial = initial or datetime.now(get_zone(zone_name)).replace(tzinfo=None)
        return st.datetime_input(field.label, value=initial, key=key, help=field.help)
    if field.kind == "time":
        initial = value or field.default or time(9, 0)
        return st.time_input(field.label, value=initial, key=key, help=field.help)
    return st.text_input(field.label, value=str(value or ""), key=key, help=field.help)


def _normalize(field: Field, value: Any, zone_name: str) -> Any:
    if field.kind in {"text", "textarea"}:
        result = str(value or "").strip()
        return result
    if field.kind == "select":
        return value or (field.default or "")
    if field.kind == "reference":
        return value or None
    if field.kind == "jsonlist":
        return [part.strip() for part in str(value or "").split(",") if part.strip()]
    if field.kind == "weekdaylist":
        return [int(day) for day in value]
    if field.kind in {"int", "positive_int"}:
        return int(value) if value is not None else None
    if field.kind == "float":
        return float(value) if value is not None else None
    if field.kind == "datetime":
        return local_to_utc(value, zone_name)
    return value


def _query_records(resource: Resource, owner_id: str) -> list[Any]:
    with session_scope(st.session_state["nexus_db_url"]) as session:
        order = getattr(resource.model, resource.order_field)
        if not resource.ascending:
            order = order.desc()
        return list_owned(session, resource.model, owner_id, order_by=order)


def render_resource(resource: Resource, owner_id: str, *, show_header: bool = True) -> None:
    if show_header:
        page_header(resource.title, resource.subtitle)
    zone_name = st.session_state.get("nexus_settings", {}).get("timezone", "Asia/Kolkata")
    records = _query_records(resource, owner_id)
    if resource.model is Task:
        view = st.selectbox("Task view", ["All tasks", "Today", "Upcoming", "Overdue", "Completed"], key="task-manager-view")
        today = datetime.now(get_zone(zone_name)).date()
        if view == "Completed":
            records = [row for row in records if row.status == "Completed"]
        elif view == "Today":
            records = [row for row in records if row.due_at and utc_to_local(row.due_at, zone_name).date() == today]
        elif view == "Upcoming":
            records = [row for row in records if row.due_at and utc_to_local(row.due_at, zone_name).date() > today and row.status not in {"Completed", "Cancelled", "Deferred"}]
        elif view == "Overdue":
            records = [row for row in records if row.due_at and utc_to_local(row.due_at, zone_name).date() < today and row.status not in {"Completed", "Cancelled", "Deferred"}]
    if resource.extra:
        st.info(resource.extra)
    search = st.text_input("Search records", key=f"{resource.key}-search", placeholder="Search this module")
    if search:
        term = search.casefold()
        records = [r for r in records if any(term in str(getattr(r, name, "")).casefold() for name, _ in resource.display_fields)]
    if records:
        frame = pd.DataFrame([
            {label: getattr(record, name, None) for name, label in resource.display_fields}
            for record in records
        ])
        show_dataframe(frame, alt=f"{resource.title} records", height=min(400, max(180, len(frame) * 38 + 40)))
        st.download_button(
            "Export this view as CSV", csv_bytes(frame), file_name=f"nexus-{resource.key}.csv", mime="text/csv",
            key=f"{resource.key}-export",
        )
    else:
        empty_state("No matching records", "Create your first record below or change the search.")

    section_title("Create or update")
    record_by_id = {record.id: record for record in records}
    record_options = [""] + list(record_by_id)
    selected_id = st.selectbox(
        "Record to edit", record_options,
        format_func=lambda ident: "Create a new record" if not ident else str(getattr(record_by_id[ident], resource.label_field, ident)),
        key=f"{resource.key}-edit-selection",
    )
    selected = record_by_id.get(selected_id)
    is_edit = selected is not None
    record_id = selected.id if is_edit else None
    with st.form(f"{resource.key}-editor-{record_id or 'new'}", clear_on_submit=False):
        values: dict[str, Any] = {}
        columns = st.columns(2)
        for index, form_field in enumerate(resource.fields):
            current = getattr(selected, form_field.name, None) if is_edit else form_field.default
            target = st if form_field.kind == "textarea" else columns[index % 2]
            with target:
                values[form_field.name] = _form_field(
                    form_field, current, f"{resource.key}-{record_id or 'new'}-{form_field.name}", zone_name, owner_id
                )
        submitted = st.form_submit_button("Save changes" if is_edit else "Create record", type="primary", width="stretch")
    if submitted:
        missing = [f.label for f in resource.fields if f.required and (values.get(f.name) is None or str(values.get(f.name)).strip() == "")]
        if missing:
            st.error("Please complete: " + ", ".join(missing))
        else:
            normalized = {f.name: _normalize(f, values[f.name], zone_name) for f in resource.fields}
            validation = _validate_values(resource, normalized, record_id)
            if resource.model is LearningSession and normalized.get("lesson_id"):
                with session_scope(st.session_state["nexus_db_url"]) as session:
                    linked_lesson = session.scalar(select(Lesson).where(Lesson.id == normalized["lesson_id"], Lesson.owner_id == owner_id))
                if linked_lesson is None:
                    validation = "Choose a lesson from your private learning library."
                elif normalized.get("program_id") and normalized["program_id"] != linked_lesson.program_id:
                    validation = "The selected lesson does not belong to the selected program."
                else:
                    normalized["program_id"] = linked_lesson.program_id
            if validation:
                st.error(validation)
                return
            try:
                with session_scope(st.session_state["nexus_db_url"]) as session:
                    existing = session.get(resource.model, record_id) if is_edit else None
                    if is_edit and existing is None:
                        st.error("This record was removed in another session. Refresh and try again.")
                    elif existing is not None and hasattr(existing, "owner_id") and existing.owner_id != owner_id:
                        st.error("Record not found in your private workspace.")
                    else:
                        old_status = existing.status if isinstance(existing, Task) else None
                        old_goal_progress = existing.progress if isinstance(existing, Goal) else None
                        old_goal_status = existing.status if isinstance(existing, Goal) else None
                        old_lesson_status = existing.status if isinstance(existing, Lesson) else None
                        if resource.model is Goal and normalized.get("linked_id"):
                            linked_type = str(normalized.get("linked_type", "")).casefold()
                            if linked_type == "task":
                                linked_task = session.scalar(select(Task).where(Task.id == normalized["linked_id"], Task.owner_id == owner_id))
                                if linked_task is None:
                                    st.error("The linked task was not found in your private workspace.")
                                    return
                                normalized["progress"] = 100 if linked_task.status == "Completed" else 0
                            elif linked_type in {"learning program", "program"}:
                                program = session.scalar(select(LearningProgram).where(LearningProgram.id == normalized["linked_id"], LearningProgram.owner_id == owner_id))
                                if program is None:
                                    st.error("The linked learning program was not found in your private workspace.")
                                    return
                                program_lessons = session.scalars(select(Lesson).where(Lesson.owner_id == owner_id, Lesson.program_id == program.id)).all()
                                normalized["progress"] = round(sum(1 for lesson in program_lessons if lesson.status == "Completed") / len(program_lessons) * 100) if program_lessons else 0
                        record = save_owned(session, resource.model, owner_id, record_id, normalized)
                        if isinstance(record, Task) and record.status != old_status:
                            if record.status == "Completed":
                                record.completed_at = utc_now_naive()
                            elif old_status == "Completed":
                                record.completed_at = None
                            session.add(TaskHistory(
                                owner_id=owner_id,
                                task_id=record.id,
                                previous_status=old_status or "",
                                new_status=record.status,
                                note="Updated from Task Manager",
                            ))
                        if isinstance(record, Goal) and (old_goal_progress != record.progress or old_goal_status != record.status):
                            session.add(GoalHistory(
                                owner_id=owner_id, goal_id=record.id, previous_progress=old_goal_progress or 0,
                                new_progress=record.progress, previous_status=old_goal_status or "", new_status=record.status,
                                note="Progress or status updated from Goals",
                            ))
                        if isinstance(record, GoalMilestone) and record.is_complete and not record.completed_at:
                            record.completed_at = utc_now_naive()
                        if isinstance(record, GoalMilestone) and not record.is_complete:
                            record.completed_at = None
                        if isinstance(record, Lesson):
                            if record.status == "Completed" and not record.completed_at:
                                record.completed_at = utc_now_naive()
                            elif record.status != "Completed":
                                record.completed_at = None
                            if record.status != old_lesson_status:
                                session.add(LessonHistory(
                                    owner_id=owner_id,
                                    lesson_id=record.id,
                                    previous_status=old_lesson_status or "",
                                    new_status=record.status,
                                    note="Updated from Study Center",
                                ))
                st.success("Record saved.")
                st.rerun()
            except Exception as exc:
                st.error(f"Could not save this record. Check required values and date ranges. ({exc.__class__.__name__})")

    if is_edit:
        section_title("Delete record")
        with st.form(f"{resource.key}-delete-{record_id}"):
            confirmed = st.checkbox(f"Confirm deletion of {getattr(selected, resource.label_field, 'this record')}")
            delete_clicked = st.form_submit_button("Delete permanently")
        if delete_clicked:
            if not confirmed:
                st.warning("Confirm deletion to continue.")
            else:
                try:
                    with session_scope(st.session_state["nexus_db_url"]) as session:
                        delete_owned(session, resource.model, owner_id, record_id)
                    st.success("Record deleted.")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Could not delete this record. ({exc.__class__.__name__})")


def _validate_values(resource: Resource, values: dict[str, Any], record_id: str | None) -> str | None:
    if resource.model is Task and values.get("parent_id") and values["parent_id"] == record_id:
        return "A task cannot be its own parent."
    if resource.model.__name__ == "Goal" and values.get("start_date") and values.get("target_date") and values["target_date"] < values["start_date"]:
        return "The goal target date must be on or after its start date."
    if resource.model.__name__ == "Budget":
        month = str(values.get("month", ""))
        if len(month) != 7 or month[4:5] != "-" or not month[:4].isdigit() or not month[5:].isdigit() or not 1 <= int(month[5:]) <= 12:
            return "Enter the budget month in YYYY-MM format."
    if resource.model.__name__ == "FinanceTransaction" and values.get("amount", 0) <= 0:
        return "Transaction amount must be greater than zero."
    if resource.model.__name__ == "RoutineItem" and values.get("end_time") <= values.get("start_time"):
        return "A routine block must end after it starts on the same day."
    if resource.model.__name__ == "CalendarEvent" and values.get("ends_at") <= values.get("starts_at"):
        return "An event must end after it starts."
    return None


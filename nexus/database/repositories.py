"""Small owner-scoped repository primitives. Never query private rows without owner_id."""

from __future__ import annotations

from typing import Any, TypeVar

from sqlalchemy import Select, select
from sqlalchemy.orm import Session

from nexus.database.models import OwnerMixin, User, new_id

T = TypeVar("T", bound=OwnerMixin)


def list_owned(session: Session, model: type[T], owner_id: str, *, order_by: Any = None) -> list[T]:
    statement: Select = select(model).where(model.owner_id == owner_id)
    if order_by is not None:
        statement = statement.order_by(order_by)
    return list(session.scalars(statement).all())


def get_owned(session: Session, model: type[T], owner_id: str, record_id: str) -> T | None:
    return session.scalar(select(model).where(model.owner_id == owner_id, model.id == record_id))


def save_owned(session: Session, model: type[T], owner_id: str, record_id: str | None, values: dict[str, Any]) -> T:
    record = get_owned(session, model, owner_id, record_id) if record_id else None
    if record is None:
        record = model(owner_id=owner_id, **values)
        session.add(record)
    else:
        for key, value in values.items():
            setattr(record, key, value)
    session.flush()
    return record


def delete_owned(session: Session, model: type[T], owner_id: str, record_id: str) -> bool:
    record = get_owned(session, model, owner_id, record_id)
    if record is None:
        return False
    session.delete(record)
    return True


def upsert_user(session: Session, user_id: str, email: str, display_name: str = "") -> User:
    user = session.get(User, user_id)
    if user is None:
        user = User(id=user_id or new_id(), email=email.casefold(), display_name=display_name)
        session.add(user)
    else:
        user.email = email.casefold()
        if display_name:
            user.display_name = display_name
    session.flush()
    return user


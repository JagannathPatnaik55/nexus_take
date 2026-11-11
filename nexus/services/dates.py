"""Timezone boundary helpers. Persist datetimes as naive UTC in PostgreSQL."""

from __future__ import annotations

from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def get_zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError:
        return ZoneInfo("Asia/Kolkata")


def utc_now_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def local_to_utc(value: datetime | None, zone_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=get_zone(zone_name))
    return value.astimezone(timezone.utc).replace(tzinfo=None)


def utc_to_local(value: datetime | None, zone_name: str) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(get_zone(zone_name)).replace(tzinfo=None)


def local_day(value: datetime, zone_name: str) -> date:
    return utc_to_local(value, zone_name).date()


def local_datetime_for_widget(value: datetime | None, zone_name: str) -> datetime:
    return utc_to_local(value, zone_name) or datetime.now(get_zone(zone_name)).replace(tzinfo=None)


def combine_local(day: date, at: time, zone_name: str) -> datetime:
    return local_to_utc(datetime.combine(day, at), zone_name)


"""Runtime configuration. Secrets are read on the server and never rendered."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]


def _streamlit_secret(*path: str, default: Any = None) -> Any:
    try:
        import streamlit as st

        value: Any = st.secrets
        for part in path:
            value = value[part]
        return value
    except Exception:
        return default


def setting(name: str, *, secret_path: tuple[str, ...] | None = None, default: Any = None) -> Any:
    value = os.getenv(name)
    if value is not None:
        return value
    if secret_path:
        return _streamlit_secret(*secret_path, default=default)
    return default


def allowed_emails() -> set[str]:
    raw = setting("NEXUS_ALLOWED_EMAILS", secret_path=("access", "allowed_emails"), default="")
    if isinstance(raw, str):
        values = raw.split(",")
    else:
        values = list(raw or [])
    return {str(email).strip().casefold() for email in values if str(email).strip()}


def is_auth_configured() -> bool:
    return bool(_streamlit_secret("auth", default=None))


def is_dev_auth_bypass() -> bool:
    return str(setting("NEXUS_DEV_AUTH_BYPASS", default="false")).casefold() in {"1", "true", "yes"}


@dataclass(frozen=True)
class DatabaseConfig:
    url: str
    is_local: bool


def database_config() -> DatabaseConfig:
    url = setting("DATABASE_URL", secret_path=("database", "url"), default="")
    if url:
        value = str(url).strip()
        if value.startswith("postgres://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgres://")
        elif value.startswith("postgresql://"):
            value = "postgresql+psycopg://" + value.removeprefix("postgresql://")
        return DatabaseConfig(value, False)
    local_path = ROOT / ".nexus-data" / "nexus.db"
    local_path.parent.mkdir(parents=True, exist_ok=True)
    return DatabaseConfig(f"sqlite:///{local_path.as_posix()}", True)


def timezone_name() -> str:
    return str(setting("NEXUS_TIMEZONE", default="Asia/Kolkata"))


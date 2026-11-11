# NEXUS architecture

## Runtime and environment

- Python 3.15 is installed in the inspected workspace; no application packages or existing project files were present.
- Streamlit's native `st.navigation`/`st.Page` router provides the multipage shell. The app uses Streamlit OIDC (`st.login`, `st.user`, `st.logout`) and an email allowlist for authorization.
- SQLAlchemy owns data access; Alembic owns production schema changes. Supabase PostgreSQL is the required deployed store. A file-backed SQLite database is available only for local development when `DATABASE_URL` is absent.
- Pandas and Plotly power data exports and interactive reports. The repository does not contain credentials.

## Request and data flow

```text
OIDC identity -> allowlist -> stable owner id -> repository query scoped by owner_id
                                               |
Streamlit navigation -> page view -> service/repository -> SQLAlchemy -> PostgreSQL
                                                      \-> SQLite for local development
```

Every private model is scoped to the authenticated OIDC subject. Repositories accept the owner id explicitly and filter reads, updates, and deletes by it. UI code does not construct SQL. Foreign keys connect learning, task, goal, habit, routine, wellness, calendar, note, and finance records. The first sign-in creates the requested SAP ABAP learning plan once; its 100 pending lessons and due dates are planning records, not completed activity or sample analytics.

## Package layout

- `app.py`: shared entry point, authentication gate, theme, migrations health check, and page router.
- `nexus/config.py`, `nexus/auth.py`: runtime configuration and authorization.
- `nexus/database/`: SQLAlchemy models, connection/session handling, owner-scoped repositories, and onboarding seed.
- `nexus/services/`: progress calculations, timezone conversion, analytics, and optional AI client.
- `nexus/ui/`: shared page chrome, CRUD form renderer, charts, exports, and page composition.
- `app_pages/`: fourteen native Streamlit pages.
- `alembic/`: versioned relational schema changes.
- `tests/`: unit tests for calculations, authorization scoping, and persistence behavior.

## Data ownership and security

The identity provider authenticates users; NEXUS checks the email allowlist because OIDC alone does not authorize access. Each row has an owner id and all repository operations require it. PostgreSQL connections stay on the Python server and are read from Streamlit secrets or environment variables. In Supabase, use a dedicated database login restricted to this app's schema and TLS. The SQLAlchemy app role is not exposed to the browser. Community Cloud deployment must use PostgreSQL and configured OIDC; local auth bypass is opt-in and must never be enabled in production.

## Migration and persistence policy

Local SQLite may initialize its schema on startup to make local setup easy. PostgreSQL schema changes are explicit: run `alembic upgrade head` before starting a deployment. The application checks connectivity and reports a migration-required state instead of silently changing production schema. PostgreSQL is the source of truth in hosted deployments. Supabase backups and exports are separate: no backup schedule is claimed or configured by this repository.

## Date and time policy

Dates are stored as calendar dates. Datetimes are stored as UTC-naive values by SQLAlchemy and converted at the UI boundary using the user's configured IANA timezone (initially `Asia/Kolkata`). Tests cover DST-aware conversion and day-boundary behavior.

## Milestones

1. Foundation: schema, auth gate, secrets template, migrations, dark theme, and native navigation.
2. Daily workflow: overview, tasks, study center, goals, habits, routines, wellness, calendar, and notes.
3. Personal insight: finance, analytics, exports, AI assistant, settings, and cross-module summaries.
4. QA and delivery: install dependencies, run automated tests and startup checks, fix defects, document local/Supabase/GitHub/Community Cloud setup and limitations.

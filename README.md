# NEXUS – Personal Command Center

**One place. Every goal. Complete control.**

NEXUS is a dark, modular Streamlit application for tasks, learning, goals, habits, reusable routines, wellness records, events, notes, manual finances, analytics, exports, and optional AI assistance. Records are stored through SQLAlchemy. Use Supabase PostgreSQL for a hosted deployment. A file-backed SQLite database is included for local development only.

## Current implementation

- Native multipage navigation for the fourteen requested areas.
- Streamlit OIDC sign-in and an authorized-email allowlist. NEXUS does not store passwords.
- Owner-scoped repository queries and relational foreign keys.
- Editable learning programs, ordered lessons, study logs, recall cards, and a self-rated spaced-revision flow.
- On first sign-in, an idempotent SAP Full-Stack ABAP Developer plan is created with 100 pending one-hour videos scheduled for November 11–21, 2026 (9 per day through November 20, then 10 on November 21). No completion is fabricated.
- Task status history and user-controlled carry-forward; goals and milestones; habit logs with a contribution-style heatmap; reusable routine templates with overlap detection and check-ins; activity and wellness records; combined calendar; Markdown notes; manual income/expense ledger and budgets.
- Analytics from saved rows, CSV/Excel/PDF exports, and an optional read-only OpenAI-compatible assistant.
- Alembic schema migration, local setup, Supabase and Community Cloud deployment guidance.

## Environment inspected

The supplied workspace was empty, had no Git repository, and had Python 3.15.1 with pip but no application dependencies. `requirements.txt` records the versions used for the Python 3.15 implementation. A project virtual environment is `.venv`.

## Local setup

PowerShell:

```powershell
cd "D:\Jagannath\Projects\My Dashboard"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
$env:NEXUS_DEV_AUTH_BYPASS = "true"
streamlit run app.py
```

The local bypass creates one development identity (`local@nexus.invalid`) and stores data in `.nexus-data/nexus.db`. It is intentionally opt-in. Do not enable it for a public deployment. Local SQLite creates its schema on startup.

To run locally against Supabase instead, create `.streamlit/secrets.toml` from `.streamlit/secrets.toml.example`, configure the OIDC values and authorized email, and set a database URL. Before first app start, export `DATABASE_URL` in the shell and run `alembic upgrade head`. The configured `DATABASE_URL` can also be supplied through `[database].url` in Streamlit secrets for the app process.

## Supabase PostgreSQL setup

1. Create a Supabase project and choose a strong database password. Keep it in a password manager.
2. In **Project Settings → Database**, copy a PostgreSQL connection string appropriate for your runtime. Use the session pooler for serverless or frequently recycled connections; use TLS (`sslmode=require`). Add it as `DATABASE_URL` for migration commands, then place it in Streamlit secrets as `[database].url`.
3. Create a dedicated application database role with a unique password. Run migrations with the project owner/migration role. Configure the app role for only the NEXUS tables and CRUD privileges; do not use the Supabase service-role key as a database credential. SQLAlchemy parameterizes values, and the application filters reads, edits, and deletes by the authenticated owner id.
4. From the repository root, set the migration connection string in your shell and run:

   ```powershell
   $env:DATABASE_URL = "postgresql+psycopg://USER:PASSWORD@HOST:5432/postgres?sslmode=require"
   .\.venv\Scripts\alembic.exe upgrade head
   ```

   Never paste a real URL into source control or a shared terminal transcript. If your password contains URL-reserved characters, percent-encode them in the URL.
5. Verify the app starts and the Settings page reports PostgreSQL configured. The URL is never shown in the UI.

OIDC authenticates identity; the email allowlist authorizes the one personal account. Configure a Google, Microsoft, or other OIDC client in the provider console. Set the callback URI to `http://localhost:8501/oauth2callback` locally and to `https://YOUR-APP.streamlit.app/oauth2callback` after deployment. Use a long random `cookie_secret`. Set `NEXUS_ALLOWED_EMAILS` or `[access].allowed_emails` to the authorized email address. Streamlit's OIDC API requires Streamlit 1.42 or later; this project uses 1.67.

## Secrets

For local OIDC setup, copy `.streamlit/secrets.toml.example` to `.streamlit/secrets.toml` and replace every placeholder. The real file is ignored by Git. On Community Cloud, paste the TOML into the app's **Settings → Secrets**. `NEXUS_ALLOWED_EMAILS` may instead be set as an environment variable. The AI integration stays disabled unless `[ai].api_key` or `OPENAI_API_KEY` is configured. Only prompts, a compact task/program summary, and notes explicitly selected in the AI page are sent to the configured endpoint.

## Run migrations

`alembic upgrade head` applies PostgreSQL schema changes. Local SQLite schema creation is automatic for development. Do not rely on production startup to silently alter the hosted schema. Configure the same `DATABASE_URL` for Alembic and the app. The migration command reads the environment variable; Streamlit secrets are not loaded by the Alembic CLI.

## GitHub and Streamlit Community Cloud

1. Create a private GitHub repository and push this project. Keep `.streamlit/secrets.toml`, `.env`, database files, and backups out of Git; `.gitignore` covers them.
2. In Streamlit Community Cloud, select the repository, branch, and `app.py` as the entry point.
3. Select a released Python version supported by Community Cloud and install the pinned `requirements.txt` dependencies.
4. Add the OIDC configuration, authorized email, and Supabase connection in Community Cloud secrets. Update the OIDC callback URI to the deployed app hostname.
5. Apply the Alembic migration once to Supabase before exposing the app. Do not use the local SQLite fallback for cloud persistence.
6. Confirm the sign-in allowlist, PostgreSQL connection, initial learning plan, page navigation, and a reversible create/edit/delete workflow before relying on the app.

Community Cloud runs a remote server; files on the developer's computer are not shared with it. PostgreSQL is the hosted source of truth. The repository does not configure or verify a Supabase backup schedule.

## Exports, backups, and restore

Analytics & Reports provides a combined CSV, a multi-sheet Excel workbook, and a date-window PDF review. Some module pages can export their current record view to CSV. These are user-initiated exports and do not replace a backup.

Configure Supabase's backup/PITR options for the project's plan and retention needs, and verify them in Supabase. To restore, restore the project database through Supabase, run `alembic upgrade head`, check the allowed OIDC email and sign in, then export a fresh copy from Analytics. Never claim a backup exists until the provider's backup status has been checked. Local SQLite can be copied from `.nexus-data/nexus.db` while the app is stopped; it is not automatically uploaded or replicated.

## Architecture

See [ARCHITECTURE.md](ARCHITECTURE.md) for the data flow, ownership boundary, schema responsibilities, and migration policy. Main paths:

```text
app.py                    authenticated router and shared shell
app_pages/                fourteen native Streamlit pages
nexus/database/models.py  normalized SQLAlchemy schema
nexus/database/           connections, repositories, onboarding seed
nexus/services/            timezone, analytics, optional AI
nexus/ui/                  reusable CRUD forms and page composition
alembic/                   schema migration history
tests/                     calculation and persistence tests
```

## Tests and startup checks

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m compileall -q app.py nexus app_pages alembic tests
```

The tests use temporary SQLite databases and do not require Supabase credentials. They do not prove a cloud connection or a deployment. Verify those against the configured project before deployment.

## Known limits

- Streamlit is request/rerun oriented; due dates are stored, but no email or push notification is sent.
- Recurring task rules are stored for reference; NEXUS does not silently generate future occurrences. Carry-forward is an explicit user action.
- Calendar views combine stored events, task due times, learning dates, revision dates, habit schedules, and routine blocks; this is not an external calendar synchronization service.
- The optional assistant is read-only and keeps its chat in the current Streamlit session. It needs a separately supplied provider API key and internet access.
- A successful local test run does not validate Supabase credentials, OIDC provider setup, Community Cloud secrets, or provider backups.

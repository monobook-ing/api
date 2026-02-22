# FastAPI Starter Kit

Simple FastAPI starter template with JWT auth and PostgreSQL via SQLAlchemy.

## Quickstart

1. Create a virtual environment and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. Set environment variables (optional) in `.env`:

```
APP_NAME=fastapi-starter-kit
DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/postgres
SUPABASE_URL=https://<project>.supabase.co
SUPABASE_DB_PASSWORD=<database-password-from-settings-database>
# Alternatively, you can use the service role key, but prefer the DB password for migrations/local runs.
# SUPABASE_SERVICE_KEY=<service-role-key-from-settings-api>
SECRET_KEY=change-me
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
RESEND_API_KEY=<resend-api-key>
RESEND_FROM_EMAIL=Product Team <onboarding@example.com>
# Optional: URL used to build the magic link (token will be appended or substituted if "{token}" is present)
# MAGIC_LINK_BASE_URL=https://example.com/auth/magic-link?token=
# Optional: Disable outbound emails (useful for local development)
# SKIP_EMAILS=true
```

If you use Supabase, set `SUPABASE_URL` to your project URL (ending with `.supabase.co`) and supply either:

- `SUPABASE_DB_PASSWORD`: copy from **Settings → Database → Connection string → Password** (works best for local runs and migrations).
- `SUPABASE_SERVICE_KEY`: the **service_role** key from **Settings → API** (can also unlock Postgres).

When `DATABASE_URL` is not provided, the app will derive the correct Postgres connection string automatically from the Supabase values.

3. Start the API:

```bash
uvicorn app.main:app --reload
```

This starter does not bundle a migrations tool; initialize your database schema using your preferred approach before running the application.

### Endpoints

- `GET /ping` — public health check
- `GET /public/ping` — health check
- `POST /auth/register` — create user
- `POST /auth/token` — obtain JWT access token
- `GET /protected/me` — current user profile (requires Bearer token)

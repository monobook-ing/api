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
- `POST /mcp` — ChatGPT Apps MCP endpoint (requires `X-Monobook-MCP-Key`)

### MCP Integration Environment Variables

- `MCP_SHARED_SECRET` (required for MCP access): shared key expected in `X-Monobook-MCP-Key`
- `MCP_PUBLIC_BASE_URL` (optional): public API base URL used for widget CSP metadata and fallback asset URL derivation.
- `CHATGPT_WIDGET_BASE_URL` (optional, legacy): base URL used to derive `/apps/chatgpt-widget.js` and `/apps/chatgpt-widget.css` when explicit URLs are not set.
- `CHATGPT_WIDGET_JS_URL` (recommended): full public URL to widget JS bundle.
- `CHATGPT_WIDGET_CSS_URL` (recommended): full public URL to widget CSS bundle.

The search widget runtime is loaded as external JS/CSS references (no inline asset cache). This ensures new widget deploys are picked up without API restarts.

### MCP Tools

- `search_hotels(...)` — cross-property hotel discovery with filters for location, availability, guests, pet-friendly, and budget.
- `search_rooms(property_id, ...)` — property-scoped room search (backward-compatible tool).
- `check_availability(property_id, room_id, check_in, check_out)` — room availability check.
- `create_booking(property_id, room_id, guest_name, ...)` — confirmed booking creation.

#### Recommended split-domain setup

Use explicit full asset URLs when widget assets are hosted on a separate static domain:

```env
MCP_PUBLIC_BASE_URL=https://api.example.com
CHATGPT_WIDGET_JS_URL=https://static.example.com/widgets/chatgpt-widget.js
CHATGPT_WIDGET_CSS_URL=https://static.example.com/widgets/chatgpt-widget.css
```

#### Validation and startup behavior

- `CHATGPT_WIDGET_JS_URL` and `CHATGPT_WIDGET_CSS_URL` must both be set together.
- Public widget URLs must be absolute `http(s)` URLs.
- Placeholder hosts (for example, `your-api-domain.com`) are rejected for explicit widget asset URLs.
- On startup, when explicit widget URLs are configured, the API performs reachability checks (`HEAD`, then `GET` fallback).
- If an explicit widget asset is unreachable or returns non-success, startup fails with a clear runtime error.

#### Widget source of truth

- `search_hotels` and `search_rooms` both use the same ChatGPT widget runtime bundle.
- In this repo, API static fallback serves `/apps/*` from `apps-sdk/chatgpt/dist/apps` first.
- Use the Apps SDK widget build as the canonical release artifact for search widget UI updates.

#### Recommended deploy order for widget updates

1. Build widget assets from `apps-sdk/chatgpt`.
2. Deploy `chatgpt-widget.js` and `chatgpt-widget.css` to your public widget host.
3. Update `CHATGPT_WIDGET_JS_URL` and `CHATGPT_WIDGET_CSS_URL` if paths changed.
4. Restart API only when configuration changed (asset content updates alone do not require restart).

#### Troubleshooting white widget frames in ChatGPT

1. Verify the exact JS/CSS URLs load publicly in a browser (no auth required).
2. Confirm `CHATGPT_WIDGET_JS_URL` and `CHATGPT_WIDGET_CSS_URL` match deployed paths exactly.
3. Ensure `MCP_PUBLIC_BASE_URL` points to the publicly reachable API origin.
4. Check API startup logs for widget asset validation errors.

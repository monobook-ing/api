import asyncio
from pathlib import Path
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import httpx

from app.api.routes import (
    public,
    signin,
    users,
    team_members,
    notifications,
    properties,
    rooms,
    guests,
    bookings,
    audit,
    host_profile,
    knowledge_files,
    settings_connections,
    seed,
    ai_connections,
    embeddings,
    chat,
)
from app.core.config import get_settings
from app.mcp.server import (
    get_mcp_asgi_app,
    get_widget_asset_urls,
    shutdown_mcp,
    startup_mcp,
)

settings = get_settings()

app = FastAPI(title=settings.app_name)


def _is_absolute_http_url(url: str | None) -> bool:
    if not url:
        return False
    parsed = urlparse(url)
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


def _is_success(status_code: int) -> bool:
    return 200 <= status_code < 400


async def _check_widget_asset(
    client: httpx.AsyncClient,
    *,
    label: str,
    url: str,
) -> None:
    try:
        head_response = await client.head(url, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Widget {label} asset check failed for {url}: HEAD request error ({exc})."
        ) from exc

    if _is_success(head_response.status_code):
        return

    try:
        get_response = await client.get(url, follow_redirects=True)
    except httpx.HTTPError as exc:
        raise RuntimeError(
            f"Widget {label} asset check failed for {url}: "
            f"HEAD {head_response.status_code}; GET request error ({exc})."
        ) from exc

    if _is_success(get_response.status_code):
        return

    raise RuntimeError(
        f"Widget {label} asset check failed for {url}: "
        f"HEAD {head_response.status_code}, GET {get_response.status_code}."
    )


async def validate_widget_runtime_assets() -> None:
    """
    Fail startup when configured widget assets are unreachable.

    Relative URLs are skipped because they are served by this app at runtime.
    """
    # Enforce fail-fast checks only for explicit split-domain asset mode.
    if not (settings.chatgpt_widget_js_url and settings.chatgpt_widget_css_url):
        return

    css_url, js_url = get_widget_asset_urls()
    raw_targets = [
        ("CSS", css_url),
        ("JS", js_url),
    ]
    absolute_targets = [
        (label, url)
        for label, url in raw_targets
        if url and _is_absolute_http_url(url)
    ]
    if not absolute_targets:
        return

    async with httpx.AsyncClient(timeout=httpx.Timeout(10.0)) as client:
        results = await asyncio.gather(
            *[
                _check_widget_asset(client, label=label, url=url)
                for label, url in absolute_targets
            ],
            return_exceptions=True,
        )

    failures = [result for result in results if isinstance(result, Exception)]
    if failures:
        details = "; ".join(str(failure) for failure in failures)
        raise RuntimeError(f"Widget runtime asset validation failed: {details}")

# Serve bundled ChatGPT widget assets from this API by default.
# Prefer the dedicated Apps SDK bundle to keep search widget UI consistent.
repo_root = Path(__file__).resolve().parents[2]
widget_apps_candidates = [
    repo_root / "apps-sdk" / "chatgpt" / "dist" / "apps",
    repo_root / "monobook" / "dist" / "apps",
]
widget_apps_dir = next((path for path in widget_apps_candidates if path.is_dir()), None)
if widget_apps_dir is not None:
    app.mount("/apps", StaticFiles(directory=str(widget_apps_dir), html=False), name="apps")

# Keep legacy `/assets/*` support for older bundles that still reference it directly.
legacy_ui_assets = repo_root / "monobook" / "dist" / "assets"
if legacy_ui_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=str(legacy_ui_assets), html=False), name="assets")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Update this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.api_route("/ping", methods=["GET", "HEAD", "OPTIONS"], tags=["public"])
async def ping() -> dict[str, str]:
    return {"status": "ok"}


# Include routers — public & auth
app.include_router(public.router)
app.include_router(signin.router)
app.include_router(users.router)
app.include_router(team_members.router)
app.include_router(notifications.router)

# Include routers — hotel domain
app.include_router(properties.router)
app.include_router(rooms.router)
app.include_router(guests.router)
app.include_router(bookings.router)
app.include_router(audit.router)
app.include_router(host_profile.router)
app.include_router(knowledge_files.router)
app.include_router(settings_connections.router)
app.include_router(seed.router)

# Include routers — AI / Layer 2 & 3
app.include_router(ai_connections.router)
app.include_router(embeddings.router)
app.include_router(chat.router)

# ChatGPT Apps remote MCP endpoint (protected by shared-secret header)
app.mount("/mcp", get_mcp_asgi_app())


@app.on_event("startup")
async def _startup_mcp() -> None:
    await validate_widget_runtime_assets()
    await startup_mcp()


@app.on_event("shutdown")
async def _shutdown_mcp() -> None:
    await shutdown_mcp()


@app.get("/", tags=["public"])
async def root() -> dict[str, str]:
    return {"message": f"Welcome to {settings.app_name}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

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
from app.mcp.server import get_mcp_asgi_app, shutdown_mcp, startup_mcp

settings = get_settings()

app = FastAPI(title=settings.app_name)

# Serve bundled ChatGPT widget assets from this API by default.
# This avoids needing a separate static host for `/apps/chatgpt-widget.{js,css}` in common deployments.
repo_root = Path(__file__).resolve().parents[2]
ui_dist = repo_root / "monobook" / "dist"
ui_apps = ui_dist / "apps"
ui_assets = ui_dist / "assets"
if ui_apps.is_dir():
    app.mount("/apps", StaticFiles(directory=str(ui_apps), html=False), name="apps")
if ui_assets.is_dir():
    app.mount("/assets", StaticFiles(directory=str(ui_assets), html=False), name="assets")

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

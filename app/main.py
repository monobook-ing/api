from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import (
    public,
    signin,
    users,
    team_members,
    notifications,
    properties,
    rooms,
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

settings = get_settings()

app = FastAPI(title=settings.app_name)

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


@app.get("/", tags=["public"])
async def root() -> dict[str, str]:
    return {"message": f"Welcome to {settings.app_name}"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)

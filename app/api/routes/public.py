from fastapi import APIRouter

router = APIRouter(prefix="/public", tags=["public"])


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong"}

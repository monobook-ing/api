from datetime import datetime, timezone

from fastapi import APIRouter, Depends
from supabase import Client

from app.core.config import get_settings
from app.crud.ai_connection import get_decrypted_api_key
from app.crud.knowledge_file import get_next_pending_file
from app.db.base import get_supabase
from app.services.knowledge_processor import process_knowledge_file

router = APIRouter(prefix="/public", tags=["public"])
settings = get_settings()


@router.get("/ping")
async def ping() -> dict[str, str]:
    return {"message": "pong"}


@router.post("/index-next")
async def index_next_pending_file(
    client: Client = Depends(get_supabase),
) -> dict:
    """Index the next pending knowledge file synchronously."""
    file_row = await get_next_pending_file(client)
    if not file_row:
        return {"processed": False}

    file_id = str(file_row["id"])
    property_id = str(file_row["property_id"])
    storage_path = file_row.get("storage_path")

    if not storage_path:
        client.table("knowledge_files").update(
            {
                "indexing_status": "error",
                "extraction_error": "Missing storage_path",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", file_id).execute()
        return {"processed": True, "file_id": file_id, "status": "error"}

    # Ensure in-progress even if fallback query path was used.
    client.table("knowledge_files").update(
        {
            "indexing_status": "in_progress",
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    ).eq("id", file_id).execute()

    try:
        file_bytes = client.storage.from_("knowledge-files").download(storage_path)
        openai_api_key = await get_decrypted_api_key(client, property_id, "openai")
        api_key = openai_api_key or settings.openai_api_key
        if not api_key:
            raise RuntimeError("No OpenAI API key configured for this property")

        result = await process_knowledge_file(
            client=client,
            file_id=file_id,
            property_id=property_id,
            file_bytes=file_bytes,
            mime_type=file_row.get("mime_type") or "text/plain",
            api_key=api_key,
            file_name=file_row.get("name") or "",
            language=file_row.get("language") or "en",
            doc_type=file_row.get("doc_type") or "general",
            effective_date=(
                str(file_row.get("effective_date"))
                if file_row.get("effective_date")
                else None
            ),
        )
        return {
            "processed": True,
            "file_id": file_id,
            "status": result.get("status", "indexed"),
        }
    except Exception as exc:
        client.table("knowledge_files").update(
            {
                "indexing_status": "error",
                "extraction_error": str(exc),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", file_id).execute()
        return {
            "processed": True,
            "file_id": file_id,
            "status": "error",
            "error": str(exc),
        }

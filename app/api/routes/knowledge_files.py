import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, UploadFile, status
from supabase import Client

from app.api import deps
from app.core.config import get_settings
from app.crud.ai_connection import get_decrypted_api_key
from app.crud.knowledge_file import (
    create_knowledge_file,
    delete_knowledge_file,
    get_knowledge_files,
)
from app.crud.property import user_owns_property
from app.db.base import get_supabase
from app.schemas.knowledge_file import (
    KnowledgeFileCreate,
    KnowledgeFileListResponse,
    KnowledgeFileResponse,
)
from app.services.knowledge_processor import process_knowledge_file

logger = logging.getLogger(__name__)
settings = get_settings()

router = APIRouter(prefix="/v1.0/properties/{property_id}/knowledge-files", tags=["knowledge-files"])

ALLOWED_MIME_TYPES = {
    "application/pdf",
    "application/x-pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/msword",
    "text/plain",
    "text/markdown",
    "text/csv",
}
MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB


@router.get("", response_model=KnowledgeFileListResponse)
async def list_knowledge_files(
    property_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """List knowledge base files for a property."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    rows = await get_knowledge_files(client, property_id)
    return KnowledgeFileListResponse(items=rows)


@router.post("", response_model=KnowledgeFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_knowledge_file(
    property_id: str,
    payload: KnowledgeFileCreate,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Register a knowledge base file (metadata only, no file upload)."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    data = payload.model_dump()
    f = await create_knowledge_file(client, property_id, data)
    return f


@router.post("/upload", response_model=KnowledgeFileResponse, status_code=status.HTTP_201_CREATED)
async def upload_knowledge_file_with_content(
    property_id: str,
    file: UploadFile,
    background_tasks: BackgroundTasks,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Upload a knowledge base file with content extraction and embedding."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    # Validate file
    if file.content_type and file.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {file.content_type}. Allowed: PDF, DOCX, TXT",
        )

    file_bytes = await file.read()
    if len(file_bytes) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File too large. Maximum size: {MAX_FILE_SIZE // (1024 * 1024)} MB",
        )

    # Format size string
    size_kb = len(file_bytes) / 1024
    size_str = f"{size_kb:.1f} KB" if size_kb < 1024 else f"{size_kb / 1024:.1f} MB"

    # Upload to Supabase Storage
    storage_path = f"knowledge/{property_id}/{file.filename}"
    try:
        client.storage.from_("knowledge-files").upload(
            storage_path, file_bytes, {"content-type": file.content_type or "application/octet-stream"}
        )
    except Exception as e:
        logger.warning(f"Storage upload failed (may already exist): {e}")
        # Try to update instead
        try:
            client.storage.from_("knowledge-files").update(
                storage_path, file_bytes, {"content-type": file.content_type or "application/octet-stream"}
            )
        except Exception:
            pass  # Storage is optional for MVP

    # Create DB record
    data = {
        "name": file.filename or "unknown",
        "size": size_str,
        "storage_path": storage_path,
        "mime_type": file.content_type,
    }
    f = await create_knowledge_file(client, property_id, data)

    # Get API key for embedding
    api_key = await get_decrypted_api_key(client, property_id, "openai")
    if not api_key:
        api_key = settings.openai_api_key

    # Process in background if we have an API key
    if api_key:
        background_tasks.add_task(
            process_knowledge_file,
            client,
            f["id"],
            property_id,
            file_bytes,
            file.content_type or "text/plain",
            api_key,
            file.filename or "unknown",
        )

    return f


@router.delete("/{file_id}", status_code=status.HTTP_200_OK)
async def remove_knowledge_file(
    property_id: str,
    file_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Soft-delete a knowledge base file and its embeddings."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")

    deleted = await delete_knowledge_file(client, file_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")

    # Remove associated embeddings
    client.table("embeddings").delete().eq(
        "source_type", "knowledge_chunk"
    ).eq("source_id", file_id).execute()

    return {"message": "File deleted", "id": file_id}

from fastapi import APIRouter, Depends, HTTPException, status
from supabase import Client

from app.api import deps
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

router = APIRouter(prefix="/v1.0/properties/{property_id}/knowledge-files", tags=["knowledge-files"])


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
    """Register a knowledge base file."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    data = payload.model_dump()
    f = await create_knowledge_file(client, property_id, data)
    return f


@router.delete("/{file_id}", status_code=status.HTTP_200_OK)
async def remove_knowledge_file(
    property_id: str,
    file_id: str,
    current_user: dict = Depends(deps.get_current_user),
    client: Client = Depends(get_supabase),
):
    """Soft-delete a knowledge base file."""
    if not await user_owns_property(client, current_user["id"], property_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Access denied")
    deleted = await delete_knowledge_file(client, file_id, current_user["id"])
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="File not found")
    return {"message": "File deleted", "id": file_id}

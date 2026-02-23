from __future__ import annotations

import io
import logging

from supabase import Client

from app.services.embedding import embed_knowledge_chunks

logger = logging.getLogger(__name__)


def extract_text(file_bytes: bytes, mime_type: str) -> str:
    """Extract plain text from PDF, DOCX, or TXT files."""
    if mime_type == "application/pdf" or mime_type == "application/x-pdf":
        return _extract_pdf(file_bytes)
    elif (
        mime_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or mime_type == "application/msword"
    ):
        return _extract_docx(file_bytes)
    elif mime_type and mime_type.startswith("text/"):
        return file_bytes.decode("utf-8", errors="replace")
    else:
        # Fallback: try as text
        return file_bytes.decode("utf-8", errors="replace")


def _extract_pdf(file_bytes: bytes) -> str:
    from PyPDF2 import PdfReader

    reader = PdfReader(io.BytesIO(file_bytes))
    pages = []
    for page in reader.pages:
        text = page.extract_text()
        if text:
            pages.append(text)
    return "\n\n".join(pages)


def _extract_docx(file_bytes: bytes) -> str:
    import docx

    doc = docx.Document(io.BytesIO(file_bytes))
    paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
    return "\n\n".join(paragraphs)


def chunk_text(text: str, chunk_size: int = 500, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks by character count."""
    if not text.strip():
        return []

    chunks = []
    start = 0
    while start < len(text):
        end = start + chunk_size
        chunk = text[start:end]

        # Try to break at a sentence or word boundary
        if end < len(text):
            # Look for last period, newline, or space within the chunk
            for sep in ["\n\n", "\n", ". ", " "]:
                last_sep = chunk.rfind(sep)
                if last_sep > chunk_size // 2:
                    chunk = chunk[: last_sep + len(sep)]
                    end = start + len(chunk)
                    break

        chunks.append(chunk.strip())
        start = end - overlap

    return [c for c in chunks if c]


async def process_knowledge_file(
    client: Client,
    file_id: str,
    property_id: str,
    file_bytes: bytes,
    mime_type: str,
    api_key: str,
    file_name: str = "",
) -> dict:
    """Full pipeline: extract text → chunk → embed → update knowledge_files record."""
    try:
        # Extract text
        text = extract_text(file_bytes, mime_type)
        if not text.strip():
            client.table("knowledge_files").update(
                {"content_extracted": True, "chunk_count": 0, "extraction_error": "No text content found"}
            ).eq("id", file_id).execute()
            return {"status": "empty", "chunks": 0}

        # Chunk
        chunks = chunk_text(text)

        # Embed
        count = await embed_knowledge_chunks(
            client, file_id, property_id, chunks, api_key, file_name
        )

        # Update knowledge_files record
        client.table("knowledge_files").update(
            {"content_extracted": True, "chunk_count": count, "extraction_error": None}
        ).eq("id", file_id).execute()

        logger.info(f"Processed knowledge file {file_id}: {count} chunks embedded")
        return {"status": "success", "chunks": count}

    except Exception as e:
        logger.error(f"Failed to process knowledge file {file_id}: {e}")
        client.table("knowledge_files").update(
            {"content_extracted": False, "chunk_count": 0, "extraction_error": str(e)}
        ).eq("id", file_id).execute()
        return {"status": "error", "error": str(e)}

from __future__ import annotations

import io
import logging
import re
from datetime import datetime, timezone

from supabase import Client

from app.services.embedding import embed_knowledge_chunks

logger = logging.getLogger(__name__)


def extract_text(file_bytes: bytes, mime_type: str) -> str:
    """Extract plain text from supported knowledge file types."""
    if mime_type == "application/pdf" or mime_type == "application/x-pdf":
        return _extract_pdf(file_bytes)
    elif (
        mime_type
        == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        or mime_type == "application/msword"
    ):
        return _extract_docx(file_bytes)
    elif mime_type in {"text/html", "application/xhtml+xml"}:
        return _extract_html(file_bytes)
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


def _extract_html(file_bytes: bytes) -> str:
    from bs4 import BeautifulSoup

    html_text = file_bytes.decode("utf-8", errors="replace")
    soup = BeautifulSoup(html_text, "html.parser")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    return soup.get_text(separator="\n", strip=True)


def _is_heading_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return False
    if stripped.startswith("#"):
        return True
    return (
        len(stripped) <= 120
        and stripped.upper() == stripped
        and any(ch.isalpha() for ch in stripped)
    )


def _normalize_heading(line: str) -> str:
    normalized = line.strip().lstrip("#").strip()
    return normalized if normalized else "General"


def _split_large_paragraph(paragraph: str, max_chars: int) -> list[str]:
    if len(paragraph) <= max_chars:
        return [paragraph]

    parts: list[str] = []
    remaining = paragraph.strip()
    while len(remaining) > max_chars:
        candidate = remaining[:max_chars]
        split_at = max(
            candidate.rfind("\n"),
            candidate.rfind(". "),
            candidate.rfind("; "),
            candidate.rfind(", "),
            candidate.rfind(" "),
        )
        if split_at < max_chars // 2:
            split_at = max_chars
        parts.append(remaining[:split_at].strip())
        remaining = remaining[split_at:].strip()

    if remaining:
        parts.append(remaining)
    return [part for part in parts if part]


def chunk_text(
    text: str,
    min_chars: int = 1500,
    max_chars: int = 2500,
    overlap_chars: int = 200,
) -> tuple[list[str], list[str]]:
    """Split text into paragraph-based chunks and keep section headings."""
    if not text.strip():
        return ([], [])

    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_paragraphs = [
        p.strip()
        for p in re.split(r"\n\s*\n+", normalized)
        if p and p.strip()
    ]
    paragraphs: list[str] = []
    for paragraph in raw_paragraphs:
        paragraphs.extend(_split_large_paragraph(paragraph, max_chars))

    base_chunks: list[str] = []
    base_sections: list[str] = []
    current_parts: list[str] = []
    current_length = 0
    active_heading = "General"
    current_heading = active_heading

    for paragraph in paragraphs:
        lines = [line.strip() for line in paragraph.split("\n") if line.strip()]
        heading_line = next((line for line in lines if _is_heading_line(line)), None)
        if heading_line:
            active_heading = _normalize_heading(heading_line)

        extra_len = len(paragraph) + (2 if current_parts else 0)
        should_flush = bool(current_parts) and current_length + extra_len > max_chars
        if should_flush:
            base_chunks.append("\n\n".join(current_parts).strip())
            base_sections.append(current_heading)
            current_parts = []
            current_length = 0
            current_heading = active_heading

        if not current_parts:
            current_heading = active_heading

        current_parts.append(paragraph)
        current_length += extra_len

        if current_length >= min_chars:
            base_chunks.append("\n\n".join(current_parts).strip())
            base_sections.append(current_heading)
            current_parts = []
            current_length = 0
            current_heading = active_heading

    if current_parts:
        base_chunks.append("\n\n".join(current_parts).strip())
        base_sections.append(current_heading)

    chunks: list[str] = []
    sections: list[str] = []
    for i, base_chunk in enumerate(base_chunks):
        if not base_chunk:
            continue
        if i > 0 and overlap_chars > 0:
            overlap = base_chunks[i - 1][-overlap_chars:].strip()
            chunk = f"{overlap}\n\n{base_chunk}" if overlap else base_chunk
        else:
            chunk = base_chunk
        chunks.append(chunk.strip())
        sections.append(base_sections[i] if i < len(base_sections) else "General")

    return chunks, sections


async def process_knowledge_file(
    client: Client,
    file_id: str,
    property_id: str,
    file_bytes: bytes,
    mime_type: str,
    api_key: str,
    file_name: str = "",
    language: str = "en",
    doc_type: str = "general",
    effective_date: str | None = None,
) -> dict:
    """Full pipeline: extract text → chunk → embed → update knowledge_files record."""
    now = datetime.now(timezone.utc).isoformat()
    try:
        client.table("knowledge_files").update(
            {"indexing_status": "in_progress", "updated_at": now}
        ).eq("id", file_id).execute()

        # Extract text
        text = extract_text(file_bytes, mime_type)
        if not text.strip():
            client.table("knowledge_files").update(
                {
                    "content_extracted": True,
                    "chunk_count": 0,
                    "extraction_error": "No text content found",
                    "indexing_status": "error",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ).eq("id", file_id).execute()
            return {"status": "empty", "chunks": 0}

        # Chunk
        chunks, sections = chunk_text(text)

        # Embed
        count = await embed_knowledge_chunks(
            client,
            file_id,
            property_id,
            chunks,
            api_key,
            file_name,
            language=language,
            doc_type=doc_type,
            effective_date=effective_date,
            sections=sections,
        )

        # Update knowledge_files record
        client.table("knowledge_files").update(
            {
                "content_extracted": True,
                "chunk_count": count,
                "extraction_error": None,
                "language": language,
                "doc_type": doc_type,
                "effective_date": effective_date,
                "indexing_status": "indexed",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", file_id).execute()

        logger.info(f"Processed knowledge file {file_id}: {count} chunks embedded")
        return {"status": "success", "chunks": count}

    except Exception as e:
        logger.error(f"Failed to process knowledge file {file_id}: {e}")
        client.table("knowledge_files").update(
            {
                "content_extracted": False,
                "chunk_count": 0,
                "extraction_error": str(e),
                "indexing_status": "error",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        ).eq("id", file_id).execute()
        return {"status": "error", "error": str(e)}

import base64
import io
import logging
from typing import Dict, List, Optional

from app.schemas import InputFile

LOGGER = logging.getLogger(__name__)

TEXT_ENCODINGS = ("utf-8", "utf-16", "latin-1")


def _decode_bytes(content: bytes) -> Optional[str]:
    for encoding in TEXT_ENCODINGS:
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    try:
        return content.decode("latin-1", errors="ignore")
    except Exception:
        return None


def _extract_pdf_text(content: bytes) -> Optional[str]:
    """Extract text from PDF bytes using pypdf."""
    try:
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(content))
        pages = []
        for page in reader.pages:
            text = page.extract_text()
            if text:
                pages.append(text.strip())
        if pages:
            return "\n\n".join(pages)
    except Exception as exc:
        LOGGER.warning("PDF extraction failed: %s", exc)
    return None


def parse_attachments(files: List[InputFile]) -> List[Dict[str, Optional[str]]]:
    normalized: List[Dict[str, Optional[str]]] = []
    for file in files:
        try:
            decoded = base64.b64decode(file.content_base64, validate=True)
        except (ValueError, TypeError):
            continue

        text_content = None
        mime = (file.mime_type or "").lower()

        # Try PDF extraction first
        if mime == "application/pdf" or (file.filename or "").lower().endswith(".pdf"):
            text_content = _extract_pdf_text(decoded)

        # Fall back to text decoding
        if text_content is None:
            text_content = _decode_bytes(decoded)

        normalized.append(
            {
                "filename": file.filename,
                "mime_type": file.mime_type,
                "content_length": len(decoded),
                "text_content": text_content,
            }
        )
        if text_content:
            LOGGER.info("attachment_parsed file=%s mime=%s text_length=%d", file.filename, mime, len(text_content))
        else:
            LOGGER.warning("attachment_no_text file=%s mime=%s size=%d", file.filename, mime, len(decoded))
    return normalized


def attachments_to_text(attachments: List[Dict[str, Optional[str]]]) -> str:
    """Convert parsed attachments into text that can be appended to the LLM prompt."""
    parts = []
    for att in attachments:
        text = att.get("text_content")
        if text:
            filename = att.get("filename", "attachment")
            parts.append("--- Attachment: {0} ---\n{1}".format(filename, text))
    return "\n\n".join(parts)

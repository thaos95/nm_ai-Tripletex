import base64
from typing import Dict, List, Optional

from app.schemas import InputFile

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


def parse_attachments(files: List[InputFile]) -> List[Dict[str, Optional[str]]]:
    normalized: List[Dict[str, Optional[str]]] = []
    for file in files:
        try:
            decoded = base64.b64decode(file.content_base64, validate=True)
        except (ValueError, TypeError):
            continue
        text_preview = _decode_bytes(decoded)
        normalized.append(
            {
                "filename": file.filename,
                "mime_type": file.mime_type,
                "content_length": len(decoded),
                "text_preview": text_preview[:400] if text_preview else None,
            }
        )
    return normalized

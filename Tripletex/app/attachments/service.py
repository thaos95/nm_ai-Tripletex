import base64
from typing import Dict, List, Union

from app.schemas import FilePayload


def decode_files(files: List[FilePayload]) -> List[Dict[str, Union[str, bytes]]]:
    decoded: List[Dict[str, Union[str, bytes]]] = []
    for file in files:
        decoded.append(
            {
                "filename": file.filename,
                "mime_type": file.mime_type,
                "content": base64.b64decode(file.content_base64),
            }
        )
    return decoded


def extract_attachment_text(decoded_files: List[Dict[str, Union[str, bytes]]]) -> str:
    chunks = []
    for file in decoded_files:
        mime_type = str(file["mime_type"])
        content = file["content"]
        if mime_type.startswith("text/") and isinstance(content, bytes):
            try:
                chunks.append(content.decode("utf-8"))
            except UnicodeDecodeError:
                chunks.append(content.decode("latin-1", errors="ignore"))
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())

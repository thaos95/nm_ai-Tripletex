import base64
import re
from typing import Dict, List, Union

from app.schemas import FilePayload


EMAIL_RE = re.compile(r"[\w.\-+]+@[\w.\-]+\.\w+")
ORG_RE = re.compile(r"\b\d{9}\b")
AMOUNT_RE = re.compile(r"\b\d+(?:[.,]\d{1,2})?\b")
DATE_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}\b")


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


def _decode_text_bytes(content: bytes) -> str:
    for encoding in ("utf-8", "utf-16", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("latin-1", errors="ignore")


def _looks_text_like(content: bytes) -> bool:
    if not content:
        return False
    text = content.decode("latin-1", errors="ignore")
    printable = sum(1 for char in text if char.isprintable() or char.isspace())
    return (printable / max(len(text), 1)) >= 0.85


def _extract_pdf_like_text(content: bytes) -> str:
    decoded = content.decode("latin-1", errors="ignore")
    decoded = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f]+", " ", decoded)
    printable = re.findall(r"[0-9A-Za-zÀ-ÿ,.:;@()\/%\-_\s]{8,}", decoded)
    return " ".join(segment.strip() for segment in printable[:80] if segment.strip())


def extract_attachment_text(decoded_files: List[Dict[str, Union[str, bytes]]]) -> str:
    chunks = []
    for file in decoded_files:
        mime_type = str(file["mime_type"])
        content = file["content"]
        if mime_type.startswith("text/") and isinstance(content, bytes):
            chunks.append(_decode_text_bytes(content))
        elif mime_type in {"application/json", "application/xml", "application/csv"} and isinstance(content, bytes):
            chunks.append(_decode_text_bytes(content))
        elif mime_type == "application/pdf" and isinstance(content, bytes):
            extracted = _extract_pdf_like_text(content)
            if extracted:
                chunks.append(extracted)
        elif mime_type == "application/octet-stream" and isinstance(content, bytes) and _looks_text_like(content):
            chunks.append(_decode_text_bytes(content))
    return "\n".join(chunk.strip() for chunk in chunks if chunk.strip())


def summarize_attachment_hints(attachment_text: str) -> str:
    if not attachment_text.strip():
        return ""

    emails = list(dict.fromkeys(EMAIL_RE.findall(attachment_text)))[:3]
    organization_numbers = list(dict.fromkeys(ORG_RE.findall(attachment_text)))[:3]
    dates = list(dict.fromkeys(DATE_RE.findall(attachment_text)))[:3]
    excluded_numbers = set(organization_numbers) | set(dates)
    amounts = [
        value
        for value in dict.fromkeys(AMOUNT_RE.findall(attachment_text))
        if len(value.replace(".", "").replace(",", "")) >= 3 and value not in excluded_numbers and not value.startswith("20")
    ][:5]

    lines = []
    if organization_numbers:
        lines.append("organization_numbers={0}".format(", ".join(organization_numbers)))
    if emails:
        lines.append("emails={0}".format(", ".join(emails)))
    if dates:
        lines.append("dates={0}".format(", ".join(dates)))
    if amounts:
        lines.append("amounts={0}".format(", ".join(amounts)))
    return "\n".join(lines)


def describe_attachments(decoded_files: List[Dict[str, Union[str, bytes]]]) -> str:
    lines = []
    for file in decoded_files:
        lines.append(
            "filename={0}, mime_type={1}".format(
                str(file["filename"]),
                str(file["mime_type"]),
            )
        )
    return "\n".join(lines)

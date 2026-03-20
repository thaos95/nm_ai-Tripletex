import base64

from app.attachments.service import (
    decode_files,
    extract_attachment_text,
    summarize_attachment_hints,
)
from app.schemas import FilePayload


def test_attachment_hints_extract_multiple_amounts_dates_and_org_numbers() -> None:
    files = [
        FilePayload(
            filename="expense.txt",
            mime_type="text/plain",
            content_base64=base64.b64encode(
                "Org.nr 923456781\nDato 2026-03-20\nBelop 1800\nBelop 250\nE-post emma.stone@example.org".encode(
                    "utf-8"
                )
            ).decode("ascii"),
        )
    ]

    decoded = decode_files(files)
    attachment_text = extract_attachment_text(decoded)
    hints = summarize_attachment_hints(attachment_text)

    assert "organization_numbers=923456781" in hints
    assert "dates=2026-03-20" in hints
    assert "emails=emma.stone@example.org" in hints
    assert "amounts=1800, 250" in hints


def test_attachment_text_like_octet_stream_is_still_indexed() -> None:
    files = [
        FilePayload(
            filename="note.bin",
            mime_type="application/octet-stream",
            content_base64=base64.b64encode("Project ERP\nHours 12\nRate 1400 NOK".encode("utf-8")).decode("ascii"),
        )
    ]

    decoded = decode_files(files)
    attachment_text = extract_attachment_text(decoded)

    assert "Hours 12" in attachment_text

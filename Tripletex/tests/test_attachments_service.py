import base64

from app.attachments.service import decode_files, describe_attachments, extract_attachment_text
from app.schemas import FilePayload


def test_decode_files_preserves_metadata_and_decodes_base64() -> None:
    files = [
        FilePayload(
            filename="invoice.txt",
            mime_type="text/plain",
            content_base64=base64.b64encode(b"hello world").decode("ascii"),
        )
    ]

    decoded = decode_files(files)

    assert decoded == [
        {
            "filename": "invoice.txt",
            "mime_type": "text/plain",
            "content": b"hello world",
        }
    ]


def test_extract_attachment_text_reads_utf8_and_latin1_text() -> None:
    decoded_files = [
        {"filename": "note.txt", "mime_type": "text/plain", "content": "Skylagring".encode("utf-8")},
        {"filename": "latin1.txt", "mime_type": "text/plain", "content": "Fakturé".encode("latin-1")},
    ]

    text = extract_attachment_text(decoded_files)

    assert "Skylagring" in text
    assert "Fakturé" in text


def test_extract_attachment_text_extracts_printable_pdf_segments() -> None:
    decoded_files = [
        {
            "filename": "invoice.pdf",
            "mime_type": "application/pdf",
            "content": b"%PDF-1.4 Invoice 845762686 Skylagring Customer Brattli AS",
        }
    ]

    text = extract_attachment_text(decoded_files)

    assert "Invoice 845762686 Skylagring Customer Brattli AS" in text


def test_describe_attachments_lists_metadata_lines() -> None:
    decoded_files = [
        {"filename": "invoice.pdf", "mime_type": "application/pdf", "content": b"pdf"},
        {"filename": "receipt.txt", "mime_type": "text/plain", "content": b"text"},
    ]

    description = describe_attachments(decoded_files)

    assert description.splitlines() == [
        "filename=invoice.pdf, mime_type=application/pdf",
        "filename=receipt.txt, mime_type=text/plain",
    ]

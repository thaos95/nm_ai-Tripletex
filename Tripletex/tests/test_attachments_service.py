import base64

from app.attachments.service import decode_files, describe_attachments, extract_attachment_text, summarize_attachment_hints
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


def test_extract_attachment_text_preserves_extended_latin_from_pdf_like_content() -> None:
    decoded_files = [
        {
            "filename": "invoice.pdf",
            "mime_type": "application/pdf",
            "content": "Faktura Brückentor GmbH Gonçalo Økonomi".encode("latin-1", errors="ignore"),
        }
    ]

    text = extract_attachment_text(decoded_files)

    assert "Brückentor GmbH" in text
    assert "Gonçalo" in text


def test_extract_attachment_text_reads_json_and_octet_stream_when_text_like() -> None:
    decoded_files = [
        {
            "filename": "invoice.json",
            "mime_type": "application/json",
            "content": b'{"customer":"Brattli AS","amount":26450}',
        },
        {
            "filename": "scan.bin",
            "mime_type": "application/octet-stream",
            "content": b"Customer Brattli AS Amount 26450",
        },
    ]

    text = extract_attachment_text(decoded_files)

    assert '"customer":"Brattli AS"' in text
    assert "Customer Brattli AS Amount 26450" in text


def test_summarize_attachment_hints_extracts_key_lookup_signals() -> None:
    hints = summarize_attachment_hints(
        "Customer Brattli AS\nOrg.nr 845762686\npost@brattli.no\nAmount 26450\nDue 2026-03-20"
    )

    assert "organization_numbers=845762686" in hints
    assert "emails=post@brattli.no" in hints
    assert "dates=2026-03-20" in hints
    assert "amounts=26450" in hints


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

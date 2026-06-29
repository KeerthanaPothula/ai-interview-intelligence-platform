"""Document text extraction — supports PDF and DOCX. Heavy deps are lazy-loaded."""

from __future__ import annotations

import logging

from app.core.tracing import get_tracer

logger = logging.getLogger(__name__)
tracer = get_tracer(__name__)

_SUPPORTED_MIME = {
    "application/pdf": "pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "docx",
}


def extract_text_from_pdf(file_path: str) -> str:
    """Extract plain text from a PDF file using pypdf."""
    import pypdf  # type: ignore

    reader = pypdf.PdfReader(file_path)
    pages = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(pages).strip()


def extract_text_from_docx(file_path: str) -> str:
    """Extract plain text from a DOCX file using python-docx."""
    import docx  # type: ignore

    doc = docx.Document(file_path)
    paragraphs = [para.text for para in doc.paragraphs if para.text.strip()]
    return "\n".join(paragraphs).strip()


def extract_text(file_path: str, mime_type: str) -> str:
    """Dispatch to the correct extractor based on mime_type."""
    with tracer.start_as_current_span("resume.extract_text") as span:
        span.set_attribute("document.mime_type", mime_type)
        fmt = _SUPPORTED_MIME.get(mime_type)
        if fmt == "pdf":
            return extract_text_from_pdf(file_path)
        if fmt == "docx":
            return extract_text_from_docx(file_path)
        raise ValueError(f"Unsupported document type: {mime_type}")


def is_supported(mime_type: str) -> bool:
    return mime_type in _SUPPORTED_MIME

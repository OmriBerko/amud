"""HTML-to-PDF. Direction comes from CSS; strings are not pre-reversed."""

from pathlib import Path

from flask import render_template
from weasyprint import HTML

FONT_DIR = Path(__file__).resolve().parent / "static" / "fonts"

DOC_TITLES = {
    "quote": "הצעת מחיר",
    "tax_invoice": "חשבונית מס",
}


def font_face_css() -> str:
    regular = (FONT_DIR / "IBMPlexSansHebrew-Regular.ttf").as_uri()
    bold = (FONT_DIR / "IBMPlexSansHebrew-Bold.ttf").as_uri()
    return f"""
    @font-face {{
        font-family: "Amud Hebrew";
        src: url("{regular}");
        font-weight: 400;
        font-style: normal;
    }}
    @font-face {{
        font-family: "Amud Hebrew";
        src: url("{bold}");
        font-weight: 700;
        font-style: normal;
    }}
    """


def render_document_pdf(payload: dict) -> bytes:
    html = render_template(
        "pdf_document.html",
        font_css=font_face_css(),
        **payload,
    )
    return HTML(string=html, base_url=str(FONT_DIR)).write_pdf()

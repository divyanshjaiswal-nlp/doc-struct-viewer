"""
Showing a document in its own format.

Dispatch is on mime_type via config.MEDIA_TYPE_TO_DOC_FORMAT_MAP, the same map the
pipeline uses. Every file is also sniffed with libmagic and a disagreement with the
database is surfaced rather than hidden: the preprocessor has an entire fallback chain
for exactly this case (main_ehealth.py re-tries with the sniffed type when the
declared one fails), so mime_type does lie sometimes.

One thing deliberately not done: style_sheet is not applied. Despite the .xsl names,
no XSLT exists anywhere in the backend -- the value is a dictionary key selecting an
HL7 section whitelist in workers/xml_to_md/hl7_filters. It is shown as metadata.

What XML *does* need is the other case: an HL7 CDA can carry a base64-encoded PDF in
<nonXMLBody>, so a row whose mime_type is application/xml may really be a PDF.
"""
from __future__ import annotations

import base64
import io
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import streamlit as st
import streamlit.components.v1 as components
from bs4 import BeautifulSoup
from lxml import etree

import config
import store
import styles

# Guards so one enormous document cannot wedge the browser tab.
MAX_TEXT_CHARS = 400_000
MAX_INLINE_BYTES = 64 * 1024 * 1024


def sniff(path: Path) -> str:
    try:
        import magic

        return magic.from_file(str(path), mime=True) or ""
    except Exception:
        return ""


# ── embedded media inside HL7 CDA XML ────────────────────────────────────────
def embedded_media(data: bytes) -> list[dict[str, Any]]:
    """
    Base64 documents wrapped in <component>/<nonXMLBody>, as
    document_preprocessor/extract_from_xml.validate_xml_content finds them. Returns
    [{media_type, data}] -- usually a single PDF.
    """
    try:
        soup = BeautifulSoup(data, "xml")
    except Exception:
        return []

    found: list[dict[str, Any]] = []
    for body in soup.find_all("nonXMLBody"):
        for node in [body, *body.find_all(True)]:
            media_type = node.get("mediaType") or node.get("mediatype")
            if not media_type:
                continue
            text = node.get_text(strip=True)
            if not text:
                continue
            representation = str(node.get("representation") or "").strip().upper()
            try:
                raw = base64.b64decode(text) if representation == "B64" else text.encode("utf-8")
            except Exception:
                continue
            if raw:
                found.append({"media_type": str(media_type).strip(), "data": raw})
    return found


# ── small helpers ────────────────────────────────────────────────────────────
def _read(path: Path) -> bytes:
    return path.read_bytes()


def _text(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


def _clip(text: str) -> tuple[str, bool]:
    if len(text) <= MAX_TEXT_CHARS:
        return text, False
    return text[:MAX_TEXT_CHARS], True


def _download(path: Path, row: dict[str, Any], widget_key: str) -> None:
    try:
        size = path.stat().st_size
    except OSError:
        return
    if size > MAX_INLINE_BYTES:
        st.caption(f"{size / 1e6:.0f} MB on disk — too large to offer inline: `{path}`")
        return
    st.download_button(
        "Save a copy to my computer",
        data=_read(path),
        file_name=store.filename_of(row),
        mime=config.media_type_for(row),
        key=f"dl-{widget_key}",
        width="stretch",
    )


def _panel(height: int | None = None):
    return st.container(height=height or config.PANEL_HEIGHT, border=True)


# ── per-format renderers ─────────────────────────────────────────────────────
def _show_pdf(data: bytes, widget_key: str) -> None:
    """
    st.pdf is a real scrollable viewer, but it is a thin wrapper over the separate
    streamlit-pdf component and raises if that is missing -- and streamlit-pdf 2.x
    needs a newer Streamlit than 1.57, so the pin in requirements.txt matters. When
    it is unavailable for any reason, fall back to page images through PyMuPDF, which
    is a dependency either way.
    """
    try:
        st.pdf(data, height=config.PANEL_HEIGHT)
        return
    except Exception as exc:
        st.warning(f"Interactive PDF viewer unavailable ({exc}). Showing rendered pages.")
    _show_pdf_pages(data, widget_key)


def _show_pdf_pages(data: bytes, widget_key: str) -> None:
    """One page at a time, rasterised with PyMuPDF."""
    try:
        import fitz
    except ImportError:
        st.error("Install streamlit-pdf or PyMuPDF to view PDFs.")
        return

    try:
        doc = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:
        st.error(f"Could not open the PDF: {exc}")
        return

    with doc:
        total = doc.page_count
        controls = st.columns([1, 1])
        page_no = 1
        if total > 1:
            with controls[0]:
                page_no = st.number_input(
                    f"Page (1–{total})",
                    min_value=1,
                    max_value=total,
                    value=1,
                    key=f"pdfpage-{widget_key}",
                )
        with controls[1]:
            zoom = st.select_slider(
                "Zoom", [1.0, 1.5, 2.0, 3.0], value=1.5, key=f"pdfzoom-{widget_key}"
            )
        try:
            pixmap = doc.load_page(int(page_no) - 1).get_pixmap(
                matrix=fitz.Matrix(zoom, zoom)
            )
        except Exception as exc:
            st.error(f"Could not render page {page_no}: {exc}")
            return
        st.image(pixmap.tobytes("png"), width="stretch")


def _show_html(data: bytes) -> None:
    # an iframe, so the document's own CSS cannot leak into the Streamlit page --
    # and a white canvas injected first, since clinical HTML assumes paper and would
    # otherwise render black ink on the dark theme
    components.html(
        styles.HTML_CANVAS + _text(data), height=config.PANEL_HEIGHT, scrolling=True
    )


def _show_plain(data: bytes) -> None:
    body, clipped = _clip(_text(data))
    st.html(styles.paper_text(body, config.PANEL_HEIGHT))
    if clipped:
        st.caption(f"Showing the first {MAX_TEXT_CHARS:,} characters. Download for the rest.")


def _show_source(data: bytes, language: str) -> None:
    body, clipped = _clip(_text(data))
    with _panel():
        st.code(body, language=language, line_numbers=True)
    if clipped:
        st.caption(f"Showing the first {MAX_TEXT_CHARS:,} characters. Download for the rest.")


def _pretty_xml(data: bytes) -> bytes:
    try:
        parser = etree.XMLParser(recover=True, huge_tree=True)
        tree = etree.fromstring(data, parser=parser)
        if tree is None:
            return data
        return etree.tostring(tree, pretty_print=True, encoding="utf-8")
    except Exception:
        return data


def _xml_narrative(data: bytes) -> str:
    """
    Readable text out of an XML document. BeautifulSoup with the xml parser, the same
    entry point workers/xml_to_md/xml_parser.py uses before its HL7 handling.
    """
    try:
        soup = BeautifulSoup(data, "xml")
    except Exception:
        return _text(data)
    lines = [line.strip() for line in soup.get_text("\n").splitlines()]
    return "\n".join(line for line in lines if line)


def _show_xml(path: Path, data: bytes, row: dict[str, Any], widget_key: str) -> None:
    media = embedded_media(data)
    if media:
        item = media[0]
        fmt = config.doc_format(item["media_type"]) or "BIN"
        st.info(
            f"This XML wraps a base64 **{fmt}** document in `<nonXMLBody>` "
            f"({item['media_type']}) — showing that."
        )
        # keep the extracted document beside its container so a Save picks it up
        extracted = store.embedded_sibling(path, fmt.lower())
        if not extracted.is_file():
            try:
                extracted.write_bytes(item["data"])
            except OSError:
                pass

        embedded_tab, source_tab = st.tabs(["Embedded document", "XML source"])
        with embedded_tab:
            if fmt == "PDF":
                _show_pdf(item["data"], f"{widget_key}-embedded")
            elif fmt == "HTML":
                _show_html(item["data"])
            elif fmt in ("TIFF", "JPEG", "PNG"):
                _show_image_bytes(item["data"], widget_key)
            else:
                _show_plain(item["data"])
            if extracted.is_file():
                st.download_button(
                    f"Save the embedded {fmt.lower()}",
                    data=item["data"],
                    file_name=extracted.name,
                    mime=item["media_type"],
                    key=f"dl-embedded-{widget_key}",
                )
        with source_tab:
            _show_source(_pretty_xml(data), "xml")
        return

    source_tab, text_tab = st.tabs(["Source", "Text"])
    with source_tab:
        _show_source(_pretty_xml(data), "xml")
    with text_tab:
        body, clipped = _clip(_xml_narrative(data))
        st.html(styles.paper_text(body, config.PANEL_HEIGHT))
        if clipped:
            st.caption("Truncated.")


def _show_rtf(path: Path, data: bytes) -> None:
    """
    pandoc converts to HTML rather than markdown, so the result lands on the same
    white sheet as any other rendered document and keeps its tables and emphasis --
    markdown would have flattened both.
    """
    rendered = None
    error = None
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "out.html"
        try:
            result = subprocess.run(
                ["pandoc", str(path), "-f", "rtf", "-t", "html", "-o", str(out)],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode == 0 and out.is_file():
                rendered = out.read_text(encoding="utf-8", errors="replace")
            else:
                error = (result.stderr or result.stdout or "").strip()
        except FileNotFoundError:
            error = "pandoc is not installed, so the RTF can only be shown as source."

    rendered_tab, source_tab = st.tabs(["Rendered", "Source"])
    with rendered_tab:
        if rendered:
            components.html(
                styles.HTML_CANVAS + rendered,
                height=config.PANEL_HEIGHT,
                scrolling=True,
            )
        else:
            st.warning(error or "pandoc produced nothing.")
    with source_tab:
        _show_source(data, "text")


def _show_image_bytes(data: bytes, widget_key: str) -> None:
    try:
        from PIL import Image
    except ImportError:
        st.warning("Pillow is not installed, so images cannot be rendered.")
        return

    try:
        image = Image.open(io.BytesIO(data))
    except Exception as exc:
        st.error(f"Could not open the image: {exc}")
        return

    frames = getattr(image, "n_frames", 1)
    index = 0
    if frames > 1:
        index = st.number_input(
            f"Page (1–{frames})",
            min_value=1,
            max_value=frames,
            value=1,
            key=f"frame-{widget_key}",
        ) - 1
        image.seek(index)

    buffer = io.BytesIO()
    frame = image if image.mode in ("RGB", "L") else image.convert("RGB")
    frame.save(buffer, format="PNG")
    st.image(buffer.getvalue(), width="stretch")


def _show_unknown(path: Path, data: bytes, sniffed: str) -> None:
    st.warning(
        "No renderer for this document type"
        + (f" (libmagic says `{sniffed}`)" if sniffed else "")
        + " — download it to open it locally."
    )
    with st.expander("First bytes"):
        st.code(repr(data[:512]))


# ── entry point ──────────────────────────────────────────────────────────────
def show(path: Path, row: dict[str, Any]) -> None:
    """Render one document, chosen by its declared format unless overridden."""
    widget_key = store.doc_id_of(row) or path.name
    declared = config.row_format(row)
    sniffed = sniff(path)
    sniffed_format = config.doc_format(sniffed)

    fmt = declared
    if sniffed_format and sniffed_format != declared:
        st.warning(
            f"The database says **{declared}** (`{row.get('mime_type')}`) but the file "
            f"looks like **{sniffed_format}** (`{sniffed}`)."
        )
        if st.checkbox(
            f"Render as {sniffed_format} instead",
            value=True,
            key=f"sniff-{widget_key}",
        ):
            fmt = sniffed_format

    try:
        data = _read(path)
    except OSError as exc:
        st.error(f"Could not read the local copy: {exc}")
        return

    _download(path, row, widget_key)

    if fmt == "PDF":
        _show_pdf(data, widget_key)
    elif fmt == "XML":
        _show_xml(path, data, row, widget_key)
    elif fmt == "HTML":
        _show_html(data)
    elif fmt == "TXT":
        _show_plain(data)
    elif fmt == "RTF":
        _show_rtf(path, data)
    elif fmt in ("TIFF", "JPEG", "PNG"):
        _show_image_bytes(data, widget_key)
    else:
        _show_unknown(path, data, sniffed)

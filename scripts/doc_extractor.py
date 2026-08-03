"""Extract and render AKN XML documents as structured HTML.

Two entry points:
  extract_article_html   — only the relevant article
  extract_full_doc_html  — the full document; target article gets id="target-article"
"""

from __future__ import annotations

import re
from pathlib import Path

from lxml import etree

AKN_NS = "http://docs.oasis-open.org/legaldocml/ns/akn/3.0"

# Tags whose subtrees are skipped during text extraction (footnotes, metadata…)
_SKIP_TAGS = {"authorialNote", "meta", "identification", "references", "publication"}
# Tags that create section headings
_SECTION_TAGS = {
    "title", "chapter", "section", "subchapter", "division", "part", "tome",
    # Canadian/New Zealand crossheadings group provisions without numbering
    "hcontainer",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def extract_article_html(local_path: str, eid: str, supporting_span: str) -> str:
    root, err = _parse(local_path)
    if err:
        return err
    art = _target_article(root, eid, supporting_span)
    if art is None:
        return '<p class="doc-error">Could not locate the relevant section.</p>'
    return _render_article(art, supporting_span, is_target=True)


def extract_full_doc_html(local_path: str, eid: str, supporting_span: str) -> str:
    root, err = _parse(local_path)
    if err:
        return err
    target_eid = _target_article(root, eid, supporting_span)
    target_eid = target_eid.get("eId", "") if target_eid is not None else ""

    parts: list[str] = []
    preface  = root.find(f".//{{{AKN_NS}}}preface")
    preamble = root.find(f".//{{{AKN_NS}}}preamble")
    body     = root.find(f".//{{{AKN_NS}}}body")

    if preface  is not None: parts.append(_render_preface(preface))
    if preamble is not None: parts.append(_render_preamble(preamble))
    if body     is not None: parts.append(_render_body(body, target_eid, supporting_span))
    return "".join(parts)


def find_pdf_path(local_path: str) -> str | None:
    p = Path(local_path)
    if "wipo" not in str(p):
        return None
    short = re.sub(r"^(\d{4}_)", "", p.stem)
    short = re.sub(r"_clean$", "", short)
    pdf = Path("data/wipo/pdf") / f"trt_{short}_001en.pdf"
    return str(pdf) if pdf.exists() else None


# ---------------------------------------------------------------------------
# Finders
# ---------------------------------------------------------------------------

def _parse(local_path: str) -> tuple[etree._Element | None, str | None]:
    path = Path(local_path)
    if not path.exists():
        return None, '<p class="doc-error">Document not found.</p>'
    try:
        return etree.parse(str(path)).getroot(), None
    except Exception as e:
        return None, f'<p class="doc-error">Parse error: {e}</p>'


def _find_eid(root: etree._Element, eid: str) -> etree._Element | None:
    if not eid:
        return None
    for el in root.iter():
        if el.get("eId") == eid:
            return el
    return None


def _is_leaf_provision(el: etree._Element) -> bool:
    """Return True if el is a leaf legal provision (has paragraph/content but no nested articles/sections)."""
    has_content = False
    for child in el:
        local = etree.QName(child.tag).localname
        if local in ("paragraph", "content", "blockList", "list", "subsection"):
            has_content = True
        if local in ("article", "section", "prov"):
            return False
    return has_content


def _ancestor_provision(el: etree._Element) -> etree._Element | None:
    """Walk up the tree to find the nearest article or leaf-section ancestor."""
    node = el
    while node is not None:
        local = etree.QName(node.tag).localname
        if local == "article":
            return node
        if local in ("section", "prov") and _is_leaf_provision(node):
            return node
        node = node.getparent()
    return None


def _provision_containing(root: etree._Element, span: str) -> etree._Element | None:
    if not span:
        return None
    for el in root.iter():
        local = etree.QName(el.tag).localname
        if local == "article" or (local in ("section", "prov") and _is_leaf_provision(el)):
            if span in _collect(el):
                return el
    return None


def _target_article(root: etree._Element, eid: str, span: str) -> etree._Element | None:
    hit = _find_eid(root, eid)
    prov = _ancestor_provision(hit) if hit is not None else None
    return prov if prov is not None else _provision_containing(root, span)


# ---------------------------------------------------------------------------
# Document-level renderers
# ---------------------------------------------------------------------------

def _render_preface(el: etree._Element) -> str:
    text = _collect(el).strip()
    return f'<div class="doc-preface"><p>{_e(text)}</p></div>' if text else ""


def _render_preamble(el: etree._Element) -> str:
    parts = ['<div class="doc-preamble"><div class="preamble-label">Preamble</div>']
    for child in el:
        if etree.QName(child.tag).localname == "p":
            text = _collect(child).strip()
            if text:
                parts.append(f"<p>{_e(text)}</p>")
    parts.append("</div>")
    return "".join(parts)


def _render_body(body_el: etree._Element, target_eid: str, span: str) -> str:
    parts: list[str] = []
    for child in body_el:
        local = etree.QName(child.tag).localname
        if local == "article":
            is_target = child.get("eId") == target_eid
            parts.append(_render_article(child, span, is_target))
        elif local in _SECTION_TAGS:
            if _is_leaf_provision(child):
                is_target = child.get("eId") == target_eid
                parts.append(_render_article(child, span, is_target))
            else:
                parts.append(_render_section(child, target_eid, span, depth=1))
    return "".join(parts)


def _render_section(el: etree._Element, target_eid: str, span: str, depth: int) -> str:
    num_el     = el.find(f"{{{AKN_NS}}}num")
    heading_el = el.find(f"{{{AKN_NS}}}heading")
    num_text     = _collect(num_el).strip()     if num_el     is not None else ""
    heading_text = _collect(heading_el).strip() if heading_el is not None else ""

    parts = [f'<div class="section-block depth-{depth}">']
    if num_text or heading_text:
        parts.append(f'<div class="section-header depth-{depth}">')
        if num_text:
            parts.append(f'<span class="section-num">{_e(num_text)}</span>')
        if heading_text:
            parts.append(f'<span class="section-heading">{_e(heading_text)}</span>')
        parts.append("</div>")

    for child in el:
        local = etree.QName(child.tag).localname
        if local == "article":
            parts.append(_render_article(child, span, child.get("eId") == target_eid))
        elif local in _SECTION_TAGS:
            if _is_leaf_provision(child):
                parts.append(_render_article(child, span, child.get("eId") == target_eid))
            else:
                parts.append(_render_section(child, target_eid, span, depth + 1))

    parts.append("</div>")
    return "".join(parts)


# ---------------------------------------------------------------------------
# Article renderer
# ---------------------------------------------------------------------------

def _render_article(article_el: etree._Element, span: str, is_target: bool) -> str:
    css   = "article-block target-article" if is_target else "article-block"
    attrs = 'id="target-article"' if is_target else ""

    num_el     = article_el.find(f"{{{AKN_NS}}}num")
    heading_el = article_el.find(f"{{{AKN_NS}}}heading")
    num_text     = _collect(num_el).strip()     if num_el     is not None else ""
    heading_text = _collect(heading_el).strip() if heading_el is not None else ""

    parts = [f'<div class="{css}" {attrs}>']
    parts.append('<div class="article-header">')
    if num_text:
        parts.append(f'<span class="article-num">{_e(num_text)}</span>')
    if heading_text:
        parts.append(f'<span class="article-heading">{_e(heading_text)}</span>')
    parts.append("</div>")

    # UK AKN uses <subsection> where continental drafting uses <paragraph>
    paragraphs = article_el.findall(f"{{{AKN_NS}}}paragraph") or article_el.findall(
        f"{{{AKN_NS}}}subsection"
    )
    if paragraphs:
        for para_el in paragraphs:
            parts.append(_render_paragraph(para_el, span))
    else:
        content_el = article_el.find(f".//{{{AKN_NS}}}content")
        if content_el is not None:
            parts.append(f'<div class="para-content">{_render_content(content_el, span)}</div>')

    parts.append("</div>")
    return "".join(parts)


def _render_paragraph(para_el: etree._Element, span: str) -> str:
    num_el   = para_el.find(f"{{{AKN_NS}}}num")
    num_text = _collect(num_el).strip() if num_el is not None else ""

    # EU AKN nests the text one level deeper: <paragraph><subparagraph><content>
    content_els = para_el.findall(f"{{{AKN_NS}}}content") or para_el.findall(
        f".//{{{AKN_NS}}}content"
    )
    if not content_els:
        return ""

    has_span  = bool(span) and any(span in _collect(c) for c in content_els)
    row_class = "para-row span-row" if has_span else "para-row"
    body      = "".join(_render_content(c, span) for c in content_els)

    return (
        f'<div class="{row_class}">'
        f'<span class="para-num">{_e(num_text)}</span>'
        f'<div class="para-content">{body}</div>'
        f"</div>"
    )


def _render_content(content_el: etree._Element, span: str) -> str:
    parts: list[str] = []
    for child in content_el:
        local = etree.QName(child.tag).localname
        if local == "p":
            parts.append(f'<p>{_highlight(_e(_collect(child).strip()), span)}</p>')
        elif local in ("blockList", "list"):
            parts.append(_render_blocklist(child, span))
        elif local not in _SKIP_TAGS:
            text = _collect(child).strip()
            if text:
                parts.append(f'<p>{_highlight(_e(text), span)}</p>')
    return "".join(parts)


def _render_blocklist(bl_el: etree._Element, span: str) -> str:
    parts: list[str] = []
    intro = bl_el.find(f"{{{AKN_NS}}}listIntroduction")
    if intro is not None:
        text = _collect(intro).strip()
        if text:
            parts.append(f'<p>{_highlight(_e(text), span)}</p>')

    parts.append('<ul class="item-list">')
    for item in bl_el.findall(f"{{{AKN_NS}}}item"):
        num_label, content = _parse_item(item)
        p_html = _highlight(_e(content), span)
        parts.append(
            f'<li>'
            f'<span class="item-num">{_e(num_label)}</span>'
            f'{p_html}'
            f'</li>'
        )
    parts.append("</ul>")

    # The sentence that closes a list ("… shall be exempted from …") is normative
    # text and must not be dropped.
    wrap_up = bl_el.find(f"{{{AKN_NS}}}listWrapUp")
    if wrap_up is not None:
        text = _collect(wrap_up).strip()
        if text:
            parts.append(f'<p>{_highlight(_e(text), span)}</p>')

    return "".join(parts)


def _parse_item(item_el: etree._Element) -> tuple[str, str]:
    """Return (num_label, content) for a list item.

    Handles both the standard structure (<num> + <p>) and the non-standard
    Swiss/national-act structure where content lives as the tail of an
    <authorialNote> inside <num>.
    """
    p_el   = item_el.find(f"{{{AKN_NS}}}p")
    num_el = item_el.find(f"{{{AKN_NS}}}num")

    if p_el is not None:
        # Standard: <num>a.</num><p>content</p>
        label   = _collect(num_el).strip() if num_el is not None else ""
        content = _collect(p_el).strip()
        return label, content

    if num_el is not None:
        # Non-standard: content embedded as tail of a skip-tag inside <num>
        # e.g. <num>a<sup>bis</sup>.<authorialNote>…</authorialNote> CONTENT</num>
        label_chunks:   list[str] = []
        content_chunks: list[str] = []
        hit_skip = False

        if num_el.text:
            label_chunks.append(num_el.text)

        for child in num_el:
            local = etree.QName(child.tag).localname
            if local in _SKIP_TAGS:
                hit_skip = True
                if child.tail:
                    content_chunks.append(child.tail)
            elif not hit_skip:
                # inline formatting (sup, b, …) — part of the label
                label_chunks.append(_collect(child))
                if child.tail:
                    label_chunks.append(child.tail)
            else:
                content_chunks.append(_collect(child))
                if child.tail:
                    content_chunks.append(child.tail)

        label   = "".join(label_chunks).strip()
        content = "".join(content_chunks).strip()
        return label, content

    # Fallback: no <num>, no <p>
    return "", _collect(item_el).strip()


# ---------------------------------------------------------------------------
# Text helpers
# ---------------------------------------------------------------------------

def _collect(el: etree._Element | None) -> str:
    """Concatenate all text in el, skipping _SKIP_TAGS subtrees."""
    if el is None:
        return ""
    chunks: list[str] = []
    _walk(el, chunks)
    return "".join(chunks)


def _walk(el: etree._Element, out: list[str]) -> None:
    if etree.QName(el.tag).localname in _SKIP_TAGS:
        return          # skip subtree; tail is handled by the parent loop
    if el.text:
        out.append(el.text)
    for child in el:
        _walk(child, out)
        if child.tail:
            out.append(child.tail)


def _highlight(html_text: str, span: str) -> str:
    if not span:
        return html_text
    escaped = _e(span)
    if escaped in html_text:
        return html_text.replace(escaped, f'<mark class="highlight">{escaped}</mark>', 1)
    return html_text


def _e(text: str) -> str:
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )

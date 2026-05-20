"""Render the viz spec as an HTML page and open it in the browser.

Usage:
    python3 scripts/render_viz.py "Which economic rights does Germany recognize?"
"""

from __future__ import annotations

import argparse
import tempfile
import webbrowser
from pathlib import Path

from scripts.orchestrator import orchestrate


# ---------------------------------------------------------------------------
# HTML templates per visualization_type
# ---------------------------------------------------------------------------

_CSS = """
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: system-ui, sans-serif;
    background: #f4f4f5;
    color: #18181b;
    padding: 2rem;
}
h1 { font-size: 1.1rem; font-weight: 600; color: #52525b; margin-bottom: 1.5rem; }
.card {
    background: #fff;
    border-radius: 12px;
    box-shadow: 0 1px 4px rgba(0,0,0,.1);
    padding: 1.75rem 2rem;
    max-width: 680px;
}
.card-title { font-size: .8rem; font-weight: 600; text-transform: uppercase;
              letter-spacing: .08em; color: #71717a; margin-bottom: .75rem; }
.big-value {
    font-size: 2.4rem; font-weight: 700; color: #2563eb;
    margin-bottom: 1.25rem; line-height: 1.15;
}
.badge-yes { display:inline-block; background:#dcfce7; color:#16a34a;
             font-size:2rem; font-weight:700; padding:.4rem 1.2rem;
             border-radius:8px; margin-bottom:1.25rem; }
.badge-no  { display:inline-block; background:#fee2e2; color:#dc2626;
             font-size:2rem; font-weight:700; padding:.4rem 1.2rem;
             border-radius:8px; margin-bottom:1.25rem; }
.rights-list { list-style: none; margin-bottom: 1.25rem; }
.rights-list li { padding: .35rem 0; border-bottom: 1px solid #f4f4f5;
                  display:flex; align-items:center; gap:.5rem; }
.rights-list li::before { content:"⚖️"; font-size:.9rem; }
.divider { border: none; border-top: 1px solid #e4e4e7; margin: 1.25rem 0; }
.ref { font-size: .8rem; color: #71717a; margin-bottom: .75rem; }
.ref a { color: #2563eb; text-decoration: none; }
.ref a:hover { text-decoration: underline; }
.passage { font-size: .9rem; color: #3f3f46; line-height: 1.6;
           background: #fafafa; border-left: 3px solid #2563eb;
           padding: .6rem .9rem; border-radius: 0 6px 6px 0; }
.passage u { text-decoration-color: #2563eb; text-underline-offset: 3px;
             font-weight: 600; }
"""


def _ref_html(source: dict) -> str:
    title = source.get("title", "")
    uri = source.get("uri", "")
    ref = source.get("reference", "")
    link = f'<a href="{uri}">{title}</a>' if uri else title
    return f'<p class="ref">{link} &mdash; {ref}</p>'


def _passage_html(highlight: dict) -> str:
    passage = highlight.get("passage", "")
    span = highlight.get("supporting_span", "")
    if span and span in passage:
        passage = passage.replace(span, f"<u>{span}</u>", 1)
    return f'<p class="passage">{passage}</p>'


def _rule_card(result: dict) -> str:
    spec = result["viz_spec"]
    display = spec["rule"]["display_value"]
    return f"""
    <div class="card">
        <p class="card-title">{spec['title']}</p>
        <div class="big-value">{display}</div>
        <hr class="divider">
        {_ref_html(spec['source_document'])}
        {_passage_html(spec['highlight'])}
    </div>"""


def _rights_list(result: dict) -> str:
    spec = result["viz_spec"]
    passage = result["evidence"].get("passage", "")
    # split on commas, semicolons, or "and"
    import re
    raw = re.split(r"[,;]|\band\b", passage)
    items = [r.strip(" .") for r in raw if r.strip(" .")]
    items_html = "".join(f"<li>{i}</li>" for i in items if i)
    return f"""
    <div class="card">
        <p class="card-title">{spec['title']}</p>
        <ul class="rights-list">{items_html}</ul>
        <hr class="divider">
        {_ref_html(spec['source_document'])}
        {_passage_html(spec['highlight'])}
    </div>"""


def _yes_no_exception(result: dict) -> str:
    spec = result["viz_spec"]
    value = spec["rule"]["normalized_value"]
    badge_class = "badge-yes" if value == "yes" else "badge-no"
    label = "Yes" if value == "yes" else "No"
    return f"""
    <div class="card">
        <p class="card-title">{spec['title']}</p>
        <div class="{badge_class}">{label}</div>
        <hr class="divider">
        {_ref_html(spec['source_document'])}
        {_passage_html(spec['highlight'])}
    </div>"""


def _document_highlight(result: dict) -> str:
    spec = result["viz_spec"]
    return f"""
    <div class="card">
        <p class="card-title">{spec['title']}</p>
        <hr class="divider">
        {_ref_html(spec['source_document'])}
        {_passage_html(spec['highlight'])}
    </div>"""


_RENDERERS = {
    "rule_card": _rule_card,
    "rights_list": _rights_list,
    "yes_no_exception": _yes_no_exception,
    "document_highlight": _document_highlight,
}


def render_html(question: str, result: dict) -> str:
    viz_type = result["viz_spec"]["visualization_type"]
    renderer = _RENDERERS.get(viz_type, _document_highlight)
    body = renderer(result)
    answer_md = result["answer"].replace("\n", "<br>")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <title>ReMeP Demo</title>
  <style>{_CSS}</style>
</head>
<body>
  <h1>Q: {question}</h1>
  {body}
  <br>
  <div class="card" style="font-size:.85rem;line-height:1.7;color:#3f3f46;">
    <p class="card-title">Full Answer</p><br>
    {answer_md}
  </div>
</body>
</html>"""


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("question", help="User's legal question.")
    args = parser.parse_args()

    result = orchestrate(args.question)
    html = render_html(args.question, result)

    with tempfile.NamedTemporaryFile(
        suffix=".html", delete=False, mode="w", encoding="utf-8"
    ) as f:
        f.write(html)
        path = f.name

    webbrowser.open(f"file://{path}")
    print(f"Opened: {path}")


if __name__ == "__main__":
    main()

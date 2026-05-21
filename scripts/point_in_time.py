"""Point-in-time navigation for versioned AKN documents.

Given a jurisdiction and a target date, returns the AKN file that was in
force at that date.  Currently supports Italy (68 versions 1941–2025).
Other jurisdictions fall back to their single canonical file.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

# Map jurisdiction code → sorted list of (valid_from, file_path)
# Built lazily on first call.
_VERSION_INDEX: dict[str, list[tuple[date, Path]]] = {}

_VERSIONS_DIRS: dict[str, Path] = {
    "IT": Path("data/countries/italy/copyright/versions"),
}

# Filename pattern: ..._VIGENZA_YYYY-MM-DD_VN.xml  or _ORIGINALE_V0.xml
_VIGENZA_RE = re.compile(r"VIGENZA_(\d{4}-\d{2}-\d{2})_V\d+\.xml$")
_ORIG_RE    = re.compile(r"ORIGINALE_V0\.xml$")


def _build_index(code: str) -> list[tuple[date, Path]]:
    vdir = _VERSIONS_DIRS.get(code)
    if not vdir or not vdir.exists():
        return []

    entries: list[tuple[date, Path]] = []
    for f in vdir.glob("*.xml"):
        m = _VIGENZA_RE.search(f.name)
        if m:
            entries.append((date.fromisoformat(m.group(1)), f))
        elif _ORIG_RE.search(f.name):
            entries.append((date(1941, 7, 16), f))

    return sorted(entries, key=lambda x: x[0])


def _get_index(code: str) -> list[tuple[date, Path]]:
    if code not in _VERSION_INDEX:
        _VERSION_INDEX[code] = _build_index(code)
    return _VERSION_INDEX[code]


def get_version_at(code: str, target: date | str) -> Path | None:
    """Return the AKN file in force for *code* on *target* date.

    Returns the latest version whose valid_from ≤ target.
    Returns None if the jurisdiction has no version index.
    """
    if isinstance(target, str):
        target = date.fromisoformat(target)

    index = _get_index(code)
    if not index:
        return None

    result = None
    for valid_from, path in index:
        if valid_from <= target:
            result = path
        else:
            break
    return result


def list_versions(code: str) -> list[dict]:
    """Return all available versions for *code* as a list of dicts."""
    return [
        {"date": str(d), "file": str(p.name)}
        for d, p in _get_index(code)
    ]

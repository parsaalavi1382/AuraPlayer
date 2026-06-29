"""
Splits a raw artist tag into a list of individual artists,
using the user's configured separators (Settings.artist_separators).

Two real-world cases this has to handle:

1. A single delimited string (most common on macOS/Linux taggers):
     "Daft Punk & Pharrell Williams feat. Nile Rodgers"
     -> ["Daft Punk", "Pharrell Williams", "Nile Rodgers"]

2. A genuine multi-value tag list (common from Windows tools writing
   Vorbis comments or MP4 atoms -- each artist is its own list entry,
   sometimes with a trailing separator on the last one):
     ["Travis Scott", "Future", "2 Chainz;"]
     -> ["Travis Scott", "Future", "2 Chainz"]

   Each individual list entry is ALSO run through separator-splitting,
   since a tool could write ["Future; 2 Chainz"] as one combined entry
   inside an otherwise multi-value list.
"""

from __future__ import annotations

import re


def _split_one_string(raw: str, pattern: str) -> list[str]:
    """Split a single string on the separator pattern, stripping
    whitespace and any leftover separator characters (e.g. a trailing
    ';' left dangling after a tagger joins a list with semicolons).
    """
    if not pattern:
        cleaned = raw.strip().rstrip(";").strip()
        return [cleaned] if cleaned else []

    parts = re.split(pattern, raw, flags=re.IGNORECASE)
    cleaned = []
    for p in parts:
        p = p.strip().rstrip(";").strip()
        if p:
            cleaned.append(p)
    return cleaned


def split_artists(raw, separators: list[str]) -> list[str]:
    """
    raw: either a string ("A & B") or a list of strings (["A", "B", "C;"]),
    as produced by mutagen for different tag formats/taggers.
    """
    if not raw:
        return ["Unknown Artist"]

    # Sort separators longest-first so multi-char ones like "feat." aren't
    # partially consumed by a shorter overlapping one before regex sees them.
    sorted_seps = sorted(separators, key=len, reverse=True)
    escaped = [re.escape(sep) for sep in sorted_seps if sep]
    pattern = "|".join(escaped) if escaped else ""

    if isinstance(raw, (list, tuple)):
        # Multi-value tag: split EACH entry (handles a tool that writes
        # one combined entry inside an otherwise-multi-value list), then
        # flatten, preserving order and dropping empties/duplicates.
        result = []
        for entry in raw:
            if not entry:
                continue
            result.extend(_split_one_string(str(entry), pattern))
    else:
        result = _split_one_string(str(raw), pattern)

    # De-duplicate while preserving first-seen order (in case a name
    # appears twice across entries, e.g. a tagger duplicating a feature).
    seen = set()
    deduped = []
    for name in result:
        key = name.lower()
        if key not in seen:
            seen.add(key)
            deduped.append(name)

    return deduped if deduped else ["Unknown Artist"]

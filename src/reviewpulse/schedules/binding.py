"""Rows bind to drawn elements by tag: 'D-12', 'd12' and 'D 012' are the same key (annotate.text_classify.tag_key)."""

from __future__ import annotations

from .model import Candidate
from .values import entity_key

KIND_CLASSES = {"doors": {"door", "opening"}, "windows": {"window", "opening"}, "fixtures": {"fixture"}}


def bind_to_elements(candidates: list[Candidate], elements) -> dict:
    """Set `element_id` on the candidates whose entity tag is the tag of a drawn element (an object with `id`, `tag`, `cls`).
    A tag drawn on two elements binds to neither (the drawing is ambiguous). Returns counts for the audit."""
    by_tag: dict[str, list] = {}
    for el in elements:
        if getattr(el, "tag", None):
            by_tag.setdefault(entity_key(el.tag), []).append(el)
    bound = ambiguous = unmatched = 0
    seen_tags: set[str] = set()
    for c in candidates:
        if not c.entity_tag:
            continue
        els = [e for e in by_tag.get(c.entity_tag, []) if e.cls in KIND_CLASSES.get(c.entity_kind, {e.cls})]
        if len(els) == 1:
            c.element_id = els[0].id
            bound += 1
        elif len(els) > 1:
            ambiguous += 1
        else:
            unmatched += 1
        seen_tags.add(c.entity_tag)
    return {"bound": bound, "ambiguous": ambiguous, "unmatched": unmatched, "tags": len(seen_tags)}


def bind_to_tags(candidates: list[Candidate], tags: dict[str, str]) -> int:
    """Same, for a plain map of tag text to element id."""
    keyed = {entity_key(t): i for t, i in tags.items()}
    n = 0
    for c in candidates:
        if c.entity_tag in keyed:
            c.element_id = keyed[c.entity_tag]
            n += 1
    return n

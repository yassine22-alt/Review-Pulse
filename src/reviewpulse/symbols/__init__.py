"""Symbols found by their legend: vector shapes in plan views matched to the drawn symbol of each legend entry, bound to rooms,
counted, and offered as fact candidates. See docs/progress/M25_symbols_by_legend.md."""

from .bind import Room, candidates, counts, place, room_of
from .descriptor import Descriptor, describe, distance, signature_hash
from .find import Detection, Exemplar, FindResult, build_exemplars, find_instances
from .primitives import Stroke, strokes_of_page

__all__ = ["Descriptor", "Detection", "Exemplar", "FindResult", "Room", "Stroke", "build_exemplars", "candidates", "counts",
           "describe", "distance", "find_instances", "place", "room_of", "signature_hash", "strokes_of_page"]

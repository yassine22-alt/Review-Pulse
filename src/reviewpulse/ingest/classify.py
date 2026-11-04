"""R1 - Ingest and classify.

Detects the file type by extension and magic bytes and, for every page, decides
whether it is vector, raster or mixed. Writes ``runs/<id>/sheets.json``.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel

MM_PER_PT = 25.4 / 72

# Mode thresholds (tune on the gold set)
VECTOR_MIN_PATHS = 200
VECTOR_MAX_IMAGE_COVER = 0.5
RASTER_MIN_IMAGE_COVER = 0.8
RASTER_MAX_PATHS = 50
OUTLINE_TEXT_MAX_WORDS = 20

FileType = Literal["pdf", "dxf", "dwg", "svg", "image"]


class IngestError(Exception):
    """A file that cannot be read; the CLI exits with code 2 and one line."""


class SheetStub(BaseModel):
    index: int
    source_file: str
    file_type: FileType
    page: int = 0
    mode: Literal["vector", "raster", "mixed"]
    width_mm: float | None = None
    height_mm: float | None = None
    rotation: int = 0
    n_path_items: int = 0
    n_words: int = 0
    image_cover: float = 0.0
    dpi: int | None = None
    layers: list[str] = []
    warnings: list[str] = []


IMAGE_EXT = {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}


def detect_type(path: Path) -> FileType:
    if not path.exists():
        raise IngestError(f"file not found: {path}")
    head = path.read_bytes()[:64]
    ext = path.suffix.lower()
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"AC10"):
        return "dwg"
    if head[:8] == b"\x89PNG\r\n\x1a\n" or head[:3] == b"\xff\xd8\xff" or head[:4] in (b"II*\x00", b"MM\x00*"):
        return "image"
    if ext == ".svg" or b"<svg" in path.read_bytes()[:2048]:
        return "svg"
    if ext == ".dxf" or b"SECTION" in head:
        return "dxf"
    if ext in IMAGE_EXT:
        return "image"
    if ext == ".pdf":
        raise IngestError(f"{path.name}: has a .pdf extension but no PDF header (corrupt?)")
    raise IngestError(f"{path.name}: unsupported file type")


def decide_mode(n_path_items: int, image_cover: float) -> Literal["vector", "raster", "mixed"]:
    if n_path_items >= VECTOR_MIN_PATHS and image_cover < VECTOR_MAX_IMAGE_COVER:
        return "vector"
    if image_cover >= RASTER_MIN_IMAGE_COVER and n_path_items < RASTER_MAX_PATHS:
        return "raster"
    return "mixed"


def _inspect_pdf(path: Path) -> list[SheetStub]:
    import pymupdf

    try:
        doc = pymupdf.open(path)
    except Exception as e:  # noqa: BLE001 - any parser error is an ingest error
        raise IngestError(f"{path.name}: cannot open PDF ({e})") from e
    if doc.needs_pass:
        raise IngestError(f"{path.name}: encrypted PDF, password required")
    if doc.page_count == 0:
        raise IngestError(f"{path.name}: PDF has zero pages")
    from .pdf_backend import pdf_layers

    layers, _hidden = pdf_layers(doc)
    stubs = []
    for i, page in enumerate(doc):
        warnings = []
        drawings = page.get_drawings()
        n_items = sum(len(d["items"]) for d in drawings)
        n_words = len(page.get_text("words"))
        area = page.rect.width * page.rect.height or 1.0
        cover = 0.0
        for img in page.get_images(full=True):
            for r in page.get_image_rects(img[0]):
                r = r & page.rect
                cover += max(r.width, 0) * max(r.height, 0)
        cover = min(cover / area, 1.0)
        if n_words < OUTLINE_TEXT_MAX_WORDS and n_items >= VECTOR_MIN_PATHS:
            small_closed = sum(1 for d in drawings if d.get("closePath") and d["rect"].width < 10 and d["rect"].height < 10)
            if small_closed > 100:
                warnings.append("text_as_outlines: few words but many small closed paths; OCR the rendered page")
        stubs.append(SheetStub(
            index=i, source_file=str(path), file_type="pdf", page=i,
            mode=decide_mode(n_items, cover),
            width_mm=round(page.rect.width * MM_PER_PT, 2), height_mm=round(page.rect.height * MM_PER_PT, 2),
            rotation=page.rotation, n_path_items=n_items, n_words=n_words, image_cover=round(cover, 3),
            layers=layers, warnings=warnings,
        ))
    return stubs


def _inspect_dxf(path: Path, file_type: FileType) -> list[SheetStub]:
    from .dxf_reader import open_dxf

    doc, warnings = open_dxf(path)
    msp = doc.modelspace()
    n = len(msp)
    if n == 0:
        warnings.append("model space is empty")
    return [SheetStub(index=0, source_file=str(path), file_type=file_type, mode="vector",
                      n_path_items=n, layers=[layer.dxf.name for layer in doc.layers], warnings=warnings)]


def _inspect_image(path: Path) -> list[SheetStub]:
    from PIL import Image

    try:
        with Image.open(path) as im:
            w, h = im.size
            dpi = im.info.get("dpi", (None, None))[0]
    except Exception as e:  # noqa: BLE001
        raise IngestError(f"{path.name}: cannot read image ({e})") from e
    warnings = []
    if not dpi:
        dpi = 300
        warnings.append("no dpi in metadata, assuming 300")
    dpi = int(round(float(dpi)))
    return [SheetStub(index=0, source_file=str(path), file_type="image", mode="raster", dpi=dpi,
                      width_mm=round(w / dpi * 25.4, 2), height_mm=round(h / dpi * 25.4, 2),
                      image_cover=1.0, warnings=warnings)]


def inspect_file(path: str | Path) -> list[SheetStub]:
    path = Path(path)
    ftype = detect_type(path)
    if ftype == "pdf":
        return _inspect_pdf(path)
    if ftype in ("dxf", "dwg"):
        return _inspect_dxf(path, ftype)
    if ftype == "svg":
        return [SheetStub(index=0, source_file=str(path), file_type="svg", mode="vector")]
    return _inspect_image(path)


def write_sheets(stubs: list[SheetStub], run_dir: Path) -> Path:
    run_dir.mkdir(parents=True, exist_ok=True)
    out = run_dir / "sheets.json"
    out.write_text(json.dumps([s.model_dump() for s in stubs], indent=1), encoding="utf-8")
    return out


def read_sheets(run_dir: Path) -> list[SheetStub]:
    data = json.loads((run_dir / "sheets.json").read_text(encoding="utf-8"))
    return [SheetStub.model_validate(d) for d in data]

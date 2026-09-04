"""Page rasteriser (design doc M2.9). Renders pages to PNG at 150 DPI for the
drill-down viewer. Cached under data/rasters/<doc_id>/page-N.png."""
from __future__ import annotations

from pathlib import Path


def raster_page(page, doc_id: str, page_no: int, out_root: Path, dpi: int = 150) -> Path:
    out_dir = out_root / doc_id
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"page-{page_no}.png"
    if not out_path.exists():
        pix = page.get_pixmap(dpi=dpi)
        pix.save(str(out_path))
    return out_path

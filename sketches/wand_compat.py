"""Patch wand.image.Image to satisfy SketchValueProtocol.

Import this module before using WandImage as a step output. The patch is
idempotent — safe to import from multiple sketches.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from wand.image import Image as WandImage

if TYPE_CHECKING:
    pass


def _to_bytes(self: WandImage, mode: Literal["dev", "build"]) -> bytes:
    """Serialize to PNG bytes. Dev: no compression. Build: max compression."""
    with self.clone() as copy:
        copy.options["png:compression-level"] = "9" if mode == "build" else "0"
        return copy.make_blob("png")


if not hasattr(WandImage, "_sketchbook_patched"):
    WandImage.extension = "png"  # type: ignore[attr-defined]
    WandImage.kind = "image"  # type: ignore[attr-defined]
    WandImage.to_bytes = _to_bytes  # type: ignore[attr-defined]
    WandImage._sketchbook_patched = True  # type: ignore[attr-defined]

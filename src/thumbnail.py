"""Thumbnail engine — custom illustrated thumbnail for the topic."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from typing import Tuple, List
from PIL import Image, ImageDraw, ImageFont

THUMBNAIL_DIR = os.path.join("output", "thumbnails")
THUMB_SIZE = (1280, 720)


@dataclass
class ThumbnailResult:
    topic_id: str
    title: str
    file_path: str = ""
    size: Tuple[int, int] = THUMB_SIZE
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ThumbnailResult":
        return cls(
            topic_id=d["topic_id"], title=d["title"],
            file_path=d.get("file_path", ""),
            size=tuple(d.get("size", THUMB_SIZE)),
            issues=d.get("issues", []),
        )


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    ]
    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def _draw_text(d: ImageDraw.ImageDraw, x, y, text, size=40, color=(240, 230, 210), bold=False, anchor="la", max_width=None):
    f = _font(size, bold)
    if max_width:
        while f.getlength(text) > max_width and size > 14:
            size -= 2
            f = _font(size, bold)
    d.text((x, y), text, font=f, fill=color, anchor=anchor)


class ThumbnailEngine:
    """Generates a custom illustrated thumbnail for the video topic."""

    def __init__(self, size: Tuple[int, int] = THUMB_SIZE,
                 thumbnail_dir: str = THUMBNAIL_DIR) -> None:
        self.size = size
        self.thumbnail_dir = thumbnail_dir
        os.makedirs(self.thumbnail_dir, exist_ok=True)

    def generate(self, topic_id: str, title: str) -> ThumbnailResult:
        result = ThumbnailResult(topic_id=topic_id, title=title)
        W, H = self.size
        img = Image.new("RGB", self.size, (34, 28, 22))  # sepia bg
        d = ImageDraw.Draw(img)

        # vignette border
        d.rectangle([0, 0, W, H], fill=(34, 28, 22))
        d.rectangle([30, 30, W - 30, H - 30], outline=(210, 190, 150), width=4)

        # Draw a stylized engine cylinder + piston (focal point)
        cx = W * 0.45
        cy = H * 0.55
        # cylinder block
        d.rectangle([cx - 190, cy - 240, cx + 190, cy + 180], fill=(210, 190, 150), outline=(40, 34, 28), width=5)
        d.line([cx - 190, cy - 240, cx + 190, cy - 240], fill=(40, 34, 28), width=6)
        d.line([cx - 190, cy + 180, cx + 190, cy + 180], fill=(40, 34, 28), width=6)
        # piston
        d.rectangle([cx - 160, cy - 30, cx + 160, cy + 30], fill=(240, 230, 210), outline=(40, 34, 28), width=4)
        d.ellipse([cx - 18, cy - 18, cx + 18, cy + 18], fill=(180, 120, 60), outline=(40, 34, 28), width=3)
        # crankshaft
        d.ellipse([cx - 28, cy + 110, cx + 28, cy + 170], fill=(240, 230, 210), outline=(40, 34, 28), width=4)
        d.line([cx - 60, cy + 140, cx, cy], fill=(40, 34, 28), width=7)
        d.line([cx + 60, cy + 140, cx, cy], fill=(40, 34, 28), width=7)
        # valves
        d.rectangle([cx - 140, cy - 120, cx - 90, cy - 95], fill=(100, 130, 90), outline=(40, 34, 28), width=3)
        d.rectangle([cx + 90, cy - 120, cx + 140, cy - 95], fill=(150, 90, 70), outline=(40, 34, 28), width=3)
        # spark
        d.line([cx - 10, cy - 165, cx + 10, cy - 145], fill=(240, 230, 210), width=4)
        d.line([cx - 10, cy - 145, cx + 10, cy - 165], fill=(240, 230, 210), width=4)

        # motion arrows
        d.line([cx, cy - 40, cx, cy - 120], fill=(180, 120, 60), width=6)
        d.line([cx, cy - 120, cx - 12, cy - 108], fill=(180, 120, 60), width=6)
        d.line([cx, cy - 120, cx + 12, cy - 108], fill=(180, 120, 60), width=6)

        # title text — large, readable, right side
        _draw_text(d, W * 0.55, H * 0.35, "How a Four-Stroke", size=56, color=(240, 230, 210), bold=True,
                   max_width=W * 0.42)
        _draw_text(d, W * 0.55, H * 0.44, "Engine Works", size=56, color=(240, 230, 210), bold=True,
                   max_width=W * 0.42)
        _draw_text(d, W * 0.55, H * 0.56, "Intake  Compression  Power  Exhaust", size=30,
                   color=(210, 190, 150))

        # subtitle
        _draw_text(d, W * 0.55, H * 0.70, "How machines work", size=26, color=(170, 150, 110))

        out_path = os.path.join(self.thumbnail_dir, f"{topic_id}_thumbnail.jpg")
        img.save(out_path, quality=90)
        result.file_path = out_path
        result.issues = self._validate(result)
        self._save(result)
        return result

    def _validate(self, result: ThumbnailResult) -> List[str]:
        issues: List[str] = []
        if not result.file_path or not os.path.exists(result.file_path):
            issues.append("Thumbnail file missing.")
            return issues
        try:
            with Image.open(result.file_path) as im:
                if im.size != self.size:
                    issues.append(f"Size {im.size} != expected {self.size}.")
                if im.mode not in ("RGB", "RGBA"):
                    issues.append(f"Unexpected mode {im.mode}.")
                im.verify()
        except Exception as exc:  # noqa: BLE001
            issues.append(f"Thumbnail corrupt: {exc}")
        return issues

    def _save(self, result: ThumbnailResult) -> None:
        path = os.path.join(self.thumbnail_dir, f"{result.topic_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

    def load(self, topic_id: str) -> ThumbnailResult:
        path = os.path.join(self.thumbnail_dir, f"{topic_id}.json")
        if not os.path.exists(path):
            return ThumbnailResult(topic_id=topic_id, title="")
        with open(path, "r", encoding="utf-8") as f:
            return ThumbnailResult.from_dict(json.load(f))

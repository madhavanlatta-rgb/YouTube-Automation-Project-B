"""Animation engine — Pillow-based 2D technical animation."""

from __future__ import annotations

import json
import math
import os
import subprocess
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Tuple
from PIL import Image, ImageDraw, ImageFont

ANIMATION_DIR = os.path.join("output", "animation")

# Vintage sepia technical palette.
SEPIA_BG = (34, 28, 22)
SEPIA_PAPER = (210, 190, 150)
INK = (40, 34, 28)
DARK_PENCIL = (70, 60, 50)
WHITE = (240, 230, 210)
ACCENT = (180, 120, 60)   # copper accent
MUTED_RED = (150, 90, 70)
MUTED_GREEN = (100, 130, 90)

W, H = 1280, 720


@dataclass
class AnimationScene:
    index: int
    title: str
    frames: List[str]  # paths to rendered frame images
    duration_seconds: float
    fps: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class AnimationResult:
    topic_id: str
    scenes: List[AnimationScene] = field(default_factory=list)
    video_file: str = ""
    total_duration_seconds: float = 0.0
    fps: int = 24
    resolution: Tuple[int, int] = (W, H)
    issues: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AnimationResult":
        return cls(
            topic_id=d["topic_id"],
            scenes=[AnimationScene(**s) for s in d.get("scenes", [])],
            video_file=d.get("video_file", ""),
            total_duration_seconds=d.get("total_duration_seconds", 0.0),
            fps=d.get("fps", 24),
            resolution=tuple(d.get("resolution", [W, H])),
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


def _draw_text(d: ImageDraw.ImageDraw, x, y, text, size=28, color=INK, bold=False, anchor="la"):
    f = _font(size, bold)
    d.text((x, y), text, font=f, fill=color, anchor=anchor)


class EngineAnimation:
    """Renders 2D technical animation of a four-stroke engine cycle."""

    def __init__(self, fps: int = 24, resolution: Tuple[int, int] = (W, H)) -> None:
        self.fps = fps
        self.resolution = resolution
        self.cx = resolution[0] * 0.42
        self.cy = resolution[1] * 0.55
        self.crank_r = 110
        self.rod_l = 220

    # ----- geometry -----
    def _piston_position(self, angle_deg: float) -> float:
        """Vertical offset of piston pin from TDC (positive = down)."""
        a = math.radians(angle_deg)
        r = self.crank_r
        l = self.rod_l
        sin_a = math.sin(a)
        under = l * l - (r * sin_a) ** 2
        if under < 0:
            under = 0
        return r * math.cos(a) + math.sqrt(under)

    def _crank_pin(self, angle_deg: float) -> Tuple[float, float]:
        a = math.radians(angle_deg)
        return (self.cx + self.crank_r * math.cos(a),
                self.cy + self.crank_r * math.sin(a))

    # ----- drawing primitives -----
    def _draw_cylinder(self, d: ImageDraw.ImageDraw) -> None:
        x0 = self.cx - 150
        x1 = self.cx + 150
        y_top = self.cy - 300
        y_bot = self.cy + 180
        d.rectangle([x0, y_top, x1, y_bot], fill=SEPIA_PAPER, outline=INK, width=3)
        d.line([x0, y_top, x1, y_top], fill=INK, width=4)   # deck
        d.line([x0, y_bot, x1, y_bot], fill=INK, width=4)   # base
        d.line([x0 + 10, y_top, x0 + 10, y_bot], fill=DARK_PENCIL, width=2)
        d.line([x1 - 10, y_top, x1 - 10, y_bot], fill=DARK_PENCIL, width=2)

    def _draw_piston(self, d: ImageDraw.ImageDraw, pin_y: float, stroke_phase: str) -> None:
        x0 = self.cx - 130
        x1 = self.cx + 130
        d.rectangle([x0, pin_y - 45, x1, pin_y + 45], fill=WHITE, outline=INK, width=3)
        d.line([x0, pin_y, x1, pin_y], fill=DARK_PENCIL, width=2)
        d.ellipse([self.cx - 14, pin_y - 14, self.cx + 14, pin_y + 14], fill=ACCENT, outline=INK, width=2)
        d.rectangle([x0 + 8, pin_y - 38, x1 - 8, pin_y - 30], fill=None, outline=INK, width=2)
        d.rectangle([x0 + 8, pin_y + 30, x1 - 8, pin_y + 38], fill=None, outline=INK, width=2)

    def _draw_crankshaft(self, d: ImageDraw.ImageDraw, angle_deg: float) -> None:
        d.ellipse([self.cx - 22, self.cy - 22, self.cx + 22, self.cy + 22], fill=WHITE, outline=INK, width=3)
        px, py = self._crank_pin(angle_deg)
        d.ellipse([px - 16, py - 16, px + 16, py + 16], fill=ACCENT, outline=INK, width=3)
        d.line([self.cx - 40, self.cy, px, py], fill=INK, width=6)
        d.line([self.cx + 40, self.cy, px, py], fill=INK, width=6)
        self._arrow(d, self.cx + 70, self.cy - 70, self.cx + 100, self.cy - 40, color=ACCENT)

    def _draw_connecting_rod(self, d: ImageDraw.ImageDraw, angle_deg: float, pin_y: float) -> None:
        px, py = self._crank_pin(angle_deg)
        d.line([self.cx, pin_y, px, py], fill=INK, width=8)

    def _draw_valves(self, d: ImageDraw.ImageDraw, intake_open: bool, exhaust_open: bool) -> None:
        ix = self.cx - 115
        iy = self.cy - 150
        ex = self.cx + 115
        ey = self.cy - 150
        d.line([ix, iy - 40, ix, iy], fill=INK, width=5)
        d.line([ex, ey - 40, ex, ey], fill=INK, width=5)
        if intake_open:
            d.rectangle([ix - 30, iy - 45, ix + 8, iy - 35], fill=MUTED_GREEN, outline=INK, width=3)
        else:
            d.rectangle([ix - 30, iy - 38, ix + 8, iy - 30], fill=MUTED_GREEN, outline=INK, width=3)
        if exhaust_open:
            d.rectangle([ex - 8, ey - 45, ex + 30, ey - 35], fill=MUTED_RED, outline=INK, width=3)
        else:
            d.rectangle([ex - 8, ey - 38, ex + 30, ey - 30], fill=MUTED_RED, outline=INK, width=3)
        _draw_text(d, ix - 55, iy - 70, "INTAKE", size=20, color=MUTED_GREEN, bold=True)
        _draw_text(d, ex + 10, ey - 70, "EXHAUST", size=20, color=MUTED_RED, bold=True)

    def _draw_spark(self, d: ImageDraw.ImageDraw, fire: bool) -> None:
        sx = self.cx
        sy = self.cy - 160
        if fire:
            d.line([sx - 12, sy - 10, sx + 12, sy + 10], fill=WHITE, width=3)
            d.line([sx - 12, sy + 10, sx + 12, sy - 10], fill=WHITE, width=3)
            d.ellipse([sx - 6, sy - 6, sx + 6, sy + 6], fill=WHITE)
        _draw_text(d, sx + 20, sy - 30, "SPARK", size=18, color=ACCENT, bold=True)

    def _draw_labels(self, d: ImageDraw.ImageDraw) -> None:
        _draw_text(d, self.cx - 170, self.cy - 290, "PISTON", size=22, color=INK, bold=True)
        _draw_text(d, self.cx + 160, self.cy + 200, "CRANKSHAFT", size=22, color=INK, bold=True)

    def _arrow(self, d, x0, y0, x1, y1, color=INK, width=4):
        d.line([x0, y0, x1, y1], fill=color, width=width)
        import math as _m
        ang = _m.atan2(y1 - y0, x1 - x0)
        size = 12
        d.line([x1, y1, x1 - size * _m.cos(ang - 0.5), y1 - size * _m.sin(ang - 0.5)], fill=color, width=width)
        d.line([x1, y1, x1 - size * _m.cos(ang + 0.5), y1 - size * _m.sin(ang + 0.5)], fill=color, width=width)

    def render_scene(self, scene_index: int, title: str, phase: str,
                     angle_deg: float, intake_open: bool, exhaust_open: bool,
                     spark: bool, out_path: str, caption: str = "") -> str:
        """Render a single frame for a stroke phase."""
        img = Image.new("RGB", self.resolution, SEPIA_BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, self.resolution[0], self.resolution[1]], fill=SEPIA_BG)
        d.rectangle([20, 20, self.resolution[0] - 20, self.resolution[1] - 20],
                    outline=SEPIA_PAPER, width=2)

        pin_y = self.cy + self._piston_position(angle_deg) - 60

        self._draw_cylinder(d)
        self._draw_valves(d, intake_open, exhaust_open)
        self._draw_spark(d, spark)
        self._draw_connecting_rod(d, angle_deg, pin_y)
        self._draw_piston(d, pin_y, phase)
        self._draw_crankshaft(d, angle_deg)
        self._draw_labels(d)

        _draw_text(d, 60, 40, title, size=34, color=WHITE, bold=True)
        if caption:
            _draw_text(d, 60, self.resolution[1] - 60, caption, size=26, color=SEPIA_PAPER)

        _draw_text(d, self.resolution[0] - 220, 40, phase.upper(), size=24, color=ACCENT, bold=True)

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        img.save(out_path, quality=92)
        return out_path

    def render_stroke_sequence(self, topic_id: str, stroke_name: str,
                               duration_seconds: float = 2.0,
                               intake_open: bool = False,
                               exhaust_open: bool = False,
                               spark: bool = False,
                               caption: str = "") -> List[str]:
        """Render a short fixed loop (1s) for one stroke; stretched to duration in build()."""
        out_dir = os.path.join(ANIMATION_DIR, topic_id, stroke_name)
        os.makedirs(out_dir, exist_ok=True)
        loop_frames = 24  # 1 second @ 24fps, looped
        paths: List[str] = []
        titles = {
            "intake": "Intake Stroke",
            "compression": "Compression Stroke",
            "power": "Power Stroke",
            "exhaust": "Exhaust Stroke",
        }
        title = titles.get(stroke_name, stroke_name.title())
        for i in range(loop_frames):
            angle = (i / max(loop_frames - 1, 1)) * 360.0
            path = os.path.join(out_dir, f"frame_{i:03d}.png")
            self.render_scene(
                scene_index=i, title=title, phase=stroke_name,
                angle_deg=angle, intake_open=intake_open,
                exhaust_open=exhaust_open, spark=spark,
                out_path=path, caption=caption,
            )
            paths.append(path)
        return paths

    def render_title_card(self, topic_id: str, text: str, out_path: str, duration_seconds: float = 2.0) -> List[str]:
        out_dir = os.path.join(ANIMATION_DIR, topic_id, "title")
        os.makedirs(out_dir, exist_ok=True)
        img = Image.new("RGB", self.resolution, SEPIA_BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, self.resolution[0], self.resolution[1]], fill=SEPIA_BG)
        d.rectangle([20, 20, self.resolution[0] - 20, self.resolution[1] - 20],
                    outline=SEPIA_PAPER, width=2)
        _draw_text(d, 60, self.resolution[1] // 2 - 40, text, size=44, color=WHITE, bold=True)
        _draw_text(d, 60, self.resolution[1] // 2 + 40, "How machines and technology work",
                   size=26, color=SEPIA_PAPER)
        path = os.path.join(out_dir, "frame_000.png")
        img.save(path, quality=92)
        return [path]

    def render_conclusion_card(self, topic_id: str, text: str, out_path: str, duration_seconds: float = 2.0) -> List[str]:
        return self.render_title_card(topic_id, text, out_path, duration_seconds)


class AnimationEngine:
    """Builds the full animation video from scene directions."""

    def __init__(self, fps: int = 24, resolution: Tuple[int, int] = (W, H),
                 animation_dir: str = ANIMATION_DIR) -> None:
        self.fps = fps
        self.resolution = resolution
        self.animation_dir = animation_dir
        self.renderer = EngineAnimation(fps=fps, resolution=resolution)
        os.makedirs(self.animation_dir, exist_ok=True)

    def build(self, topic_id: str, script, scene_durations: Optional[dict] = None) -> AnimationResult:
        """Build the full animation video, matching narration scene durations."""
        result = AnimationResult(topic_id=topic_id, fps=self.fps, resolution=self.resolution)
        scene_durations = scene_durations or {}
        scene_videos: List[str] = []
        scene_durs: List[float] = []

        def dur_for(index: int, default: float) -> float:
            return float(scene_durations.get(index, default))

        scene_defs: List[tuple] = []

        # Title card (scene 1)
        title_dur = dur_for(1, 1.5)
        scene_defs.append((1, "Title", None, title_dur, None, None, None, None, "intro"))

        stroke_map = {
            4: ("intake", True, False, False, "Intake: piston down, mixture in."),
            5: ("compression", False, False, False, "Compression: both valves closed, mixture squeezed."),
            6: ("power", False, False, True, "Power: spark ignites, piston driven down."),
            7: ("exhaust", False, True, False, "Exhaust: piston up, burned gas out."),
        }

        for scene in script.scenes:
            if scene.index == 1:
                continue
            if scene.index in stroke_map:
                stroke, io, eo, sp, cap = stroke_map[scene.index]
                d = dur_for(scene.index, 4.0)
                scene_defs.append((scene.index, scene.title, stroke, d, io, eo, sp, cap, "stroke"))
            else:
                d = dur_for(scene.index, 4.0)
                scene_defs.append((scene.index, scene.title, None, d, None, None, None, None, "generic"))

        # Conclusion card
        concl_dur = dur_for(99, 1.5)
        scene_defs.append((99, "Conclusion", None, concl_dur, None, None, None, None, "conclusion"))

        for (idx, title, stroke, d, io, eo, sp, cap, kind) in scene_defs:
            scene_video = os.path.join(
                self.animation_dir, topic_id, f"scene_{idx:03d}.mp4")
            os.makedirs(os.path.dirname(scene_video), exist_ok=True)
            if kind == "stroke":
                frames = self.renderer.render_stroke_sequence(
                    topic_id, stroke, duration_seconds=1.0,
                    intake_open=bool(io), exhaust_open=bool(eo), spark=bool(sp),
                    caption=cap,
                )
                self._encode_looped(frames, d, scene_video)
            elif kind == "intro":
                frames = self.renderer.render_title_card(
                    topic_id, title,
                    os.path.join(self.animation_dir, topic_id, "title", "title.png"),
                    duration_seconds=d,
                )
                self._encode_looped(frames, d, scene_video)
            elif kind == "conclusion":
                frames = self.renderer.render_conclusion_card(
                    topic_id, "Intake, compression, power, exhaust.",
                    os.path.join(self.animation_dir, topic_id, "conclusion", "conclusion.png"),
                    duration_seconds=d,
                )
                self._encode_looped(frames, d, scene_video)
            else:  # generic
                frames = self._generic_frame(topic_id, type("S", (), {
                    "title": title, "narration": ""})(), d)
                self._encode_looped(frames, d, scene_video)

            result.scenes.append(AnimationScene(
                index=idx, title=title, frames=frames,
                duration_seconds=d, fps=self.fps,
            ))
            scene_videos.append(scene_video)
            scene_durs.append(d)

        result.total_duration_seconds = sum(scene_durs)

        # Concat scene videos into final animation.
        result.video_file = os.path.join(self.animation_dir, f"{topic_id}_animation.mp4")
        self._concat_videos(scene_videos, result.video_file)

        result.issues = self._validate(result)
        self._save(result)
        return result

    def _generic_frame(self, topic_id: str, scene, duration_seconds: float) -> List[str]:
        """Render a single keyframe; stretched to duration_seconds in _encode_looped."""
        idx = getattr(scene, "index", 0)
        out_dir = os.path.join(self.animation_dir, topic_id, f"scene{idx}")
        os.makedirs(out_dir, exist_ok=True)
        img = Image.new("RGB", self.resolution, SEPIA_BG)
        d = ImageDraw.Draw(img)
        d.rectangle([0, 0, self.resolution[0], self.resolution[1]], fill=SEPIA_BG)
        d.rectangle([20, 20, self.resolution[0] - 20, self.resolution[1] - 20],
                    outline=SEPIA_PAPER, width=2)
        _draw_text(d, 60, self.resolution[1] // 2 - 50, getattr(scene, "title", "Scene"),
                   size=40, color=WHITE, bold=True)
        _draw_text(d, 60, self.resolution[1] // 2 + 10,
                   getattr(scene, "narration", "")[:90], size=26, color=SEPIA_PAPER)
        path = os.path.join(out_dir, "frame_000.png")
        img.save(path, quality=92)
        return [path]

    def _encode_looped(self, frames: List[str], target_seconds: float, output: str) -> None:
        """Encode frames stretched to exactly target_seconds."""
        if not frames:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 f"color=c=221c16:size={W}x{H}:duration={target_seconds}:r={self.fps}",
                 output], capture_output=True, check=True,
            )
            return
        # Single still image: loop it for the full duration.
        if len(frames) == 1:
            subprocess.run(
                ["ffmpeg", "-y", "-loop", "1", "-i", os.path.abspath(frames[0]),
                 "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
                 "-preset", "ultrafast", "-r", str(self.fps), "-t", f"{target_seconds:.6f}",
                 "-frames:v", str(int(target_seconds * self.fps) + 1),
                 output], capture_output=True, check=True,
            )
            return
        # Multi-frame loop: concat with per-frame durations.
        list_file = output + ".txt"
        per_frame = target_seconds / len(frames)
        with open(list_file, "w", encoding="utf-8") as f:
            for fp in frames:
                f.write(f"file '{os.path.abspath(fp)}'\n")
                f.write(f"duration {per_frame:.6f}\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
             "-vsync", "cfr", "-r", str(self.fps),
             "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "23",
             "-preset", "ultrafast",
             output], capture_output=True, check=True,
        )
        os.remove(list_file)

    def _concat_videos(self, videos: List[str], output: str) -> None:
        if not videos:
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i",
                 f"color=c=221c16:size={W}x{H}:duration=1:r={self.fps}",
                 output], capture_output=True, check=True,
            )
            return
        list_file = output + ".txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for vp in videos:
                f.write(f"file '{os.path.abspath(vp)}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
             "-c", "copy", output], capture_output=True, check=True,
        )
        os.remove(list_file)

    def _validate(self, result: AnimationResult) -> List[str]:
        issues: List[str] = []
        if not result.video_file or not os.path.exists(result.video_file):
            issues.append("Animation video file missing.")
        if result.total_duration_seconds <= 0:
            issues.append("Animation duration is zero.")
        if not result.scenes:
            issues.append("No animation scenes.")
        return issues

    def _save(self, result: AnimationResult) -> None:
        path = os.path.join(self.animation_dir, f"{result.topic_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

    def load(self, topic_id: str) -> Optional[AnimationResult]:
        path = os.path.join(self.animation_dir, f"{topic_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return AnimationResult.from_dict(json.load(f))

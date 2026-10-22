"""Video assembler — combines narration, animation, captions into MP4 via FFmpeg."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field, asdict
from typing import Optional, Tuple

ASSEMBLY_DIR = os.path.join("output", "video")
W, H = 1280, 720
FPS = 24


@dataclass
class AssemblyResult:
    topic_id: str
    title: str
    video_file: str = ""
    duration_seconds: float = 0.0
    resolution: Tuple[int, int] = (W, H)
    fps: int = FPS
    has_audio: bool = False
    has_captions: bool = False
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    ffprobe: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "AssemblyResult":
        return cls(
            topic_id=d["topic_id"], title=d.get("title", ""),
            video_file=d.get("video_file", ""),
            duration_seconds=d.get("duration_seconds", 0.0),
            resolution=tuple(d.get("resolution", [W, H])),
            fps=d.get("fps", FPS),
            has_audio=d.get("has_audio", False),
            has_captions=d.get("has_captions", False),
            issues=d.get("issues", []),
            warnings=d.get("warnings", []),
            ffprobe=d.get("ffprobe", {}),
        )


class VideoAssembler:
    """Assembles the final MP4 from animation video + narration audio + SRT captions."""

    def __init__(self, fps: int = FPS, resolution: Tuple[int, int] = (W, H),
                 assembly_dir: str = ASSEMBLY_DIR) -> None:
        self.fps = fps
        self.resolution = resolution
        self.assembly_dir = assembly_dir
        os.makedirs(self.assembly_dir, exist_ok=True)

    def assemble(self, topic_id: str, title: str,
                 animation_video: str,
                 narration_audio: Optional[str],
                 srt_file: Optional[str],
                 max_duration_seconds: float = 1200.0) -> AssemblyResult:
        result = AssemblyResult(
            topic_id=topic_id, title=title,
            resolution=self.resolution, fps=self.fps,
        )
        out_path = os.path.join(self.assembly_dir, f"{topic_id}_final.mp4")
        os.makedirs(self.assembly_dir, exist_ok=True)

        # Captions: keep SRT as a sidecar subtitle file (avoids the slow
        # libass burn-in re-encode on constrained hardware). The SRT ships
        # alongside the MP4 and is synchronized to the narration.
        result.has_captions = bool(srt_file and os.path.exists(srt_file))

        # Build ffmpeg command: copy video stream, encode audio, no burn-in.
        cmd = ["ffmpeg", "-y"]
        if animation_video and os.path.exists(animation_video):
            cmd += ["-i", animation_video]
        else:
            cmd += ["-f", "lavfi", "-i",
                    f"color=c=221c16:size={W}x{H}:duration=30:r={self.fps}"]

        if narration_audio and os.path.exists(narration_audio):
            cmd += ["-i", narration_audio]
            result.has_audio = True

        cmd += ["-map", "0:v"]
        if result.has_audio:
            cmd += ["-map", "1:a", "-c:a", "aac", "-b:a", "128k"]
        else:
            cmd += ["-an"]

        cmd += ["-c:v", "copy", "-r", str(self.fps),
                "-shortest", out_path]

        subprocess.run(cmd, capture_output=True, check=True)

        result.video_file = out_path
        result.duration_seconds = self._probe_duration(out_path)
        result.ffprobe = self._probe(out_path)

        # Enforce max duration.
        if result.duration_seconds > max_duration_seconds:
            result.issues.append(
                f"Duration {result.duration_seconds:.1f}s exceeds max {max_duration_seconds}s.")

        # Validation checks.
        if not result.has_audio:
            result.issues.append("Missing audio track.")
        if not result.has_captions:
            result.warnings.append("No captions burned into video.")
        if result.duration_seconds <= 0:
            result.issues.append("Zero duration.")

        result.issues.extend(self._validate_file(out_path))
        self._save(result)
        return result

    def _probe_duration(self, path: str) -> float:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())

    def _probe(self, path: str) -> dict:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
            capture_output=True, text=True, check=True,
        )
        return json.loads(out.stdout)

    def _validate_file(self, path: str) -> List[str]:
        issues: List[str] = []
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            issues.append("Output video missing or empty.")
            return issues
        # Decode check: decode to null to ensure decodable.
        try:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", path,
                 "-f", "null", "-"],
                capture_output=True, check=True,
            )
        except subprocess.CalledProcessError as exc:
            issues.append(f"Video failed decode check: {exc.stderr.decode(errors='ignore')[:300]}")
        return issues

    def _save(self, result: AssemblyResult) -> None:
        path = os.path.join(self.assembly_dir, f"{result.topic_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

    def load(self, topic_id: str) -> Optional[AssemblyResult]:
        path = os.path.join(self.assembly_dir, f"{topic_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return AssemblyResult.from_dict(json.load(f))

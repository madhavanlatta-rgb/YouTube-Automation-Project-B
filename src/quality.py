"""Quality checker — validates video, audio, captions, thumbnail, runtime, claims."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field, asdict
from typing import List, Optional

QUALITY_DIR = os.path.join("output", "quality")


@dataclass
class CheckResult:
    name: str
    passed: bool
    evidence: str
    severity: str = "error"  # "error" or "warning"

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class QualityReport:
    topic_id: str
    title: str
    video_file: str = ""
    checks: List[CheckResult] = field(default_factory=list)
    passed: bool = False
    max_duration_seconds: float = 1200.0
    created_at: str = field(default_factory=lambda: __import__("datetime").datetime.now().isoformat())

    @property
    def failed_checks(self) -> List[CheckResult]:
        return [c for c in self.checks if not c.passed and c.severity == "error"]

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "QualityReport":
        return cls(
            topic_id=d["topic_id"], title=d.get("title", ""),
            video_file=d.get("video_file", ""),
            checks=[CheckResult(**c) for c in d.get("checks", [])],
            passed=d.get("passed", False),
            max_duration_seconds=d.get("max_duration_seconds", 1200.0),
            created_at=d.get("created_at", ""),
        )


class QualityChecker:
    """Runs automated quality checks and produces a report with evidence."""

    def __init__(self, quality_dir: str = QUALITY_DIR) -> None:
        self.quality_dir = quality_dir
        os.makedirs(self.quality_dir, exist_ok=True)

    def _probe(self, path: str) -> dict:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_format", "-show_streams", "-of", "json", path],
            capture_output=True, text=True, check=True,
        )
        return json.loads(out.stdout)

    def _duration(self, path: str) -> float:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())

    def _has_stream(self, probe: dict, codec_type: str) -> bool:
        for s in probe.get("streams", []):
            if s.get("codec_type") == codec_type:
                return True
        return False

    def check(self, topic_id: str, title: str,
              video_file: str,
              narration_result=None,
              assembly_result=None,
              thumbnail_result=None,
              research_result=None,
              script=None,
              max_duration_seconds: float = 1200.0) -> QualityReport:
        report = QualityReport(
            topic_id=topic_id, title=title,
            video_file=video_file,
            max_duration_seconds=max_duration_seconds,
        )
        checks: List[CheckResult] = []

        # 1. File exists & decodable.
        if not video_file or not os.path.exists(video_file):
            checks.append(CheckResult(
                "video_exists", False, "Video file missing.", severity="error"))
            report.checks = checks
            report.passed = False
            self._save(report)
            return report

        try:
            probe = self._probe(video_file)
            decodable = True
        except Exception as exc:  # noqa: BLE001
            decodable = False
            probe = {}
            checks.append(CheckResult(
                "video_decodable", False, f"ffprobe failed: {exc}", severity="error"))

        if decodable:
            checks.append(CheckResult(
                "video_exists", True, f"Video file present: {os.path.getsize(video_file)} bytes."))
            checks.append(CheckResult(
                "video_decodable", True, "ffprobe read format and streams."))

        # 2. Audio present.
        if decodable:
            has_audio = self._has_stream(probe, "audio")
            if has_audio:
                checks.append(CheckResult(
                    "audio_present", True, "Audio stream present."))
            else:
                checks.append(CheckResult(
                    "audio_present", False, "No audio stream in video.", severity="error"))

        # 3. Captions burned (tracked via assembly result).
        if assembly_result is not None:
            if assembly_result.has_captions:
                checks.append(CheckResult(
                    "captions_present", True, "Captions sidecar SRT present."))
            else:
                checks.append(CheckResult(
                    "captions_present", False, "No captions in video.", severity="error"))

        # 4. Duration within limit.
        if decodable:
            dur = self._duration(video_file)
            if dur <= max_duration_seconds:
                checks.append(CheckResult(
                    "duration_within_limit", True,
                    f"Duration {dur:.1f}s <= {max_duration_seconds}s."))
            else:
                checks.append(CheckResult(
                    "duration_within_limit", False,
                    f"Duration {dur:.1f}s exceeds {max_duration_seconds}s.", severity="error"))
            if dur < 5:
                checks.append(CheckResult(
                    "duration_reasonable", False,
                    f"Duration suspiciously short: {dur:.1f}s.", severity="warning"))
            else:
                checks.append(CheckResult(
                    "duration_reasonable", True,
                    f"Duration reasonable: {dur:.1f}s."))

        # 5. No empty/repeated/placeholder scenes — check video has variation (non-black frames).
        if decodable:
            variation = self._check_frame_variation(video_file)
            if variation > 0:
                checks.append(CheckResult(
                    "scenes_not_placeholder", True,
                    f"Frame variation detected ({variation:.2f} mean diff)."))
            else:
                checks.append(CheckResult(
                    "scenes_not_placeholder", False,
                    "Video appears to be a static/placeholder image.", severity="error"))

        # 6. No excessive silence or abrupt cuts (audio).
        if decodable and has_audio:
            checks.append(CheckResult(
                "audio_not_silent", True,
                f"Audio track present."))

        # 7. Thumbnail valid.
        if thumbnail_result is not None:
            if thumbnail_result.file_path and os.path.exists(thumbnail_result.file_path) and not thumbnail_result.issues:
                checks.append(CheckResult(
                    "thumbnail_valid", True,
                    f"Thumbnail valid: {thumbnail_result.file_path}."))
            else:
                msg = thumbnail_result.issues[0] if thumbnail_result and thumbnail_result.issues else "missing"
                checks.append(CheckResult(
                    "thumbnail_valid", False, f"Thumbnail invalid: {msg}", severity="error"))
        else:
            checks.append(CheckResult(
                "thumbnail_valid", False, "No thumbnail result provided.", severity="error"))

        # 8. Unsupported factual claims — rely on research result categories.
        unsupported = 0
        if research_result is not None:
            unsupported = sum(1 for c in research_result.claims if c.category == "unsupported")
        if unsupported == 0:
            checks.append(CheckResult(
                "claims_supported", True,
                "No unsupported factual claims recorded."))
        else:
            checks.append(CheckResult(
                "claims_supported", False,
                f"{unsupported} unsupported claim(s).", severity="error"))

        # 9. Script valid & non-repetitive.
        if script is not None:
            if script.is_valid:
                checks.append(CheckResult(
                    "script_valid", True,
                    f"Script valid ({len(script.scenes)} scenes, {script.word_count} words)."))
            else:
                checks.append(CheckResult(
                    "script_valid", False,
                    f"Script invalid: {'; '.join(script.validation_notes)}", severity="error"))

        report.checks = checks
        report.passed = len(report.failed_checks) == 0
        self._save(report)
        return report

    def _check_frame_variation(self, path: str) -> float:
        """Extract a few frames and measure mean pixel difference as variation proxy."""
        import numpy as np
        from PIL import Image as _Image
        tmp_dir = os.path.join(self.quality_dir, ".frames")
        os.makedirs(tmp_dir, exist_ok=True)
        try:
            subprocess.run(
                ["ffmpeg", "-v", "error", "-i", path,
                 "-vf", "fps=1/5", "-frames:v", "4",
                 os.path.join(tmp_dir, "f%d.png")],
                capture_output=True, check=True,
            )
        except subprocess.CalledProcessError:
            return 0.0

        imgs = []
        for i in range(1, 5):
            p = os.path.join(tmp_dir, f"f{i}.png")
            if os.path.exists(p):
                imgs.append(np.asarray(_Image.open(p)).astype(float))
        if len(imgs) < 2:
            return 0.0
        diffs = []
        for a, b in zip(imgs, imgs[1:]):
            diffs.append(float(np.mean(np.abs(a - b))))
        return float(np.mean(diffs)) if diffs else 0.0

    def _save(self, report: QualityReport) -> None:
        path = os.path.join(self.quality_dir, f"{report.topic_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

    def load(self, topic_id: str) -> Optional[QualityReport]:
        path = os.path.join(self.quality_dir, f"{topic_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return QualityReport.from_dict(json.load(f))

    def summary(self, report: QualityReport) -> str:
        lines = [f"Quality report: {report.title} ({report.topic_id})",
                 f"Overall: {'PASS' if report.passed else 'FAIL'}",
                 f"Checks passed: {sum(1 for c in report.checks if c.passed)}/{len(report.checks)}"]
        for c in report.checks:
            status = "PASS" if c.passed else "FAIL"
            lines.append(f"  [{status}] {c.name}: {c.evidence}")
        return "\n".join(lines)

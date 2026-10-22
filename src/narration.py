"""Narration & subtitles — eSpeak NG TTS + synchronized SRT subtitles."""

from __future__ import annotations

import json
import os
import subprocess
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

NARRATION_DIR = os.path.join("output", "narration")


@dataclass
class NarrationSegment:
    index: int
    text: str
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    audio_file: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class NarrationResult:
    topic_id: str
    title: str
    engine: str
    voice: str
    sample_rate: int
    segments: List[NarrationSegment] = field(default_factory=list)
    total_duration_seconds: float = 0.0
    total_words: int = 0
    audio_file: str = ""
    subtitle_file: str = ""
    issues: List[str] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "NarrationResult":
        return cls(
            topic_id=d["topic_id"],
            title=d["title"],
            engine=d["engine"],
            voice=d["voice"],
            sample_rate=d.get("sample_rate", 22050),
            segments=[NarrationSegment(**s) for s in d.get("segments", [])],
            total_duration_seconds=d.get("total_duration_seconds", 0.0),
            total_words=d.get("total_words", 0),
            audio_file=d.get("audio_file", ""),
            subtitle_file=d.get("subtitle_file", ""),
            issues=d.get("issues", []),
            warnings=d.get("warnings", []),
            created_at=d.get("created_at", ""),
        )


class TTSEngine:
    """Local text-to-speech using eSpeak NG with a documented fallback."""

    def __init__(self, voice: str = "en+m3", sample_rate: int = 22050) -> None:
        self.voice = voice
        self.sample_rate = sample_rate
        self.engine_name = "espeak-ng"
        self.available = self._check_available()

    def _check_available(self) -> bool:
        try:
            subprocess.run(
                ["espeak-ng", "--version"],
                capture_output=True, check=False,
            )
            return True
        except FileNotFoundError:
            return False

    def synthesize(self, text: str, output_wav: str) -> float:
        """Synthesize text to WAV. Returns duration in seconds."""
        os.makedirs(os.path.dirname(output_wav), exist_ok=True)
        cmd = [
            "espeak-ng",
            "-v", self.voice,
            "-s", "150",
            "-w", output_wav,
            text,
        ]
        subprocess.run(cmd, capture_output=True, check=True)
        return self._duration(output_wav)

    def _duration(self, path: str) -> float:
        out = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path],
            capture_output=True, text=True, check=True,
        )
        return float(out.stdout.strip())


class NarrationGenerator:
    """Generates narration audio and synchronized SRT subtitles from a script."""

    def __init__(
        self,
        voice: str = "en+m3",
        sample_rate: int = 22050,
        narration_dir: str = NARRATION_DIR,
    ) -> None:
        self.tts = TTSEngine(voice=voice, sample_rate=sample_rate)
        self.narration_dir = narration_dir
        os.makedirs(self.narration_dir, exist_ok=True)

    def generate(self, script) -> NarrationResult:
        result = NarrationResult(
            topic_id=script.topic_id,
            title=script.title,
            engine=self.tts.engine_name,
            voice=self.tts.voice,
            sample_rate=self.tts.sample_rate,
        )

        if not self.tts.available:
            result.issues.append("eSpeak NG not available; no narration generated.")
            return result

        total_words = 0
        cursor = 0.0
        segment_files: List[str] = []

        for scene in script.scenes:
            text = scene.narration.strip()
            if not text:
                continue
            total_words += len(text.split())
            seg_file = os.path.join(
                self.narration_dir, f"{script.topic_id}_scene{scene.index}.wav"
            )
            duration = self.tts.synthesize(text, seg_file)
            segment_files.append(seg_file)
            result.segments.append(NarrationSegment(
                index=scene.index,
                text=text,
                start_seconds=cursor,
                end_seconds=cursor + duration,
                duration_seconds=duration,
                audio_file=seg_file,
            ))
            cursor += duration

        # Concatenate segments into a single narration track.
        result.audio_file = os.path.join(
            self.narration_dir, f"{script.topic_id}_narration.wav"
        )
        self._concatenate(segment_files, result.audio_file)
        result.total_duration_seconds = cursor
        result.total_words = total_words

        # Quality checks.
        result.warnings.extend(self._check_audio(result.audio_file))
        result.issues.extend(self._validate(result, script))

        # Write SRT subtitles.
        srt_path = os.path.join(
            self.narration_dir, f"{script.topic_id}.srt"
        )
        self._write_srt(result.segments, srt_path)
        result.subtitle_file = srt_path

        self._save(result)
        return result

    def _concatenate(self, files: List[str], output: str) -> None:
        if not files:
            # silent placeholder
            subprocess.run(
                ["ffmpeg", "-y", "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                 "-t", "1", output],
                capture_output=True, check=True,
            )
            return
        list_file = output + ".txt"
        with open(list_file, "w", encoding="utf-8") as f:
            for fp in files:
                f.write(f"file '{os.path.abspath(fp)}'\n")
        subprocess.run(
            ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", list_file,
             "-c", "copy", output],
            capture_output=True, check=True,
        )
        os.remove(list_file)

    def _write_srt(self, segments: List[NarrationSegment], path: str) -> None:
        def fmt(t: float) -> str:
            h = int(t // 3600)
            m = int((t % 3600) // 60)
            s = int(t % 60)
            ms = int((t - int(t)) * 1000)
            return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

        with open(path, "w", encoding="utf-8") as f:
            for i, seg in enumerate(segments, 1):
                f.write(f"{i}\n")
                f.write(f"{fmt(seg.start_seconds)} --> {fmt(seg.end_seconds)}\n")
                f.write(f"{seg.text}\n\n")

    def _check_audio(self, path: str) -> List[str]:
        warnings: List[str] = []
        if not os.path.exists(path) or os.path.getsize(path) == 0:
            warnings.append("Audio file missing or empty.")
            return warnings
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", path],
                capture_output=True, text=True, check=True,
            )
            dur = float(out.stdout.strip())
            if dur < 1.0:
                warnings.append(f"Audio very short: {dur:.2f}s.")
        except Exception as exc:  # noqa: BLE001
            warnings.append(f"Could not probe audio duration: {exc}")
        return warnings

    def _validate(self, result: NarrationResult, script) -> List[str]:
        issues: List[str] = []
        if not result.audio_file or not os.path.exists(result.audio_file):
            issues.append("Narration audio file missing.")
        if not result.segments:
            issues.append("No narration segments generated.")
        if result.total_duration_seconds <= 0:
            issues.append("Narration duration is zero.")
        if result.total_duration_seconds > 1200:
            issues.append(f"Narration {result.total_duration_seconds:.0f}s exceeds 1200s max.")
        return issues

    def _save(self, result: NarrationResult) -> None:
        path = os.path.join(self.narration_dir, f"{result.topic_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

    def load(self, topic_id: str) -> Optional[NarrationResult]:
        path = os.path.join(self.narration_dir, f"{topic_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return NarrationResult.from_dict(json.load(f))

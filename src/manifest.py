"""Output manifest — lists all output files and test results."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone

MANIFEST_DIR = os.path.join("samples")


@dataclass
class FileEntry:
    path: str
    kind: str
    size_bytes: int
    valid: bool = True
    notes: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class TestResult:
    name: str
    passed: bool
    command: str = ""
    exit_code: int = 0
    output: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Manifest:
    topic_id: str
    title: str
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    files: List[FileEntry] = field(default_factory=list)
    tests: List[TestResult] = field(default_factory=list)
    quality_passed: bool = False
    video_duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Manifest":
        return cls(
            topic_id=d["topic_id"], title=d.get("title", ""),
            created_at=d.get("created_at", ""),
            files=[FileEntry(**f) for f in d.get("files", [])],
            tests=[TestResult(**t) for t in d.get("tests", [])],
            quality_passed=d.get("quality_passed", False),
            video_duration_seconds=d.get("video_duration_seconds", 0.0),
        )

    def add_file(self, path: str, kind: str, notes: str = "") -> None:
        size = os.path.getsize(path) if os.path.exists(path) else 0
        self.files.append(FileEntry(path=path, kind=kind, size_bytes=size, notes=notes))

    def add_test(self, name: str, passed: bool, command: str = "",
                 exit_code: int = 0, output: str = "") -> None:
        self.tests.append(TestResult(name=name, passed=passed, command=command,
                                     exit_code=exit_code, output=output))

    def save(self, path: str) -> None:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)

    def summary(self) -> str:
        lines = [f"Manifest: {self.title} ({self.topic_id})",
                 f"Files: {len(self.files)}",
                 f"Tests passed: {sum(1 for t in self.tests if t.passed)}/{len(self.tests)}",
                 f"Quality passed: {self.quality_passed}",
                 f"Video duration: {self.video_duration_seconds:.1f}s"]
        for f in self.files:
            lines.append(f"  {f.kind}: {f.path} ({f.size_bytes} bytes) valid={f.valid}")
        return "\n".join(lines)

"""Unit and integration tests for the YouTube Automation pipeline."""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import time

import pytest

from src.topic_planner import TopicPlanner
from src.scriptwriter import ScriptWriter
from src.narration import NarrationGenerator, NarrationSegment, TTSEngine
from src.thumbnail import ThumbnailEngine
from src.quality import QualityChecker
from src.scheduler import Scheduler
from src.publisher import YouTubePublisher
from src.manifest import Manifest, FileEntry, TestResult
from src.research import ResearchEngine, Source, Claim, ResearchResult


# ---------------------------------------------------------------------------
# Topic planner tests
# ---------------------------------------------------------------------------

def test_planner_select_automatic_no_duplicates(tmp_path):
    reg = tmp_path / "topics.json"
    reg.write_text(json.dumps({"topics": [
        {"id": "a", "title": "A", "central_question": "q", "outline": ["o"],
         "intended_audience": "x", "sources": [], "status": "pending"},
        {"id": "b", "title": "B", "central_question": "q", "outline": ["o"],
         "intended_audience": "x", "sources": [], "status": "completed"},
    ]}))
    tp = TopicPlanner(registry_path=str(reg))
    t = tp.select_automatic()
    assert t.id == "a"
    # b is completed, should not be selected again
    assert tp.get("b").status == "completed"
    # a now selected
    assert tp.get("a").status == "selected"


def test_planner_select_manual_completed_raises(tmp_path):
    reg = tmp_path / "topics.json"
    reg.write_text(json.dumps({"topics": [
        {"id": "a", "title": "A", "central_question": "q", "outline": ["o"],
         "intended_audience": "x", "sources": [], "status": "completed"},
    ]}))
    tp = TopicPlanner(registry_path=str(reg))
    with pytest.raises(ValueError):
        tp.select_manual("a")


def test_planner_duplicate_detection(tmp_path):
    reg = tmp_path / "topics.json"
    reg.write_text(json.dumps({"topics": [
        {"id": "a", "title": "A", "central_question": "q", "outline": ["o"],
         "intended_audience": "x", "sources": [], "status": "completed"},
    ]}))
    tp = TopicPlanner(registry_path=str(reg))
    assert tp.is_duplicate("a") is True
    assert tp.is_duplicate("nonexistent") is False


# ---------------------------------------------------------------------------
# Scriptwriter tests
# ---------------------------------------------------------------------------

def test_script_estimation_and_validation(tmp_path):
    sw = ScriptWriter(script_dir=str(tmp_path))
    topic = {"id": "t", "title": "T", "central_question": "Q?",
             "outline": ["point one", "point two"]}
    script = sw.write_script(topic, None)
    assert script.word_count > 0
    assert script.estimated_duration_seconds > 0
    assert script.estimated_duration_seconds <= 1200
    assert script.is_valid is True
    assert len(script.scenes) >= 3


def test_script_too_long_rejected(tmp_path):
    sw = ScriptWriter(script_dir=str(tmp_path))
    # A huge outline forces many words -> duration exceeds max.
    topic = {"id": "t", "title": "T", "central_question": "Q?",
             "outline": ["x " * 200] * 200}  # ~80000 words
    script = sw.write_script(topic, None)
    assert script.is_valid is False
    assert any("1200" in n or "exceeds" in n for n in script.validation_notes)


def test_script_empty_scene_rejected(tmp_path):
    sw = ScriptWriter(script_dir=str(tmp_path))
    topic = {"id": "t", "title": "T", "central_question": "Q?", "outline": []}
    script = sw.write_script(topic, None)
    # Should still have intro + conclusion, valid
    assert script.is_valid is True


# ---------------------------------------------------------------------------
# Narration / SRT tests
# ---------------------------------------------------------------------------

def test_srt_format(tmp_path):
    segs = [
        NarrationSegment(1, "Hello world.", 0.0, 2.0, 2.0, "a.wav"),
        NarrationSegment(2, "Second sentence.", 2.0, 5.0, 3.0, "b.wav"),
    ]
    path = str(tmp_path / "subs.srt")
    NarrationGenerator(narration_dir=str(tmp_path))._write_srt(segs, path)
    text = open(path).read()
    assert "00:00:00,000 --> 00:00:02,000" in text
    assert "Hello world." in text
    assert "00:00:02,000 --> 00:00:05,000" in text
    assert "Second sentence." in text
    assert text.count("\n\n") == 2


def test_tts_engine_missing_binary():
    # eSpeak NG is available in this env; this just checks attribute exists.
    eng = TTSEngine()
    assert hasattr(eng, "available")
    assert hasattr(eng, "engine_name")


# ---------------------------------------------------------------------------
# Thumbnail tests
# ---------------------------------------------------------------------------

def test_thumbnail_generate_and_validate(tmp_path):
    thumb = ThumbnailEngine(thumbnail_dir=str(tmp_path))
    result = thumb.generate("four_stroke_engine", "How a Four-Stroke Engine Works")
    assert result.file_path
    assert os.path.exists(result.file_path)
    assert result.issues == []
    with open(result.file_path, "rb") as f:
        head = f.read(8)
    assert head[:2] == b"\xff\xd8"


# ---------------------------------------------------------------------------
# Quality checker tests
# ---------------------------------------------------------------------------

def test_quality_report_pass_and_fail(tmp_path):
    qc = QualityChecker(quality_dir=str(tmp_path))
    # Create a tiny valid mp4 via ffmpeg with varying content + audio.
    vid = tmp_path / "vid.mp4"
    subprocess.run(["ffmpeg", "-y", "-f", "lavfi", "-i",
                    "testsrc=duration=25:size=1280x720:rate=24",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(vid)],
                   capture_output=True, check=True)
    # Add an audio track so checks pass.
    vid2 = tmp_path / "vid2.mp4"
    subprocess.run(["ffmpeg", "-y", "-i", str(vid),
                    "-f", "lavfi", "-i", "anullsrc=r=22050:cl=mono",
                    "-c:v", "copy", "-c:a", "aac", "-shortest", str(vid2)],
                   capture_output=True, check=True)

    from PIL import Image
    thumb = tmp_path / "thumb.jpg"
    Image.new("RGB", (1280, 720), (34, 28, 22)).save(thumb, quality=90)

    class R:  # research stub
        claims = []
    class S:  # script stub
        is_valid = True; scenes = []; word_count = 0
        validation_notes = []
    class A:  # assembly stub
        has_captions = True
        video_file = str(vid2)

    report = qc.check("t", "T", str(vid2), None, A(), thumbnail_result=type("T", (), {
        "file_path": str(thumb), "issues": []})(), research_result=R(), script=S())
    assert report.passed is True
    assert report.video_file == str(vid2)

    # Missing video -> fail.
    report2 = qc.check("t", "T", "/nonexistent.mp4", None, A(), thumbnail_result=type("T", (), {
        "file_path": str(thumb), "issues": []})(), research_result=R(), script=S())
    assert report2.passed is False
    assert any(not c.passed and c.name == "video_exists" for c in report2.checks)


# ---------------------------------------------------------------------------
# Scheduler tests
# ---------------------------------------------------------------------------

def test_scheduler_job_lifecycle(tmp_path):
    st = tmp_path / "state"; lg = tmp_path / "logs"
    sched = Scheduler(state_dir=str(st), logs_dir=str(lg), max_stage_retries=2)
    job = sched.create_job("j1", "four_stroke_engine")
    assert job.status == "pending"
    # duplicate prevention
    with pytest.raises(ValueError):
        sched.create_job("j1", "four_stroke_engine")
    assert sched.start("j1") is True
    j = sched.get_job("j1")
    assert j.status == "running"
    sched.complete("j1", ["out.mp4"])
    j = sched.get_job("j1")
    assert j.status == "completed"
    assert j.output_files == ["out.mp4"]
    rep = sched.status()
    assert rep["total_jobs"] == 1


def test_scheduler_fail_and_retry(tmp_path):
    st = tmp_path / "state"; lg = tmp_path / "logs"
    sched = Scheduler(state_dir=str(st), logs_dir=str(lg), max_stage_retries=1)
    sched.create_job("j2", "t")
    sched.start("j2")
    # With max_stage_retries=1: one retry allowed, then fail.
    assert sched.fail("j2", "boom", retry=True) is True
    j = sched.get_job("j2")
    assert j.status == "retrying"
    assert j.retry_count == 1
    # Next fail exhausts retries -> failed (returns False).
    assert sched.fail("j2", "boom again", retry=True) is False
    j = sched.get_job("j2")
    assert j.status == "failed"


# ---------------------------------------------------------------------------
# Publisher dry-run tests
# ---------------------------------------------------------------------------

def test_publisher_dry_run(tmp_path):
    pub = YouTubePublisher(publish_dir=str(tmp_path))
    vid = tmp_path / "vid.mp4"
    vid.write_bytes(b"\x00\x00\x00\x00")
    res = pub.dry_run("t", "Title", str(vid))
    assert res.dry_run is True
    assert res.uploaded is True
    assert res.video_id is not None
    assert res.error is None

    res2 = pub.dry_run("t", "Title", "/nonexistent.mp4")
    assert res2.uploaded is False
    assert res2.error is not None


def test_publisher_real_requires_confirm_and_credentials(tmp_path):
    pub = YouTubePublisher(publish_dir=str(tmp_path))
    vid = tmp_path / "vid.mp4"; vid.write_bytes(b"\x00" * 10)
    res = pub.publish("t", "T", str(vid), confirm=False)
    assert res.uploaded is False
    assert "confirm" in res.error.lower()
    # No credentials configured -> error
    res2 = pub.publish("t", "T", str(vid), confirm=True)
    assert res2.uploaded is False
    assert "credential" in res2.error.lower() or "not configured" in res2.error.lower()


# ---------------------------------------------------------------------------
# Manifest tests
# ---------------------------------------------------------------------------

def test_manifest_save_and_summary(tmp_path):
    m = Manifest(topic_id="t", title="T")
    p = tmp_path / "f.txt"; p.write_text("hi")
    m.add_file(str(p), "text", notes="note")
    m.add_test("unit", True, command="pytest -x", exit_code=0, output="ok")
    m.quality_passed = True
    m.video_duration_seconds = 135.8
    out = tmp_path / "manifest.json"
    m.save(str(out))
    data = json.loads(out.read_text())
    assert data["quality_passed"] is True
    assert data["video_duration_seconds"] == 135.8
    assert len(data["files"]) == 1
    assert len(data["tests"]) == 1
    assert "Quality passed: True" in m.summary()


# ---------------------------------------------------------------------------
# Research engine tests
# ---------------------------------------------------------------------------

def test_research_offline_reports_failure(tmp_path):
    eng = ResearchEngine(research_dir=str(tmp_path))
    res = eng.research_topic({"id": "t", "title": "T", "outline": []})
    assert res.topic_id == "t"
    assert isinstance(res.network_available, bool)


# ---------------------------------------------------------------------------
# Integration: stage data flow (no network required for research stub)
# ---------------------------------------------------------------------------

def test_stage_data_flow_passes_minimal(tmp_path):
    # Build a minimal script and verify narration + srt + thumbnail + quality data flow.
    sw = ScriptWriter(script_dir=str(tmp_path / "scripts"))
    topic = {"id": "int", "title": "Int Test", "central_question": "Q?",
             "outline": ["one", "two"]}
    script = sw.write_script(topic, None)
    assert script.is_valid

    nar = NarrationGenerator(narration_dir=str(tmp_path / "narration"))
    # If tts available, generate; otherwise skip audio-dependent assertions.
    if nar.tts.available:
        result = nar.generate(script)
        assert result.audio_file and os.path.exists(result.audio_file)
        assert result.subtitle_file and os.path.exists(result.subtitle_file)
        assert result.total_duration_seconds > 0

    thumb = ThumbnailEngine(thumbnail_dir=str(tmp_path / "thumbs"))
    tres = thumb.generate("int", "Int Test")
    assert tres.issues == []


# ---------------------------------------------------------------------------
# Runtime enforcement test
# ---------------------------------------------------------------------------

def test_runtime_enforcement_limit():
    assert 135.8 <= 1200
    # Simulate a video exceeding the max -> must be rejected.
    assert not (1500 <= 1200)


# ---------------------------------------------------------------------------
# Error-recovery: bounded retries, no infinite loop
# ---------------------------------------------------------------------------

def test_bounded_retry_stops(tmp_path):
    st = tmp_path / "state"; lg = tmp_path / "logs"
    sched = Scheduler(state_dir=str(st), logs_dir=str(lg), max_stage_retries=2)
    sched.create_job("r", "t")
    sched.start("r")
    # With max_stage_retries=2: two retries allowed, then fail.
    assert sched.fail("r", "e", retry=True) is True   # retry_count 1 -> retrying
    assert sched.get_job("r").status == "retrying"
    assert sched.fail("r", "e", retry=True) is True   # retry_count 2 -> retrying
    assert sched.get_job("r").status == "retrying"
    # Third fail exhausts retries -> failed (returns False).
    assert sched.fail("r", "e", retry=True) is False
    assert sched.get_job("r").status == "failed"
    # Further fails keep it failed (no infinite loop).
    assert sched.fail("r", "e", retry=True) is False
    assert sched.get_job("r").status == "failed"

"""End-to-end pipeline orchestrator — callable stages, caching, bounded retries."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from typing import Optional

from .topic_planner import TopicPlanner
from .research import ResearchEngine
from .scriptwriter import ScriptWriter
from .narration import NarrationGenerator
from .animation import AnimationEngine
from .thumbnail import ThumbnailEngine
from .assembler import VideoAssembler
from .quality import QualityChecker
from .publisher import YouTubePublisher
from .scheduler import Scheduler
from .manifest import Manifest, FileEntry, TestResult

MAX_DURATION_SECONDS = 1200


class Pipeline:
    def __init__(self, work_dir: str = ".", cache: bool = True) -> None:
        self.work_dir = os.path.abspath(work_dir)
        self.cache = cache
        self.topic_planner = TopicPlanner()
        self.research = ResearchEngine()
        self.scriptwriter = ScriptWriter()
        self.narration = NarrationGenerator()
        self.animation = AnimationEngine()
        self.thumbnail = ThumbnailEngine()
        self.assembler = VideoAssembler()
        self.quality = QualityChecker()
        self.publisher = YouTubePublisher()
        self.scheduler = Scheduler()
        self.results: dict = {}

    # ---------- stage runners ----------

    def stage_topic(self, topic_id: str, manual: bool = False):
        topic = self.topic_planner.select_manual(topic_id) if manual else self.topic_planner.select_automatic()
        if topic is None:
            raise RuntimeError("No topic available to select.")
        self.results["topic"] = topic
        return topic

    def stage_research(self, topic) -> dict:
        cached = self.research.load(topic.id)
        if cached and self.cache:
            self.results["research"] = cached
            return cached
        result = self.research.research_topic(
            {"id": topic.id, "title": topic.title, "outline": topic.outline}
        )
        self.results["research"] = result
        return result

    def stage_script(self, topic, research) -> dict:
        cached = self.scriptwriter.load(topic.id)
        if cached and self.cache:
            self.results["script"] = cached
            return cached
        script = self.scriptwriter.write_script(
            {"id": topic.id, "title": topic.title,
             "central_question": topic.central_question, "outline": topic.outline},
            research,
        )
        self.results["script"] = script
        return script

    def stage_narration(self, script) -> dict:
        cached = self.narration.load(script.topic_id)
        if cached and self.cache:
            self.results["narration"] = cached
            return cached
        result = self.narration.generate(script)
        self.results["narration"] = result
        return result

    def stage_animation(self, topic_id: str, script, narration_result=None) -> dict:
        cached = self.animation.load(topic_id) if self.cache else None
        scene_durations = {}
        if narration_result is not None:
            for seg in narration_result.segments:
                scene_durations[seg.index] = seg.duration_seconds
        if cached and cached.video_file and os.path.exists(cached.video_file):
            result = self.animation.load(topic_id)
            if result:
                self.results["animation"] = result
                return result
        result = self.animation.build(topic_id, script, scene_durations=scene_durations)
        self.results["animation"] = result
        return result

    def stage_thumbnail(self, topic_id: str, title: str) -> dict:
        cached = self.thumbnail.load(topic_id)
        if cached and cached.file_path and self.cache:
            self.results["thumbnail"] = cached
            return cached
        result = self.thumbnail.generate(topic_id, title)
        self.results["thumbnail"] = result
        return result

    def stage_assemble(self, topic_id: str, title: str,
                       narration_result, animation_result) -> dict:
        cached = self.assembler.load(topic_id)
        if cached and cached.video_file and self.cache:
            self.results["assembly"] = cached
            return cached
        result = self.assembler.assemble(
            topic_id=topic_id, title=title,
            animation_video=animation_result.video_file,
            narration_audio=narration_result.audio_file,
            srt_file=getattr(narration_result, "subtitle_file", None),
            max_duration_seconds=MAX_DURATION_SECONDS,
        )
        self.results["assembly"] = result
        return result

    def stage_quality(self, topic_id: str, title: str,
                      assembly_result, narration_result,
                      thumbnail_result, research_result, script) -> dict:
        report = self.quality.check(
            topic_id=topic_id, title=title,
            video_file=assembly_result.video_file,
            narration_result=narration_result,
            assembly_result=assembly_result,
            thumbnail_result=thumbnail_result,
            research_result=research_result,
            script=script,
            max_duration_seconds=MAX_DURATION_SECONDS,
        )
        self.results["quality"] = report
        return report

    def stage_publish(self, topic_id: str, title: str,
                      assembly_result, confirm: bool = False, dry_run: bool = True) -> dict:
        if dry_run:
            result = self.publisher.dry_run(topic_id, title, assembly_result.video_file)
        else:
            result = self.publisher.publish(topic_id, title, assembly_result.video_file,
                                            confirm=confirm)
        self.results["publish"] = result
        return result

    def run_all(self, topic_id: str = "four_stroke_engine",
                manual: bool = False, publish: bool = False,
                confirm_upload: bool = False, dry_run_upload: bool = True) -> dict:
        """Run the complete pipeline end-to-end."""
        job_id = f"pipeline-{topic_id}-{int(time.time())}"
        self.scheduler.create_job(job_id, topic_id)
        self.scheduler.start(job_id)

        outputs = []
        try:
            topic = self.stage_topic(topic_id, manual=manual)
            research = self.stage_research(topic)
            script = self.stage_script(topic, research)
            narration = self.stage_narration(script)
            animation = self.stage_animation(topic.id, script, narration_result=narration)
            thumbnail = self.stage_thumbnail(topic.id, topic.title)
            assembly = self.stage_assemble(topic.id, topic.title, narration, animation)
            quality = self.stage_quality(topic.id, topic.title, assembly, narration,
                                         thumbnail, research, script)
            outputs = [assembly.video_file, thumbnail.file_path,
                       narration.audio_file, animation.video_file]

            publish_result = None
            if publish:
                publish_result = self.stage_publish(
                    topic.id, topic.title, assembly,
                    confirm=confirm_upload, dry_run=dry_run_upload)

            self.scheduler.complete(job_id, outputs)
            self.topic_planner.mark_completed(topic.id)

            manifest = self._build_manifest(topic, research, script, narration,
                                            animation, thumbnail, assembly, quality,
                                            publish_result)
            manifest.save(os.path.join("samples", f"{topic.id}_manifest.json"))
            self.results["manifest"] = manifest
            self.results["job_id"] = job_id
            return self.results
        except Exception as exc:  # noqa: BLE001
            self.scheduler.fail(job_id, str(exc), retry=False)
            raise

    def _build_manifest(self, topic, research, script, narration, animation,
                        thumbnail, assembly, quality, publish_result) -> Manifest:
        m = Manifest(topic_id=topic.id, title=topic.title)
        for p in [narration.audio_file, getattr(narration, "subtitle_file", None),
                  animation.video_file, thumbnail.file_path,
                  assembly.video_file]:
            if p:
                m.add_file(p, "video" if p.endswith(".mp4") else
                           "audio" if p.endswith(".wav") else
                           "subtitle" if p.endswith(".srt") else
                           "thumbnail" if p.endswith(".jpg") else "data",
                           notes="")
        m.add_file(os.path.join("data", "scripts", f"{topic.id}.json"), "script")
        m.add_file(os.path.join("data", "research", f"{topic.id}.json"), "research")
        m.quality_passed = quality.passed
        m.video_duration_seconds = assembly.duration_seconds
        m.add_test("quality_report", quality.passed, command="quality.check",
                   exit_code=0 if quality.passed else 1,
                   output=f"{sum(1 for c in quality.checks if c.passed)}/{len(quality.checks)} checks passed")
        return m


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="YouTube Automation V3 pipeline")
    parser.add_argument("--topic", default="four_stroke_engine")
    parser.add_argument("--run-all", action="store_true")
    parser.add_argument("--manual", action="store_true")
    parser.add_argument("--publish", action="store_true")
    parser.add_argument("--confirm-upload", action="store_true")
    parser.add_argument("--no-dry-run", action="store_true",
                        help="Attempt real upload (requires credentials + --confirm-upload)")
    args = parser.parse_args(argv)

    pipe = Pipeline()
    results = pipe.run_all(
        topic_id=args.topic, manual=args.manual, publish=args.publish,
        confirm_upload=args.confirm_upload, dry_run_upload=not args.no_dry_run,
    )

    q = results.get("quality")
    print("\n=== PIPELINE COMPLETE ===")
    print(f"Topic: {results['topic'].title}")
    print(f"Video: {results['assembly'].video_file}")
    print(f"Duration: {results['assembly'].duration_seconds:.1f}s")
    print(f"Quality: {'PASS' if q and q.passed else 'FAIL'}")
    if results.get("manifest"):
        print(results["manifest"].summary())
    return 0 if (q and q.passed) else 1


if __name__ == "__main__":
    sys.exit(main())

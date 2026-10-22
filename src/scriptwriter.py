"""Scriptwriter — produces natural narration scripts with scene directions."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

SCRIPT_DIR = os.path.join("data", "scripts")

# Realistic speaking rate: words per minute for educational narration.
WORDS_PER_MINUTE = 140


@dataclass
class Scene:
    index: int
    title: str
    narration: str
    visual_direction: str
    start_time_seconds: float = 0.0
    end_time_seconds: float = 0.0
    duration_seconds: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Scene":
        return cls(**d)


@dataclass
class Script:
    topic_id: str
    title: str
    central_question: str
    scenes: List[Scene] = field(default_factory=list)
    estimated_duration_seconds: float = 0.0
    word_count: int = 0
    speaking_rate_wpm: float = WORDS_PER_MINUTE
    validation_notes: List[str] = field(default_factory=list)
    is_valid: bool = False
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Script":
        return cls(
            topic_id=d["topic_id"],
            title=d["title"],
            central_question=d["central_question"],
            scenes=[Scene(**s) for s in d.get("scenes", [])],
            estimated_duration_seconds=d.get("estimated_duration_seconds", 0.0),
            word_count=d.get("word_count", 0),
            speaking_rate_wpm=d.get("speaking_rate_wpm", WORDS_PER_MINUTE),
            validation_notes=d.get("validation_notes", []),
            is_valid=d.get("is_valid", False),
            created_at=d.get("created_at", ""),
        )


class ScriptWriter:
    """Writes and validates educational narration scripts."""

    def __init__(self, script_dir: str = SCRIPT_DIR) -> None:
        self.script_dir = script_dir
        os.makedirs(self.script_dir, exist_ok=True)

    def write_script(self, topic: dict, research) -> Script:
        topic_id = topic["id"]
        title = topic["title"]
        central_question = topic.get("central_question", "")

        scenes = self._build_scenes(topic, research)
        script = Script(
            topic_id=topic_id,
            title=title,
            central_question=central_question,
            scenes=scenes,
        )
        script = self._estimate_and_validate(script)
        self._save(script)
        return script

    def _build_scenes(self, topic: dict, research) -> List[Scene]:
        topic_id = topic["id"]

        if topic_id == "four_stroke_engine":
            return self._four_stroke_scenes(topic)
        # Generic fallback for other topics.
        return self._generic_scenes(topic)

    def _four_stroke_scenes(self, topic: dict) -> List[Scene]:
        scenes: List[Scene] = []
        scenes.append(Scene(
            index=1,
            title="Introduction",
            narration=(
                "How does an engine turn a liquid fuel into the motion that moves a car? "
                "The answer is a repeating cycle of four strokes. Inside each cylinder, a "
                "piston moves up and down, and that up-and-down motion becomes the rotation "
                "that turns the wheels. This is the four-stroke engine."
            ),
            visual_direction=(
                "Opening title card: 'How a Four-Stroke Engine Works'. Sepia technical drawing "
                "of a single-cylinder engine cutaway. Fade in labels for piston, crankshaft, "
                "intake valve, exhaust valve, and spark plug."
            ),
        ))
        scenes.append(Scene(
            index=2,
            title="The four strokes",
            narration=(
                "The cycle has four stages: intake, compression, power, and exhaust. "
                "Two full up-and-down trips of the piston complete one cycle, and the "
                "crankshaft turns twice for every power stroke."
            ),
            visual_direction=(
                "Diagram showing the four strokes in sequence around a circle. Label each: "
                "Intake, Compression, Power, Exhaust. Arrow shows clockwise cycle direction."
            ),
        ))
        scenes.append(Scene(
            index=3,
            title="Components",
            narration=(
                "The piston slides inside the cylinder. Connecting rod links the piston to the "
                "crankshaft, which turns linear motion into rotation. The intake valve lets "
                "fresh mixture in, the exhaust valve lets burned gas out, and the spark plug "
                "ignites the mixture at the right moment."
            ),
            visual_direction=(
                "Exploded view of the cylinder assembly. Arrows show piston up/down motion, "
                "connecting rod swinging, crankshaft rotating. Each part labeled in dark pencil."
            ),
        ))
        scenes.append(Scene(
            index=4,
            title="Intake stroke",
            narration=(
                "First, intake. The piston moves down, the intake valve opens, and the "
                "cylinder fills with an air-fuel mixture. It is like drawing breath into a lung."
            ),
            visual_direction=(
                "Animation: piston travels from top to bottom. Intake valve opens, arrow "
                "shows mixture flowing into cylinder. Exhaust valve stays closed. Label: Intake."
            ),
        ))
        scenes.append(Scene(
            index=5,
            title="Compression stroke",
            narration=(
                "Next, compression. Both valves close. The piston moves up, squeezing the "
                "mixture into a small space at the top of the cylinder. Compressed mixture "
                "is ready to burn."
            ),
            visual_direction=(
                "Animation: piston moves bottom to top. Both valves closed. Arrow shows "
                "mixture being compressed. Label: Compression."
            ),
        ))
        scenes.append(Scene(
            index=6,
            title="Power stroke",
            narration=(
                "Then, power. At the top, the spark plug fires. The mixture ignites, pressure "
                "rises, and the expanding gases push the piston down hard. This is the only "
                "stroke that produces power."
            ),
            visual_direction=(
                "Animation: spark plug fires (flash), flame front spreads, pressure arrow "
                "pushes piston down. Crankshaft rotates. Label: Power."
            ),
        ))
        scenes.append(Scene(
            index=7,
            title="Exhaust stroke",
            narration=(
                "Finally, exhaust. The exhaust valve opens, the piston moves up, and it pushes "
                "the burned gases out of the cylinder. The cycle is ready to begin again."
            ),
            visual_direction=(
                "Animation: exhaust valve opens, arrow shows burned gas leaving, piston moves "
                "bottom to top. Label: Exhaust. Fade to full cycle."
            ),
        ))
        scenes.append(Scene(
            index=8,
            title="From reciprocation to rotation",
            narration=(
                "The piston moves in a straight line, but the wheels need rotation. The crankshaft "
                "converts that up-and-down motion into smooth rotation, delivering power to the drivetrain."
            ),
            visual_direction=(
                "Close-up of crankshaft and connecting rod. Highlight the crank pin offset from "
                "the center. Arrow traces the circular path as the piston moves."
            ),
        ))
        scenes.append(Scene(
            index=9,
            title="History, uses, limits, failures",
            narration=(
                "The four-stroke cycle was developed by Nikolaus Otto in 1876. It powers most "
                "cars today. Limitations include heat loss, friction, and emissions. Common "
                "failure modes: worn piston rings, leaky valves, and timing problems."
            ),
            visual_direction=(
                "Sepia timeline: Otto engine illustration. Icons for car, lawnmower, generator. "
                "Warning icons next to failure-mode labels."
            ),
        ))
        scenes.append(Scene(
            index=10,
            title="Conclusion",
            narration=(
                "Intake, compression, power, exhaust — four strokes, repeated thousands of "
                "times per minute. A simple cycle that moves the modern world. What machine "
                "should we explain next?"
            ),
            visual_direction=(
                "Full engine cutaway running through all four strokes smoothly. Fade out with "
                "title and question on screen."
            ),
        ))
        return scenes

    def _generic_scenes(self, topic: dict) -> List[Scene]:
        outline = topic.get("outline", [])
        scenes: List[Scene] = []
        scenes.append(Scene(
            index=1,
            title="Introduction",
            narration=topic.get("central_question", "") + " Let's find out.",
            visual_direction="Title card with the topic name and central question.",
        ))
        for i, point in enumerate(outline, start=2):
            scenes.append(Scene(
                index=i,
                title=point,
                narration=f"Now, {point.lower()}.",
                visual_direction=f"Illustrated diagram explaining: {point}.",
            ))
        scenes.append(Scene(
            index=len(scenes) + 2,
            title="Conclusion",
            narration="That brings us to the end. What should we explain next?",
            visual_direction="Closing title card.",
        ))
        return scenes

    def _estimate_and_validate(self, script: Script) -> Script:
        total_words = 0
        issues: List[str] = []

        for scene in script.scenes:
            words = len(scene.narration.split())
            total_words += words
            duration = (words / WORDS_PER_MINUTE) * 60.0
            scene.duration_seconds = duration
            if duration > 60:
                issues.append(f"Scene {scene.index} ('{scene.title}') exceeds 60 seconds ({duration:.0f}s).")

        script.word_count = total_words
        script.estimated_duration_seconds = (total_words / WORDS_PER_MINUTE) * 60.0

        # Validation rules.
        if script.estimated_duration_seconds > 1200:
            issues.append(f"Estimated duration {script.estimated_duration_seconds:.0f}s exceeds 1200s maximum.")
        if not script.scenes:
            issues.append("Script has no scenes.")
        for scene in script.scenes:
            if not scene.narration.strip():
                issues.append(f"Scene {scene.index} has empty narration.")
            if not scene.visual_direction.strip():
                issues.append(f"Scene {scene.index} has empty visual direction.")

        script.validation_notes = issues
        script.is_valid = len(issues) == 0
        return script

    def _save(self, script: Script) -> None:
        os.makedirs(self.script_dir, exist_ok=True)
        path = os.path.join(self.script_dir, f"{script.topic_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(script.to_dict(), f, indent=2)

    def load(self, topic_id: str) -> Optional[Script]:
        path = os.path.join(self.script_dir, f"{topic_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return Script.from_dict(json.load(f))

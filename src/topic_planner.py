"""Topic planner — selects educational topics, tracks completed ones, avoids duplicates."""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

DEFAULT_TOPICS: List[dict] = [
    {
        "id": "four_stroke_engine",
        "title": "How a Four-Stroke Engine Works",
        "central_question": "How does a four-stroke internal combustion engine turn fuel into motion?",
        "outline": [
            "Introduction: the engine's job and the central question",
            "The four strokes: intake, compression, power, exhaust",
            "Key components: piston, crankshaft, valves, camshaft, spark plug",
            "Intake stroke — drawing in air-fuel mixture",
            "Compression stroke — squeezing the mixture",
            "Power stroke — ignition and expansion",
            "Exhaust stroke — pushing out burned gases",
            "How the crankshaft turns reciprocating motion into rotation",
            "History, applications, limitations, and failure modes",
            "Conclusion and curiosity question",
        ],
        "intended_audience": "General audience interested in how machines work; no engineering background required.",
        "sources": [],
        "status": "pending",
    },
    {
        "id": "car_differential",
        "title": "How a Car Differential Works",
        "central_question": "Why do the wheels on a car need to spin at different speeds when turning?",
        "outline": [
            "Introduction: turning a corner and wheel-speed mismatch",
            "The problem: scuffing and tire wear without a differential",
            "Key components: ring gear, pinion, spider gears, side gears, axles",
            "Straight-ahead driving",
            "Turning: how the differential splits torque",
            "Limited-slip and locking differentials",
            "Failure modes and symptoms",
            "Conclusion",
        ],
        "intended_audience": "General audience interested in automotive mechanisms.",
        "sources": [],
        "status": "pending",
    },
    {
        "id": "jet_engine",
        "title": "How a Jet Engine Works",
        "central_question": "How does a jet engine produce thrust from air and fuel?",
        "outline": [
            "Introduction: Newton's third law and thrust",
            "The Brayton cycle: suck, squeeze, bang, blow",
            "Key components: intake, compressor, combustor, turbine, nozzle",
            "Airflow through the engine",
            "Turbojet vs turbofan",
            "Applications and limitations",
            "Conclusion",
        ],
        "intended_audience": "General audience interested in aviation and propulsion.",
        "sources": [],
        "status": "pending",
    },
]

TOPIC_REGISTRY_PATH = os.path.join("data", "topics.json")


@dataclass
class Topic:
    id: str
    title: str
    central_question: str
    outline: List[str]
    intended_audience: str
    sources: List[str] = field(default_factory=list)
    status: str = "pending"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    selected_at: Optional[str] = None
    completed_at: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "Topic":
        return cls(**d)


class TopicPlanner:
    """Manages topic selection, duplicate avoidance, and completion tracking."""

    def __init__(self, registry_path: str = TOPIC_REGISTRY_PATH) -> None:
        self.registry_path = registry_path
        self.topics: List[Topic] = []
        self._load_or_seed()

    def _load_or_seed(self) -> None:
        if os.path.exists(self.registry_path):
            self._load()
        else:
            self.topics = [Topic(**t) for t in DEFAULT_TOPICS]
            self._save()

    def _load(self) -> None:
        with open(self.registry_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        self.topics = [Topic.from_dict(t) for t in data.get("topics", [])]

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.registry_path), exist_ok=True)
        with open(self.registry_path, "w", encoding="utf-8") as f:
            json.dump({"topics": [t.to_dict() for t in self.topics]}, f, indent=2)

    def list_topics(self, status: Optional[str] = None) -> List[Topic]:
        if status:
            return [t for t in self.topics if t.status == status]
        return list(self.topics)

    def get(self, topic_id: str) -> Optional[Topic]:
        for t in self.topics:
            if t.id == topic_id:
                return t
        return None

    def select_automatic(self) -> Optional[Topic]:
        """Pick the first pending topic (deterministic, no duplicates)."""
        for t in self.topics:
            if t.status == "pending":
                t.status = "selected"
                t.selected_at = datetime.now(timezone.utc).isoformat()
                self._save()
                return t
        return None

    def select_manual(self, topic_id: str) -> Optional[Topic]:
        t = self.get(topic_id)
        if t is None:
            return None
        if t.status == "completed":
            raise ValueError(f"Topic '{topic_id}' is already completed; avoid duplicates.")
        t.status = "selected"
        t.selected_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return t

    def mark_completed(self, topic_id: str) -> bool:
        t = self.get(topic_id)
        if t is None:
            return False
        t.status = "completed"
        t.completed_at = datetime.now(timezone.utc).isoformat()
        self._save()
        return True

    def is_duplicate(self, topic_id: str) -> bool:
        t = self.get(topic_id)
        return t is not None and t.status == "completed"

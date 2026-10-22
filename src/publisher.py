"""YouTube publishing — official interface, dry-run by default, credentials from env."""

from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import Optional

PUBLISH_DIR = os.path.join("output", "publish")


@dataclass
class PublishResult:
    topic_id: str
    title: str
    dry_run: bool = True
    uploaded: bool = False
    video_id: Optional[str] = None
    video_url: Optional[str] = None
    error: Optional[str] = None
    confirmed: bool = False
    attempt_count: int = 0
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "PublishResult":
        return cls(**d)


class YouTubePublisher:
    """Optional YouTube Data API v3 publishing with dry-run mode."""

    def __init__(self, publish_dir: str = PUBLISH_DIR) -> None:
        self.publish_dir = publish_dir
        os.makedirs(self.publish_dir, exist_ok=True)
        self.client_id = os.environ.get("YOUTUBE_CLIENT_ID")
        self.client_secret = os.environ.get("YOUTUBE_CLIENT_SECRET")
        self.refresh_token = os.environ.get("YOUTUBE_REFRESH_TOKEN")
        self.credentials_configured = bool(self.client_id and self.client_secret and self.refresh_token)

    def dry_run(self, topic_id: str, title: str, video_file: str) -> PublishResult:
        """Simulate an upload without contacting YouTube. Always safe."""
        result = PublishResult(
            topic_id=topic_id, title=title, dry_run=True, uploaded=False,
            confirmed=False,
        )
        if not video_file or not os.path.exists(video_file):
            result.error = f"Video file not found: {video_file}"
            self._save(result)
            return result
        size = os.path.getsize(video_file)
        result.video_id = "dry-run-video-id-" + topic_id
        result.video_url = f"https://youtube.com/watch?v={result.video_id}"
        result.uploaded = True  # simulated
        result.error = None
        self._save(result)
        return result

    def publish(self, topic_id: str, title: str, video_file: str,
                confirm: bool = False, max_retries: int = 3) -> PublishResult:
        """Real upload. Requires credentials and explicit confirmation."""
        result = PublishResult(topic_id=topic_id, title=title, dry_run=False)

        if not confirm:
            result.error = ("Real upload requires explicit confirmation (confirm=True). "
                            "Use dry_run() to test without credentials.")
            self._save(result)
            return result

        if not self.credentials_configured:
            result.error = ("YouTube credentials not configured. Set YOUTUBE_CLIENT_ID, "
                            "YOUTUBE_CLIENT_SECRET, YOUTUBE_REFRESH_TOKEN.")
            self._save(result)
            return result

        if not video_file or not os.path.exists(video_file):
            result.error = f"Video file not found: {video_file}"
            self._save(result)
            return result

        # Attempt upload with retries.
        last_error = None
        for attempt in range(1, max_retries + 1):
            result.attempt_count = attempt
            try:
                uploaded = self._attempt_upload(video_file, title)
                if uploaded:
                    result.uploaded = True
                    result.video_id = "yt-" + topic_id + "-" + str(int(time.time()))
                    result.video_url = f"https://youtube.com/watch?v={result.video_id}"
                    result.error = None
                    self._save(result)
                    return result
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                time.sleep(1 * attempt)
        result.error = f"Upload failed after {max_retries} attempts: {last_error}"
        self._save(result)
        return result

    def _attempt_upload(self, video_file: str, title: str) -> bool:
        # Placeholder for real YouTube Data API v3 resumable upload.
        # To implement: use google-auth + googleapiclient with the env credentials.
        # Not installed by default to avoid mandatory dependency.
        raise NotImplementedError(
            "Real YouTube upload not implemented. Install google-api-python-client "
            "and google-auth-oauthlib, then wire the env credentials here."
        )

    def _save(self, result: PublishResult) -> None:
        path = os.path.join(self.publish_dir, f"{result.topic_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

    def load(self, topic_id: str) -> Optional[PublishResult]:
        path = os.path.join(self.publish_dir, f"{topic_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return PublishResult.from_dict(json.load(f))

"""Research & fact-checking engine — gathers sources, maps claims to evidence."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional
from urllib.request import urlopen, Request
from urllib.error import URLError, HTTPError


@dataclass
class Source:
    url: str
    title: str
    kind: str  # "documentation", "primary", "educational", "publication", "other"
    accessed_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    fetched_ok: bool = False
    fetch_error: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Claim:
    text: str
    category: str  # "fact", "estimate", "uncertainty", "unsupported"
    source_urls: List[str] = field(default_factory=list)
    evidence_quote: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class ResearchResult:
    topic_id: str
    topic_title: str
    sources: List[Source] = field(default_factory=list)
    claims: List[Claim] = field(default_factory=list)
    network_available: bool = False
    network_error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "ResearchResult":
        return cls(
            topic_id=d["topic_id"],
            topic_title=d["topic_title"],
            sources=[Source(**s) for s in d.get("sources", [])],
            claims=[Claim(**c) for c in d.get("claims", [])],
            network_available=d.get("network_available", False),
            network_error=d.get("network_error"),
            created_at=d.get("created_at", ""),
        )


RESEARCH_DIR = os.path.join("data", "research")


class ResearchEngine:
    """Searches accessible online sources and records claims with evidence."""

    def __init__(self, research_dir: str = RESEARCH_DIR) -> None:
        self.research_dir = research_dir
        os.makedirs(self.research_dir, exist_ok=True)

    def _fetch(self, url: str, timeout: int = 12) -> Optional[str]:
        try:
            req = Request(url, headers={"User-Agent": "youtube-automation/0.1 (educational research)"})
            with urlopen(req, timeout=timeout) as resp:
                data = resp.read(200000)
                return data.decode("utf-8", errors="replace")
        except (URLError, HTTPError, OSError, ValueError) as exc:
            return None

    def research_topic(self, topic: dict) -> ResearchResult:
        result = ResearchResult(topic_id=topic["id"], topic_title=topic["title"])

        # Probe network availability.
        probe = self._fetch("https://example.com", timeout=8)
        result.network_available = probe is not None
        if not result.network_available:
            result.network_error = "Unable to reach example.com; offline."
            self._save(result)
            return result

        # Candidate sources (technical / educational / primary).
        candidate_urls: List[str] = []
        topic_id = topic["id"]
        if topic_id == "four_stroke_engine":
            candidate_urls = [
                "https://en.wikipedia.org/wiki/Four-stroke_engine",
                "https://en.wikipedia.org/wiki/Internal_combustion_engine",
            ]
        elif topic_id == "car_differential":
            candidate_urls = [
                "https://en.wikipedia.org/wiki/Differential_(mechanical_device)",
            ]
        elif topic_id == "jet_engine":
            candidate_urls = [
                "https://en.wikipedia.org/wiki/Jet_engine",
            ]

        for url in candidate_urls:
            html = self._fetch(url)
            title = self._guess_title(url)
            source = Source(url=url, title=title, kind="educational")
            if html is not None:
                source.fetched_ok = True
                snippet = self._extract_snippet(html)
                if snippet:
                    result.claims.append(
                        Claim(
                            text=snippet,
                            category="fact",
                            source_urls=[url],
                            evidence_quote=snippet[:300],
                        )
                    )
            else:
                source.fetch_error = "fetch failed"
            result.sources.append(source)

        self._save(result)
        return result

    def _guess_title(self, url: str) -> str:
        return url.split("//")[-1].split("/")[0]

    def _extract_snippet(self, html: str) -> Optional[str]:
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.S | re.I)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.S | re.I)
        text = re.sub(r"<[^>]+>", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text[:500] if text else None

    def _save(self, result: ResearchResult) -> None:
        path = os.path.join(self.research_dir, f"{result.topic_id}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump(result.to_dict(), f, indent=2)

    def load(self, topic_id: str) -> Optional[ResearchResult]:
        path = os.path.join(self.research_dir, f"{topic_id}.json")
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return ResearchResult.from_dict(json.load(f))

    def summarize(self, result: ResearchResult) -> str:
        lines = [
            f"Research for {result.topic_title} ({result.topic_id})",
            f"Network available: {result.network_available}",
            f"Sources fetched: {sum(1 for s in result.sources if s.fetched_ok)}/{len(result.sources)}",
            f"Claims recorded: {len(result.claims)}",
        ]
        if result.network_error:
            lines.append(f"Network error: {result.network_error}")
        for s in result.sources:
            lines.append(f"  - {s.title} ({s.url}) ok={s.fetched_ok}")
        return "\n".join(lines)

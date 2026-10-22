"""Scheduler & monitoring — unattended cloud schedule, status, retry, resume."""

from __future__ import annotations

import json
import os
import argparse
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from typing import List, Optional

STATE_DIR = os.path.join(".state")
LOGS_DIR = os.path.join("logs")


@dataclass
class JobRecord:
    job_id: str
    topic_id: str
    status: str  # pending, running, completed, failed, retrying
    created_at: str
    started_at: Optional[str] = None
    completed_at: Optional[str] = None
    retry_count: int = 0
    max_retries: int = 3
    error: Optional[str] = None
    output_files: List[str] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "JobRecord":
        return cls(**d)


class Scheduler:
    """Lightweight file-based scheduler with status, retries, duplicate prevention, safe resume."""

    def __init__(self, state_dir: str = STATE_DIR, logs_dir: str = LOGS_DIR,
                 max_stage_retries: int = 3) -> None:
        self.state_dir = state_dir
        self.logs_dir = logs_dir
        self.max_stage_retries = max_stage_retries
        os.makedirs(self.state_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)

    def _job_path(self, job_id: str) -> str:
        return os.path.join(self.state_dir, f"{job_id}.json")

    def create_job(self, job_id: str, topic_id: str) -> JobRecord:
        """Create a job. Prevents duplicates by job_id."""
        if self.get_job(job_id) is not None:
            raise ValueError(f"Job {job_id} already exists (duplicate prevention).")
        job = JobRecord(
            job_id=job_id, topic_id=topic_id, status="pending",
            created_at=datetime.now(timezone.utc).isoformat(),
            max_retries=self.max_stage_retries,
        )
        self._save(job)
        return job

    def get_job(self, job_id: str) -> Optional[JobRecord]:
        path = self._job_path(job_id)
        if not os.path.exists(path):
            return None
        with open(path, "r", encoding="utf-8") as f:
            return JobRecord.from_dict(json.load(f))

    def start(self, job_id: str) -> bool:
        job = self.get_job(job_id)
        if job is None:
            return False
        if job.status == "completed":
            return True  # already done, safe resume
        job.status = "running"
        job.started_at = datetime.now(timezone.utc).isoformat()
        self._save(job)
        self._log(job_id, f"Job started at {job.started_at}")
        return True

    def complete(self, job_id: str, output_files: List[str]) -> None:
        job = self.get_job(job_id)
        if job is None:
            return
        job.status = "completed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        job.output_files = output_files
        self._save(job)
        self._log(job_id, f"Job completed. Outputs: {output_files}")

    def fail(self, job_id: str, error: str, retry: bool = False) -> bool:
        job = self.get_job(job_id)
        if job is None:
            return False
        job.error = error
        if retry and job.retry_count < job.max_retries:
            job.retry_count += 1
            job.status = "retrying"
            self._save(job)
            self._log(job_id, f"Retry {job.retry_count}/{job.max_retries}: {error}")
            return True
        job.status = "failed"
        job.completed_at = datetime.now(timezone.utc).isoformat()
        self._save(job)
        self._log(job_id, f"Job failed: {error}")
        return False

    def status(self) -> dict:
        jobs: List[JobRecord] = []
        if os.path.isdir(self.state_dir):
            for fname in os.listdir(self.state_dir):
                if fname.endswith(".json"):
                    with open(os.path.join(self.state_dir, fname), "r", encoding="utf-8") as f:
                        jobs.append(JobRecord.from_dict(json.load(f)))
        jobs.sort(key=lambda j: j.created_at, reverse=True)
        return {
            "total_jobs": len(jobs),
            "jobs": [j.to_dict() for j in jobs],
        }

    def _save(self, job: JobRecord) -> None:
        with open(self._job_path(job.job_id), "w", encoding="utf-8") as f:
            json.dump(job.to_dict(), f, indent=2)

    def _log(self, job_id: str, message: str) -> None:
        path = os.path.join(self.logs_dir, f"{job_id}.log")
        ts = datetime.now(timezone.utc).isoformat()
        with open(path, "a", encoding="utf-8") as f:
            f.write(f"[{ts}] {message}\n")

    def report(self) -> str:
        st = self.status()
        lines = [f"Scheduler status: {st['total_jobs']} job(s)"]
        for j in st["jobs"]:
            lines.append(f"  {j['job_id']} topic={j['topic_id']} status={j['status']} "
                         f"retries={j['retry_count']}/{j['max_retries']}")
            if j.get("error"):
                lines.append(f"    error: {j['error']}")
        return "\n".join(lines)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="YouTube Automation scheduler")
    sub = parser.add_subparsers(dest="cmd")
    sub.add_parser("status", help="show scheduler status report")
    sub.add_parser("report", help="alias for status")
    args = parser.parse_args(argv)
    sched = Scheduler()
    if args.cmd in ("status", "report") or args.cmd is None:
        print(sched.report())
        return 0
    parser.print_help()
    return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())

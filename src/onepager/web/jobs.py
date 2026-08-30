"""In-memory job store.

A deck analysis takes roughly a minute, which is too long to hold an HTTP request open
behind a proxy. Uploads therefore create a job, the work runs on a worker thread, and the
browser polls. State lives in memory: one process, no database, jobs expire on a TTL.
Results are held as bytes so nothing sensitive is left on disk.
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass, field
from typing import Literal

from ..config import JOB_TTL_MINUTES

Status = Literal["queued", "extracting", "analyzing", "rendering", "done", "error"]

#: Human-facing progress copy. The client renders these verbatim.
STAGE_TEXT: dict[Status, str] = {
    "queued": "Queued",
    "extracting": "Reading the deck",
    "analyzing": "Analyzing the team with Claude (this is the slow part, ~60-90s)",
    "rendering": "Rendering the one-pager",
    "done": "Complete",
    "error": "Failed",
}


@dataclass
class Job:
    id: str
    filename: str
    status: Status = "queued"
    created_at: float = field(default_factory=time.time)
    finished_at: float | None = None
    detail: str = ""
    """Error message, or a note about the run."""
    notes: list[str] = field(default_factory=list)
    """Non-fatal observations: extraction fallbacks, one-page degradations."""
    exit_code: int | None = None
    company_name: str | None = None
    team_score: int | None = None
    evidence_quality: int | None = None
    low_confidence: bool = False
    pdf: bytes | None = None
    analysis_json: str | None = None
    slides: int | None = None
    used_vision: bool = False
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd: float = 0.0
    emailed: bool = False
    """Whether a copy was successfully mailed to the configured recipients."""

    @property
    def elapsed(self) -> float:
        return (self.finished_at or time.time()) - self.created_at

    @property
    def download_stem(self) -> str:
        stem = self.filename.rsplit(".", 1)[0] or "deck"
        safe = "".join(ch if ch.isalnum() or ch in "-_ " else "_" for ch in stem).strip()
        return (safe or "deck")[:80]

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "filename": self.filename,
            "status": self.status,
            "stage_text": STAGE_TEXT[self.status],
            "detail": self.detail,
            "notes": self.notes,
            "exit_code": self.exit_code,
            "elapsed_seconds": round(self.elapsed, 1),
            "company_name": self.company_name,
            "team_score": self.team_score,
            "evidence_quality": self.evidence_quality,
            "low_confidence": self.low_confidence,
            "slides": self.slides,
            "used_vision": self.used_vision,
            "has_pdf": self.pdf is not None,
            "tokens": {"input": self.input_tokens, "output": self.output_tokens},
            "cost_usd": round(self.cost_usd, 4),
            "emailed": self.emailed,
        }


class JobStore:
    """Thread-safe job registry with TTL eviction."""

    def __init__(self, ttl_minutes: int = JOB_TTL_MINUTES) -> None:
        self._jobs: dict[str, Job] = {}
        self._lock = threading.Lock()
        self.ttl_seconds = ttl_minutes * 60

    def create(self, filename: str) -> Job:
        job = Job(id=secrets.token_urlsafe(12), filename=filename)
        with self._lock:
            self._jobs[job.id] = job
        return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **fields) -> Job | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if job is None:
                return None
            for key, value in fields.items():
                setattr(job, key, value)
            if job.status in ("done", "error") and job.finished_at is None:
                job.finished_at = time.time()
            return job

    def sweep(self) -> int:
        """Drop expired jobs. Returns how many were evicted."""
        cutoff = time.time() - self.ttl_seconds
        with self._lock:
            stale = [jid for jid, job in self._jobs.items() if job.created_at < cutoff]
            for jid in stale:
                del self._jobs[jid]
        return len(stale)

    def __len__(self) -> int:
        with self._lock:
            return len(self._jobs)

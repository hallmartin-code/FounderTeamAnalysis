"""The worker: runs one deck through extract -> analyze -> render, into a Job.

This is the same pipeline the CLI drives. It maps every failure onto the CLI's exit codes
so the web app and the terminal agree about what went wrong.
"""

from __future__ import annotations

import logging
import tempfile
from datetime import date
from pathlib import Path

from ..analyze import AnalysisClient, AuthFailure, BadModelOutput
from ..config import ExitCode
from ..extract import ExtractionError, NoContentError, extract
from ..models import TeamAnalysis
from ..notify import is_configured as email_configured
from ..notify import send_onepager
from ..render import RenderError, render
from .jobs import Job, JobStore

_log = logging.getLogger("onepager.web")


class _WarningCollector(logging.Handler):
    """Captures the renderer's one-page degradation warnings for this job."""

    def __init__(self) -> None:
        super().__init__(level=logging.WARNING)
        self.messages: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.messages.append(record.getMessage())


def run_job(
    store: JobStore,
    job_id: str,
    data: bytes,
    filename: str,
    company: str | None = None,
    model: str | None = None,
) -> None:
    """Execute one analysis end to end. Never raises; failures land on the job."""
    suffix = Path(filename).suffix.lower() or ".pdf"
    collector = _WarningCollector()
    logging.getLogger("onepager").addHandler(collector)

    with tempfile.TemporaryDirectory(prefix="onepager-") as tmp:
        deck_path = Path(tmp) / f"upload{suffix}"
        deck_path.write_bytes(data)
        try:
            store.update(job_id, status="extracting")
            deck = extract(deck_path)
            store.update(
                job_id,
                slides=len(deck.slides),
                used_vision=deck.used_vision,
                notes=list(deck.notes),
            )

            store.update(job_id, status="analyzing")
            client = AnalysisClient(model=model)
            analysis: TeamAnalysis = client.analyze(deck, company)

            store.update(job_id, status="rendering")
            out = Path(tmp) / "onepager.pdf"
            render(analysis, out, filename, generated=date.today())
            pdf = out.read_bytes()

            job = store.get(job_id)
            notes = list(job.notes) if job else []
            notes.extend(m for m in collector.messages if "one-page fit" in m)

            # Notification is a side channel: a failed send must not fail the job.
            emailed = False
            if email_configured():
                result = send_onepager(
                    analysis,
                    pdf,
                    filename,
                    analysis_json=analysis.model_dump_json(indent=2),
                    meta_line=(
                        f"{len(deck.slides)} slides - "
                        f"{client.usage.input_tokens} in / {client.usage.output_tokens} out - "
                        f"~${client.usage.cost_usd:.3f}"
                    ),
                    notes=notes,
                )
                emailed = result.sent
                notes.append(result.note)

            store.update(
                job_id,
                status="done",
                emailed=emailed,
                pdf=pdf,
                analysis_json=analysis.model_dump_json(indent=2),
                company_name=analysis.company_name,
                team_score=analysis.team_score,
                evidence_quality=analysis.evidence_quality,
                low_confidence=analysis.low_confidence,
                input_tokens=client.usage.input_tokens,
                output_tokens=client.usage.output_tokens,
                cost_usd=client.usage.cost_usd,
                notes=notes,
                exit_code=int(ExitCode.OK),
            )
        except NoContentError as exc:
            _fail(store, job_id, exc, ExitCode.NO_CONTENT)
        except ExtractionError as exc:
            _fail(store, job_id, exc, ExitCode.UNSUPPORTED_FILE)
        except AuthFailure as exc:
            _fail(store, job_id, exc, ExitCode.API_FAILURE)
        except BadModelOutput as exc:
            _fail(store, job_id, exc, ExitCode.BAD_MODEL_OUTPUT)
        except RenderError as exc:
            _fail(store, job_id, exc, ExitCode.RENDER_FAILURE)
        except Exception as exc:  # a bug, not a handled condition - log it fully
            _log.exception("unhandled failure in job %s", job_id)
            _fail(store, job_id, exc, ExitCode.RENDER_FAILURE, generic=True)
        finally:
            logging.getLogger("onepager").removeHandler(collector)


def _fail(
    store: JobStore,
    job_id: str,
    exc: Exception,
    code: ExitCode,
    generic: bool = False,
) -> Job | None:
    # Never surface a raw traceback or an API key to the browser.
    detail = "Something went wrong while generating the one-pager." if generic else str(exc)
    return store.update(job_id, status="error", detail=detail, exit_code=int(code))

"""FastAPI application.

Upload a deck, poll a job, download the one-pager. The API key never leaves the server and
is never echoed into a response.
"""

from __future__ import annotations

import asyncio
import contextlib
import secrets
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Annotated

from fastapi import (
    APIRouter,
    Depends,
    FastAPI,
    File,
    Form,
    HTTPException,
    Request,
    UploadFile,
    status,
)
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, Response
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from .. import __version__
from ..config import JOB_TTL_MINUTES, MAX_UPLOAD_MB, app_password, model_id, resend_recipients
from ..config import api_key as configured_api_key
from ..notify import is_configured as email_configured
from ..render import render
from ..template import blank_analysis
from .jobs import JobStore
from .pipeline import run_job
from .ui import render_page

SUPPORTED_SUFFIXES = (".pdf", ".pptx", ".ppt")
_SWEEP_INTERVAL_SECONDS = 300

_security = HTTPBasic(auto_error=False)


def _require_auth(
    credentials: Annotated[HTTPBasicCredentials | None, Depends(_security)],
) -> None:
    """Shared-secret gate. Open when APP_PASSWORD is unset, which is local-dev only."""
    expected = app_password()
    if expected is None:
        return
    supplied = credentials.password if credentials else ""
    if not secrets.compare_digest(supplied, expected):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authorized.",
            headers={"WWW-Authenticate": 'Basic realm="deck-onepager"'},
        )


def create_app() -> FastAPI:
    store = JobStore()
    tasks: set[asyncio.Task] = set()

    @contextlib.asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        sweeper = asyncio.create_task(_sweep_forever(store))
        try:
            yield
        finally:
            sweeper.cancel()
            for task in list(tasks):
                task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await sweeper

    app = FastAPI(
        title="deck-onepager",
        version=__version__,
        description="Founder & team one-pager generator for TEN Capital.",
        lifespan=lifespan,
        docs_url="/api/docs",
        redoc_url=None,
    )

    gated = APIRouter(dependencies=[Depends(_require_auth)])

    # --- pages -------------------------------------------------------------------------

    @gated.get("/", response_class=HTMLResponse)
    async def index() -> HTMLResponse:
        return HTMLResponse(
            render_page(
                accept=SUPPORTED_SUFFIXES,
                max_upload_mb=MAX_UPLOAD_MB,
                job_ttl_minutes=JOB_TTL_MINUTES,
                email_to=resend_recipients() if email_configured() else None,
            )
        )

    @app.get("/healthz", response_class=PlainTextResponse)
    async def healthz() -> PlainTextResponse:
        """Unauthenticated so Railway can health-check without the password."""
        ready = configured_api_key() is not None
        body = (
            f"ok version={__version__} model={model_id()} "
            f"api_key={'set' if ready else 'MISSING'}"
        )
        return PlainTextResponse(body, status_code=200 if ready else 503)

    # --- jobs --------------------------------------------------------------------------

    @gated.post("/api/jobs", status_code=status.HTTP_202_ACCEPTED)
    async def create_job(
        request: Request,
        deck: Annotated[UploadFile, File(description="Pitch deck: .pdf, .pptx or .ppt")],
        company: Annotated[str | None, Form()] = None,
        model: Annotated[str | None, Form()] = None,
    ) -> JSONResponse:
        filename = (deck.filename or "deck.pdf").strip()
        if not filename.lower().endswith(SUPPORTED_SUFFIXES):
            raise HTTPException(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                f"Unsupported file type. Upload one of: {', '.join(SUPPORTED_SUFFIXES)}.",
            )

        data = await _read_capped(deck)
        if not data:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "The uploaded file is empty.")

        if configured_api_key() is None:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "ANTHROPIC_API_KEY is not configured on the server.",
            )

        job = store.create(filename)
        task = asyncio.create_task(
            asyncio.to_thread(
                run_job,
                store,
                job.id,
                data,
                filename,
                (company or "").strip() or None,
                (model or "").strip() or None,
            )
        )
        tasks.add(task)
        task.add_done_callback(tasks.discard)

        return JSONResponse(
            job.to_dict(),
            status_code=status.HTTP_202_ACCEPTED,
            headers={"Location": str(request.url_for("get_job", job_id=job.id))},
        )

    @gated.get("/api/jobs/{job_id}", name="get_job")
    async def get_job(job_id: str) -> JSONResponse:
        return JSONResponse(_lookup(store, job_id).to_dict())

    @gated.get("/api/jobs/{job_id}/pdf")
    async def get_job_pdf(job_id: str) -> Response:
        job = _lookup(store, job_id)
        if job.pdf is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Job is {job.status}, not done.")
        return Response(
            job.pdf,
            media_type="application/pdf",
            headers=_attachment(f"{job.download_stem}_Team_OnePager.pdf"),
        )

    @gated.get("/api/jobs/{job_id}/json")
    async def get_job_json(job_id: str) -> Response:
        job = _lookup(store, job_id)
        if job.analysis_json is None:
            raise HTTPException(status.HTTP_409_CONFLICT, f"Job is {job.status}, not done.")
        return Response(
            job.analysis_json,
            media_type="application/json",
            headers=_attachment(f"{job.download_stem}_Team_Analysis.json"),
        )

    # --- the blank template --------------------------------------------------------------

    @gated.get("/api/template.pdf")
    async def template_pdf() -> Response:
        with tempfile.TemporaryDirectory(prefix="onepager-tpl-") as tmp:
            out = Path(tmp) / "template.pdf"
            render(blank_analysis(), out, "[DECK FILENAME]")
            data = out.read_bytes()
        return Response(
            data,
            media_type="application/pdf",
            headers=_attachment("TEN_Capital_OnePager_Template.pdf"),
        )

    app.include_router(gated)
    return app


# --- helpers ------------------------------------------------------------------------------


def _attachment(filename: str) -> dict[str, str]:
    return {"Content-Disposition": f'attachment; filename="{filename}"'}


def _lookup(store: JobStore, job_id: str):
    job = store.get(job_id)
    if job is None:
        raise HTTPException(
            status.HTTP_404_NOT_FOUND, "No such job. It may have expired; upload the deck again."
        )
    return job


async def _read_capped(upload: UploadFile) -> bytes:
    """Stream the upload, refusing anything over the cap instead of buffering it whole."""
    cap = MAX_UPLOAD_MB * 1024 * 1024
    chunks: list[bytes] = []
    total = 0
    while chunk := await upload.read(1024 * 1024):
        total += len(chunk)
        if total > cap:
            raise HTTPException(
                status.HTTP_413_CONTENT_TOO_LARGE,
                f"Deck is larger than the {MAX_UPLOAD_MB} MB limit.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


async def _sweep_forever(store: JobStore) -> None:
    while True:
        await asyncio.sleep(_SWEEP_INTERVAL_SECONDS)
        store.sweep()


app = create_app()

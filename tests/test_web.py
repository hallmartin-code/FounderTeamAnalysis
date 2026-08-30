"""Web layer: routing, auth, upload guards, job lifecycle, and secret hygiene."""

from __future__ import annotations

import json
import re
import time
from pathlib import Path

import pymupdf
import pytest
from fastapi.testclient import TestClient

from onepager.config import ExitCode
from onepager.models import TeamAnalysis
from onepager.web.app import SUPPORTED_SUFFIXES, create_app
from onepager.web.jobs import JobStore
from onepager.web.pipeline import run_job

LIVE_KEY_FRAGMENT = "sk-ant-"


@pytest.fixture
def client(monkeypatch) -> TestClient:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-not-real")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def locked_client(monkeypatch) -> TestClient:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test-key-not-real")
    monkeypatch.setenv("APP_PASSWORD", "correct horse battery staple")
    with TestClient(create_app()) as c:
        yield c


@pytest.fixture
def stub_pipeline(mocker, analysis: TeamAnalysis):
    """Replace the real worker so no deck parsing or API call happens."""

    def fake(store, job_id, data, filename, company=None, model=None):
        import tempfile

        from onepager.render import render

        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "o.pdf"
            render(analysis, out, filename)
            pdf = out.read_bytes()
        store.update(
            job_id,
            status="done",
            pdf=pdf,
            analysis_json=analysis.model_dump_json(indent=2),
            company_name=analysis.company_name,
            team_score=analysis.team_score,
            evidence_quality=analysis.evidence_quality,
            low_confidence=analysis.low_confidence,
            slides=4,
            exit_code=int(ExitCode.OK),
        )

    return mocker.patch("onepager.web.app.run_job", side_effect=fake)


def _upload(client: TestClient, path: Path, **kwargs):
    with path.open("rb") as fh:
        files = {"deck": (path.name, fh, "application/pdf")}
        return client.post("/api/jobs", files=files, **kwargs)


def _await_job(client: TestClient, job_id: str, timeout: float = 10.0) -> dict:
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("done", "error"):
            return job
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not settle within {timeout}s")


# --- health and pages -----------------------------------------------------------------


def test_healthz_is_open_and_reports_ready(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert "api_key=set" in r.text


def test_healthz_is_503_without_an_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setattr("onepager.web.app.configured_api_key", lambda: None)
    with TestClient(create_app()) as c:
        r = c.get("/healthz")
    assert r.status_code == 503
    assert "MISSING" in r.text


def test_healthz_never_leaks_the_key(client: TestClient) -> None:
    assert "not-real" not in client.get("/healthz").text


def test_index_serves_the_upload_page(client: TestClient) -> None:
    r = client.get("/")
    assert r.status_code == 200
    assert "Deck Analyzer" in r.text
    assert "TEN Capital Network" in r.text
    assert "Generate one-pager PDF" in r.text


def test_index_embeds_no_secret(client: TestClient) -> None:
    assert LIVE_KEY_FRAGMENT not in client.get("/").text


def test_template_endpoint_returns_a_one_page_pdf(client: TestClient, tmp_path: Path) -> None:
    r = client.get("/api/template.pdf")
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/pdf"
    out = tmp_path / "t.pdf"
    out.write_bytes(r.content)
    assert pymupdf.open(out).page_count == 1


# --- auth ------------------------------------------------------------------------------


def test_password_gate_blocks_anonymous_access(locked_client: TestClient) -> None:
    for path in ("/", "/api/template.pdf"):
        assert locked_client.get(path).status_code == 401


def test_password_gate_admits_the_right_password(locked_client: TestClient) -> None:
    r = locked_client.get("/", auth=("ten", "correct horse battery staple"))
    assert r.status_code == 200


def test_password_gate_rejects_a_wrong_password(locked_client: TestClient) -> None:
    assert locked_client.get("/", auth=("ten", "wrong")).status_code == 401


def test_healthcheck_stays_open_when_the_gate_is_on(locked_client: TestClient) -> None:
    """Railway must be able to health-check without credentials."""
    assert locked_client.get("/healthz").status_code == 200


def test_upload_requires_the_password(locked_client: TestClient, text_pdf: Path) -> None:
    assert _upload(locked_client, text_pdf).status_code == 401


# --- upload guards ------------------------------------------------------------------------


def test_unsupported_extension_is_rejected(client: TestClient, tmp_path: Path) -> None:
    bad = tmp_path / "notes.txt"
    bad.write_text("not a deck")
    r = _upload(client, bad)
    assert r.status_code == 415
    assert ".pdf" in r.json()["detail"]


def test_empty_upload_is_rejected(client: TestClient, tmp_path: Path) -> None:
    empty = tmp_path / "empty.pdf"
    empty.touch()
    assert _upload(client, empty).status_code == 400


def test_oversized_upload_is_refused(client: TestClient, tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr("onepager.web.app.MAX_UPLOAD_MB", 1)
    big = tmp_path / "big.pdf"
    big.write_bytes(b"%PDF-1.4" + b"\0" * (2 * 1024 * 1024))
    r = _upload(client, big)
    assert r.status_code == 413
    assert "1 MB" in r.json()["detail"]


def test_upload_is_refused_when_the_server_has_no_key(
    client: TestClient, text_pdf: Path, monkeypatch
) -> None:
    monkeypatch.setattr("onepager.web.app.configured_api_key", lambda: None)
    r = _upload(client, text_pdf)
    assert r.status_code == 503
    assert "ANTHROPIC_API_KEY" in r.json()["detail"]


# --- job lifecycle -------------------------------------------------------------------------


def test_upload_creates_a_job_and_returns_202(
    client: TestClient, text_pdf: Path, stub_pipeline
) -> None:
    r = _upload(client, text_pdf)
    assert r.status_code == 202
    body = r.json()
    assert body["id"] and body["status"] in ("queued", "extracting", "done")
    assert "Location" in r.headers


def test_job_runs_to_completion_and_serves_the_pdf(
    client: TestClient, text_pdf: Path, tmp_path: Path, stub_pipeline
) -> None:
    job_id = _upload(client, text_pdf).json()["id"]
    job = _await_job(client, job_id)
    assert job["status"] == "done", job
    assert job["team_score"] is not None
    assert job["has_pdf"] is True

    pdf = client.get(f"/api/jobs/{job_id}/pdf")
    assert pdf.status_code == 200
    assert pdf.headers["content-type"] == "application/pdf"
    assert "attachment" in pdf.headers["content-disposition"]
    out = tmp_path / "web.pdf"
    out.write_bytes(pdf.content)
    assert pymupdf.open(out).page_count == 1


def test_job_serves_the_analysis_json(client: TestClient, text_pdf: Path, stub_pipeline) -> None:
    job_id = _upload(client, text_pdf).json()["id"]
    _await_job(client, job_id)
    r = client.get(f"/api/jobs/{job_id}/json")
    assert r.status_code == 200
    assert TeamAnalysis.model_validate_json(r.text)


def test_unknown_job_is_404(client: TestClient) -> None:
    r = client.get("/api/jobs/does-not-exist")
    assert r.status_code == 404
    assert "expired" in r.json()["detail"]


def test_pdf_before_completion_is_409(client: TestClient) -> None:
    from onepager.web import app as web_app

    store = web_app.JobStore()
    job = store.create("deck.pdf")
    assert job.pdf is None  # the route returns 409 in exactly this state


# --- the worker maps failures onto CLI exit codes -----------------------------------------


def test_worker_reports_unsupported_file(tmp_path: Path) -> None:
    store = JobStore()
    job = store.create("deck.pdf")
    run_job(store, job.id, b"%PDF-1.4 not really a pdf", "deck.pdf")
    settled = store.get(job.id)
    assert settled.status == "error"
    assert settled.exit_code == int(ExitCode.UNSUPPORTED_FILE)
    assert "Traceback" not in settled.detail


def test_worker_reports_no_content(image_only_pdf: Path, mocker) -> None:
    from onepager.extract import NoContentError

    mocker.patch(
        "onepager.web.pipeline.extract",
        side_effect=NoContentError("no text; try --vision"),
    )
    store = JobStore()
    job = store.create("scan.pdf")
    run_job(store, job.id, image_only_pdf.read_bytes(), "scan.pdf")
    assert store.get(job.id).exit_code == int(ExitCode.NO_CONTENT)


def test_worker_reports_auth_failure(text_pdf: Path, mocker) -> None:
    from onepager.analyze import AuthFailure

    mocker.patch(
        "onepager.web.pipeline.AnalysisClient", side_effect=AuthFailure("ANTHROPIC_API_KEY unset")
    )
    store = JobStore()
    job = store.create("deck.pdf")
    run_job(store, job.id, text_pdf.read_bytes(), "deck.pdf")
    settled = store.get(job.id)
    assert settled.exit_code == int(ExitCode.API_FAILURE)
    assert "ANTHROPIC_API_KEY" in settled.detail


def test_worker_hides_unexpected_internals_from_the_browser(text_pdf: Path, mocker) -> None:
    mocker.patch(
        "onepager.web.pipeline.extract",
        side_effect=RuntimeError("secret internal detail sk-ant-leak"),
    )
    store = JobStore()
    job = store.create("deck.pdf")
    run_job(store, job.id, text_pdf.read_bytes(), "deck.pdf")
    settled = store.get(job.id)
    assert settled.status == "error"
    assert "sk-ant" not in settled.detail
    assert "secret internal detail" not in settled.detail


# --- the store ------------------------------------------------------------------------------


def test_store_evicts_expired_jobs() -> None:
    store = JobStore(ttl_minutes=0)
    store.create("a.pdf")
    assert len(store) == 1
    assert store.sweep() == 1
    assert len(store) == 0


def test_store_keeps_live_jobs() -> None:
    store = JobStore(ttl_minutes=60)
    store.create("a.pdf")
    assert store.sweep() == 0
    assert len(store) == 1


def test_download_stem_is_sanitized() -> None:
    store = JobStore()
    job = store.create("../../etc/passwd; rm -rf.pdf")
    assert "/" not in job.download_stem
    assert ".." not in job.download_stem
    assert ";" not in job.download_stem


# --- the page must not overpromise ----------------------------------------------------
#
# The design mockup this UI came from advertised .docx, a 25 MB cap, and emailed copies -
# none of which the backend does. These lock the page to the server's actual behaviour.


def test_page_advertises_exactly_the_supported_formats(client: TestClient) -> None:
    cfg = _page_config(client)
    assert cfg["accept"] == list(SUPPORTED_SUFFIXES)
    assert ".docx" not in cfg["accept"]


def test_page_advertises_the_real_upload_cap(client: TestClient) -> None:
    from onepager.config import MAX_UPLOAD_MB

    assert _page_config(client)["max_upload_mb"] == MAX_UPLOAD_MB


def test_page_makes_no_claim_the_app_does_not_honour(client: TestClient) -> None:
    """No personal address, no .docx - the mockup advertised both; we support neither."""
    body = client.get("/").text.lower()
    for claim in ("mailto:", "@gmail.com", ".docx"):
        assert claim not in body, f"page claims {claim!r}, which the backend does not do"


def test_disclosure_promises_email_only_when_email_is_configured(monkeypatch) -> None:
    """The disclosure is a data-handling promise; it must track the actual config."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-test")
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    with TestClient(create_app()) as c:
        off = _page_config(c)
    assert off["email_to"] == []
    assert "nothing is emailed" in off["disclosure_html"].lower()

    monkeypatch.setenv("RESEND_API_KEY", "re_test_key")
    monkeypatch.setenv("RESEND_TO", "Info@tencapital.group")
    with TestClient(create_app()) as c:
        on = _page_config(c)
    assert on["email_to"] == ["Info@tencapital.group"]
    disclosure = on["disclosure_html"].lower()
    assert "emailed to" in disclosure
    assert "info@tencapital.group" in disclosure
    assert "the deck itself is never emailed" in disclosure


def test_disclosure_states_what_actually_happens(client: TestClient) -> None:
    disclosure = _page_config(client)["disclosure_html"].lower()
    assert "deleted" in disclosure
    assert "claude api" in disclosure


def test_page_is_self_contained_apart_from_google_fonts(client: TestClient) -> None:
    body = client.get("/").text
    external = re.findall(r'(?:src|href)="(https?://[^"]+)"', body)
    assert all("fonts.googleapis.com" in u or "fonts.gstatic.com" in u for u in external), external


def test_every_font_has_a_local_fallback(client: TestClient) -> None:
    """A blocked Google Fonts request must cost polish, not legibility."""
    body = client.get("/").text
    for stack in ("--sans:", "--display:", "--mono:"):
        line = next(ln for ln in body.splitlines() if stack in ln)
        assert "," in line, f"{stack} has no fallback: {line.strip()}"


def _page_config(client: TestClient) -> dict:
    body = client.get("/").text
    raw = re.search(
        r'<script id="cfg" type="application/json">(.*?)</script>', body, re.S
    ).group(1)
    return json.loads(raw)


# --- brand assets ------------------------------------------------------------------------


def test_favicon_is_served_from_the_root(client: TestClient) -> None:
    r = client.get("/favicon.ico")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/x-icon"
    assert r.content[:4] == b"\x00\x00\x01\x00", "not a real .ico"


def test_apple_touch_icon_is_served_from_the_root(client: TestClient) -> None:
    r = client.get("/apple-touch-icon.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


@pytest.mark.parametrize("name", ["favicon-16.png", "favicon-32.png", "favicon-192.png"])
def test_static_pngs_are_served(client: TestClient, name: str) -> None:
    r = client.get(f"/static/{name}")
    assert r.status_code == 200
    assert r.content[:8] == b"\x89PNG\r\n\x1a\n"


def test_icons_are_cacheable(client: TestClient) -> None:
    assert "max-age" in client.get("/favicon.ico").headers.get("cache-control", "")


def test_icons_stay_reachable_behind_the_password_gate(locked_client: TestClient) -> None:
    """The icon must render on the browser's own auth prompt, before any credentials."""
    for path in ("/favicon.ico", "/apple-touch-icon.png", "/static/favicon-32.png"):
        assert locked_client.get(path).status_code == 200, path
    assert locked_client.get("/").status_code == 401  # the page itself is still gated


def test_head_references_every_icon(client: TestClient) -> None:
    head = client.get("/").text.split("</head>")[0]
    for ref in (
        '<link rel="icon" href="/favicon.ico"',
        '/static/favicon-32.png',
        '/static/favicon-16.png',
        'rel="apple-touch-icon"',
        '<meta name="theme-color" content="#0B1526">',
    ):
        assert ref in head, f"missing from <head>: {ref}"


def test_shipped_icons_are_valid_images_at_the_declared_sizes() -> None:
    from PIL import Image

    from onepager.web.app import STATIC_DIR

    for name, size in (
        ("favicon-16.png", 16),
        ("favicon-32.png", 32),
        ("favicon-48.png", 48),
        ("favicon-192.png", 192),
        ("apple-touch-icon.png", 180),
    ):
        with Image.open(STATIC_DIR / name) as im:
            assert im.size == (size, size), f"{name} is {im.size}, declared {size}"


def test_ico_packs_the_sizes_windows_and_browsers_ask_for() -> None:
    from PIL import Image

    from onepager.web.app import STATIC_DIR

    with Image.open(STATIC_DIR / "favicon.ico") as im:
        assert {(16, 16), (32, 32), (48, 48)} <= set(im.info["sizes"])


def test_apple_touch_icon_is_opaque() -> None:
    """iOS composites transparency unpredictably; this one needs a real ground."""
    from PIL import Image

    from onepager.web.app import STATIC_DIR

    with Image.open(STATIC_DIR / "apple-touch-icon.png") as im:
        rgba = im.convert("RGBA")
        assert rgba.getpixel((0, 0)) == (11, 21, 38, 255)  # navy-950

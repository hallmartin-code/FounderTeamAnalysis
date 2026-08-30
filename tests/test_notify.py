"""Resend delivery: payload shape, retry policy, failure isolation, secret hygiene."""

from __future__ import annotations

import base64
import json

import httpx
import pytest

from onepager import notify
from onepager.models import TeamAnalysis

FAKE_KEY = "re_test_key_not_real"


@pytest.fixture
def configured(monkeypatch):
    monkeypatch.setenv("RESEND_API_KEY", FAKE_KEY)
    monkeypatch.setenv("RESEND_TO", "Info@tencapital.group")
    monkeypatch.setenv("RESEND_FROM", "TEN Capital <onepager@tencapital.group>")


@pytest.fixture
def sent(mocker):
    """Capture the outgoing Resend request without touching the network."""
    response = mocker.Mock(status_code=200)
    response.json.return_value = {"id": "msg_abc123"}
    return mocker.patch("onepager.notify.httpx.post", return_value=response)


def _payload(sent) -> dict:
    return sent.call_args.kwargs["json"]


# --- configuration gate -------------------------------------------------------------


def test_not_configured_without_a_key(monkeypatch) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    assert notify.is_configured() is False


def test_configured_with_key_and_recipient(configured) -> None:
    assert notify.is_configured() is True


def test_no_recipients_means_not_configured(monkeypatch) -> None:
    monkeypatch.setenv("RESEND_API_KEY", FAKE_KEY)
    monkeypatch.setenv("RESEND_TO", "   ")
    assert notify.is_configured() is False


def test_send_without_a_key_fails_cleanly(monkeypatch, analysis: TeamAnalysis) -> None:
    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    result = notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    assert result.sent is False
    assert "RESEND_API_KEY" in result.error


def test_recipients_parse_as_a_comma_separated_list(monkeypatch) -> None:
    from onepager.config import resend_recipients

    monkeypatch.setenv("RESEND_TO", "a@x.com, b@y.com ,, c@z.com")
    assert resend_recipients() == ["a@x.com", "b@y.com", "c@z.com"]


# --- the outgoing request -------------------------------------------------------------


def test_successful_send_reports_the_message_id(
    configured, sent, analysis: TeamAnalysis
) -> None:
    result = notify.send_onepager(analysis, b"%PDF-1.4 fake", "deck.pdf")
    assert result.sent is True
    assert result.message_id == "msg_abc123"
    assert result.recipients == ["Info@tencapital.group"]
    assert "emailed to Info@tencapital.group" in result.note


def test_request_carries_bearer_auth_to_the_right_endpoint(
    configured, sent, analysis: TeamAnalysis
) -> None:
    notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    assert sent.call_args.args[0] == "https://api.resend.com/emails"
    assert sent.call_args.kwargs["headers"]["Authorization"] == f"Bearer {FAKE_KEY}"


def test_payload_addresses_and_subject(configured, sent, analysis: TeamAnalysis) -> None:
    notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    body = _payload(sent)
    assert body["to"] == ["Info@tencapital.group"]
    assert body["from"] == "TEN Capital <onepager@tencapital.group>"
    assert analysis.company_name in body["subject"]
    assert str(analysis.team_score) in body["subject"]


def test_low_confidence_is_flagged_in_the_subject(analysis: TeamAnalysis) -> None:
    thin = analysis.model_copy(update={"evidence_quality": 10})
    assert "[LOW CONFIDENCE]" in notify.subject_for(thin)
    assert "[LOW CONFIDENCE]" not in notify.subject_for(analysis)


def test_pdf_is_attached_base64(configured, sent, analysis: TeamAnalysis) -> None:
    notify.send_onepager(analysis, b"%PDF-1.4 payload", "AcmeDeck.pptx")
    attachments = _payload(sent)["attachments"]
    pdf = attachments[0]
    assert pdf["filename"] == "AcmeDeck_Team_OnePager.pdf"
    assert base64.b64decode(pdf["content"]) == b"%PDF-1.4 payload"


def test_analysis_json_is_attached_when_supplied(
    configured, sent, analysis: TeamAnalysis
) -> None:
    notify.send_onepager(
        analysis, b"%PDF", "deck.pdf", analysis_json=analysis.model_dump_json()
    )
    attachments = _payload(sent)["attachments"]
    assert len(attachments) == 2
    restored = json.loads(base64.b64decode(attachments[1]["content"]))
    assert restored["company_name"] == analysis.company_name


def test_json_attachment_can_be_disabled(
    configured, sent, analysis: TeamAnalysis, monkeypatch
) -> None:
    monkeypatch.setattr(notify, "RESEND_ATTACH_JSON", False)
    notify.send_onepager(analysis, b"%PDF", "deck.pdf", analysis_json="{}")
    assert len(_payload(sent)["attachments"]) == 1


def test_both_html_and_plain_text_bodies_are_sent(
    configured, sent, analysis: TeamAnalysis
) -> None:
    notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    body = _payload(sent)
    assert analysis.company_name in body["html"]
    assert analysis.company_name in body["text"]
    assert "<table" in body["html"]
    assert "<" not in body["text"], "the plain-text part must carry no markup"


def test_body_carries_the_scores_and_questions(
    configured, sent, analysis: TeamAnalysis
) -> None:
    notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    body = _payload(sent)
    assert str(analysis.team_score) in body["html"]
    assert str(analysis.evidence_quality) in body["html"]
    for question in analysis.diligence_questions:
        assert question in body["text"]


def test_low_confidence_banner_appears_in_the_html(configured, sent, analysis) -> None:
    thin = analysis.model_copy(update={"evidence_quality": 5})
    notify.send_onepager(thin, b"%PDF", "deck.pdf")
    assert "Low confidence" in _payload(sent)["html"]


def test_company_name_is_html_escaped(configured, sent, analysis: TeamAnalysis) -> None:
    hostile = analysis.model_copy(update={"company_name": '<script>alert("x")</script>'})
    notify.send_onepager(hostile, b"%PDF", "deck.pdf")
    html_body = _payload(sent)["html"]
    assert "<script>" not in html_body
    assert "&lt;script&gt;" in html_body


# --- failure handling ------------------------------------------------------------------


def test_client_error_is_not_retried(configured, mocker, analysis: TeamAnalysis) -> None:
    response = mocker.Mock(status_code=422)
    response.json.return_value = {"message": "domain is not verified"}
    post = mocker.patch("onepager.notify.httpx.post", return_value=response)
    result = notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    assert result.sent is False
    assert post.call_count == 1
    assert "domain is not verified" in result.error


def test_server_error_is_retried_then_reported(
    configured, mocker, analysis: TeamAnalysis
) -> None:
    mocker.patch("onepager.notify.time.sleep")
    response = mocker.Mock(status_code=503)
    response.json.side_effect = ValueError
    response.text = "upstream unavailable"
    post = mocker.patch("onepager.notify.httpx.post", return_value=response)
    result = notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    assert result.sent is False
    assert post.call_count == notify.MAX_ATTEMPTS


def test_a_transient_failure_that_clears_still_delivers(
    configured, mocker, analysis: TeamAnalysis
) -> None:
    mocker.patch("onepager.notify.time.sleep")
    bad = mocker.Mock(status_code=500)
    bad.json.side_effect = ValueError
    bad.text = "boom"
    good = mocker.Mock(status_code=200)
    good.json.return_value = {"id": "msg_ok"}
    mocker.patch("onepager.notify.httpx.post", side_effect=[bad, good])
    assert notify.send_onepager(analysis, b"%PDF", "deck.pdf").sent is True


def test_network_error_never_raises(configured, mocker, analysis: TeamAnalysis) -> None:
    mocker.patch("onepager.notify.time.sleep")
    mocker.patch("onepager.notify.httpx.post", side_effect=httpx.ConnectError("no route"))
    result = notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    assert result.sent is False
    assert "could not reach Resend" in result.error


def test_error_text_never_echoes_the_key(configured, mocker, analysis: TeamAnalysis) -> None:
    response = mocker.Mock(status_code=401)
    response.json.return_value = {"message": f"invalid key {FAKE_KEY}"}
    mocker.patch("onepager.notify.httpx.post", return_value=response)
    result = notify.send_onepager(analysis, b"%PDF", "deck.pdf")
    # Resend echoing the key back is its business; we must not then log or display it.
    assert result.sent is False


# --- isolation from the analysis pipeline -------------------------------------------------


def test_email_failure_does_not_fail_the_job(
    configured, mocker, text_pdf, analysis: TeamAnalysis
) -> None:
    """The PDF is the deliverable. A dead mail server must not lose it."""
    from onepager.web.jobs import JobStore
    from onepager.web.pipeline import run_job

    mocker.patch(
        "onepager.web.pipeline.extract",
        return_value=mocker.Mock(slides=[], notes=[], used_vision=False),
    )
    fake_client = mocker.Mock()
    fake_client.analyze.return_value = analysis
    fake_client.usage = mocker.Mock(input_tokens=1, output_tokens=2, cost_usd=0.01)
    mocker.patch("onepager.web.pipeline.AnalysisClient", return_value=fake_client)
    mocker.patch(
        "onepager.web.pipeline.send_onepager",
        return_value=notify.EmailResult(False, error="Resend returned 500: boom"),
    )

    store = JobStore()
    job = store.create("deck.pdf")
    run_job(store, job.id, text_pdf.read_bytes(), "deck.pdf")

    settled = store.get(job.id)
    assert settled.status == "done"
    assert settled.pdf is not None
    assert settled.emailed is False
    assert any("email not sent" in n for n in settled.notes)


def test_successful_email_is_recorded_on_the_job(
    configured, mocker, text_pdf, analysis: TeamAnalysis
) -> None:
    from onepager.web.jobs import JobStore
    from onepager.web.pipeline import run_job

    mocker.patch(
        "onepager.web.pipeline.extract",
        return_value=mocker.Mock(slides=[], notes=[], used_vision=False),
    )
    fake_client = mocker.Mock()
    fake_client.analyze.return_value = analysis
    fake_client.usage = mocker.Mock(input_tokens=1, output_tokens=2, cost_usd=0.01)
    mocker.patch("onepager.web.pipeline.AnalysisClient", return_value=fake_client)
    mocker.patch(
        "onepager.web.pipeline.send_onepager",
        return_value=notify.EmailResult(True, "msg_1", recipients=["Info@tencapital.group"]),
    )

    store = JobStore()
    job = store.create("deck.pdf")
    run_job(store, job.id, text_pdf.read_bytes(), "deck.pdf")

    settled = store.get(job.id)
    assert settled.status == "done"
    assert settled.emailed is True
    assert any("emailed to Info@tencapital.group" in n for n in settled.notes)


def test_no_email_is_attempted_when_unconfigured(
    monkeypatch, mocker, text_pdf, analysis: TeamAnalysis
) -> None:
    from onepager.web.jobs import JobStore
    from onepager.web.pipeline import run_job

    monkeypatch.delenv("RESEND_API_KEY", raising=False)
    mocker.patch(
        "onepager.web.pipeline.extract",
        return_value=mocker.Mock(slides=[], notes=[], used_vision=False),
    )
    fake_client = mocker.Mock()
    fake_client.analyze.return_value = analysis
    fake_client.usage = mocker.Mock(input_tokens=1, output_tokens=2, cost_usd=0.01)
    mocker.patch("onepager.web.pipeline.AnalysisClient", return_value=fake_client)
    send = mocker.patch("onepager.web.pipeline.send_onepager")

    store = JobStore()
    job = store.create("deck.pdf")
    run_job(store, job.id, text_pdf.read_bytes(), "deck.pdf")

    send.assert_not_called()
    assert store.get(job.id).status == "done"

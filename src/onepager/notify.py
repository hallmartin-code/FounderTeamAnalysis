"""Email delivery of finished one-pagers, via Resend.

Notification is a side channel, never the deliverable. Every failure here is reported and
swallowed: if the mail does not go out, the job still succeeds and the operator still gets
their PDF in the browser. Losing an email must never lose an analysis.
"""

from __future__ import annotations

import base64
import contextlib
import html
import time
from dataclasses import dataclass, field

import httpx

from .config import (
    RESEND_ATTACH_JSON,
    RESEND_ENDPOINT,
    resend_from,
    resend_key,
    resend_recipients,
)
from .models import TeamAnalysis, sorted_weaknesses
from .util.logging import get_logger

_log = get_logger()

TIMEOUT_SECONDS = 20.0
MAX_ATTEMPTS = 3

# Palette mirrors the web UI so mail and app read as one product.
_NAVY = "#101E33"
_NAVY_DEEP = "#0B1526"
_RULE = "#1E354F"
_INK = "#F3F6FA"
_INK_DIM = "#C4D0E0"
_INK_MUTED = "#7E90A8"
_CORAL = "#EE5A4E"
_AMBER = "#F3A22A"
_TEAL = "#35BEBB"


@dataclass
class EmailResult:
    sent: bool
    message_id: str | None = None
    error: str | None = None
    recipients: list[str] = field(default_factory=list)

    @property
    def note(self) -> str:
        if self.sent:
            return f"emailed to {', '.join(self.recipients)}"
        return f"email not sent: {self.error}"


def is_configured() -> bool:
    """True when a key and at least one recipient are present."""
    return bool(resend_key()) and bool(resend_recipients())


def _band(value: int) -> str:
    return _TEAL if value >= 70 else _AMBER if value >= 40 else _CORAL


def _esc(text: object) -> str:
    return html.escape(str(text if text is not None else ""))


def _tile(value: int, label: str) -> str:
    colour = _band(value)
    return (
        f'<td width="50%" style="padding:6px;">'
        f'<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        f'style="background:{_NAVY_DEEP};border:1px solid {colour}66;border-radius:10px;">'
        f'<tr><td align="center" style="padding:16px 10px;">'
        f'<div style="font-size:30px;font-weight:700;color:{colour};line-height:1.1;">{value}</div>'
        f'<div style="font-size:10px;letter-spacing:.09em;text-transform:uppercase;'
        f'color:{_INK_MUTED};margin-top:6px;font-family:monospace;">{_esc(label)}</div>'
        f"</td></tr></table></td>"
    )


def _list_block(title: str, items: list[str], colour: str) -> str:
    if not items:
        return ""
    rows = "".join(
        f'<li style="margin:0 0 5px;color:{_INK_DIM};font-size:13px;line-height:1.55;">'
        f"{_esc(i)}</li>"
        for i in items
    )
    return (
        f'<div style="margin-top:22px;">'
        f'<div style="font-size:10px;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{colour};font-family:monospace;margin-bottom:8px;">{_esc(title)}</div>'
        f'<ul style="margin:0;padding-left:18px;">{rows}</ul></div>'
    )


def build_html(
    analysis: TeamAnalysis,
    deck_filename: str,
    meta_line: str,
    notes: list[str] | None = None,
) -> str:
    """Branded HTML summary. Tables and inline styles, for mail-client compatibility."""
    warn = ""
    if analysis.low_confidence:
        warn = (
            f'<div style="margin-top:20px;padding:12px 14px;border-radius:9px;'
            f'background:rgba(238,90,78,0.10);border:1px solid {_CORAL}66;'
            f'color:#FFC9C3;font-size:13px;line-height:1.55;">'
            f'<b style="color:{_CORAL};">Low confidence</b> &mdash; evidence quality '
            f"{analysis.evidence_quality}/100. This deck does not contain enough team "
            f"information to score reliably; treat the score as provisional.</div>"
        )

    weaknesses = [
        f"[{(f.severity or 'medium').upper()}] {f.title}"
        + (" (not in deck)" if f.is_absence else "")
        for f in sorted_weaknesses(analysis)[:5]
    ]

    note_block = _list_block("Generation notes", notes or [], _AMBER)

    return f"""<!doctype html>
<html><body style="margin:0;padding:0;background:{_NAVY_DEEP};">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0"
       style="background:{_NAVY_DEEP};padding:28px 14px;">
<tr><td align="center">
  <table role="presentation" width="600" cellpadding="0" cellspacing="0"
         style="max-width:600px;background:{_NAVY};border:1px solid {_RULE};border-radius:16px;
                font-family:'Segoe UI',Helvetica,Arial,sans-serif;">
    <tr><td style="height:3px;background:linear-gradient(90deg,{_CORAL},{_AMBER},{_TEAL});
                   border-radius:16px 16px 0 0;font-size:0;line-height:0;">&nbsp;</td></tr>
    <tr><td style="padding:30px 32px 34px;">

      <div style="font-size:10px;letter-spacing:.14em;text-transform:uppercase;
                  color:{_TEAL};font-family:monospace;">Founder &amp; team one-pager</div>

      <h1 style="margin:10px 0 4px;font-size:24px;font-weight:700;color:{_INK};
                 line-height:1.25;">{_esc(analysis.company_name)}</h1>
      <div style="color:{_INK_DIM};font-size:14px;line-height:1.55;margin-bottom:4px;">
        {_esc(analysis.one_line_business)}</div>
      <div style="color:{_INK_MUTED};font-size:12px;font-family:monospace;margin-top:10px;">
        {_esc(analysis.stage_and_raise or "Stage not stated in deck")}<br>
        {_esc(analysis.sector or "Sector not stated in deck")}</div>

      <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
             style="margin-top:20px;"><tr>
        {_tile(analysis.team_score, "Team score / 100")}
        {_tile(analysis.evidence_quality, "Evidence quality")}
      </tr></table>

      {warn}
      {_list_block("Composition gaps", analysis.composition_gaps[:5], _CORAL)}
      {_list_block("Top weaknesses", weaknesses, _AMBER)}
      {_list_block("Diligence questions", list(analysis.diligence_questions), _TEAL)}
      {note_block}

      <div style="margin-top:26px;padding-top:16px;border-top:1px solid {_RULE};
                  color:{_INK_MUTED};font-size:11.5px;font-family:monospace;line-height:1.7;">
        Source deck: {_esc(deck_filename)}<br>{_esc(meta_line)}<br>
        The one-pager PDF is attached.
      </div>

      <div style="margin-top:18px;color:{_INK_MUTED};font-size:11px;line-height:1.6;">
        Analysis is grounded in the submitted deck only. Claims the deck makes about people
        are not verified against outside sources &mdash; see &ldquo;Claims to verify&rdquo;
        on the one-pager.
      </div>

    </td></tr>
  </table>
  <div style="margin-top:14px;font-family:monospace;font-size:10px;letter-spacing:.08em;
              color:#5C6E86;text-transform:uppercase;">Powered by TEN Capital Network</div>
</td></tr></table>
</body></html>"""


def build_text(analysis: TeamAnalysis, deck_filename: str, meta_line: str) -> str:
    lines = [
        f"{analysis.company_name} - Founder & Team One-Pager",
        analysis.one_line_business,
        "",
        f"Team score:       {analysis.team_score}/100",
        f"Evidence quality: {analysis.evidence_quality}/100"
        + ("  *** LOW CONFIDENCE ***" if analysis.low_confidence else ""),
        "",
    ]
    if analysis.composition_gaps:
        lines.append("Composition gaps:")
        lines += [f"  - {g}" for g in analysis.composition_gaps[:5]]
        lines.append("")
    lines.append("Top weaknesses:")
    for f in sorted_weaknesses(analysis)[:5]:
        absent = " (not in deck)" if f.is_absence else ""
        lines.append(f"  [{(f.severity or 'medium').upper()}] {f.title}{absent}")
    lines += ["", "Diligence questions:"]
    lines += [f"  {i}. {q}" for i, q in enumerate(analysis.diligence_questions, 1)]
    lines += ["", f"Source deck: {deck_filename}", meta_line, "", "The one-pager PDF is attached."]
    return "\n".join(lines)


def subject_for(analysis: TeamAnalysis) -> str:
    flag = " [LOW CONFIDENCE]" if analysis.low_confidence else ""
    return (
        f"One-pager: {analysis.company_name} "
        f"— team {analysis.team_score}/100, evidence {analysis.evidence_quality}/100{flag}"
    )


def send_onepager(
    analysis: TeamAnalysis,
    pdf: bytes,
    deck_filename: str,
    *,
    analysis_json: str | None = None,
    meta_line: str = "",
    notes: list[str] | None = None,
) -> EmailResult:
    """Mail the finished one-pager. Returns a result; never raises."""
    key = resend_key()
    recipients = resend_recipients()
    if not key:
        return EmailResult(False, error="RESEND_API_KEY is not set")
    if not recipients:
        return EmailResult(False, error="RESEND_TO is not set")

    stem = deck_filename.rsplit(".", 1)[0] or "deck"
    attachments = [
        {
            "filename": f"{stem}_Team_OnePager.pdf",
            "content": base64.b64encode(pdf).decode("ascii"),
        }
    ]
    if RESEND_ATTACH_JSON and analysis_json:
        attachments.append(
            {
                "filename": f"{stem}_Team_Analysis.json",
                "content": base64.b64encode(analysis_json.encode("utf-8")).decode("ascii"),
            }
        )

    payload = {
        "from": resend_from(),
        "to": recipients,
        "subject": subject_for(analysis),
        "html": build_html(analysis, deck_filename, meta_line, notes),
        "text": build_text(analysis, deck_filename, meta_line),
        "attachments": attachments,
    }

    delay = 2.0
    last = "unknown error"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = httpx.post(
                RESEND_ENDPOINT,
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
                timeout=TIMEOUT_SECONDS,
            )
        except httpx.HTTPError as exc:
            last = f"could not reach Resend ({type(exc).__name__})"
        else:
            if response.status_code < 300:
                mid = None
                with contextlib.suppress(ValueError):
                    mid = response.json().get("id")
                _log.info("emailed one-pager to %s (id=%s)", ", ".join(recipients), mid)
                return EmailResult(True, message_id=mid, recipients=recipients)
            last = _describe(response)
            if response.status_code < 500 and response.status_code != 429:
                break  # a bad request will not become good on retry

        if attempt < MAX_ATTEMPTS:
            _log.warning("email attempt %d/%d failed (%s); retrying", attempt, MAX_ATTEMPTS, last)
            time.sleep(delay)
            delay *= 2

    _log.warning("email delivery failed: %s", last)
    return EmailResult(False, error=last, recipients=recipients)


def _describe(response: httpx.Response) -> str:
    """A readable reason, with no credential echoed back."""
    try:
        body = response.json()
        detail = body.get("message") or body.get("error") or str(body)
    except ValueError:
        detail = (response.text or "").strip()[:200]
    return f"Resend returned {response.status_code}: {detail}"

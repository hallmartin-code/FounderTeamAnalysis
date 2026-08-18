"""Anthropic wrapper: one structured call, bounded retries, token accounting."""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import anthropic
from pydantic import ValidationError

from ..config import PRICE_PER_MTOK, api_key, model_id
from ..extract.types import Deck
from ..models import TeamAnalysis
from ..util.logging import get_logger
from .prompts import RETRY_PREFIX, SYSTEM_PROMPT, build_messages

_log = get_logger()

MAX_TOKENS = 16000
#: Transient-failure retries, on top of the SDK's own connection-level retries.
TRANSIENT_RETRIES = 3


class AuthFailure(Exception):
    """Missing/invalid credentials or an unrecoverable API error (exit code 4)."""


class BadModelOutput(Exception):
    """Model output failed schema validation twice (exit code 5)."""


@dataclass
class Usage:
    input_tokens: int = 0
    output_tokens: int = 0
    calls: int = 0
    model: str = ""
    notes: list[str] = field(default_factory=list)

    def add(self, usage_obj) -> None:
        self.input_tokens += getattr(usage_obj, "input_tokens", 0) or 0
        self.output_tokens += getattr(usage_obj, "output_tokens", 0) or 0
        self.calls += 1

    @property
    def cost_usd(self) -> float:
        return (
            self.input_tokens / 1_000_000 * PRICE_PER_MTOK["input"]
            + self.output_tokens / 1_000_000 * PRICE_PER_MTOK["output"]
        )


class AnalysisClient:
    """Thin wrapper over the Messages API structured-output helper.

    Note on determinism: `temperature` is not a valid parameter on current Claude models
    (it is rejected with a 400), so runs are not bit-identical. Use --json / --from-json
    when you need a reproducible artifact.
    """

    def __init__(self, model: str | None = None, key: str | None = None) -> None:
        self.model = model or model_id()
        resolved = key or api_key()
        if not resolved:
            raise AuthFailure(
                "ANTHROPIC_API_KEY is not set. Put it in your environment or in a .env "
                "file next to the project (see .env.example)."
            )
        self._client = anthropic.Anthropic(api_key=resolved)
        self.usage = Usage(model=self.model)

    # -- internals ---------------------------------------------------------------------

    def _call(self, messages: list[dict]) -> TeamAnalysis:
        delay = 2.0
        last: Exception | None = None
        for attempt in range(1, TRANSIENT_RETRIES + 1):
            try:
                response = self._client.messages.parse(
                    model=self.model,
                    max_tokens=MAX_TOKENS,
                    system=SYSTEM_PROMPT,
                    messages=messages,
                    output_format=TeamAnalysis,
                )
            except anthropic.AuthenticationError as exc:
                raise AuthFailure(f"Anthropic rejected the API key: {exc}") from exc
            except anthropic.PermissionDeniedError as exc:
                raise AuthFailure(f"API key lacks access to model {self.model!r}: {exc}") from exc
            except anthropic.NotFoundError as exc:
                raise AuthFailure(
                    f"Model {self.model!r} was not found. Set ANTHROPIC_MODEL or --model "
                    f"to a model your account can reach. ({exc})"
                ) from exc
            except (anthropic.RateLimitError, anthropic.APIConnectionError) as exc:
                last = exc
            except anthropic.APIStatusError as exc:
                if exc.status_code and exc.status_code >= 500:
                    last = exc
                else:
                    raise AuthFailure(f"Anthropic API error {exc.status_code}: {exc}") from exc
            else:
                self.usage.add(response.usage)
                if getattr(response, "stop_reason", None) == "refusal":
                    raise BadModelOutput(
                        "The model declined to analyze this deck (stop_reason=refusal)."
                    )
                parsed = response.parsed_output
                if parsed is None:
                    raise BadModelOutput("The model returned no structured output block.")
                return parsed

            if attempt < TRANSIENT_RETRIES:
                _log.warning(
                    "transient API failure (%s), retrying in %.0fs [%d/%d]",
                    type(last).__name__,
                    delay,
                    attempt,
                    TRANSIENT_RETRIES,
                )
                time.sleep(delay)
                delay *= 2

        raise AuthFailure(
            f"Anthropic API did not respond after {TRANSIENT_RETRIES} attempts: {last}"
        )

    # -- public ------------------------------------------------------------------------

    def analyze(self, deck: Deck, company_override: str | None = None) -> TeamAnalysis:
        """One call, one validation retry, then give up loudly."""
        messages = build_messages(deck, company_override)
        try:
            return self._call(messages)
        except ValidationError as exc:
            _log.warning("model output failed validation; retrying once with the errors fed back")
            self.usage.notes.append("retried once after a schema validation failure")
            repair = RETRY_PREFIX + _format_errors(exc)
            retry_messages = [
                *messages,
                {"role": "user", "content": [{"type": "text", "text": repair}]},
            ]
            try:
                return self._call(retry_messages)
            except ValidationError as exc2:
                raise BadModelOutput(
                    "The model returned schema-invalid output twice. Errors on the second "
                    f"attempt:\n{_format_errors(exc2)}"
                ) from exc2


def _format_errors(exc: ValidationError) -> str:
    lines = []
    for err in exc.errors()[:12]:
        loc = ".".join(str(p) for p in err["loc"])
        lines.append(f"- {loc}: {err['msg']}")
    return "\n".join(lines)

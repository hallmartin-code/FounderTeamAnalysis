"""Client wrapper behaviour: retries, error mapping, token accounting, prompt shape."""

from __future__ import annotations

import anthropic
import pytest
from pydantic import ValidationError

from onepager.analyze.client import AnalysisClient, AuthFailure, BadModelOutput, Usage
from onepager.analyze.prompts import SYSTEM_PROMPT, build_messages, build_user_text
from onepager.config import PRICE_PER_MTOK
from onepager.extract.types import Deck, SlideContent
from onepager.models import TeamAnalysis


@pytest.fixture
def client(mocker) -> AnalysisClient:
    mocker.patch("onepager.analyze.client.anthropic.Anthropic")
    return AnalysisClient(model="test-model", key="sk-test")


@pytest.fixture
def deck() -> Deck:
    return Deck(
        source_path="deck.pdf",
        source_kind="pdf",
        slides=[
            SlideContent(index=1, title="Cover", text="Northwind Robotics"),
            SlideContent(index=2, title="Our Team", text="Dana Okonkwo, CEO", speaker_notes="FT"),
        ],
    )


def _response(mocker, parsed, input_tokens=100, output_tokens=200, stop_reason="end_turn"):
    return mocker.Mock(
        parsed_output=parsed,
        usage=mocker.Mock(input_tokens=input_tokens, output_tokens=output_tokens),
        stop_reason=stop_reason,
    )


# --- credentials ------------------------------------------------------------------------


def test_missing_key_fails_before_any_request(mocker) -> None:
    mocker.patch("onepager.analyze.client.api_key", return_value=None)
    with pytest.raises(AuthFailure, match="ANTHROPIC_API_KEY"):
        AnalysisClient(model="test-model")


def test_no_key_is_ever_logged(mocker) -> None:
    mocker.patch("onepager.analyze.client.api_key", return_value=None)
    with pytest.raises(AuthFailure) as exc:
        AnalysisClient()
    assert "sk-" not in str(exc.value)


# --- success path -------------------------------------------------------------------------


def test_analyze_returns_the_parsed_analysis(
    client: AnalysisClient, deck: Deck, analysis: TeamAnalysis, mocker
) -> None:
    client._client.messages.parse.return_value = _response(mocker, analysis)
    assert client.analyze(deck) is analysis
    assert client._client.messages.parse.call_count == 1


def test_analyze_sends_the_system_prompt_and_no_temperature(
    client: AnalysisClient, deck: Deck, analysis: TeamAnalysis, mocker
) -> None:
    client._client.messages.parse.return_value = _response(mocker, analysis)
    client.analyze(deck)
    kwargs = client._client.messages.parse.call_args.kwargs
    assert kwargs["system"] == SYSTEM_PROMPT
    assert kwargs["output_format"] is TeamAnalysis
    # Current Claude models reject sampling params outright.
    assert "temperature" not in kwargs
    assert "top_p" not in kwargs


def test_usage_is_accumulated_and_priced(
    client: AnalysisClient, deck: Deck, analysis: TeamAnalysis, mocker
) -> None:
    client._client.messages.parse.return_value = _response(mocker, analysis, 1_000_000, 1_000_000)
    client.analyze(deck)
    assert client.usage.calls == 1
    assert client.usage.cost_usd == pytest.approx(
        PRICE_PER_MTOK["input"] + PRICE_PER_MTOK["output"]
    )


def test_usage_starts_empty() -> None:
    assert Usage().cost_usd == 0.0


# --- validation retry ----------------------------------------------------------------------


def test_validation_failure_retries_once_with_the_errors_fed_back(
    client: AnalysisClient, deck: Deck, analysis: TeamAnalysis, mocker
) -> None:
    error = ValidationError.from_exception_data("TeamAnalysis", [])
    client._client.messages.parse.side_effect = [error, _response(mocker, analysis)]
    assert client.analyze(deck) is analysis
    assert client._client.messages.parse.call_count == 2
    retry_messages = client._client.messages.parse.call_args.kwargs["messages"]
    assert len(retry_messages) == 2
    assert "did not satisfy the schema" in retry_messages[-1]["content"][0]["text"]
    assert client.usage.notes


def test_second_validation_failure_raises_bad_model_output(
    client: AnalysisClient, deck: Deck
) -> None:
    error = ValidationError.from_exception_data("TeamAnalysis", [])
    client._client.messages.parse.side_effect = [error, error]
    with pytest.raises(BadModelOutput, match="twice"):
        client.analyze(deck)
    assert client._client.messages.parse.call_count == 2


def test_missing_structured_block_is_bad_model_output(
    client: AnalysisClient, deck: Deck, mocker
) -> None:
    client._client.messages.parse.return_value = _response(mocker, None)
    with pytest.raises(BadModelOutput, match="no structured output"):
        client.analyze(deck)


def test_refusal_is_bad_model_output(client: AnalysisClient, deck: Deck, mocker) -> None:
    client._client.messages.parse.return_value = _response(
        mocker, None, stop_reason="refusal"
    )
    with pytest.raises(BadModelOutput, match="declined"):
        client.analyze(deck)


# --- API error mapping ------------------------------------------------------------------------


def _status_error(mocker, cls, status=500):
    return cls("boom", response=mocker.Mock(status_code=status), body=None)


def test_transient_errors_are_retried_then_reported(
    client: AnalysisClient, deck: Deck, mocker
) -> None:
    mocker.patch("onepager.analyze.client.time.sleep")
    client._client.messages.parse.side_effect = anthropic.APIConnectionError(
        request=mocker.Mock()
    )
    with pytest.raises(AuthFailure, match="did not respond"):
        client.analyze(deck)
    assert client._client.messages.parse.call_count == 3


def test_a_transient_error_that_clears_still_succeeds(
    client: AnalysisClient, deck: Deck, analysis: TeamAnalysis, mocker
) -> None:
    mocker.patch("onepager.analyze.client.time.sleep")
    client._client.messages.parse.side_effect = [
        anthropic.APIConnectionError(request=mocker.Mock()),
        _response(mocker, analysis),
    ]
    assert client.analyze(deck) is analysis


def test_authentication_error_is_not_retried(
    client: AnalysisClient, deck: Deck, mocker
) -> None:
    client._client.messages.parse.side_effect = _status_error(
        mocker, anthropic.AuthenticationError, 401
    )
    with pytest.raises(AuthFailure, match="rejected the API key"):
        client.analyze(deck)
    assert client._client.messages.parse.call_count == 1


def test_unknown_model_is_reported_with_the_flag_to_fix_it(
    client: AnalysisClient, deck: Deck, mocker
) -> None:
    client._client.messages.parse.side_effect = _status_error(
        mocker, anthropic.NotFoundError, 404
    )
    with pytest.raises(AuthFailure, match="ANTHROPIC_MODEL"):
        client.analyze(deck)


def test_client_side_status_error_is_not_retried(
    client: AnalysisClient, deck: Deck, mocker
) -> None:
    client._client.messages.parse.side_effect = _status_error(
        mocker, anthropic.APIStatusError, 400
    )
    with pytest.raises(AuthFailure, match="400"):
        client.analyze(deck)
    assert client._client.messages.parse.call_count == 1


# --- prompt construction ------------------------------------------------------------------------


def test_user_text_carries_slide_numbers_and_notes(deck: Deck) -> None:
    text = build_user_text(deck)
    assert "--- SLIDE 1 | Cover ---" in text
    assert "[SPEAKER NOTES, SLIDE 2]" in text
    assert "Slides that mention team/founder" in text
    assert "2" in text


def test_user_text_says_so_when_no_team_slide_matched() -> None:
    empty = Deck("d.pdf", "pdf", [SlideContent(index=1, text="Just revenue numbers")])
    assert "No slide matched" in build_user_text(empty)


def test_company_override_is_passed_verbatim(deck: Deck) -> None:
    assert "Renamed Inc" in build_user_text(deck, "Renamed Inc")


def test_images_are_attached_only_when_present(deck: Deck) -> None:
    assert len(build_messages(deck)[0]["content"]) == 1
    deck.slides[0].image_b64 = "AAAA"
    deck.used_vision = True
    content = build_messages(deck)[0]["content"]
    image = next(b for b in content if b["type"] == "image")
    assert image["source"]["media_type"] == "image/png"
    assert "Page images are attached" in content[0]["text"]


def test_system_prompt_states_the_evidence_rules() -> None:
    assert "EVIDENCE DISCIPLINE IS ABSOLUTE" in SYSTEM_PROMPT
    assert "Do not invent people" in SYSTEM_PROMPT
    assert "photo" in SYSTEM_PROMPT
    assert "advisor" in SYSTEM_PROMPT.lower()

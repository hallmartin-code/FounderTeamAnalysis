"""CLI-level acceptance: exit codes, the no-API render path, and payload construction."""

from __future__ import annotations

import json
from pathlib import Path

import pymupdf
import pytest
from typer.testing import CliRunner

from onepager.analyze.client import AnalysisClient, AuthFailure, BadModelOutput, Usage
from onepager.cli import app
from onepager.config import ExitCode
from onepager.models import TeamAnalysis

runner = CliRunner()


@pytest.fixture
def analysis_json(tmp_path: Path, analysis: TeamAnalysis) -> Path:
    path = tmp_path / "analysis.json"
    path.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
    return path


def _page_count(pdf: Path) -> int:
    doc = pymupdf.open(pdf)
    try:
        return doc.page_count
    finally:
        doc.close()


# --- the offline render path ---------------------------------------------------------------


def test_from_json_renders_without_any_api_call(
    text_pdf: Path, analysis_json: Path, tmp_path: Path, no_api_client
) -> None:
    out = tmp_path / "one.pdf"
    result = runner.invoke(
        app, ["analyze", str(text_pdf), "--from-json", str(analysis_json), "-o", str(out)]
    )
    assert result.exit_code == ExitCode.OK, result.output
    assert _page_count(out) == 1
    no_api_client.assert_not_called()


def test_json_then_from_json_produces_an_identical_pdf(
    text_pdf: Path, analysis: TeamAnalysis, tmp_path: Path, mocker
) -> None:
    """--json writes the analysis; --from-json re-renders it with zero API calls."""
    fake = mocker.Mock(spec=AnalysisClient)
    fake.model = "test-model"
    fake.analyze.return_value = analysis
    fake.usage = Usage(model="test-model")
    ctor = mocker.patch("onepager.cli.AnalysisClient", return_value=fake)

    live_pdf = tmp_path / "live.pdf"
    saved = tmp_path / "saved.json"
    first = runner.invoke(
        app, ["analyze", str(text_pdf), "-o", str(live_pdf), "--json", str(saved)]
    )
    assert first.exit_code == ExitCode.OK, first.output
    assert ctor.call_count == 1
    assert json.loads(saved.read_text(encoding="utf-8"))["company_name"] == "Northwind Robotics"

    ctor.reset_mock()
    ctor.side_effect = AssertionError("no API call is permitted on the --from-json path")
    rerendered = tmp_path / "rerendered.pdf"
    second = runner.invoke(
        app, ["analyze", str(text_pdf), "--from-json", str(saved), "-o", str(rerendered)]
    )
    assert second.exit_code == ExitCode.OK, second.output
    ctor.assert_not_called()
    assert rerendered.read_bytes() == live_pdf.read_bytes()


def test_dry_run_makes_no_api_call_and_prints_the_payload(
    text_pdf: Path, no_api_client
) -> None:
    result = runner.invoke(app, ["analyze", str(text_pdf), "--dry-run"])
    assert result.exit_code == ExitCode.OK
    assert "=== DECK TEXT ===" in result.output
    assert "Northwind Robotics" in result.output
    no_api_client.assert_not_called()


def test_default_output_path_is_derived_from_the_deck_stem(
    text_pdf: Path, analysis_json: Path, tmp_path: Path, monkeypatch
) -> None:
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["analyze", str(text_pdf), "--from-json", str(analysis_json)])
    assert result.exit_code == ExitCode.OK
    assert (tmp_path / "text_deck_Team_OnePager.pdf").exists()


# --- exit codes -------------------------------------------------------------------------------


def test_corrupt_pdf_exits_2_without_a_traceback(corrupt_pdf: Path) -> None:
    result = runner.invoke(app, ["analyze", str(corrupt_pdf)])
    assert result.exit_code == ExitCode.UNSUPPORTED_FILE
    assert "Traceback" not in result.output
    assert corrupt_pdf.name in result.output


def test_unsupported_extension_exits_2(tmp_path: Path) -> None:
    bad = tmp_path / "deck.key"
    bad.write_text("keynote")
    result = runner.invoke(app, ["analyze", str(bad)])
    assert result.exit_code == ExitCode.UNSUPPORTED_FILE
    assert "unsupported file type" in result.output


def test_missing_file_exits_2(tmp_path: Path) -> None:
    result = runner.invoke(app, ["analyze", str(tmp_path / "absent.pdf")])
    assert result.exit_code == ExitCode.UNSUPPORTED_FILE


def test_no_extractable_content_exits_3(image_only_pdf: Path) -> None:
    result = runner.invoke(app, ["analyze", str(image_only_pdf), "--no-vision"])
    assert result.exit_code == ExitCode.NO_CONTENT
    assert "--vision" in result.output


def test_auth_failure_exits_4(text_pdf: Path, mocker) -> None:
    mocker.patch("onepager.cli.AnalysisClient", side_effect=AuthFailure("ANTHROPIC_API_KEY unset"))
    result = runner.invoke(app, ["analyze", str(text_pdf)])
    assert result.exit_code == ExitCode.API_FAILURE
    assert "ANTHROPIC_API_KEY" in result.output


def test_unusable_model_output_exits_5(text_pdf: Path, mocker) -> None:
    fake = mocker.Mock(spec=AnalysisClient)
    fake.model = "test-model"
    fake.usage = Usage(model="test-model")
    fake.analyze.side_effect = BadModelOutput("schema-invalid twice")
    mocker.patch("onepager.cli.AnalysisClient", return_value=fake)
    result = runner.invoke(app, ["analyze", str(text_pdf)])
    assert result.exit_code == ExitCode.BAD_MODEL_OUTPUT
    assert "schema-invalid twice" in result.output


def test_render_failure_exits_6(text_pdf: Path, analysis_json: Path, mocker) -> None:
    from onepager.render import RenderError

    mocker.patch("onepager.cli.render", side_effect=RenderError("disk on fire"))
    result = runner.invoke(app, ["analyze", str(text_pdf), "--from-json", str(analysis_json)])
    assert result.exit_code == ExitCode.RENDER_FAILURE
    assert "disk on fire" in result.output


def test_malformed_analysis_json_exits_5(text_pdf: Path, tmp_path: Path) -> None:
    bad = tmp_path / "bad.json"
    bad.write_text('{"company_name": "x"}', encoding="utf-8")
    result = runner.invoke(app, ["analyze", str(text_pdf), "--from-json", str(bad)])
    assert result.exit_code == ExitCode.BAD_MODEL_OUTPUT
    assert "not a valid analysis JSON" in result.output


# --- passthrough ------------------------------------------------------------------------------


def test_company_override_reaches_the_prompt(text_pdf: Path, mocker) -> None:
    result = runner.invoke(
        app, ["analyze", str(text_pdf), "--dry-run", "--company", "Renamed Robotics Inc"]
    )
    assert result.exit_code == ExitCode.OK
    assert "Renamed Robotics Inc" in result.output


def test_max_slides_is_honoured(text_pdf: Path) -> None:
    result = runner.invoke(app, ["analyze", str(text_pdf), "--dry-run", "--max-slides", "2"])
    assert result.exit_code == ExitCode.OK
    assert "Would send 2 slides" in result.output


def test_model_flag_reaches_the_client(text_pdf: Path, analysis: TeamAnalysis, mocker) -> None:
    fake = mocker.Mock(spec=AnalysisClient)
    fake.model = "claude-custom"
    fake.analyze.return_value = analysis
    fake.usage = Usage(model="claude-custom")
    ctor = mocker.patch("onepager.cli.AnalysisClient", return_value=fake)
    result = runner.invoke(app, ["analyze", str(text_pdf), "--model", "claude-custom"])
    assert result.exit_code == ExitCode.OK
    assert ctor.call_args.kwargs["model"] == "claude-custom"

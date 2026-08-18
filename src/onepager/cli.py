"""Typer entry point: argument handling, progress, exit codes."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Annotated

import typer
from pydantic import ValidationError
from rich.table import Table

from .analyze import AnalysisClient, AuthFailure, BadModelOutput
from .analyze.prompts import build_user_text
from .config import MAX_SLIDES, ExitCode, model_id
from .extract import Deck, ExtractionError, NoContentError, extract
from .models import TeamAnalysis
from .render import RenderError, render
from .template import blank_analysis
from .util.logging import configure, err_console, fail, out_console

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="Generate a one-page, TEN Capital-branded founder & team assessment from a pitch deck.",
)


def _default_output(deck_path: Path) -> Path:
    return Path.cwd() / f"{deck_path.stem}_Team_OnePager.pdf"


def _extraction_table(deck: Deck) -> Table:
    table = Table(title="Extraction", show_lines=False, title_justify="left")
    table.add_column("Slide", justify="right")
    table.add_column("Title", overflow="ellipsis", max_width=44)
    table.add_column("Chars", justify="right")
    table.add_column("Notes?", justify="center")
    table.add_column("Image?", justify="center")
    table.add_column("Team?", justify="center")
    for s in deck.slides:
        table.add_row(
            str(s.index),
            s.title or "-",
            str(s.char_count),
            "yes" if s.speaker_notes else "-",
            "yes" if s.image_b64 else "-",
            "[bold]HINT[/bold]" if s.looks_like_team_slide() else "-",
        )
    return table


@app.callback()
def main() -> None:
    """Keeps `analyze` a named subcommand instead of collapsing into the app root."""


@app.command()
def analyze(
    deck_path: Annotated[Path, typer.Argument(help="Pitch deck: .pdf, .pptx, or .ppt")],
    output: Annotated[
        Path | None,
        typer.Option("--output", "-o", help="Output PDF path."),
    ] = None,
    json_out: Annotated[
        Path | None,
        typer.Option("--json", help="Also write the raw analysis JSON, for audit or re-render."),
    ] = None,
    from_json: Annotated[
        Path | None,
        typer.Option("--from-json", help="Render from a saved analysis JSON. Makes no API call."),
    ] = None,
    company: Annotated[
        str | None,
        typer.Option("--company", help="Override the company name if extraction gets it wrong."),
    ] = None,
    model: Annotated[
        str | None,
        typer.Option("--model", help="Model ID. Defaults to $ANTHROPIC_MODEL."),
    ] = None,
    max_slides: Annotated[
        int, typer.Option("--max-slides", help="Cap slides sent to the model.")
    ] = MAX_SLIDES,
    vision: Annotated[
        bool | None,
        typer.Option("--vision/--no-vision", help="Send page images. Default: auto-detect."),
    ] = None,
    verbose: Annotated[
        bool, typer.Option("--verbose", "-v", help="Extraction stats, token usage, cost estimate.")
    ] = False,
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Extract and print the payload. Makes no API call.")
    ] = False,
) -> None:
    """Analyze DECK_PATH and write a one-page founder & team assessment."""
    configure(verbose)
    output = output or _default_output(deck_path)

    # --- render-only path: no extraction, no API, byte-identical output ----------------
    if from_json:
        analysis = _load_analysis(from_json)
        _render_or_exit(analysis, output, deck_path.name)
        return

    deck = _extract_or_exit(deck_path, vision, max_slides)

    if verbose:
        err_console.print(_extraction_table(deck))
        err_console.print(
            f"[dim]{len(deck.slides)} slides · {deck.total_chars} chars · "
            f"{deck.mean_chars:.0f} chars/slide · vision={'on' if deck.used_vision else 'off'} · "
            f"team-slide hints: {deck.team_slide_indices or 'none'}[/dim]"
        )
    for note in deck.notes:
        err_console.print(f"[yellow]note[/yellow] {note}")

    if dry_run:
        out_console.print(build_user_text(deck, company))
        images = sum(1 for s in deck.slides if s.image_b64)
        err_console.print(
            f"[bold]--dry-run[/bold] no API call made. Would send {len(deck.slides)} slides"
            f"{f' and {images} page images' if images else ''} to {model or model_id()}."
        )
        raise typer.Exit(ExitCode.OK)

    analysis = _analyze_or_exit(deck, company, model, verbose)

    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(analysis.model_dump_json(indent=2), encoding="utf-8")
        err_console.print(f"[green]wrote[/green] {json_out}")

    _render_or_exit(analysis, output, deck_path.name)


@app.command()
def template(
    output: Annotated[
        Path,
        typer.Option("--output", "-o", help="Where to write the template PDF."),
    ] = Path("onepager_template.pdf"),
    json_out: Annotated[
        Path | None,
        typer.Option("--json", help="Also write the placeholder analysis JSON."),
    ] = None,
) -> None:
    """Write the blank document template: structure and fields only, no company data.

    The template is rendered through the same layout engine as a real analysis, so it
    cannot drift from what the app actually produces. Makes no API call.
    """
    configure(False)
    blank = blank_analysis()
    if json_out:
        json_out.parent.mkdir(parents=True, exist_ok=True)
        json_out.write_text(blank.model_dump_json(indent=2), encoding="utf-8")
        err_console.print(f"[green]wrote[/green] {json_out}")
    _render_or_exit(blank, output, "[DECK FILENAME]")


# --- step wrappers: each owns one exit code ----------------------------------------------


def _extract_or_exit(deck_path: Path, vision: bool | None, max_slides: int) -> Deck:
    try:
        return extract(deck_path, vision=vision, max_slides=max_slides)
    except NoContentError as exc:
        fail(str(exc), "try --vision, or export a text-based version of the deck")
        raise typer.Exit(ExitCode.NO_CONTENT) from exc
    except ExtractionError as exc:
        fail(str(exc))
        raise typer.Exit(ExitCode.UNSUPPORTED_FILE) from exc


def _analyze_or_exit(
    deck: Deck, company: str | None, model: str | None, verbose: bool
) -> TeamAnalysis:
    try:
        client = AnalysisClient(model=model)
    except AuthFailure as exc:
        fail(str(exc), "see .env.example")
        raise typer.Exit(ExitCode.API_FAILURE) from exc

    with err_console.status(f"analyzing {len(deck.slides)} slides with {client.model}..."):
        try:
            analysis = client.analyze(deck, company)
        except AuthFailure as exc:
            fail(str(exc))
            raise typer.Exit(ExitCode.API_FAILURE) from exc
        except BadModelOutput as exc:
            fail(str(exc), "re-run, or use --model to try a different model")
            raise typer.Exit(ExitCode.BAD_MODEL_OUTPUT) from exc

    if verbose:
        u = client.usage
        err_console.print(
            f"[dim]{u.calls} API call(s) · {u.input_tokens} in / {u.output_tokens} out · "
            f"~${u.cost_usd:.3f} at list price · model {u.model}[/dim]"
        )
        for note in u.notes:
            err_console.print(f"[yellow]note[/yellow] {note}")
    return analysis


def _load_analysis(path: Path) -> TeamAnalysis:
    try:
        raw = path.read_text(encoding="utf-8")
    except OSError as exc:
        fail(f"could not read {path}: {exc}")
        raise typer.Exit(ExitCode.UNSUPPORTED_FILE) from exc
    try:
        return TeamAnalysis.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as exc:
        fail(f"{path} is not a valid analysis JSON.", str(exc).splitlines()[0])
        raise typer.Exit(ExitCode.BAD_MODEL_OUTPUT) from exc


def _render_or_exit(analysis: TeamAnalysis, output: Path, deck_name: str) -> None:
    try:
        report = render(analysis, output, deck_name, generated=date.today())
    except RenderError as exc:
        fail(str(exc))
        raise typer.Exit(ExitCode.RENDER_FAILURE) from exc
    status = " [yellow](degraded to fit one page)[/yellow]" if report.degraded else ""
    out_console.print(f"[green]wrote[/green] {output}{status}")


if __name__ == "__main__":  # pragma: no cover
    app()

"""Console + warning plumbing. Everything diagnostic goes to stderr."""

from __future__ import annotations

import logging

from rich.console import Console
from rich.logging import RichHandler

err_console = Console(stderr=True)
out_console = Console()

_LOGGER_NAME = "onepager"


def configure(verbose: bool = False) -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    logger.handlers.clear()
    handler = RichHandler(
        console=err_console, show_time=False, show_path=False, markup=False, rich_tracebacks=False
    )
    handler.setFormatter(logging.Formatter("%(message)s"))
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG if verbose else logging.INFO)
    logger.propagate = False
    return logger


def get_logger() -> logging.Logger:
    logger = logging.getLogger(_LOGGER_NAME)
    if not logger.handlers:
        configure(False)
    return logger


def fail(message: str, hint: str | None = None) -> None:
    """Print a user-facing error with no traceback."""
    err_console.print(f"[bold red]error[/bold red] {message}")
    if hint:
        err_console.print(f"[dim]hint:[/dim] {hint}")

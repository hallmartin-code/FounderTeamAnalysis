"""Measure-and-shrink helpers that keep the one-pager to exactly one page.

The renderer hands `find_fit` a builder that turns a `FitConfig` into laid-out columns.
`find_fit` walks a fixed degradation ladder, re-measuring after every step, and returns
the first config whose columns all fit — or the last one, with a record of the overflow.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace

_MEASURE_HEIGHT = 100_000.0
"""Effectively-infinite available height, so wrap() reports the natural height."""


@dataclass(frozen=True)
class FitConfig:
    """One rung of the degradation ladder."""

    body_size: float = 8.5
    spacing_scale: float = 1.0
    truncate_details: bool = False
    max_team_rows: int = 6
    max_strengths: int = 5
    max_weaknesses: int = 5

    def describe_drops(self, base: FitConfig) -> list[str]:
        drops: list[str] = []
        if self.body_size < base.body_size:
            drops.append(f"body font reduced {base.body_size:g}pt -> {self.body_size:g}pt")
        if self.spacing_scale < base.spacing_scale:
            pct = round((1 - self.spacing_scale) * 100)
            drops.append(f"leading and section spacing reduced {pct}%")
        if self.truncate_details and not base.truncate_details:
            drops.append("finding detail text truncated to the first sentence")
        if self.max_team_rows < base.max_team_rows:
            drops.append(f"team roster trimmed to {self.max_team_rows} rows")
        if self.max_strengths < base.max_strengths:
            drops.append(f"strengths trimmed to {self.max_strengths}")
        if self.max_weaknesses < base.max_weaknesses:
            drops.append(f"weaknesses trimmed to {self.max_weaknesses}")
        return drops


BASE_CONFIG = FitConfig()

#: Degradation order is fixed and deliberate: cosmetic loss before content loss.
LADDER: tuple[FitConfig, ...] = (
    BASE_CONFIG,
    replace(BASE_CONFIG, body_size=8.0),
    replace(BASE_CONFIG, body_size=7.5),
    replace(BASE_CONFIG, body_size=7.5, spacing_scale=0.85),
    replace(BASE_CONFIG, body_size=7.5, spacing_scale=0.85, truncate_details=True),
    replace(
        BASE_CONFIG,
        body_size=7.5,
        spacing_scale=0.85,
        truncate_details=True,
        max_team_rows=5,
    ),
    replace(
        BASE_CONFIG,
        body_size=7.5,
        spacing_scale=0.85,
        truncate_details=True,
        max_team_rows=4,
    ),
    replace(
        BASE_CONFIG,
        body_size=7.5,
        spacing_scale=0.85,
        truncate_details=True,
        max_team_rows=4,
        max_strengths=4,
    ),
    replace(
        BASE_CONFIG,
        body_size=7.5,
        spacing_scale=0.85,
        truncate_details=True,
        max_team_rows=4,
        max_strengths=4,
        max_weaknesses=4,
    ),
    replace(
        BASE_CONFIG,
        body_size=7.5,
        spacing_scale=0.85,
        truncate_details=True,
        max_team_rows=4,
        max_strengths=3,
        max_weaknesses=4,
    ),
    replace(
        BASE_CONFIG,
        body_size=7.5,
        spacing_scale=0.85,
        truncate_details=True,
        max_team_rows=4,
        max_strengths=3,
        max_weaknesses=3,
    ),
)


@dataclass
class Column:
    name: str
    flowables: list
    width: float
    available: float

    @property
    def required(self) -> float:
        return measure(self.flowables, self.width)

    @property
    def overflow(self) -> float:
        return max(0.0, self.required - self.available)


@dataclass
class FitResult:
    config: FitConfig
    columns: dict[str, Column]
    overflowed: bool
    dropped: list[str]
    overflow_by_column: dict[str, float]


def measure(flowables: list, width: float) -> float:
    """Natural stacked height of a flowable list at the given width."""
    total = 0.0
    for flowable in flowables:
        try:
            total += flowable.wrap(width, _MEASURE_HEIGHT)[1]
        except Exception:
            # A flowable that will not measure cannot be laid out either; charge it
            # a nominal height so it still counts toward overflow.
            total += 12.0
        total += getattr(flowable, "getSpaceBefore", lambda: 0)()
        total += getattr(flowable, "getSpaceAfter", lambda: 0)()
    return total


Builder = Callable[[FitConfig], dict[str, Column]]


def find_fit(build: Builder, ladder: tuple[FitConfig, ...] | None = None) -> FitResult:
    """Return the first ladder rung whose every column fits, else the last rung."""
    ladder = ladder if ladder is not None else LADDER
    columns: dict[str, Column] = {}
    config = ladder[0]
    for config in ladder:
        columns = build(config)
        if all(col.overflow <= 0 for col in columns.values()):
            return FitResult(
                config=config,
                columns=columns,
                overflowed=False,
                dropped=config.describe_drops(ladder[0]),
                overflow_by_column={},
            )
    return FitResult(
        config=config,
        columns=columns,
        overflowed=True,
        dropped=config.describe_drops(ladder[0]),
        overflow_by_column={n: c.overflow for n, c in columns.items() if c.overflow > 0},
    )


def first_sentence(text: str, hard_cap: int = 160) -> str:
    """Trim to the first sentence, falling back to a character cap."""
    stripped = text.strip()
    for end in (". ", "? ", "! "):
        idx = stripped.find(end)
        if 0 < idx <= hard_cap:
            return stripped[: idx + 1]
    if stripped.endswith((".", "?", "!")) and len(stripped) <= hard_cap:
        return stripped
    if len(stripped) <= hard_cap:
        return stripped
    cut = stripped[:hard_cap].rsplit(" ", 1)[0]
    return cut.rstrip(",;:") + "..."

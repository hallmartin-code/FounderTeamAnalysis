"""Normalized deck representation shared by every extractor."""

from __future__ import annotations

from dataclasses import dataclass, field

from ..config import TEAM_KEYWORDS


@dataclass
class SlideContent:
    index: int
    """1-based, matching what a human sees when flipping through the deck."""
    title: str | None = None
    text: str = ""
    speaker_notes: str | None = None
    image_b64: str | None = None
    char_count: int = 0

    def __post_init__(self) -> None:
        if not self.char_count:
            self.char_count = len(self.text)

    @property
    def searchable(self) -> str:
        return " ".join(filter(None, [self.title, self.text, self.speaker_notes])).lower()

    def looks_like_team_slide(self) -> bool:
        blob = self.searchable
        return any(kw in blob for kw in TEAM_KEYWORDS)


@dataclass
class Deck:
    source_path: str
    source_kind: str
    """'pdf', 'pptx', or 'ppt'."""
    slides: list[SlideContent] = field(default_factory=list)
    used_vision: bool = False
    notes: list[str] = field(default_factory=list)
    """Extraction observations worth telling the operator about."""

    @property
    def total_chars(self) -> int:
        return sum(s.char_count for s in self.slides)

    @property
    def mean_chars(self) -> float:
        return self.total_chars / len(self.slides) if self.slides else 0.0

    @property
    def team_slide_indices(self) -> list[int]:
        return [s.index for s in self.slides if s.looks_like_team_slide()]


class ExtractionError(Exception):
    """Raised when a deck cannot be opened or read at all (exit code 2)."""


class NoContentError(Exception):
    """Raised when a deck opens but yields nothing usable (exit code 3)."""

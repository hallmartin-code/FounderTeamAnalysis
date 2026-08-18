"""Environment, tunables, and branding constants."""

from __future__ import annotations

import os
import shutil
from enum import IntEnum
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

DEFAULT_MODEL = "claude-opus-5"

# Approximate Claude Opus 5 list pricing, USD per million tokens. Used only for the
# --verbose cost estimate; it is an estimate, not a bill.
PRICE_PER_MTOK = {"input": 5.00, "output": 25.00}

# --- extraction tunables -------------------------------------------------------------

#: Below this mean chars/page a PDF is treated as image-based and rasterized.
IMAGE_TEXT_THRESHOLD = 120
#: Below this total char count with no vision available we cannot analyze at all.
MIN_TOTAL_CHARS = 200
#: Rasterization DPI and the longest-edge pixel cap for vision images.
RASTER_DPI = 110
RASTER_MAX_EDGE = 1568
#: Default cap on slides handed to the model.
MAX_SLIDES = 40
#: Vision is expensive; never send more page images than this.
MAX_VISION_IMAGES = 25

TEAM_KEYWORDS = (
    "team",
    "founder",
    "founding",
    "leadership",
    "advisor",
    "advisory",
    "who we are",
    "management",
    "board",
    "our people",
    "leadership team",
)

# --- scoring -------------------------------------------------------------------------

SCORE_WEIGHTS = {
    "founder_market_fit": 30,
    "founder_product_fit": 20,
    "track_record": 20,
    "team_completeness": 20,
    "commitment_structure": 10,
}

#: Below this evidence_quality the one-pager must band the score LOW CONFIDENCE.
LOW_CONFIDENCE_THRESHOLD = 40

# --- branding ------------------------------------------------------------------------

BRAND_NAME = "TEN Capital Network"
FOOTER_TAGLINE = "Analysis grounded in the submitted deck; unverified claims flagged"


# --- web app -------------------------------------------------------------------------

#: Upload ceiling. Image-heavy decks are routinely 50 MB+.
MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB") or 64)
#: How long a finished job (and its PDF) stays in memory.
JOB_TTL_MINUTES = int(os.getenv("JOB_TTL_MINUTES") or 60)


def app_password() -> str | None:
    """Shared secret gating the web app. Unset means the app is open to anyone."""
    return (os.getenv("APP_PASSWORD") or "").strip() or None


class ExitCode(IntEnum):
    OK = 0
    UNSUPPORTED_FILE = 2
    NO_CONTENT = 3
    API_FAILURE = 4
    BAD_MODEL_OUTPUT = 5
    RENDER_FAILURE = 6


def model_id() -> str:
    return os.getenv("ANTHROPIC_MODEL") or DEFAULT_MODEL


def api_key() -> str | None:
    return os.getenv("ANTHROPIC_API_KEY") or None


def soffice_path() -> str | None:
    """Locate a LibreOffice headless binary, or None if unavailable."""
    for name in ("soffice", "soffice.exe", "libreoffice"):
        found = shutil.which(name)
        if found:
            return found
    for candidate in (
        r"C:\Program Files\LibreOffice\program\soffice.exe",
        r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
        "/usr/bin/soffice",
        "/Applications/LibreOffice.app/Contents/MacOS/soffice",
    ):
        if Path(candidate).exists():
            return candidate
    return None

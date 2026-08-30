"""Derive the favicon set from the TEN Capital brand mark.

The source of record is ``src/onepager/web/static/logo-source.png`` — the mark as
delivered, transparent, with its own padding. Everything else in that directory is
generated from it by this script. All outputs are checked in; rerun only when the mark
itself changes:

    python tools/make_favicon.py

Conventions match the sibling TEN Capital tools: transparent favicons, and an
apple-touch icon on the navy-950 ground the web UI uses (iOS composites transparency
unpredictably, so that one needs a real background).
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

STATIC = Path(__file__).resolve().parents[1] / "src" / "onepager" / "web" / "static"
SOURCE = STATIC / "logo-source.png"

#: navy-950, the web UI's page ground.
APPLE_BG = (11, 21, 38, 255)

#: Sizes packed into favicon.ico. 48 is what Windows taskbar pins use.
ICO_SIZES = ((16, 16), (32, 32), (48, 48), (64, 64))
APPLE_SIZE = 180

#: Fraction of the edge left as empty margin around the mark.
FAVICON_MARGIN = 0.04
APPLE_MARGIN = 0.14  # iOS crops to a rounded rect; leave it room


def _trimmed(source: Image.Image) -> Image.Image:
    """The mark with its own padding removed, so small sizes stay legible."""
    box = source.getchannel("A").getbbox()
    return source.crop(box) if box else source


def render(mark: Image.Image, size: int, margin: float, background=None) -> Image.Image:
    """Square icon at `size` px, the mark centred with `margin` breathing room."""
    inner = max(1, round(size * (1 - 2 * margin)))
    scaled = mark.resize((inner, inner), Image.LANCZOS)
    canvas = Image.new("RGBA", (size, size), background or (0, 0, 0, 0))
    offset = (size - inner) // 2
    canvas.paste(scaled, (offset, offset), scaled)
    return canvas


def main() -> None:
    if not SOURCE.exists():
        raise SystemExit(f"missing brand mark: {SOURCE}")

    mark = _trimmed(Image.open(SOURCE).convert("RGBA"))
    written: list[tuple[str, int]] = []

    def save(image: Image.Image, name: str, **kwargs) -> None:
        path = STATIC / name
        image.save(path, **kwargs)
        written.append((name, path.stat().st_size))

    # Multi-resolution .ico: browsers and OS pins pick the size they need.
    save(
        render(mark, 256, FAVICON_MARGIN),
        "favicon.ico",
        format="ICO",
        sizes=ICO_SIZES,
    )
    for size in (16, 32, 48, 192):
        save(render(mark, size, FAVICON_MARGIN), f"favicon-{size}.png", format="PNG")
    save(
        render(mark, APPLE_SIZE, APPLE_MARGIN, APPLE_BG),
        "apple-touch-icon.png",
        format="PNG",
    )

    for name, size in written:
        print(f"  {name:<24} {size:>7,} bytes")


if __name__ == "__main__":
    main()

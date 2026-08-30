"""Packaging invariants.

These exist because of a real production failure: `onepager/notify.py` imported `httpx`,
which was declared only in the dev extra. It worked in development because the test tooling
pulled it in, and it worked nowhere else — the Anthropic SDK ships `httpx2`, not `httpx`, so
the container had no `httpx` at all and the app died on import at startup.

A missing runtime dependency is invisible until deploy unless something checks for it.
"""

from __future__ import annotations

import ast
import sys
import tomllib
from importlib.metadata import packages_distributions
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "onepager"
FIRST_PARTY = {"onepager"}


def _normalise(name: str) -> str:
    """PEP 503 name normalisation."""
    out = name.lower()
    for ch in "-_.":
        out = out.replace(ch, "-")
    while "--" in out:
        out = out.replace("--", "-")
    return out


def _declared() -> set[str]:
    """Every distribution this project declares, across the main list and all extras."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    project = data["project"]
    specs = list(project.get("dependencies", []))
    for extra in project.get("optional-dependencies", {}).values():
        specs.extend(extra)
    names = set()
    for spec in specs:
        # Strip extras, markers and version constraints: "uvicorn[standard]>=0.30" -> uvicorn
        head = spec.split(";")[0].strip()
        for sep in ("[", ">", "<", "=", "!", "~", " "):
            head = head.split(sep)[0]
        if head:
            names.add(_normalise(head))
    return names


def _runtime_declared() -> set[str]:
    """Only the main dependency list — what a plain `pip install .` actually provides."""
    data = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    names = set()
    for spec in data["project"].get("dependencies", []):
        head = spec.split(";")[0].strip()
        for sep in ("[", ">", "<", "=", "!", "~", " "):
            head = head.split(sep)[0]
        if head:
            names.add(_normalise(head))
    return names


def _imports(path: Path) -> set[str]:
    """Top-level absolute imports in one module."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            found.add(node.module.split(".")[0])
    return found


def _third_party(modules: set[str]) -> set[str]:
    return {
        m
        for m in modules
        if m not in sys.stdlib_module_names and m not in FIRST_PARTY and not m.startswith("_")
    }


def _distribution_for(module: str) -> str | None:
    dists = packages_distributions().get(module)
    return _normalise(dists[0]) if dists else None


def _modules_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*.py") if "__pycache__" not in p.parts)


def test_src_tree_is_non_empty() -> None:
    assert _modules_under(SRC), "no source modules found; the walk below would pass vacuously"


@pytest.mark.parametrize("module", _modules_under(SRC), ids=lambda p: p.stem)
def test_every_import_is_a_declared_dependency(module: Path) -> None:
    declared = _declared()
    for name in sorted(_third_party(_imports(module))):
        dist = _distribution_for(name)
        assert dist is not None, f"{module.name} imports {name!r}, which is not installed"
        assert dist in declared, (
            f"{module.relative_to(ROOT)} imports {name!r} (from {dist!r}), "
            f"which pyproject.toml does not declare"
        )


def test_core_modules_only_import_runtime_dependencies() -> None:
    """Everything outside `web/` must work from a plain `pip install .`.

    The CLI is installed without the `web` extra, so a core module reaching for a
    web-only package would break it.
    """
    runtime = _runtime_declared()
    offenders: list[str] = []
    for module in _modules_under(SRC):
        if "web" in module.relative_to(SRC).parts:
            continue
        for name in sorted(_third_party(_imports(module))):
            dist = _distribution_for(name)
            if dist and dist not in runtime:
                offenders.append(f"{module.relative_to(ROOT)} imports {name} (from {dist})")
    assert not offenders, "core modules depend on non-runtime packages:\n  " + "\n  ".join(
        offenders
    )


def test_httpx_is_a_runtime_dependency() -> None:
    """The exact regression: notify.py needs httpx, and anthropic no longer supplies it."""
    assert "httpx" in _runtime_declared()


def test_notify_is_importable_without_the_web_extra() -> None:
    """notify.py sits outside web/, so the CLI install must be able to import it."""
    import onepager.notify  # noqa: F401

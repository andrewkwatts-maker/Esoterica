"""The extension's real surface, the wrapper's list of it, and the stub agree.

This is the test that catches the failure mode nobody notices. In the sibling
`arithma` package the compiled extension exported 87 symbols while the Python
wrapper listed 42: the missing 45 were compiled into the wheel, shipped, and
unreachable. Nothing failed. They were simply absent, and stayed absent across
several releases.

So the comparison here runs in **both** directions:

* every symbol the extension exports must appear in `_backend`'s lists, or the
  binding is dead weight nobody can call;
* every name in those lists must exist in the extension, or the wrapper is
  advertising something that will raise `AttributeError` on first use.

The same two directions are then checked against `_core.pyi`, because a stub
that has drifted lies to every type checker and editor downstream, and against
the three places the version is written down.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest

import esoterica
from esoterica import _backend

ROOT = Path(__file__).resolve().parents[1]

#: Names Python puts on every module object. They are not part of the
#: extension's surface and must not be compared against the wrapper's lists.
_MODULE_DUNDERS = frozenset(
    {
        "__all__",
        "__builtins__",
        "__doc__",
        "__file__",
        "__loader__",
        "__name__",
        "__package__",
        "__spec__",
        "__path__",
        "__test__",
    }
)


def _extension_surface() -> set[str]:
    """Every name `esoterica._core` actually exports.

    PyO3 fills `__all__` in from the registrations themselves, so it is the
    module's own account of what it added. `dir()` is the objects that are
    really reachable on it. They are compared here rather than one being
    trusted: a name in only one of them means a registration and its object
    disagree, and that is worth failing on before anything else is checked.
    """
    core = _backend._core
    declared = set(core.__all__)
    visible = {
        name
        for name in dir(core)
        if name not in _MODULE_DUNDERS and not name.startswith("_")
    }
    assert declared == visible, (
        "esoterica._core.__all__ and dir() disagree: "
        f"only in __all__ {sorted(declared - visible)}, "
        f"only reachable {sorted(visible - declared)}"
    )
    return visible


def _declared_surface() -> set[str]:
    """Every name `_backend` claims the extension exports."""
    return set(_backend._FUNCTIONS) | set(_backend._CONSTANTS)


def _version_in(path: Path) -> str:
    """First `version = "..."` in a TOML file.

    A three-line regex rather than `tomllib`, which is 3.11+ while this
    package supports 3.10. Both files put the version in the first table, so
    the first match is the right one.
    """
    text = path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"([^"]+)"', text, re.MULTILINE)
    assert match is not None, f"no version found in {path}"
    return match.group(1)


def _stub_surface() -> set[str]:
    """Every name declared in `_core.pyi`."""
    text = (ROOT / "src" / "esoterica" / "_core.pyi").read_text(encoding="utf-8")
    functions = set(re.findall(r"^def ([A-Za-z_][A-Za-z0-9_]*)\(", text, re.MULTILINE))
    constants = set(
        re.findall(r"^([A-Za-z_][A-Za-z0-9_]*)\s*:\s*[A-Za-z]", text, re.MULTILINE)
    )
    return functions | constants


# ---------------------------------------------------------------------------
# The backend has to be there at all
# ---------------------------------------------------------------------------

def test_the_extension_is_loaded():
    """Everything below compares against a live extension, so say so first.

    Deliberately a failure and not a skip: a skipped surface test is exactly
    the silence this package was rewritten to remove.
    """
    assert _backend.HAS_RUST, (
        "esoterica._core is not loaded, so the surface cannot be compared. "
        "Build it with `python -m maturin develop --features extension-module`. "
        f"Reported reason: {_backend._REASON or 'none given'}"
    )


def test_assert_rust_backend_accepts_a_live_current_extension():
    esoterica.assert_rust_backend()


def test_backend_report_describes_a_healthy_backend():
    report = esoterica.backend_report()
    assert report["has_rust"] is True
    assert report["version_mismatch"] is None
    assert report["reason"] is None
    assert report["functions"] == len(_backend._FUNCTIONS)
    assert report["constants"] == len(_backend._CONSTANTS)


# ---------------------------------------------------------------------------
# Drift, both directions
# ---------------------------------------------------------------------------

def test_no_binding_is_compiled_in_and_left_unreachable():
    """Extension -> wrapper. A symbol here that is not listed is dead weight."""
    unreachable = sorted(_extension_surface() - _declared_surface())
    assert not unreachable, (
        "esoterica._core exports symbols that _backend does not re-export, so "
        "they are compiled into the wheel and unreachable from Python: "
        f"{unreachable}. Add them to _FUNCTIONS or _CONSTANTS."
    )


def test_the_wrapper_advertises_nothing_the_extension_lacks():
    """Wrapper -> extension. A name listed here that is absent raises later."""
    missing = sorted(_declared_surface() - _extension_surface())
    assert not missing, (
        "_backend lists symbols esoterica._core does not export: "
        f"{missing}. Either the extension is stale or the list is wrong."
    )


def test_the_lists_agree_with_what_the_names_actually_are():
    """A function in the constant list (or the reverse) breaks the fallback path.

    The degraded path substitutes a raising *callable* for every function and
    `None` for every constant. Filing a name under the wrong heading is only
    visible when the extension is missing -- which is the one moment nobody
    wants a second bug.
    """
    for name in _backend._FUNCTIONS:
        assert callable(getattr(_backend._core, name)), (
            f"{name} is listed as a function but is not callable"
        )
    for name in _backend._CONSTANTS:
        value = getattr(_backend._core, name)
        assert not callable(value), f"{name} is listed as a constant but is callable"
        assert isinstance(value, (int, float, str)), (
            f"{name} is {type(value).__name__}, which the degraded path cannot "
            "stand in for with None"
        )


def test_the_stub_matches_the_extension_both_ways():
    stub = _stub_surface()
    extension = _extension_surface()
    assert not (extension - stub), (
        f"_core.pyi is missing {sorted(extension - stub)}; type checkers will "
        "reject calls that work at runtime."
    )
    assert not (stub - extension), (
        f"_core.pyi declares {sorted(stub - extension)}, which the extension "
        "does not export; type checkers will accept calls that raise."
    )


def test_the_package_re_exports_every_accelerated_function():
    """`import esoterica; esoterica.strip_html(...)` has to keep working."""
    exported = set(esoterica.__all__)
    for name in _backend._FUNCTIONS:
        assert name in exported, f"esoterica.__all__ omits {name}"
        assert callable(getattr(esoterica, name)), f"esoterica.{name} is not callable"


# ---------------------------------------------------------------------------
# The version handshake
# ---------------------------------------------------------------------------

def test_the_version_is_the_same_in_all_four_places():
    """pyproject, Cargo.toml, the package and the compiled extension.

    A mismatch is not cosmetic: `assert_rust_backend()` refuses to run on one,
    and the whole point of that refusal is to catch a stale `_core` left in
    the tree from an earlier build.
    """
    pyproject = _version_in(ROOT / "pyproject.toml")
    crate = _version_in(ROOT / "rust" / "apocrypha_core" / "Cargo.toml")
    assert pyproject == crate == _backend.PACKAGE_VERSION == esoterica.__version__, (
        f"pyproject={pyproject!r} crate={crate!r} "
        f"package={_backend.PACKAGE_VERSION!r} dunder={esoterica.__version__!r}"
    )
    assert esoterica.version_rust() == _backend.PACKAGE_VERSION
    assert _backend.VERSION == _backend.PACKAGE_VERSION
    assert esoterica.is_rust_backend() is True


def test_a_version_mismatch_is_refused_rather_than_tolerated():
    """The handshake has to be able to fail, or it is decoration.

    Patches the recorded extension version so the check sees the stale-build
    case it exists for, then puts it back.
    """
    original = _backend._RUST_VERSION
    try:
        _backend._RUST_VERSION = "0.0.0-not-a-real-build"
        with pytest.raises(esoterica.RustBackendUnavailable):
            esoterica.assert_rust_backend()
        assert esoterica.backend_report()["version_mismatch"] is not None
    finally:
        _backend._RUST_VERSION = original
    esoterica.assert_rust_backend()


# ---------------------------------------------------------------------------
# The package's own export list
# ---------------------------------------------------------------------------

def test_every_name_in_all_resolves_and_appears_once():
    missing = [name for name in esoterica.__all__ if not hasattr(esoterica, name)]
    assert not missing, f"esoterica.__all__ names nothing: {missing}"
    duplicates = sorted(
        {name for name in esoterica.__all__ if esoterica.__all__.count(name) > 1}
    )
    assert not duplicates, f"esoterica.__all__ repeats {duplicates}"


def test_no_public_name_is_reachable_but_undeclared():
    """A name reachable as an attribute but absent from `__all__` is invisible.

    `from esoterica import *` and every documentation tool that reads the list
    skip it, which is how a public entry point disappears without anything
    failing. The sibling package had exactly that: `Refresh` was importable
    for a whole release and named nowhere.
    """
    import inspect

    exempt = {"annotations"}  # the __future__ feature object, not an export
    undeclared = sorted(
        name
        for name, value in vars(esoterica).items()
        if not name.startswith("_")
        and name not in set(esoterica.__all__)
        and name not in exempt
        and not inspect.ismodule(value)
    )
    assert not undeclared, (
        f"reachable as esoterica.<name> but missing from __all__: {undeclared}"
    )

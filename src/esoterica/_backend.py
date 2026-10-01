"""The Rust backend: the import, the version handshake, and the no-fallback policy.

Every accelerated symbol in this package comes from the compiled extension
``esoterica._core``, built from the ``apocrypha_core`` crate. There is no
second implementation. That is deliberate, and it is a change of policy:

The package used to carry a Python copy of ``score_entity`` and ``tags_match``
behind ``except ImportError``, and the two disagreed -- the Rust version
awarded a subsequence bonus the Python version did not. Which one you got
depended on whether a wheel had been built, and nothing told you. A shadow
implementation that drifts is worse than no implementation, because the
failure is invisible. So when the extension is missing, every symbol that
*computes* something raises :class:`RustBackendUnavailable` naming the reason,
and callers that need to know in advance ask :func:`assert_rust_backend`.

The two symbols that only *report* on the backend -- :func:`is_rust_backend`
and :func:`version_rust` -- keep answering, with ``False`` and ``""``. A
health check that raises leaves a caller with no way to ask the question,
which is a different kind of silence and no better.

A stale extension is the other half of the same problem: a ``_core`` left in
the source tree from an earlier build produces behaviour nobody can explain.
Import performs a version handshake and warns loudly on a mismatch;
:func:`assert_rust_backend` treats it as an error.
"""
from __future__ import annotations

import warnings

#: Kept in step with ``pyproject.toml`` and ``apocrypha_core``'s
#: ``Cargo.toml``. The handshake below is what makes the three-way sync
#: enforceable rather than aspirational.
PACKAGE_VERSION = "1.2.0"

#: Callables the extension provides.
_FUNCTIONS = (
    "is_rust_backend",
    "is_subsequence",
    "rank_entities",
    "score_entity",
    "strip_html",
    "strip_html_batch",
    "tags_match",
    "version_rust",
)

#: Plain values the extension provides. They need a separate list because the
#: degradation path below substitutes a raising callable for everything else,
#: and a constant is not called.
_CONSTANTS = (
    "MAX_BATCH_LEN",
    "MAX_TAGS",
    "MAX_TEXT_BYTES",
    "VERSION",
    "WEIGHT_DESCRIPTION",
    "WEIGHT_FUZZY",
    "WEIGHT_NAME_PREFIX",
    "WEIGHT_NAME_SUBSTRING",
    "WEIGHT_SEARCH_TEXT",
)


class RustBackendUnavailable(RuntimeError):
    """Raised when the Rust backend is required but is not usable.

    Covers both "the extension did not import" and "the extension is a
    different version from this package".
    """


HAS_RUST = False
_REASON = ""
_RUST_VERSION: str | None = None

#: The two symbols that must keep answering when the extension is absent.
#: They report on the backend rather than using it, so raising from them would
#: leave a caller with no way to ask the question at all -- and
#: `apocrypha_core::pyfacade::is_rust_backend` documents the Python side as
#: providing a ``False``-returning counterpart. Everything else in
#: :data:`_FUNCTIONS` computes something, and computing is what has become
#: impossible.
_HEALTH_FUNCTIONS = ("is_rust_backend", "version_rust")

try:
    from . import _core  # type: ignore[attr-defined]
except ImportError as _import_error:  # pragma: no cover - depends on the build
    _core = None  # type: ignore[assignment]
    _REASON = (
        f"esoterica._core failed to load ({_import_error}). Install the "
        "prebuilt wheel, or build in place with "
        "`python -m maturin develop --features extension-module`."
    )

    def _missing(symbol: str):
        """Build a stand-in that raises instead of degrading silently."""

        def _raise(*_args, **_kwargs):
            raise RustBackendUnavailable(f"esoterica.{symbol} unavailable: {_REASON}")

        return _raise

    def is_rust_backend() -> bool:  # type: ignore[misc]
        """False. The question is answered, not refused -- see the note above."""
        return False

    def version_rust() -> str:  # type: ignore[misc]
        """The empty string: no extension loaded, so none reported a version.

        Deliberately not :data:`PACKAGE_VERSION`. Returning that would make a
        missing extension indistinguishable from a matching one to anything
        that compares the two, which is the handshake this module exists for.
        """
        return ""

    for _name in _FUNCTIONS:
        if _name not in _HEALTH_FUNCTIONS:
            globals()[_name] = _missing(_name)
    for _name in _CONSTANTS:
        globals()[_name] = None
    del _name
else:
    for _name in _FUNCTIONS + _CONSTANTS:
        globals()[_name] = getattr(_core, _name)
    del _name
    HAS_RUST = True
    _RUST_VERSION = _core.version_rust()
    if str(_RUST_VERSION) != PACKAGE_VERSION:
        _REASON = (
            f"esoterica._core reports version {_RUST_VERSION!r} but the "
            f"package is {PACKAGE_VERSION!r}. A stale extension is left over "
            "from an earlier build; rebuild with "
            "`python -m maturin develop --features extension-module`."
        )
        # Loud rather than fatal: import must still succeed so the mismatch
        # can be diagnosed, but nothing about it is allowed to be quiet.
        warnings.warn(_REASON, RuntimeWarning, stacklevel=2)


def assert_rust_backend() -> None:
    """Raise :class:`RustBackendUnavailable` unless the backend is live and current.

    Call this at the top of any program that depends on the accelerated path,
    so a missing or stale extension fails at startup rather than at the first
    query. ``HAS_RUST`` alone only says the extension imported; this also
    checks the version handshake.
    """
    if not HAS_RUST:
        raise RustBackendUnavailable(
            _REASON
            or "esoterica._core is not available; install the wheel or run "
            "`python -m maturin develop --features extension-module`."
        )
    if str(_RUST_VERSION) != PACKAGE_VERSION:
        raise RustBackendUnavailable(_REASON)


def backend_report() -> dict:
    """Describe the backend, for diagnostics and bug reports."""
    return {
        "has_rust": HAS_RUST,
        "rust_version": _RUST_VERSION,
        "package_version": PACKAGE_VERSION,
        "version_mismatch": (
            None
            if HAS_RUST and str(_RUST_VERSION) == PACKAGE_VERSION
            else f"{_RUST_VERSION!r} != {PACKAGE_VERSION!r}"
        ),
        "reason": _REASON or None,
        "functions": len(_FUNCTIONS),
        "constants": len(_CONSTANTS),
    }


__all__ = [
    "HAS_RUST",
    "PACKAGE_VERSION",
    "RustBackendUnavailable",
    "assert_rust_backend",
    "backend_report",
    *_FUNCTIONS,
    *_CONSTANTS,
]

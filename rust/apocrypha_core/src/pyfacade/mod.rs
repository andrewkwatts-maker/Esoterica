//! PyO3 facade for the `esoterica` Python package, exposed as `esoterica._core`.
//!
//! Gated behind the `python` cargo feature, which is purely additive:
//! `apocrypha_core` is a complete library without it and never depends on a
//! Python interpreter. `python` enables the bindings and still links
//! libpython, so a test binary built with it runs; `extension-module` sits on
//! top and is turned on only by the wheel build, because it tells PyO3 not to
//! link libpython and makes any test binary unloadable. Fusing the two is why
//! `cargo test --features python` is missing from most PyO3 projects: the
//! tests below could never have executed anywhere.
//!
//! ## Conventions for everything in this directory
//!
//! - **Two meaningful runtime assertions minimum** per function, checking the
//!   preconditions the Python boundary cannot express in types.
//! - **Bounded loops.** Any iteration over Python-supplied data checks its
//!   length against a constant first.
//! - **Every non-void return is checked.** No discarded `Result`.
//! - **Errors surface as Python exceptions**, never as a default value. A
//!   wrapper that swallows an error is worse than one that does not exist,
//!   because it makes a dead backend look healthy. That is precisely the
//!   defect this rewrite removed from `esoterica`.

use pyo3::exceptions::{PyOverflowError, PyValueError};
use pyo3::prelude::*;

use crate::error::CoreError;

pub mod scoring;
pub mod text;

/// Translate a core error into the Python exception that fits it.
///
/// Bound violations are `OverflowError` rather than `ValueError` so a caller
/// can tell "you handed me more data than I accept" apart from "this argument
/// is wrong", and can react by chunking rather than by discarding.
pub fn to_py_err(error: CoreError) -> PyErr {
    debug_assert!(
        !error.to_string().is_empty(),
        "every CoreError variant carries a message"
    );
    match error {
        CoreError::TextTooLong { .. } | CoreError::SequenceTooLong { .. } => {
            PyOverflowError::new_err(error.to_string())
        }
        CoreError::ZeroLimit { .. } => PyValueError::new_err(error.to_string()),
    }
}

/// True when the accelerated backend is live.
///
/// Always `true` here by construction -- this function only exists inside the
/// extension. The Python package defines a `False`-returning counterpart when
/// the import fails, so callers have one question to ask either way.
#[pyfunction]
fn is_rust_backend() -> bool {
    true
}

/// The crate version, for the handshake `esoterica` performs on import.
#[pyfunction]
fn version_rust() -> &'static str {
    crate::VERSION
}

/// `esoterica._core` module entry point. Maturin routes to it through the
/// `[tool.maturin] module-name` setting in `pyproject.toml`.
#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add("VERSION", crate::VERSION)?;
    m.add("MAX_TEXT_BYTES", crate::MAX_TEXT_BYTES)?;
    m.add("MAX_BATCH_LEN", crate::MAX_BATCH_LEN)?;
    m.add("MAX_TAGS", crate::MAX_TAGS)?;
    m.add_function(wrap_pyfunction!(is_rust_backend, m)?)?;
    m.add_function(wrap_pyfunction!(version_rust, m)?)?;
    scoring::register(m)?;
    text::register(m)?;
    Ok(())
}

/// Start an interpreter for a test that needs one.
///
/// `cargo test --features python` links libpython but never starts it. PyO3's
/// `auto-initialize` feature would do this implicitly, and is deliberately not
/// enabled: it would be inherited by the wheel build, where an extension
/// module must never start its own interpreter. Asking explicitly here keeps
/// that separation, and is why these tests can run at all.
#[cfg(test)]
pub(crate) fn init_interpreter() {
    pyo3::prepare_freethreaded_python();
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bound_violations_map_to_overflow_error() {
        init_interpreter();
        Python::with_gil(|py| {
            let err = to_py_err(CoreError::TextTooLong {
                what: "op",
                field: "text",
                len: 9,
                limit: 8,
            });
            assert!(err.is_instance_of::<PyOverflowError>(py));
            let err = to_py_err(CoreError::SequenceTooLong {
                what: "op",
                field: "items",
                len: 9,
                limit: 8,
            });
            assert!(err.is_instance_of::<PyOverflowError>(py));
        });
    }

    #[test]
    fn a_zero_limit_maps_to_value_error() {
        init_interpreter();
        Python::with_gil(|py| {
            let err = to_py_err(CoreError::ZeroLimit {
                what: "rank",
                field: "limit",
            });
            assert!(err.is_instance_of::<PyValueError>(py));
        });
    }

    #[test]
    fn the_error_message_survives_translation() {
        init_interpreter();
        let err = to_py_err(CoreError::TextTooLong {
            what: "strip_html",
            field: "text",
            len: 99,
            limit: 8,
        });
        let message = err.to_string();
        assert!(message.contains("strip_html"), "lost the operation name");
        assert!(message.contains("99"), "lost the actual length");
        assert!(message.contains("OverflowError"), "lost the exception type");
    }

    #[test]
    fn the_backend_flag_and_version_agree_with_the_crate() {
        assert!(is_rust_backend());
        assert_eq!(version_rust(), crate::VERSION);
    }
}

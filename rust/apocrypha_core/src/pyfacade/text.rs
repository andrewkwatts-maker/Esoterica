//! PyO3 bindings for the HTML normalisation path.

// `#[pyfunction]` on pyo3 0.22 expands `-> PyResult<T>` into a `PyErr::from`
// round-trip that clippy reads as a no-op conversion in our own signature span.
#![allow(clippy::useless_conversion)]

use pyo3::prelude::*;

use crate::pyfacade::to_py_err;
use crate::text::{
    is_python_re_space, strip_html as core_strip_html, strip_html_batch as core_strip_html_batch,
};

/// Strip HTML tags, decode character references, and normalise whitespace.
///
/// Replaces the three-`re.sub` pipeline that `_scraper._strip_html` ran two or
/// three times per scraped item. Raises `OverflowError` above
/// `MAX_TEXT_BYTES` rather than truncating: a silent prefix would corrupt an
/// article body without saying anything.
#[pyfunction]
#[pyo3(signature = (text))]
fn strip_html(text: &str) -> PyResult<String> {
    let out = core_strip_html(text).map_err(to_py_err)?;
    // Every stage removes bytes or leaves them alone: a tag becomes one
    // space, a reference is never longer encoded than written, and a
    // whitespace run becomes one space. Growth would mean a decoder bug.
    debug_assert!(
        out.len() <= text.len(),
        "normalisation grew the input from {} to {} bytes",
        text.len(),
        out.len()
    );
    debug_assert!(
        !out.starts_with(is_python_re_space) && !out.ends_with(is_python_re_space),
        "the output must already be trimmed"
    );
    Ok(out)
}

/// Apply [`strip_html`] across a list, crossing the FFI boundary once.
///
/// One over-long element fails the whole call. Substituting an empty string
/// for it would hide a truncated article among thousands of good ones, which
/// is the failure mode this module exists to prevent.
#[pyfunction]
#[pyo3(signature = (texts))]
fn strip_html_batch(texts: Vec<String>) -> PyResult<Vec<String>> {
    let count = texts.len();
    let out = core_strip_html_batch(&texts).map_err(to_py_err)?;
    debug_assert_eq!(out.len(), count, "every input must produce one output");
    debug_assert!(
        count <= crate::MAX_BATCH_LEN,
        "an over-long batch must have been rejected, not accepted"
    );
    Ok(out)
}

/// Register this module's functions on the extension module object.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Registering twice would silently rebind the names, so catch it here
    // rather than wonder later which definition won.
    debug_assert!(
        m.getattr("strip_html").is_err(),
        "text::register was already called on this module"
    );
    m.add_function(wrap_pyfunction!(strip_html, m)?)?;
    m.add_function(wrap_pyfunction!(strip_html_batch, m)?)?;
    debug_assert!(
        m.getattr("strip_html").is_ok() && m.getattr("strip_html_batch").is_ok(),
        "both functions must be reachable after registration"
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn tags_and_references_are_handled_across_the_boundary() {
        assert_eq!(strip_html("<p>caf&eacute;</p>").unwrap(), "caf\u{e9}");
        assert_eq!(strip_html("").unwrap(), "");
        assert_eq!(strip_html("  a \n b  ").unwrap(), "a b");
    }

    #[test]
    fn an_over_long_text_raises_rather_than_truncating() {
        crate::pyfacade::init_interpreter();
        let huge = "a".repeat(crate::MAX_TEXT_BYTES + 1);
        Python::with_gil(|py| {
            let err = strip_html(&huge).unwrap_err();
            assert!(err.is_instance_of::<pyo3::exceptions::PyOverflowError>(py));
        });
    }

    #[test]
    fn the_batch_form_agrees_with_the_scalar_form() {
        let inputs = vec![
            "<b>one</b>".to_string(),
            "t&amp;w".to_string(),
            String::new(),
        ];
        let batch = strip_html_batch(inputs.clone()).unwrap();
        let each: Vec<String> = inputs.iter().map(|s| strip_html(s).unwrap()).collect();
        assert_eq!(batch, each);
    }

    #[test]
    fn one_bad_element_fails_the_batch() {
        let inputs = vec!["fine".to_string(), "a".repeat(crate::MAX_TEXT_BYTES + 1)];
        assert!(strip_html_batch(inputs).is_err());
    }
}

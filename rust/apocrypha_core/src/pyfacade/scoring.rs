//! PyO3 bindings for relevance scoring and ranking.
//!
//! `score_entity` and `tags_match` keep the signatures and the numeric
//! behaviour they were published with in `_core.pyi`, so nothing that called
//! them breaks. What changed is that they are now the *only* implementation:
//! the shadow copies in `esoterica/__init__.py` disagreed with these -- they
//! omitted the subsequence bonus -- and whichever one you got depended on
//! whether a wheel had been built.

// `#[pyfunction]` on pyo3 0.22 expands `-> PyResult<T>` into a `PyErr::from`
// round-trip that clippy reads as a no-op conversion in our own signature span.
#![allow(clippy::useless_conversion)]

use pyo3::prelude::*;

use crate::error::check_text;
use crate::pyfacade::to_py_err;
use crate::scoring::{
    is_subsequence as core_is_subsequence, rank_candidates, score_entity as core_score_entity,
    tags_match as core_tags_match, Candidate, WEIGHT_DESCRIPTION, WEIGHT_FUZZY, WEIGHT_NAME_PREFIX,
    WEIGHT_NAME_SUBSTRING, WEIGHT_SEARCH_TEXT,
};

/// One row of [`rank_entities`] input: name, description, search text.
type Row = (String, String, String);

/// Score one entity against a query. An empty query scores `0.0`.
#[pyfunction]
#[pyo3(signature = (name, description, search_text, query))]
fn score_entity(name: &str, description: &str, search_text: &str, query: &str) -> PyResult<f64> {
    let score = core_score_entity(name, description, search_text, query).map_err(to_py_err)?;
    debug_assert!(score >= 0.0, "no weight is negative, so no score can be");
    debug_assert!(
        !query.is_empty() || score == 0.0,
        "an empty query must score exactly zero"
    );
    Ok(score)
}

/// True when any tag contains the query, case-insensitively.
#[pyfunction]
#[pyo3(signature = (tags, query))]
fn tags_match(tags: Vec<String>, query: &str) -> PyResult<bool> {
    let count = tags.len();
    let matched = core_tags_match(&tags, query).map_err(to_py_err)?;
    debug_assert!(
        !matched || count > 0,
        "an empty tag list cannot produce a match"
    );
    debug_assert!(
        count <= crate::MAX_TAGS,
        "an over-long tag list must have been rejected, not accepted"
    );
    Ok(matched)
}

/// True when `pattern`'s characters appear in `text` in order.
///
/// Exposed so a caller -- and the parity tests -- can check the fuzzy rule
/// directly rather than inferring it from a score.
#[pyfunction]
#[pyo3(signature = (text, pattern))]
fn is_subsequence(text: &str, pattern: &str) -> PyResult<bool> {
    let what = "is_subsequence";
    check_text(what, "text", text, crate::MAX_TEXT_BYTES).map_err(to_py_err)?;
    check_text(what, "pattern", pattern, crate::MAX_TEXT_BYTES).map_err(to_py_err)?;
    let matched = core_is_subsequence(text, pattern);
    debug_assert!(
        matched || !pattern.is_empty(),
        "an empty pattern is a subsequence of everything"
    );
    debug_assert!(
        !matched || pattern.chars().count() <= text.chars().count(),
        "a subsequence cannot be longer than its host"
    );
    Ok(matched)
}

/// Score a batch of `(name, description, search_text)` rows and return the
/// best `limit` as `(row_index, score)`, highest score first.
///
/// This is the call the ranking path is built around: one boundary crossing
/// for a whole result set, one case fold per string, and a deterministic
/// order. Rows scoring zero are omitted, so the result length is the number
/// of genuine matches and not a padded window.
#[pyfunction]
#[pyo3(signature = (rows, query, limit = 20))]
fn rank_entities(rows: Vec<Row>, query: &str, limit: usize) -> PyResult<Vec<(usize, f64)>> {
    let count = rows.len();
    let candidates: Vec<Candidate<'_>> = rows
        .iter()
        .take(crate::MAX_BATCH_LEN)
        .map(|(name, description, search_text)| Candidate {
            name,
            description,
            search_text,
        })
        .collect();
    debug_assert!(
        candidates.len() == count || count > crate::MAX_BATCH_LEN,
        "only an over-long batch may lose rows before validation"
    );
    let ranked = rank_candidates(&candidates, query, limit).map_err(to_py_err)?;
    debug_assert!(
        ranked.len() <= limit,
        "the core returned more rows than the caller asked for"
    );
    Ok(ranked.iter().map(|r| (r.index, r.score)).collect())
}

/// Register this module's functions and the weight constants.
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Registering twice would silently rebind the names, so catch it here
    // rather than wonder later which definition won.
    debug_assert!(
        m.getattr("score_entity").is_err(),
        "scoring::register was already called on this module"
    );
    m.add("WEIGHT_NAME_PREFIX", WEIGHT_NAME_PREFIX)?;
    m.add("WEIGHT_NAME_SUBSTRING", WEIGHT_NAME_SUBSTRING)?;
    m.add("WEIGHT_DESCRIPTION", WEIGHT_DESCRIPTION)?;
    m.add("WEIGHT_SEARCH_TEXT", WEIGHT_SEARCH_TEXT)?;
    m.add("WEIGHT_FUZZY", WEIGHT_FUZZY)?;
    m.add_function(wrap_pyfunction!(score_entity, m)?)?;
    m.add_function(wrap_pyfunction!(tags_match, m)?)?;
    m.add_function(wrap_pyfunction!(is_subsequence, m)?)?;
    m.add_function(wrap_pyfunction!(rank_entities, m)?)?;
    debug_assert!(
        m.getattr("rank_entities").is_ok() && m.getattr("score_entity").is_ok(),
        "the scoring functions must be reachable after registration"
    );
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn scoring_survives_the_boundary_unchanged() {
        assert_eq!(
            score_entity("Fireball", "", "", "fire").unwrap(),
            WEIGHT_NAME_PREFIX
        );
        assert_eq!(score_entity("Fireball", "", "", "").unwrap(), 0.0);
        assert_eq!(
            score_entity("Fireball", "", "", "fbl").unwrap(),
            WEIGHT_FUZZY
        );
    }

    #[test]
    fn tags_match_survives_the_boundary_unchanged() {
        let tags = vec!["Ceremonial-Magic".to_string()];
        assert!(tags_match(tags.clone(), "magic").unwrap());
        assert!(!tags_match(tags, "necromancy").unwrap());
        assert!(!tags_match(Vec::new(), "magic").unwrap());
    }

    #[test]
    fn subsequence_survives_the_boundary_unchanged() {
        assert!(is_subsequence("fireball", "fbl").unwrap());
        assert!(!is_subsequence("fireball", "fbz").unwrap());
        assert!(is_subsequence("anything", "").unwrap());
    }

    #[test]
    fn ranking_returns_indices_in_descending_score_order() {
        let rows = vec![
            ("Wildfire".to_string(), String::new(), String::new()),
            ("Fireball".to_string(), String::new(), String::new()),
        ];
        let ranked = rank_entities(rows, "fire", 20).unwrap();
        assert_eq!(ranked[0].0, 1);
        assert_eq!(ranked[0].1, WEIGHT_NAME_PREFIX);
        assert_eq!(ranked[1].0, 0);
        assert_eq!(ranked[1].1, WEIGHT_NAME_SUBSTRING);
    }

    #[test]
    fn ranking_agrees_with_scoring_row_by_row() {
        let rows = vec![
            (
                "Fireball".to_string(),
                "a fire spell".to_string(),
                "fire".to_string(),
            ),
            (
                "Hermeticism".to_string(),
                "alchemy".to_string(),
                "hermetic".to_string(),
            ),
            (
                "Fire Shield".to_string(),
                "wards".to_string(),
                "abjuration".to_string(),
            ),
        ];
        let ranked = rank_entities(rows.clone(), "fire", 20).unwrap();
        for (index, score) in ranked {
            let row = &rows[index];
            let direct = score_entity(&row.0, &row.1, &row.2, "fire").unwrap();
            assert_eq!(score, direct, "rank_entities disagreed with score_entity");
        }
    }

    #[test]
    fn a_zero_limit_raises_rather_than_returning_nothing() {
        crate::pyfacade::init_interpreter();
        let rows = vec![("Fireball".to_string(), String::new(), String::new())];
        Python::with_gil(|py| {
            let err = rank_entities(rows, "fire", 0).unwrap_err();
            assert!(err.is_instance_of::<pyo3::exceptions::PyValueError>(py));
        });
    }

    #[test]
    fn scoring_weights_still_add_the_way_the_pyi_promised() {
        let total = score_entity("Fireball", "a fire spell", "fire evocation", "fire").unwrap();
        assert_eq!(
            total,
            WEIGHT_NAME_PREFIX + WEIGHT_DESCRIPTION + WEIGHT_SEARCH_TEXT
        );
    }
}

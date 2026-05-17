use pyo3::prelude::*;

/// Score a magic/esoteric entity against a query.
#[pyfunction]
fn score_entity(name: &str, description: &str, search_text: &str, query: &str) -> f64 {
    let q = query.to_lowercase();
    let n = name.to_lowercase();
    if q.is_empty() { return 0.0; }
    let mut score = 0.0_f64;
    if n.starts_with(&q)   { score += 1000.0; }
    else if n.contains(&q) { score += 500.0; }
    if description.to_lowercase().contains(&q) { score += 150.0; }
    if search_text.to_lowercase().contains(&q) { score += 120.0; }
    if score == 0.0 && fuzzy_contains(&n, &q)  { score += 40.0; }
    score
}

/// Check if any tag in a list matches the query prefix (case-insensitive).
#[pyfunction]
fn tags_match(tags: Vec<String>, query: &str) -> bool {
    let q = query.to_lowercase();
    tags.iter().any(|t| t.to_lowercase().starts_with(&q) || t.to_lowercase().contains(&q))
}

fn fuzzy_contains(text: &str, pattern: &str) -> bool {
    let mut pi = pattern.chars().peekable();
    for tc in text.chars() {
        if let Some(&pc) = pi.peek() { if tc == pc { pi.next(); } }
        else { break; }
    }
    pi.peek().is_none()
}

#[pymodule]
fn _core(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(score_entity, m)?)?;
    m.add_function(wrap_pyfunction!(tags_match, m)?)?;
    Ok(())
}

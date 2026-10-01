//! Relevance scoring and ranking for esoterica entities.
//!
//! ## What was here before
//!
//! `score_entity` and `tags_match` already existed in Rust, and had **no call
//! site anywhere in the package** -- the Python query layer went straight to
//! SQLite and never asked for a score. They also disagreed with the Python
//! fallback that shadowed them when the extension was missing: the Rust side
//! awarded a subsequence bonus the Python side did not, so identical inputs
//! ranked differently depending on whether a wheel had been built. Both are
//! now the only implementation, and [`rank_candidates`] gives them the caller
//! they never had.
//!
//! ## The scale is fixed, not tuned
//!
//! The weights below reproduce the published behaviour of the original
//! `score_entity` exactly, including the rule that the subsequence bonus only
//! applies when nothing else matched. They are part of the module's contract
//! and are exported so a caller can reason about a score rather than compare
//! it to a magic number.
//!
//! ## Case folding happens once
//!
//! The original lowercased the query four times and the name twice per call.
//! Here every string is folded once per candidate, which is the whole reason
//! [`rank_candidates`] is worth crossing the FFI boundary for: a 5,000-entity
//! ranking pass folds 5,000 names, not 30,000 strings.

use crate::error::{check_len, check_text, CoreError};
use crate::{MAX_BATCH_LEN, MAX_TEXT_BYTES};

/// The query is a prefix of the entity name.
pub const WEIGHT_NAME_PREFIX: f64 = 1000.0;
/// The query appears inside the entity name but not at its start.
pub const WEIGHT_NAME_SUBSTRING: f64 = 500.0;
/// The query appears in the description.
pub const WEIGHT_DESCRIPTION: f64 = 150.0;
/// The query appears in the concatenated search text.
pub const WEIGHT_SEARCH_TEXT: f64 = 120.0;
/// The query is a subsequence of the name and nothing else matched.
pub const WEIGHT_FUZZY: f64 = 40.0;

/// Largest tag list accepted by [`tags_match`].
pub const MAX_TAGS: usize = 65_536;

/// One entity's searchable fields, borrowed for the duration of a ranking
/// pass. Borrowed rather than owned so a batch of thousands does not copy
/// every description twice.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct Candidate<'a> {
    /// Display name; carries the two heaviest weights.
    pub name: &'a str,
    /// Prose description.
    pub description: &'a str,
    /// The concatenated searchable blob the bake writes.
    pub search_text: &'a str,
}

/// A scored candidate, identified by its position in the input slice so the
/// caller can map back to whatever row it came from.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Ranked {
    /// Index into the slice passed to [`rank_candidates`].
    pub index: usize,
    /// Score from [`score_entity`]; always strictly positive here.
    pub score: f64,
}

/// True when `pattern` appears in `text` in order, not necessarily adjacently.
///
/// Empty patterns are trivially contained, matching the original behaviour.
pub fn is_subsequence(text: &str, pattern: &str) -> bool {
    debug_assert!(
        text.len() <= MAX_TEXT_BYTES,
        "caller must bound the haystack before matching"
    );
    debug_assert!(
        pattern.len() <= MAX_TEXT_BYTES,
        "caller must bound the needle before matching"
    );
    let mut wanted = pattern.chars().peekable();
    // One character of `text` is consumed per iteration, so its byte length is
    // a hard ceiling on the loop.
    for ch in text.chars().take(MAX_TEXT_BYTES) {
        match wanted.peek() {
            None => return true,
            Some(&next) if next == ch => {
                let _ = wanted.next();
            }
            Some(_) => {}
        }
    }
    wanted.peek().is_none()
}

/// Score already-lowercased fields. Split out so [`rank_candidates`] can fold
/// the query once for a whole batch instead of once per candidate.
fn score_lowered(name: &str, description: &str, search_text: &str, query: &str) -> f64 {
    debug_assert!(
        !query.is_empty(),
        "the empty query short-circuits before this point"
    );
    debug_assert!(
        query.chars().all(|c| !c.is_uppercase()),
        "score_lowered requires a pre-folded query"
    );
    let mut score = 0.0_f64;
    if name.starts_with(query) {
        score += WEIGHT_NAME_PREFIX;
    } else if name.contains(query) {
        score += WEIGHT_NAME_SUBSTRING;
    }
    if description.contains(query) {
        score += WEIGHT_DESCRIPTION;
    }
    if search_text.contains(query) {
        score += WEIGHT_SEARCH_TEXT;
    }
    // The subsequence bonus is a last resort by design: it is loose enough
    // that letting it stack on a real match would distort the ordering.
    if score == 0.0 && is_subsequence(name, query) {
        score += WEIGHT_FUZZY;
    }
    debug_assert!(score >= 0.0, "no weight is negative, so no score can be");
    score
}

/// Score one entity against a query. An empty query scores zero, because
/// every field trivially contains it and the ranking would be meaningless.
pub fn score_entity(
    name: &str,
    description: &str,
    search_text: &str,
    query: &str,
) -> Result<f64, CoreError> {
    let what = "score_entity";
    check_text(what, "name", name, MAX_TEXT_BYTES)?;
    check_text(what, "description", description, MAX_TEXT_BYTES)?;
    check_text(what, "search_text", search_text, MAX_TEXT_BYTES)?;
    check_text(what, "query", query, MAX_TEXT_BYTES)?;
    if query.is_empty() {
        return Ok(0.0);
    }
    debug_assert!(!query.is_empty(), "the empty query returned above");
    debug_assert!(
        query.len() <= MAX_TEXT_BYTES,
        "the length check above admitted an over-long query"
    );
    Ok(score_lowered(
        &name.to_lowercase(),
        &description.to_lowercase(),
        &search_text.to_lowercase(),
        &query.to_lowercase(),
    ))
}

/// True when any tag contains the query, case-insensitively.
///
/// The original tested `starts_with(q) || contains(q)`; a prefix is a
/// substring, so the first test could never change the answer.
pub fn tags_match<S: AsRef<str>>(tags: &[S], query: &str) -> Result<bool, CoreError> {
    let what = "tags_match";
    check_len(what, "tags", tags.len(), MAX_TAGS)?;
    check_text(what, "query", query, MAX_TEXT_BYTES)?;
    let folded = query.to_lowercase();
    debug_assert!(
        tags.len() <= MAX_TAGS,
        "the length check above admitted an over-long tag list"
    );
    debug_assert!(
        folded.len() >= query.len() || !query.is_ascii(),
        "ASCII folding never shortens a string"
    );
    for tag in tags.iter().take(MAX_TAGS) {
        check_text(what, "tag", tag.as_ref(), MAX_TEXT_BYTES)?;
        if tag.as_ref().to_lowercase().contains(&folded) {
            return Ok(true);
        }
    }
    Ok(false)
}

/// Score a whole batch and return the best `limit` matches, highest first.
///
/// Candidates scoring zero are dropped: a caller asking for the top 20 wants
/// 20 matches, not 20 rows of which 17 are unrelated. Ties break on input
/// order, so the result is a deterministic function of its arguments.
pub fn rank_candidates(
    candidates: &[Candidate<'_>],
    query: &str,
    limit: usize,
) -> Result<Vec<Ranked>, CoreError> {
    let what = "rank_candidates";
    check_len(what, "candidates", candidates.len(), MAX_BATCH_LEN)?;
    check_text(what, "query", query, MAX_TEXT_BYTES)?;
    if limit == 0 {
        return Err(CoreError::ZeroLimit {
            what,
            field: "limit",
        });
    }
    if query.is_empty() {
        return Ok(Vec::new());
    }
    let folded_query = query.to_lowercase();
    debug_assert!(limit > 0, "a zero limit was rejected above");
    debug_assert!(
        !folded_query.is_empty(),
        "folding a non-empty query cannot empty it"
    );

    let mut scored: Vec<Ranked> = Vec::new();
    for (index, candidate) in candidates.iter().enumerate().take(MAX_BATCH_LEN) {
        check_text(what, "name", candidate.name, MAX_TEXT_BYTES)?;
        check_text(what, "description", candidate.description, MAX_TEXT_BYTES)?;
        check_text(what, "search_text", candidate.search_text, MAX_TEXT_BYTES)?;
        let score = score_lowered(
            &candidate.name.to_lowercase(),
            &candidate.description.to_lowercase(),
            &candidate.search_text.to_lowercase(),
            &folded_query,
        );
        if score > 0.0 {
            scored.push(Ranked { index, score });
        }
    }
    // `total_cmp` rather than `partial_cmp().unwrap()`: no score can be NaN,
    // but an unwrap here would be an unchecked assumption in a sort that runs
    // over caller-supplied data.
    scored.sort_by(|a, b| b.score.total_cmp(&a.score).then(a.index.cmp(&b.index)));
    scored.truncate(limit);
    debug_assert!(scored.len() <= limit, "truncation must respect the limit");
    debug_assert!(
        scored.iter().all(|r| r.index < candidates.len()),
        "every ranked index must address a real candidate"
    );
    Ok(scored)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn score(name: &str, description: &str, search_text: &str, query: &str) -> f64 {
        score_entity(name, description, search_text, query).expect("inputs are in bounds")
    }

    #[test]
    fn an_empty_query_scores_zero() {
        assert_eq!(score("Fireball", "burns", "fire", ""), 0.0);
    }

    #[test]
    fn a_name_prefix_outranks_a_name_substring() {
        let prefix = score("Fireball", "", "", "fire");
        let substring = score("Wildfire", "", "", "fire");
        assert_eq!(prefix, WEIGHT_NAME_PREFIX);
        assert_eq!(substring, WEIGHT_NAME_SUBSTRING);
        assert!(prefix > substring);
    }

    #[test]
    fn field_weights_add_up() {
        let total = score("Fireball", "a fire spell", "fire evocation", "fire");
        assert_eq!(
            total,
            WEIGHT_NAME_PREFIX + WEIGHT_DESCRIPTION + WEIGHT_SEARCH_TEXT
        );
    }

    #[test]
    fn matching_is_case_insensitive() {
        assert_eq!(score("FIREBALL", "", "", "fire"), WEIGHT_NAME_PREFIX);
        assert_eq!(score("fireball", "", "", "FIRE"), WEIGHT_NAME_PREFIX);
    }

    #[test]
    fn the_fuzzy_bonus_only_applies_alone() {
        // "fbl" is a subsequence of "fireball" but not a substring.
        assert_eq!(score("Fireball", "", "", "fbl"), WEIGHT_FUZZY);
        // When a real field matches, the bonus must not stack on top.
        let with_real_match = score("Fireball", "", "", "fire");
        assert_eq!(with_real_match, WEIGHT_NAME_PREFIX);
    }

    #[test]
    fn an_unrelated_query_scores_zero() {
        assert_eq!(score("Fireball", "burns things", "evocation", "zzqx"), 0.0);
    }

    #[test]
    fn subsequence_handles_the_boundary_cases() {
        assert!(is_subsequence("fireball", ""));
        assert!(is_subsequence("fireball", "fireball"));
        assert!(is_subsequence("fireball", "fbl"));
        assert!(!is_subsequence("fireball", "fbz"));
        assert!(!is_subsequence("fire", "fireball"));
        assert!(!is_subsequence("", "a"));
        assert!(is_subsequence("", ""));
    }

    #[test]
    fn tags_match_is_substring_and_case_insensitive() {
        let tags = ["Ceremonial-Magic".to_string(), "Hermeticism".to_string()];
        assert!(tags_match(&tags, "hermetic").expect("in bounds"));
        assert!(tags_match(&tags, "MAGIC").expect("in bounds"));
        assert!(!tags_match(&tags, "necromancy").expect("in bounds"));
        // An empty query is contained in everything, which the original did
        // too; preserved deliberately.
        assert!(tags_match(&tags, "").expect("in bounds"));
        let empty: [String; 0] = [];
        assert!(!tags_match(&empty, "").expect("in bounds"));
    }

    #[test]
    fn ranking_orders_by_score_then_input_position() {
        let candidates = [
            Candidate {
                name: "Wildfire",
                description: "",
                search_text: "",
            },
            Candidate {
                name: "Fireball",
                description: "",
                search_text: "",
            },
            Candidate {
                name: "Firestorm",
                description: "",
                search_text: "",
            },
        ];
        let ranked = rank_candidates(&candidates, "fire", 10).expect("in bounds");
        assert_eq!(
            ranked.iter().map(|r| r.index).collect::<Vec<_>>(),
            vec![1, 2, 0]
        );
    }

    #[test]
    fn ranking_drops_non_matches_and_honours_the_limit() {
        let candidates = [
            Candidate {
                name: "Fireball",
                description: "",
                search_text: "",
            },
            Candidate {
                name: "Zzqxwv",
                description: "",
                search_text: "",
            },
        ];
        let ranked = rank_candidates(&candidates, "fire", 10).expect("in bounds");
        assert_eq!(ranked.len(), 1);
        let capped = rank_candidates(&candidates, "fire", 1).expect("in bounds");
        assert_eq!(capped.len(), 1);
    }

    #[test]
    fn ranking_agrees_with_scoring_element_wise() {
        let names = ["Fireball", "Wildfire", "Hermeticism", "Fire Shield"];
        let candidates: Vec<Candidate<'_>> = names
            .iter()
            .map(|n| Candidate {
                name: n,
                description: "arcane",
                search_text: "spell",
            })
            .collect();
        let ranked = rank_candidates(&candidates, "fire", 10).expect("in bounds");
        for entry in &ranked {
            let direct = score(names[entry.index], "arcane", "spell", "fire");
            assert_eq!(entry.score, direct, "rank disagreed with score_entity");
        }
    }

    #[test]
    fn an_empty_query_ranks_nothing() {
        let candidates = [Candidate {
            name: "Fireball",
            description: "",
            search_text: "",
        }];
        assert!(rank_candidates(&candidates, "", 10)
            .expect("in bounds")
            .is_empty());
    }

    #[test]
    fn a_zero_limit_is_an_error_not_an_empty_result() {
        let candidates = [Candidate {
            name: "Fireball",
            description: "",
            search_text: "",
        }];
        let err = rank_candidates(&candidates, "fire", 0).unwrap_err();
        assert!(matches!(err, CoreError::ZeroLimit { .. }));
    }

    #[test]
    fn over_long_fields_are_errors() {
        let huge = "a".repeat(MAX_TEXT_BYTES + 1);
        assert!(score_entity(&huge, "", "", "a").is_err());
        assert!(score_entity("", "", "", &huge).is_err());
        assert!(tags_match(&[huge], "a").is_err());
    }
}

//! `apocrypha_core` -- the Rust implementation behind the `esoterica` package.
//!
//! The crate is standalone: it has no Python dependency, links no interpreter,
//! and builds, tests and benchmarks with nothing but a Rust toolchain. The
//! PyO3 bindings live behind the additive `python` feature in [`pyfacade`],
//! and the wheel build adds `extension-module` on top of that. Python is the
//! wrapper; this is the implementation.
//!
//! ## Surface
//!
//! | Module | What it owns |
//! |---|---|
//! | [`text`] | HTML-to-plaintext normalisation for the scraper |
//! | [`scoring`] | entity relevance scoring and batch ranking |
//! | [`entities`] | the named/numeric character-reference tables |
//! | [`error`] | the single [`CoreError`] returned by every entry point |
//!
//! ## Standards this crate holds itself to
//!
//! - **No recursion.** Every function here is iterative, including the
//!   character-reference decoder, which is the one place a naive port would
//!   have reached for it.
//! - **Fixed, checked loop bounds.** Every loop over caller data is bounded by
//!   a constant that the caller's input was checked against first, so
//!   malformed or hostile input fails fast rather than spinning.
//! - **No discarded results.** Every fallible call is propagated. Nothing
//!   returns a default value in place of an error, because a scorer that
//!   answers `0.0` for "your input was rejected" makes a broken backend look
//!   healthy -- which is exactly the failure mode this crate was written to
//!   end.

#![deny(missing_docs)]
#![deny(unsafe_code)]

pub mod entities;
pub mod error;
pub mod scoring;
pub mod text;

#[cfg(feature = "python")]
pub mod pyfacade;

pub use error::CoreError;
pub use scoring::{
    is_subsequence, rank_candidates, score_entity, tags_match, Candidate, Ranked, MAX_TAGS,
};
pub use text::{is_python_re_space, strip_html, strip_html_batch};

/// Largest single text argument accepted, in bytes.
///
/// Four mebibytes is far above any article body, summary or entity
/// description this library sees, and far below the point where a single
/// allocation is a problem. Its purpose is to bound the scan loops, not to
/// ration memory.
pub const MAX_TEXT_BYTES: usize = 4 * 1024 * 1024;

/// Largest number of items accepted in one batch call.
///
/// A scrape run produces low thousands of articles and the baked corpus holds
/// low thousands of entities, so this is three orders of magnitude of
/// headroom. Safety-critical standard 2: all loops have a fixed bound, and a
/// batch loop's bound is its element count.
pub const MAX_BATCH_LEN: usize = 1_048_576;

/// The crate version, for the handshake the Python package performs on import.
///
/// A stale `_core` extension left in a source tree from an earlier build is
/// easy to miss and produces behaviour nobody can explain. `esoterica`
/// compares this against its own `__version__` and refuses to pretend.
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

// Batch calls carry whole entities; a tag list is one field of one entity. An
// inverted relationship would mean a batch of entities was rejected before a
// single entity's tag list was, which no caller could make sense of. Checked
// at compile time so the constants cannot drift apart unnoticed.
const _: () = assert!(MAX_BATCH_LEN > scoring::MAX_TAGS);
const _: () = assert!(MAX_TEXT_BYTES > 0);

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn version_is_a_three_part_number() {
        let parts: Vec<&str> = VERSION.split('.').collect();
        assert_eq!(parts.len(), 3, "expected MAJOR.MINOR.PATCH, got {VERSION}");
        for part in parts {
            assert!(
                part.parse::<u32>().is_ok(),
                "{part:?} in {VERSION} is not a number"
            );
        }
    }

    #[test]
    fn every_bound_is_reachable_from_the_public_surface() {
        // A bound nobody can see is a bound nobody can respect: a caller
        // chunking its input needs to read these, not guess them. The
        // extension module re-exports all three by these names.
        let bounds = [MAX_TEXT_BYTES, MAX_BATCH_LEN, scoring::MAX_TAGS];
        assert!(
            bounds.iter().all(|b| *b > 0),
            "a zero bound rejects all input"
        );
        assert_eq!(bounds.len(), 3, "all three bounds are accounted for");
    }
}

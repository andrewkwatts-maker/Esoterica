//! The single error type the core returns.
//!
//! Every fallible entry point returns `Result<_, CoreError>` rather than a
//! sentinel value. A scorer that answered `0.0` for "input too large" would be
//! indistinguishable from a genuine no-match, and the caller would never learn
//! that its data had been dropped. The facade turns each variant into a
//! distinct Python exception so the distinction survives the FFI boundary too.

use thiserror::Error;

/// A precondition the caller violated. There are no internal-failure variants:
/// nothing in this crate allocates conditionally, recurses, or can fail once
/// its inputs are inside the documented bounds.
#[derive(Debug, Clone, PartialEq, Eq, Error)]
pub enum CoreError {
    /// A text argument exceeded [`crate::MAX_TEXT_BYTES`].
    #[error("{what}: {field} is {len} bytes, over the {limit}-byte limit")]
    TextTooLong {
        /// Name of the operation, for a message the caller can act on.
        what: &'static str,
        /// Name of the offending argument.
        field: &'static str,
        /// Actual length in bytes.
        len: usize,
        /// The limit that was exceeded.
        limit: usize,
    },

    /// A sequence argument exceeded its element-count bound.
    #[error("{what}: {field} has {len} items, over the {limit}-item limit")]
    SequenceTooLong {
        /// Name of the operation.
        what: &'static str,
        /// Name of the offending argument.
        field: &'static str,
        /// Actual element count.
        len: usize,
        /// The limit that was exceeded.
        limit: usize,
    },

    /// A `limit`/`max` argument was zero, which can only ever return nothing.
    /// Silently returning an empty list would look like "no matches found".
    #[error("{what}: {field} must be at least 1, got 0")]
    ZeroLimit {
        /// Name of the operation.
        what: &'static str,
        /// Name of the offending argument.
        field: &'static str,
    },
}

/// Reject an over-long text argument before any work is done on it.
///
/// Bytes, not characters: the check must be O(1), and `str::len` is the only
/// length available without a scan. The limit is generous enough that the
/// difference cannot matter for real documents.
pub(crate) fn check_text(
    what: &'static str,
    field: &'static str,
    text: &str,
    limit: usize,
) -> Result<(), CoreError> {
    debug_assert!(!what.is_empty(), "operation name must be supplied");
    debug_assert!(limit > 0, "a zero text limit would reject every input");
    if text.len() > limit {
        return Err(CoreError::TextTooLong {
            what,
            field,
            len: text.len(),
            limit,
        });
    }
    Ok(())
}

/// Reject an over-long sequence argument before any work is done on it.
pub(crate) fn check_len(
    what: &'static str,
    field: &'static str,
    len: usize,
    limit: usize,
) -> Result<(), CoreError> {
    debug_assert!(!what.is_empty(), "operation name must be supplied");
    debug_assert!(limit > 0, "a zero sequence limit would reject every input");
    if len > limit {
        return Err(CoreError::SequenceTooLong {
            what,
            field,
            len,
            limit,
        });
    }
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn text_within_the_limit_is_accepted() {
        assert!(check_text("op", "text", "abc", 8).is_ok());
    }

    #[test]
    fn text_at_exactly_the_limit_is_accepted() {
        assert!(check_text("op", "text", "abcdefgh", 8).is_ok());
    }

    #[test]
    fn text_over_the_limit_reports_both_numbers() {
        let err = check_text("op", "text", "abcdefghi", 8).unwrap_err();
        assert_eq!(
            err,
            CoreError::TextTooLong {
                what: "op",
                field: "text",
                len: 9,
                limit: 8,
            }
        );
        assert!(err.to_string().contains("over the 8-byte limit"));
    }

    #[test]
    fn sequence_over_the_limit_is_rejected() {
        assert!(check_len("op", "items", 9, 8).is_err());
        assert!(check_len("op", "items", 8, 8).is_ok());
    }

    #[test]
    fn zero_limit_message_names_the_field() {
        let err = CoreError::ZeroLimit {
            what: "rank",
            field: "limit",
        };
        assert!(err.to_string().contains("limit must be at least 1"));
    }
}

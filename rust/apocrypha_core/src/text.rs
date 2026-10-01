//! HTML-to-plaintext normalisation: the hot path of the scraper.
//!
//! This is a faithful port of `esoterica._scraper._strip_html`, which ran
//!
//! ```python
//! text = re.sub(r"<[^>]+>", " ", text)
//! text = html.unescape(text)
//! text = re.sub(r"\s+", " ", text).strip()
//! ```
//!
//! two or three times per scraped item, over thousands of items per run. The
//! three passes here allocate once each and never backtrack, where the regex
//! version built an intermediate string per `re.sub` and paid the interpreter
//! loop for every replacement.
//!
//! ## Order is part of the contract
//!
//! Tags are stripped *before* references are decoded, exactly as above. That
//! ordering means `&lt;b&gt;` survives as the literal text `<b>` rather than
//! being decoded into a tag and then removed. Reversing the two passes is the
//! obvious "optimisation" and it silently changes the output, so both orders
//! are covered by tests.
//!
//! ## Whitespace matches CPython's `\s`, not Rust's
//!
//! CPython's `\s` on a `str` pattern is `Py_UNICODE_ISSPACE`, which is the
//! Unicode `White_Space` property *plus* the four C0 information separators
//! U+001C..U+001F. `char::is_whitespace` is `White_Space` alone. The gap is
//! reachable -- `&#28;` appears in mojibake feed content -- so
//! [`is_python_re_space`] adds them back.

use crate::entities::{lookup_named, resolve_numeric, MAX_ENTITY_NAME_LEN};
use crate::error::{check_len, check_text, CoreError};
use crate::{MAX_BATCH_LEN, MAX_TEXT_BYTES};

/// Largest digit run accepted in a numeric reference, after leading zeros are
/// skipped. Ten decimal digits cover every codepoint; a longer run is
/// necessarily above U+10FFFF, which CPython maps to U+FFFD anyway, so the
/// bound changes no result while keeping the parse in `u32`.
const MAX_NUMERIC_DIGITS: usize = 10;

/// Characters CPython's `html._charref` excludes from a named reference.
/// `\r` and `>` are deliberately absent: the pattern permits them.
const NAME_TERMINATORS: [char; 7] = ['\t', '\n', '\u{c}', ' ', '<', '&', '#'];

/// True for exactly the characters CPython's `\s` matches in a `str` pattern.
pub fn is_python_re_space(ch: char) -> bool {
    // Both assertions cross-check the classification itself: they fire if the
    // base predicate is ever swapped for a hand-rolled table with a typo in
    // it, which is the realistic way this function goes wrong.
    debug_assert!(
        !matches!(ch, '\u{1c}'..='\u{1f}') || !char::is_whitespace(ch),
        "the C0 separators are additions to White_Space, not duplicates of it"
    );
    debug_assert!(
        !ch.is_ascii_alphanumeric() || !char::is_whitespace(ch),
        "an alphanumeric character must never classify as whitespace"
    );
    ch.is_whitespace() || matches!(ch, '\u{1c}'..='\u{1f}')
}

/// Replace every `<...>` span with a single space, appending to `out`.
///
/// Mirrors `re.sub(r"<[^>]+>", " ", text)`, including its edge cases: a bare
/// `<>` is not a tag because `[^>]+` needs at least one character, and an
/// unterminated `<` at the end of the input is literal text.
fn strip_tags(input: &str, out: &mut String) {
    debug_assert!(out.is_empty(), "strip_tags writes into a fresh buffer");
    debug_assert!(
        input.len() <= MAX_TEXT_BYTES,
        "caller must bound the input before stripping"
    );
    let end = input.len();
    let mut cursor = 0_usize;
    // Every iteration advances `cursor` by at least one byte, so `end + 1`
    // iterations is a hard ceiling rather than an estimate.
    for _ in 0..=end {
        if cursor >= end {
            break;
        }
        let rest = &input[cursor..];
        let Some(open) = rest.find('<').map(|rel| cursor + rel) else {
            out.push_str(rest);
            cursor = end;
            break;
        };
        // `<` is ASCII, so `open + 1` is always a character boundary.
        let Some(close_rel) = input[open + 1..].find('>') else {
            out.push_str(rest);
            cursor = end;
            break;
        };
        if close_rel == 0 {
            // A literal `<>`: not a tag, so it survives verbatim.
            out.push_str(&input[cursor..open + 2]);
            cursor = open + 2;
        } else {
            out.push_str(&input[cursor..open]);
            out.push(' ');
            cursor = open + 1 + close_rel + 1;
        }
    }
    debug_assert!(cursor >= end, "the scan must consume the whole input");
}

/// Parse the body of a numeric reference, returning its value and the number
/// of bytes consumed (including any terminating `;`).
fn parse_numeric(body: &str) -> Option<(u32, usize)> {
    debug_assert!(
        body.starts_with('#'),
        "parse_numeric is only called on a `#` reference"
    );
    let hex = matches!(body.as_bytes().get(1), Some(b'x') | Some(b'X'));
    let radix = if hex { 16 } else { 10 };
    let digits_at = if hex { 2 } else { 1 };
    let digits = &body[digits_at..];
    let zeros = digits.len() - digits.trim_start_matches('0').len();
    let significant: String = digits[zeros..]
        .chars()
        .take_while(|c| c.is_digit(radix))
        .collect();
    let run = zeros + significant.len();
    if run == 0 {
        return None;
    }
    let semicolon = usize::from(body[digits_at + run..].starts_with(';'));
    // Radix, not `parse`: `&#x27;` is an apostrophe, and reading it as
    // decimal 27 would yield an escape character instead.
    //
    // An all-zero run is the value zero. A run longer than the bound cannot
    // fit a codepoint, and CPython maps every such value to U+FFFD, so
    // saturating to `u32::MAX` reaches the same answer without a bignum.
    let value = if significant.is_empty() {
        0
    } else if significant.len() > MAX_NUMERIC_DIGITS {
        u32::MAX
    } else {
        u32::from_str_radix(&significant, radix).unwrap_or(u32::MAX)
    };
    debug_assert!(run > 0, "an empty digit run was rejected above");
    debug_assert!(
        digits_at + run + semicolon <= body.len(),
        "the reference cannot consume more than its own body"
    );
    Some((value, digits_at + run + semicolon))
}

/// Parse the body of a named reference. Requires the terminating `;` -- see
/// the module docs on `entities` for why the legacy form is not accepted.
fn parse_named(body: &str) -> Option<(char, usize)> {
    debug_assert!(
        !body.starts_with('#'),
        "numeric references take the other branch"
    );
    let mut name_len = 0_usize;
    for ch in body.chars().take(MAX_ENTITY_NAME_LEN) {
        if NAME_TERMINATORS.contains(&ch) || ch == ';' {
            break;
        }
        name_len += ch.len_utf8();
    }
    if name_len == 0 || !body[name_len..].starts_with(';') {
        return None;
    }
    debug_assert!(name_len <= body.len(), "name length stays inside the body");
    lookup_named(&body[..name_len]).map(|ch| (ch, name_len + 1))
}

/// Decode one reference. The outer `Option` distinguishes "not a reference"
/// (leave the `&` alone) from a valid one; the inner `Option` distinguishes a
/// character to emit from a valid reference that HTML5 maps to nothing.
fn decode_reference(body: &str) -> Option<(Option<char>, usize)> {
    debug_assert!(
        !body.starts_with('&'),
        "the leading ampersand is stripped by the caller"
    );
    if body.starts_with('#') {
        let (value, consumed) = parse_numeric(body)?;
        debug_assert!(consumed > 1, "a numeric reference is at least `#d`");
        return Some((resolve_numeric(value), consumed));
    }
    let (ch, consumed) = parse_named(body)?;
    debug_assert!(consumed >= 2, "a named reference is at least `a;`");
    Some((Some(ch), consumed))
}

/// Decode HTML character references, appending to `out`.
fn unescape(input: &str, out: &mut String) {
    debug_assert!(out.is_empty(), "unescape writes into a fresh buffer");
    debug_assert!(
        input.len() <= MAX_TEXT_BYTES,
        "caller must bound the input before unescaping"
    );
    let end = input.len();
    let mut cursor = 0_usize;
    for _ in 0..=end {
        if cursor >= end {
            break;
        }
        let rest = &input[cursor..];
        let Some(amp) = rest.find('&').map(|rel| cursor + rel) else {
            out.push_str(rest);
            cursor = end;
            break;
        };
        out.push_str(&input[cursor..amp]);
        match decode_reference(&input[amp + 1..]) {
            Some((decoded, consumed)) => {
                if let Some(ch) = decoded {
                    out.push(ch);
                }
                cursor = amp + 1 + consumed;
            }
            None => {
                out.push('&');
                cursor = amp + 1;
            }
        }
    }
    debug_assert!(cursor >= end, "the scan must consume the whole input");
}

/// Collapse runs of whitespace to one space and trim the ends, appending to
/// `out`. Equivalent to `re.sub(r"\s+", " ", text).strip()` in one pass.
fn collapse_whitespace(input: &str, out: &mut String) {
    debug_assert!(
        out.is_empty(),
        "collapse_whitespace writes into a fresh buffer"
    );
    debug_assert!(
        input.len() <= MAX_TEXT_BYTES,
        "caller must bound the input before collapsing"
    );
    let mut pending = false;
    let mut wrote_any = false;
    // A `str` never yields more characters than it has bytes, so the standing
    // byte bound also bounds this loop.
    for ch in input.chars().take(MAX_TEXT_BYTES) {
        if is_python_re_space(ch) {
            pending = true;
            continue;
        }
        // A pending run before the first real character is leading
        // whitespace, which `strip()` removes rather than collapsing.
        if pending && wrote_any {
            out.push(' ');
        }
        pending = false;
        wrote_any = true;
        out.push(ch);
    }
}

/// Strip tags, decode references, and normalise whitespace.
///
/// Returns [`CoreError::TextTooLong`] rather than truncating: a caller that
/// handed over more than [`MAX_TEXT_BYTES`] has a bug, and quietly returning
/// a prefix would corrupt its data without saying so.
pub fn strip_html(input: &str) -> Result<String, CoreError> {
    check_text("strip_html", "text", input, MAX_TEXT_BYTES)?;
    if input.is_empty() {
        return Ok(String::new());
    }
    debug_assert!(!input.is_empty(), "the empty case returned above");
    debug_assert!(
        input.len() <= MAX_TEXT_BYTES,
        "the length check above admitted an over-long input"
    );
    let mut stripped = String::with_capacity(input.len());
    strip_tags(input, &mut stripped);
    let mut decoded = String::with_capacity(stripped.len());
    unescape(&stripped, &mut decoded);
    let mut collapsed = String::with_capacity(decoded.len());
    collapse_whitespace(&decoded, &mut collapsed);
    Ok(collapsed)
}

/// Apply [`strip_html`] across a batch, so a scrape of several thousand items
/// crosses the Python boundary once instead of once per field.
pub fn strip_html_batch<S: AsRef<str>>(inputs: &[S]) -> Result<Vec<String>, CoreError> {
    check_len("strip_html_batch", "texts", inputs.len(), MAX_BATCH_LEN)?;
    debug_assert!(
        inputs.len() <= MAX_BATCH_LEN,
        "the length check above admitted an over-long batch"
    );
    let mut out = Vec::with_capacity(inputs.len());
    for item in inputs.iter().take(MAX_BATCH_LEN) {
        // `?` rather than a default: one over-long field must fail the batch,
        // not silently become an empty string among thousands of good ones.
        out.push(strip_html(item.as_ref())?);
    }
    debug_assert_eq!(out.len(), inputs.len(), "every input produced an output");
    Ok(out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn strip(input: &str) -> String {
        strip_html(input).expect("test inputs are inside the bounds")
    }

    #[test]
    fn empty_input_yields_empty_output() {
        assert_eq!(strip(""), "");
        assert_eq!(strip("   \t\n  "), "");
    }

    #[test]
    fn tags_become_single_spaces() {
        assert_eq!(strip("<p>hello</p>"), "hello");
        assert_eq!(strip("a<br/>b"), "a b");
        assert_eq!(strip("<a href=\"x\">link</a> text"), "link text");
    }

    #[test]
    fn a_tag_may_span_newlines() {
        // `[^>]` matches newlines in Python, so a wrapped attribute list is
        // still one tag.
        assert_eq!(strip("a<div\n  class='x'\n>b"), "a b");
    }

    #[test]
    fn an_empty_angle_pair_is_not_a_tag() {
        assert_eq!(strip("a<>b"), "a<>b");
        assert_eq!(strip("<><b>c"), "<> c");
    }

    #[test]
    fn an_unterminated_tag_is_literal() {
        assert_eq!(strip("a<b"), "a<b");
        assert_eq!(strip("text <"), "text <");
    }

    #[test]
    fn references_decode_after_tags_are_removed() {
        assert_eq!(strip("&lt;b&gt;"), "<b>");
        assert_eq!(strip("A&amp;B"), "A&B");
        assert_eq!(strip("caf&eacute;"), "caf\u{e9}");
        assert_eq!(strip("it&#39;s"), "it's");
        assert_eq!(strip("it&#x27;s"), "it's");
    }

    #[test]
    fn nbsp_decodes_and_then_collapses() {
        // U+00A0 is whitespace to CPython's `\s`, so `strip()` removes it.
        assert_eq!(strip("a&nbsp;&nbsp;b"), "a b");
        assert_eq!(strip("&nbsp;edge&nbsp;"), "edge");
    }

    #[test]
    fn unknown_references_survive_verbatim() {
        assert_eq!(
            strip("&alpha; &notareference; &"),
            "&alpha; &notareference; &"
        );
        assert_eq!(strip("&amp"), "&amp");
        assert_eq!(strip("5 &lt 6"), "5 &lt 6");
    }

    #[test]
    fn numeric_references_follow_cpython_rules() {
        assert_eq!(strip("&#146;"), "\u{2019}");
        assert_eq!(strip("x&#0;y"), "x\u{fffd}y");
        assert_eq!(strip("x&#1;y"), "xy");
        assert_eq!(strip("&#00000000039;"), "'");
        assert_eq!(strip("&#99999999999999;"), "\u{fffd}");
        assert_eq!(strip("&#;"), "&#;");
        assert_eq!(strip("&#x;"), "&#x;");
    }

    #[test]
    fn information_separators_count_as_whitespace() {
        // Rust's char::is_whitespace says no; CPython's `\s` says yes, so a
        // literal separator collapses into the surrounding run.
        assert_eq!(strip("a\u{1f}b"), "a b");
        assert_eq!(strip("a\u{1c}\u{1d}\u{1e}b"), "a b");
        // Reaching one *through a reference* is a different path: HTML5
        // declares U+001C invalid and CPython drops it before `\s` is ever
        // consulted, so no space appears. Verified against html.unescape.
        assert_eq!(strip("a&#28;b"), "ab");
    }

    #[test]
    fn whitespace_runs_collapse_and_edges_trim() {
        assert_eq!(strip("  a \t\n\r b  "), "a b");
        assert_eq!(strip("a\u{2003}\u{2003}b"), "a b");
    }

    #[test]
    fn over_long_input_is_an_error_not_a_truncation() {
        let huge = "a".repeat(MAX_TEXT_BYTES + 1);
        let err = strip_html(&huge).unwrap_err();
        assert!(matches!(err, CoreError::TextTooLong { .. }));
    }

    #[test]
    fn batch_matches_element_wise_application() {
        let inputs = ["<p>one</p>", "t&amp;w", "", "  three  "];
        let batch = strip_html_batch(&inputs).expect("inputs are in bounds");
        let each: Vec<String> = inputs.iter().map(|s| strip(s)).collect();
        assert_eq!(batch, each);
        assert_eq!(batch, vec!["one", "t&w", "", "three"]);
    }

    #[test]
    fn a_bad_element_fails_the_whole_batch() {
        let huge = "a".repeat(MAX_TEXT_BYTES + 1);
        let inputs = ["fine".to_string(), huge];
        assert!(strip_html_batch(&inputs).is_err());
    }

    #[test]
    fn multibyte_text_is_not_split() {
        assert_eq!(strip("<b>na\u{ef}ve caf\u{e9}</b>"), "na\u{ef}ve caf\u{e9}");
        assert_eq!(strip("\u{1f600}<i>x</i>"), "\u{1f600} x");
    }
}

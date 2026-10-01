//! Named HTML character references, and the numeric-reference rules.
//!
//! ## Why a table and not a dependency
//!
//! Python's `html.unescape` carries the full HTML5 table of 2,231 references.
//! Reproducing it would be 2,231 lines of generated data to accelerate a
//! function that spends its time in tag stripping, not entity lookup. The
//! table below is the subset that actually occurs in feed and forum text:
//! the five XML references, the Latin-1 punctuation and symbol block, the
//! General Punctuation quotes and dashes, and every accented Latin letter.
//!
//! ## Deliberate exclusions
//!
//! Greek references (`&alpha;` and friends), `&micro;`, and the superscript
//! digits are **not** decoded, and pass through unchanged. This project emits
//! Latin script only; a decoder that turned caller text into Greek script or
//! a micro sign would be the one place the rule could be violated silently.
//! Unknown references are left verbatim, which is also what Python does.
//!
//! ## Known deviation from `html.unescape`
//!
//! A named reference here **must** be terminated by `;`. Python additionally
//! accepts the semicolon-less legacy spellings (`&amp` -> `&`). Real feed and
//! forum markup writes the semicolon; accepting the legacy form would mean
//! reproducing HTML5's exact longest-prefix backtracking for a case that does
//! not arise. Numeric references keep the optional semicolon, because that
//! costs one line.

/// Longest named reference accepted, matching the `{1,32}` bound in CPython's
/// `html._charref` pattern. Also the bound on the scan for the closing `;`,
/// so a stray `&` in a megabyte of text cannot walk the whole buffer.
pub const MAX_ENTITY_NAME_LEN: usize = 32;

/// Named references, **sorted by ASCII byte order** so lookup can bisect.
///
/// The ordering is load-bearing and easy to break by hand, so
/// `table_is_sorted_and_unique` asserts it. Note that `Dagger` sorts before
/// `dagger`: uppercase letters are the lower byte values.
pub const NAMED: &[(&str, char)] = &[
    ("AElig", '\u{c6}'),
    ("Aacute", '\u{c1}'),
    ("Acirc", '\u{c2}'),
    ("Agrave", '\u{c0}'),
    ("Aring", '\u{c5}'),
    ("Atilde", '\u{c3}'),
    ("Auml", '\u{c4}'),
    ("Ccedil", '\u{c7}'),
    ("Dagger", '\u{2021}'),
    ("ETH", '\u{d0}'),
    ("Eacute", '\u{c9}'),
    ("Ecirc", '\u{ca}'),
    ("Egrave", '\u{c8}'),
    ("Euml", '\u{cb}'),
    ("Iacute", '\u{cd}'),
    ("Icirc", '\u{ce}'),
    ("Igrave", '\u{cc}'),
    ("Iuml", '\u{cf}'),
    ("Ntilde", '\u{d1}'),
    ("Oacute", '\u{d3}'),
    ("Ocirc", '\u{d4}'),
    ("Ograve", '\u{d2}'),
    ("Oslash", '\u{d8}'),
    ("Otilde", '\u{d5}'),
    ("Ouml", '\u{d6}'),
    ("THORN", '\u{de}'),
    ("Uacute", '\u{da}'),
    ("Ucirc", '\u{db}'),
    ("Ugrave", '\u{d9}'),
    ("Uuml", '\u{dc}'),
    ("Yacute", '\u{dd}'),
    ("Yuml", '\u{178}'),
    ("aacute", '\u{e1}'),
    ("acirc", '\u{e2}'),
    ("acute", '\u{b4}'),
    ("aelig", '\u{e6}'),
    ("agrave", '\u{e0}'),
    ("amp", '&'),
    ("apos", '\u{27}'),
    ("aring", '\u{e5}'),
    ("atilde", '\u{e3}'),
    ("auml", '\u{e4}'),
    ("bdquo", '\u{201e}'),
    ("brvbar", '\u{a6}'),
    ("bull", '\u{2022}'),
    ("ccedil", '\u{e7}'),
    ("cedil", '\u{b8}'),
    ("cent", '\u{a2}'),
    ("copy", '\u{a9}'),
    ("curren", '\u{a4}'),
    ("dagger", '\u{2020}'),
    ("deg", '\u{b0}'),
    ("divide", '\u{f7}'),
    ("eacute", '\u{e9}'),
    ("ecirc", '\u{ea}'),
    ("egrave", '\u{e8}'),
    ("emsp", '\u{2003}'),
    ("ensp", '\u{2002}'),
    ("eth", '\u{f0}'),
    ("euml", '\u{eb}'),
    ("euro", '\u{20ac}'),
    ("gt", '>'),
    ("hellip", '\u{2026}'),
    ("iacute", '\u{ed}'),
    ("icirc", '\u{ee}'),
    ("iexcl", '\u{a1}'),
    ("igrave", '\u{ec}'),
    ("iquest", '\u{bf}'),
    ("iuml", '\u{ef}'),
    ("laquo", '\u{ab}'),
    ("ldquo", '\u{201c}'),
    ("lsaquo", '\u{2039}'),
    ("lsquo", '\u{2018}'),
    ("lt", '<'),
    ("macr", '\u{af}'),
    ("mdash", '\u{2014}'),
    ("middot", '\u{b7}'),
    ("minus", '\u{2212}'),
    ("nbsp", '\u{a0}'),
    ("ndash", '\u{2013}'),
    ("not", '\u{ac}'),
    ("ntilde", '\u{f1}'),
    ("oacute", '\u{f3}'),
    ("ocirc", '\u{f4}'),
    ("ograve", '\u{f2}'),
    ("ordf", '\u{aa}'),
    ("ordm", '\u{ba}'),
    ("oslash", '\u{f8}'),
    ("otilde", '\u{f5}'),
    ("ouml", '\u{f6}'),
    ("para", '\u{b6}'),
    ("permil", '\u{2030}'),
    ("plusmn", '\u{b1}'),
    ("pound", '\u{a3}'),
    ("quot", '"'),
    ("raquo", '\u{bb}'),
    ("rdquo", '\u{201d}'),
    ("reg", '\u{ae}'),
    ("rsaquo", '\u{203a}'),
    ("rsquo", '\u{2019}'),
    ("sbquo", '\u{201a}'),
    ("sect", '\u{a7}'),
    ("shy", '\u{ad}'),
    ("szlig", '\u{df}'),
    ("thinsp", '\u{2009}'),
    ("thorn", '\u{fe}'),
    ("tilde", '\u{2dc}'),
    ("times", '\u{d7}'),
    ("trade", '\u{2122}'),
    ("uacute", '\u{fa}'),
    ("ucirc", '\u{fb}'),
    ("ugrave", '\u{f9}'),
    ("uml", '\u{a8}'),
    ("uuml", '\u{fc}'),
    ("yacute", '\u{fd}'),
    ("yen", '\u{a5}'),
    ("yuml", '\u{ff}'),
];

/// Marks a windows-1252 position that has no character, where CPython keeps
/// the raw codepoint instead of substituting. Not a real table entry.
const NO_CP1252_CHAR: char = '\u{0}';

/// The windows-1252 substitutions CPython applies in `_invalid_charrefs`
/// before its range checks. Authors who write `&#146;` mean a right single
/// quote and browsers agree, so a faithful port must agree as well.
///
/// Indexed by `codepoint - 0x80`.
const CP1252: [char; 32] = [
    '\u{20ac}',
    NO_CP1252_CHAR,
    '\u{201a}',
    '\u{192}',
    '\u{201e}',
    '\u{2026}',
    '\u{2020}',
    '\u{2021}',
    '\u{2c6}',
    '\u{2030}',
    '\u{160}',
    '\u{2039}',
    '\u{152}',
    NO_CP1252_CHAR,
    '\u{17d}',
    NO_CP1252_CHAR,
    NO_CP1252_CHAR,
    '\u{2018}',
    '\u{2019}',
    '\u{201c}',
    '\u{201d}',
    '\u{2022}',
    '\u{2013}',
    '\u{2014}',
    '\u{2dc}',
    '\u{2122}',
    '\u{161}',
    '\u{203a}',
    '\u{153}',
    NO_CP1252_CHAR,
    '\u{17e}',
    '\u{178}',
];

/// First codepoint the windows-1252 substitution table covers.
const CP1252_BASE: u32 = 0x80;

/// Resolve a named reference, or `None` if it is outside the table above.
pub fn lookup_named(name: &str) -> Option<char> {
    debug_assert!(
        !name.is_empty(),
        "an empty reference name cannot be looked up"
    );
    debug_assert!(
        name.len() <= MAX_ENTITY_NAME_LEN,
        "caller must bound the name length before lookup"
    );
    NAMED
        .binary_search_by(|(key, _)| (*key).cmp(name))
        .ok()
        .map(|index| NAMED[index].1)
}

/// Resolve a numeric reference, following CPython's `_replace_charref` order:
/// the windows-1252 substitutions first, then surrogates and out-of-range
/// values to U+FFFD, then the codepoints HTML5 declares invalid to nothing.
///
/// `None` means "emit nothing", which is distinct from an unparsable
/// reference -- the caller decides that before calling this.
pub fn resolve_numeric(value: u32) -> Option<char> {
    debug_assert!(
        CP1252.len() == 32,
        "the windows-1252 window is exactly 0x80..0xa0"
    );
    if value == 0 {
        return Some('\u{fffd}');
    }
    if value == 0x0d {
        return Some('\r');
    }
    if (CP1252_BASE..CP1252_BASE + 32).contains(&value) {
        let index = (value - CP1252_BASE) as usize;
        debug_assert!(index < CP1252.len(), "index derived from a checked range");
        let replacement = CP1252[index];
        return if replacement == NO_CP1252_CHAR {
            char::from_u32(value)
        } else {
            Some(replacement)
        };
    }
    if (0xd800..=0xdfff).contains(&value) || value > 0x10_FFFF {
        return Some('\u{fffd}');
    }
    if is_invalid_codepoint(value) {
        return None;
    }
    debug_assert!(value <= 0x10_FFFF, "out-of-range values were handled above");
    char::from_u32(value)
}

/// The codepoints CPython's `_invalid_codepoints` drops entirely: the C0
/// controls that are not whitespace, DEL, the Arabic-presentation-forms
/// noncharacter block, and the last two codepoints of every plane.
fn is_invalid_codepoint(value: u32) -> bool {
    debug_assert!(value != 0, "zero is mapped to U+FFFD before this point");
    debug_assert!(value != 0x0d, "carriage return is mapped before this point");
    let control = (0x01..=0x08).contains(&value)
        || value == 0x0b
        || (0x0e..=0x1f).contains(&value)
        || value == 0x7f;
    let noncharacter = (0xfdd0..=0xfdef).contains(&value) || (value & 0xfffe) == 0xfffe;
    control || noncharacter
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn table_is_sorted_and_unique() {
        // The binary search in `lookup_named` is silently wrong on an
        // unsorted table, so this guards every future edit to NAMED.
        for pair in NAMED.windows(2) {
            assert!(
                pair[0].0 < pair[1].0,
                "NAMED is out of order at {:?} / {:?}",
                pair[0].0,
                pair[1].0
            );
        }
    }

    #[test]
    fn every_name_fits_the_scan_bound() {
        for (name, _) in NAMED {
            assert!(!name.is_empty(), "an empty reference name is unreachable");
            assert!(name.len() <= MAX_ENTITY_NAME_LEN, "{name} is too long");
        }
    }

    #[test]
    fn lookup_finds_first_last_and_middle() {
        assert_eq!(lookup_named("AElig"), Some('\u{c6}'));
        assert_eq!(lookup_named("yuml"), Some('\u{ff}'));
        assert_eq!(lookup_named("amp"), Some('&'));
        assert_eq!(lookup_named("nbsp"), Some('\u{a0}'));
    }

    #[test]
    fn lookup_is_case_sensitive_and_rejects_unknowns() {
        assert_eq!(lookup_named("AMP"), None);
        assert_eq!(lookup_named("alpha"), None);
        assert_eq!(lookup_named("notareference"), None);
        assert_eq!(lookup_named("Dagger"), Some('\u{2021}'));
        assert_eq!(lookup_named("dagger"), Some('\u{2020}'));
    }

    #[test]
    fn numeric_matches_cpython_special_cases() {
        assert_eq!(resolve_numeric(0), Some('\u{fffd}'));
        assert_eq!(resolve_numeric(0x0d), Some('\r'));
        assert_eq!(resolve_numeric(146), Some('\u{2019}'));
        assert_eq!(resolve_numeric(128), Some('\u{20ac}'));
        assert_eq!(resolve_numeric(0x81), Some('\u{81}'));
        assert_eq!(resolve_numeric(0xd800), Some('\u{fffd}'));
        assert_eq!(resolve_numeric(0x11_0000), Some('\u{fffd}'));
        assert_eq!(resolve_numeric(0x01), None);
        assert_eq!(resolve_numeric(0x7f), None);
        assert_eq!(resolve_numeric(0xfffe), None);
        assert_eq!(resolve_numeric(0xfdd0), None);
        assert_eq!(resolve_numeric(39), Some('\u{27}'));
        assert_eq!(resolve_numeric(8217), Some('\u{2019}'));
    }
}

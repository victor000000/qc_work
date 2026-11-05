//! Char-safe shared name and text formatters.

pub(crate) fn truncate_name(name: &str, max_len: usize) -> String {
    // Char-safe (was byte-safe): would panic if max_len-3 landed mid-codepoint.
    if name.chars().count() <= max_len {
        name.to_string()
    } else {
        let head: String = name.chars().take(max_len.saturating_sub(3)).collect();
        format!("{head}...")
    }
}

/// First `max_chars` chars of `s` (not bytes), char-safe.
pub(crate) fn head_chars(s: &str, max_chars: usize) -> &str {
    match s.char_indices().nth(max_chars) {
        Some((idx, _)) => &s[..idx],
        None => s,
    }
}

/// Last `max_chars` chars of `s` (not bytes), char-safe.
pub(crate) fn tail_chars(s: &str, max_chars: usize) -> &str {
    let n = s.chars().count();
    if n <= max_chars {
        return s;
    }
    let skip = n - max_chars;
    match s.char_indices().nth(skip) {
        Some((idx, _)) => &s[idx..],
        None => "",
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn truncate_passthrough_when_under_limit() {
        assert_eq!(truncate_name("short", 10), "short");
        assert_eq!(truncate_name("exactly_ten", 11), "exactly_ten");
    }

    #[test]
    fn truncate_adds_ellipsis_when_over_limit() {
        assert_eq!(truncate_name("S001_R1234_long_thing", 12), "S001_R123...");
        assert_eq!(truncate_name("S001_R1234_long_thing", 12).len(), 12);
    }

    #[test]
    fn truncate_handles_multibyte_names_without_panic() {
        // Pre-fix used &name[..max_len - 3] which panics on multi-byte.
        let n = "中".repeat(20); // 20 chars, 60 bytes
        assert_eq!(truncate_name(&n, 10), format!("{}...", "中".repeat(7)));
    }

    #[test]
    fn head_and_tail_chars_are_char_safe() {
        let s = "中abc中def"; // 8 chars (中 = 1 char each)
        assert_eq!(head_chars(s, 3), "中ab");
        assert_eq!(tail_chars(s, 3), "def");
        assert_eq!(head_chars("short", 99), "short");
        assert_eq!(tail_chars("short", 99), "short");
    }
}

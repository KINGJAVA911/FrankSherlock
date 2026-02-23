/// Normalize a path string to forward slashes (canonical DB representation).
///
/// On Unix this is a no-op. On Windows, backslashes become forward slashes.
pub fn normalize_rel_path(raw: &str) -> String {
    raw.replace('\\', "/")
}

/// Parent directory of a normalized rel_path (everything before the last '/'),
/// or `None` if there is no directory component.
pub fn rel_path_parent(rel: &str) -> Option<&str> {
    rel.rfind('/').map(|idx| &rel[..idx])
}

/// Filename component from a normalized rel_path (everything after the last '/').
/// Returns the whole string if there is no '/'.
#[cfg_attr(not(test), allow(dead_code))]
pub fn rel_path_filename(rel: &str) -> &str {
    rel.rsplit('/').next().unwrap_or(rel)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn normalize_forward_slashes_noop() {
        assert_eq!(normalize_rel_path("a/b/c.jpg"), "a/b/c.jpg");
    }

    #[test]
    fn normalize_backslashes() {
        assert_eq!(normalize_rel_path("a\\b\\c.jpg"), "a/b/c.jpg");
    }

    #[test]
    fn normalize_mixed_slashes() {
        assert_eq!(normalize_rel_path("a\\b/c\\d.jpg"), "a/b/c/d.jpg");
    }

    #[test]
    fn parent_nested() {
        assert_eq!(rel_path_parent("photos/2024/img.jpg"), Some("photos/2024"));
    }

    #[test]
    fn parent_flat() {
        assert_eq!(rel_path_parent("img.jpg"), None);
    }

    #[test]
    fn parent_empty() {
        assert_eq!(rel_path_parent(""), None);
    }

    #[test]
    fn filename_nested() {
        assert_eq!(rel_path_filename("photos/2024/img.jpg"), "img.jpg");
    }

    #[test]
    fn filename_flat() {
        assert_eq!(rel_path_filename("img.jpg"), "img.jpg");
    }
}

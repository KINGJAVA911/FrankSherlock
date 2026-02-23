pub mod clipboard;
pub mod gpu;
pub mod paths;
pub mod process;
pub mod python;

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "lowercase")]
// Variants are constructed via cfg-conditional blocks in current_os(); clippy sees only one on each target.
#[allow(dead_code)]
pub enum OsKind {
    Linux,
    MacOS,
    Windows,
}

pub fn current_os() -> OsKind {
    #[cfg(target_os = "linux")]
    {
        OsKind::Linux
    }
    #[cfg(target_os = "macos")]
    {
        OsKind::MacOS
    }
    #[cfg(target_os = "windows")]
    {
        OsKind::Windows
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn current_os_returns_valid_variant() {
        let os = current_os();
        // Just verify it returns one of the valid variants without panicking
        match os {
            OsKind::Linux | OsKind::MacOS | OsKind::Windows => {}
        }
    }

    #[test]
    fn os_kind_is_copy_and_eq() {
        let a = current_os();
        let b = a;
        assert_eq!(a, b);
    }
}

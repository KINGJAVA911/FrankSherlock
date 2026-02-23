use std::io::{BufRead, BufReader};
use std::path::{Path, PathBuf};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};

use crate::models::VenvProvisionStatus;

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct PythonStatus {
    pub available: bool,
    pub version: Option<String>,
    pub venv_exists: bool,
}

/// Returns the path to the Python binary inside a virtual environment.
/// On Unix: `venv/bin/python`
/// On Windows: `venv/Scripts/python.exe`
pub fn python_venv_binary(venv: &Path) -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        venv.join("Scripts").join("python.exe")
    }
    #[cfg(not(target_os = "windows"))]
    {
        venv.join("bin").join("python")
    }
}

/// Returns the path to the pip binary inside a virtual environment.
pub fn pip_venv_binary(venv: &Path) -> PathBuf {
    #[cfg(target_os = "windows")]
    {
        venv.join("Scripts").join("pip.exe")
    }
    #[cfg(not(target_os = "windows"))]
    {
        venv.join("bin").join("pip")
    }
}

/// Check whether a Python venv exists and the interpreter is runnable.
pub fn check_python_available(venv: &Path) -> PythonStatus {
    let venv_exists = venv.exists();
    let python_bin = python_venv_binary(venv);

    if !venv_exists || !python_bin.exists() {
        return PythonStatus {
            available: false,
            version: None,
            venv_exists,
        };
    }

    match Command::new(&python_bin).arg("--version").output() {
        Ok(output) if output.status.success() => {
            let stdout = String::from_utf8_lossy(&output.stdout);
            let version = stdout
                .trim()
                .strip_prefix("Python ")
                .unwrap_or(stdout.trim())
                .to_string();
            PythonStatus {
                available: true,
                version: Some(version),
                venv_exists,
            }
        }
        _ => PythonStatus {
            available: false,
            version: None,
            venv_exists,
        },
    }
}

/// Validate that a given path is a working Python 3 interpreter.
pub fn validate_python3(path: &Path) -> bool {
    let output = Command::new(path).arg("--version").output();
    match output {
        Ok(o) if o.status.success() => {
            let stdout = String::from_utf8_lossy(&o.stdout);
            let stderr = String::from_utf8_lossy(&o.stderr);
            // Python may print version to stdout or stderr
            stdout.trim().starts_with("Python 3.") || stderr.trim().starts_with("Python 3.")
        }
        _ => false,
    }
}

/// Returns well-known fallback paths where Python 3 might be installed.
pub fn platform_python_fallback_paths() -> Vec<PathBuf> {
    let mut paths = Vec::new();

    #[cfg(target_os = "linux")]
    {
        if let Some(home) = dirs::home_dir() {
            paths.push(home.join(".local/share/mise/shims/python3"));
            paths.push(home.join(".local/bin/python3"));
        }
        paths.push(PathBuf::from("/usr/bin/python3"));
    }

    #[cfg(target_os = "macos")]
    {
        if let Some(home) = dirs::home_dir() {
            paths.push(home.join(".local/share/mise/shims/python3"));
        }
        paths.push(PathBuf::from("/opt/homebrew/bin/python3"));
        paths.push(PathBuf::from("/usr/local/bin/python3"));
        paths.push(PathBuf::from("/usr/bin/python3"));
    }

    #[cfg(target_os = "windows")]
    {
        // Try the Python Launcher first
        paths.push(PathBuf::from("py"));
        // Common install locations
        if let Ok(local) = std::env::var("LOCALAPPDATA") {
            let local_path = PathBuf::from(&local).join("Programs").join("Python");
            if let Ok(entries) = std::fs::read_dir(&local_path) {
                let mut python_dirs: Vec<PathBuf> = entries
                    .filter_map(|e| e.ok())
                    .filter(|e| e.file_name().to_string_lossy().starts_with("Python3"))
                    .map(|e| e.path().join("python.exe"))
                    .collect();
                python_dirs.sort();
                python_dirs.reverse(); // newest first
                paths.extend(python_dirs);
            }
        }
    }

    paths
}

/// Find a working Python 3 interpreter on the system.
/// Checks PATH first via `which`, then well-known fallback locations.
pub fn find_system_python() -> Option<PathBuf> {
    // Try python3 on PATH first, then python
    for name in &["python3", "python"] {
        if let Ok(path) = which::which(name) {
            if validate_python3(&path) {
                return Some(path);
            }
        }
    }

    // Fallback: probe well-known locations
    platform_python_fallback_paths()
        .into_iter()
        .find(|path| path.exists() && validate_python3(path))
}

// ── Venv provisioning state ──────────────────────────────────────────

#[derive(Clone, Debug)]
pub struct VenvProvisionState {
    pub status: String,
    pub step: String,
    pub progress_pct: f32,
    pub message: String,
}

impl VenvProvisionState {
    pub fn idle() -> Self {
        Self {
            status: "idle".to_string(),
            step: String::new(),
            progress_pct: 0.0,
            message: "No OCR setup in progress".to_string(),
        }
    }

    pub fn as_view(&self) -> VenvProvisionStatus {
        VenvProvisionStatus {
            status: self.status.clone(),
            step: self.step.clone(),
            progress_pct: self.progress_pct,
            message: self.message.clone(),
        }
    }
}

/// Provision a Surya OCR venv: create venv, install surya-ocr, verify import.
pub async fn run_venv_provision(
    state: Arc<Mutex<VenvProvisionState>>,
    system_python: PathBuf,
    venv_dir: PathBuf,
) {
    // Step 1: Create venv
    {
        let mut s = state.lock().expect("venv provision mutex poisoned");
        s.status = "running".to_string();
        s.step = "creating_venv".to_string();
        s.progress_pct = 5.0;
        s.message = "Creating Python virtual environment...".to_string();
    }

    let venv_result = Command::new(&system_python)
        .args(["-m", "venv", "--clear"])
        .arg(&venv_dir)
        .output();

    match venv_result {
        Ok(output) if output.status.success() => {}
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr);
            let mut s = state.lock().expect("venv provision mutex poisoned");
            s.status = "failed".to_string();
            s.message = format!("Failed to create venv: {}", stderr.trim());
            return;
        }
        Err(e) => {
            let mut s = state.lock().expect("venv provision mutex poisoned");
            s.status = "failed".to_string();
            s.message = format!("Failed to run python -m venv: {e}");
            return;
        }
    }

    // Step 2: Install surya-ocr
    {
        let mut s = state.lock().expect("venv provision mutex poisoned");
        s.step = "installing_surya".to_string();
        s.progress_pct = 10.0;
        s.message = "Installing surya-ocr (this may take a few minutes)...".to_string();
    }

    let pip = pip_venv_binary(&venv_dir);
    let child = Command::new(&pip)
        .args(["install", "surya-ocr"])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();

    let Ok(mut child) = child else {
        let mut s = state.lock().expect("venv provision mutex poisoned");
        s.status = "failed".to_string();
        s.message = "Failed to spawn pip install process.".to_string();
        return;
    };

    // Stream output lines for progress feedback.
    // surya-ocr pulls many transitive deps, so pip can produce 200+ lines.
    // We use an asymptotic curve: progress = 10 + 85 * (1 - e^(-lines/120))
    // This approaches 95% smoothly without hard-capping at 90%.
    let stdout = child.stdout.take();
    let stderr = child.stderr.take();
    let mut line_count = 0u32;

    if let Some(out) = stdout {
        let reader = BufReader::new(out);
        for line in reader.lines().map_while(Result::ok) {
            line_count += 1;
            let mut s = state.lock().expect("venv provision mutex poisoned");
            let frac = 1.0 - (-(line_count as f32) / 120.0).exp();
            s.progress_pct = 10.0 + 85.0 * frac;
            s.message = line.trim().to_string();
        }
    }
    if let Some(err) = stderr {
        let reader = BufReader::new(err);
        for line in reader.lines().map_while(Result::ok) {
            line_count += 1;
            let mut s = state.lock().expect("venv provision mutex poisoned");
            let frac = 1.0 - (-(line_count as f32) / 120.0).exp();
            s.progress_pct = 10.0 + 85.0 * frac;
            s.message = line.trim().to_string();
        }
    }

    match child.wait() {
        Ok(status) if status.success() => {
            let mut s = state.lock().expect("venv provision mutex poisoned");
            s.progress_pct = 95.0;
            s.message = "pip install completed, verifying...".to_string();
        }
        Ok(status) => {
            let mut s = state.lock().expect("venv provision mutex poisoned");
            s.status = "failed".to_string();
            s.message = format!("pip install failed with exit code {:?}", status.code());
            return;
        }
        Err(e) => {
            let mut s = state.lock().expect("venv provision mutex poisoned");
            s.status = "failed".to_string();
            s.message = format!("Failed to wait for pip process: {e}");
            return;
        }
    }

    // Step 3: Verify import
    {
        let mut s = state.lock().expect("venv provision mutex poisoned");
        s.step = "verifying".to_string();
        s.progress_pct = 95.0;
        s.message = "Verifying surya-ocr installation...".to_string();
    }

    let venv_python = python_venv_binary(&venv_dir);
    let verify = Command::new(&venv_python)
        .args(["-c", "import surya"])
        .output();

    match verify {
        Ok(output) if output.status.success() => {
            let mut s = state.lock().expect("venv provision mutex poisoned");
            s.status = "completed".to_string();
            s.progress_pct = 100.0;
            s.message = "Surya OCR installed successfully.".to_string();
        }
        Ok(output) => {
            let stderr = String::from_utf8_lossy(&output.stderr);
            let mut s = state.lock().expect("venv provision mutex poisoned");
            s.status = "failed".to_string();
            s.message = format!("Surya installed but import failed: {}", stderr.trim());
        }
        Err(e) => {
            let mut s = state.lock().expect("venv provision mutex poisoned");
            s.status = "failed".to_string();
            s.message = format!("Failed to verify surya import: {e}");
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn python_venv_binary_path() {
        let venv = Path::new("test_venv");
        let bin = python_venv_binary(venv);

        #[cfg(target_os = "windows")]
        assert_eq!(bin, PathBuf::from("test_venv\\Scripts\\python.exe"));
        #[cfg(not(target_os = "windows"))]
        assert_eq!(bin, PathBuf::from("test_venv/bin/python"));
    }

    #[test]
    fn pip_venv_binary_path() {
        let venv = Path::new("test_venv");
        let bin = pip_venv_binary(venv);

        #[cfg(target_os = "windows")]
        assert_eq!(bin, PathBuf::from("test_venv\\Scripts\\pip.exe"));
        #[cfg(not(target_os = "windows"))]
        assert_eq!(bin, PathBuf::from("test_venv/bin/pip"));
    }

    #[test]
    fn check_python_nonexistent_venv() {
        let status = check_python_available(Path::new("/nonexistent/venv/path"));
        assert!(!status.available);
        assert!(status.version.is_none());
        assert!(!status.venv_exists);
    }

    #[test]
    fn validate_python3_nonexistent_returns_false() {
        assert!(!validate_python3(Path::new("/nonexistent/python3")));
    }

    #[test]
    fn platform_python_fallback_paths_not_empty() {
        let paths = platform_python_fallback_paths();
        assert!(!paths.is_empty());
    }

    #[test]
    fn venv_provision_state_idle() {
        let state = VenvProvisionState::idle();
        assert_eq!(state.status, "idle");
        assert_eq!(state.progress_pct, 0.0);
        assert!(state.step.is_empty());
    }

    #[test]
    fn venv_provision_state_as_view() {
        let state = VenvProvisionState {
            status: "running".to_string(),
            step: "installing_surya".to_string(),
            progress_pct: 50.0,
            message: "Installing...".to_string(),
        };
        let view = state.as_view();
        assert_eq!(view.status, "running");
        assert_eq!(view.step, "installing_surya");
        assert_eq!(view.progress_pct, 50.0);
        assert_eq!(view.message, "Installing...");
    }

    #[test]
    fn find_system_python_smoke() {
        // Just verify it doesn't panic. Result depends on the environment.
        let _ = find_system_python();
    }
}

use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};
use std::sync::{Arc, Mutex};

use crate::error::AppResult;
use crate::models::{CleanupResult, SetupDownloadStatus};

#[derive(Clone, Debug)]
pub struct DownloadState {
    pub status: String,
    pub model: Option<String>,
    pub progress_pct: f32,
    pub message: String,
}

impl DownloadState {
    pub fn idle() -> Self {
        Self {
            status: "idle".to_string(),
            model: None,
            progress_pct: 0.0,
            message: "No download in progress".to_string(),
        }
    }

    pub fn as_view(&self) -> SetupDownloadStatus {
        SetupDownloadStatus {
            status: self.status.clone(),
            model: self.model.clone(),
            progress_pct: self.progress_pct,
            message: self.message.clone(),
        }
    }
}

/// List models installed locally via `ollama list`.
pub fn list_installed_models() -> Option<Vec<String>> {
    let output = Command::new("ollama").arg("list").output().ok()?;
    if !output.status.success() {
        return None;
    }
    Some(parse_ollama_table_output(&String::from_utf8_lossy(
        &output.stdout,
    )))
}

/// List models currently loaded in Ollama via `ollama ps`.
/// Returns (ollama_available, loaded_model_names).
pub fn list_loaded_models() -> (bool, Vec<String>) {
    match Command::new("ollama").arg("ps").output() {
        Ok(output) if output.status.success() => {
            let models = parse_ollama_table_output(&String::from_utf8_lossy(&output.stdout));
            (true, models)
        }
        _ => (false, Vec::new()),
    }
}

/// Stop all currently loaded Ollama models.
pub fn cleanup_loaded_models() -> AppResult<CleanupResult> {
    let output = Command::new("ollama").arg("ps").output()?;
    let text = String::from_utf8_lossy(&output.stdout);
    let models = parse_ollama_table_output(&text);

    let mut stopped = 0_u64;
    for model in &models {
        let status = Command::new("ollama").args(["stop", model]).status()?;
        if status.success() {
            stopped += 1;
        }
    }

    Ok(CleanupResult {
        running_models: models.len() as u64,
        stopped_models: stopped,
    })
}

/// Run `ollama pull <model>`, streaming progress to a shared state.
pub async fn run_model_download(setup_state: Arc<Mutex<DownloadState>>, model: String) {
    let child = Command::new("ollama")
        .args(["pull", &model])
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .spawn();

    let Ok(mut child) = child else {
        let mut state = setup_state.lock().expect("setup download mutex poisoned");
        state.status = "failed".to_string();
        state.message = "Could not spawn `ollama pull` process.".to_string();
        return;
    };

    let stdout = child.stdout.take();
    let stderr = child.stderr.take();

    if let Some(out) = stdout {
        let reader = BufReader::new(out);
        for line in reader.lines().map_while(Result::ok) {
            update_download_state_from_line(&setup_state, &model, &line);
        }
    }
    if let Some(err) = stderr {
        let reader = BufReader::new(err);
        for line in reader.lines().map_while(Result::ok) {
            update_download_state_from_line(&setup_state, &model, &line);
        }
    }

    match child.wait() {
        Ok(status) if status.success() => {
            let mut state = setup_state.lock().expect("setup download mutex poisoned");
            state.status = "completed".to_string();
            state.progress_pct = 100.0;
            state.message = format!("Model {model} downloaded.");
        }
        Ok(status) => {
            let mut state = setup_state.lock().expect("setup download mutex poisoned");
            state.status = "failed".to_string();
            state.message = format!("Model download failed with code {:?}", status.code());
        }
        Err(err) => {
            let mut state = setup_state.lock().expect("setup download mutex poisoned");
            state.status = "failed".to_string();
            state.message = format!("Failed to wait for pull process: {err}");
        }
    }
}

fn update_download_state_from_line(
    setup_state: &Arc<Mutex<DownloadState>>,
    model: &str,
    line: &str,
) {
    let mut state = setup_state.lock().expect("setup download mutex poisoned");
    state.model = Some(model.to_string());
    state.status = "running".to_string();
    if let Some(progress) = parse_progress_percent(line) {
        state.progress_pct = progress;
    }
    state.message = line.trim().to_string();
}

fn parse_progress_percent(line: &str) -> Option<f32> {
    let percent_pos = line.find('%')?;
    let prefix = &line[..percent_pos];
    let start = prefix
        .rfind(|c: char| !(c.is_ascii_digit() || c == '.'))
        .map(|idx| idx + 1)
        .unwrap_or(0);
    let number = prefix.get(start..)?.trim();
    number.parse::<f32>().ok().map(|v| v.clamp(0.0, 100.0))
}

/// Parse the first whitespace-delimited column from each non-header line.
/// Works for both `ollama ps` and `ollama list` output.
fn parse_ollama_table_output(text: &str) -> Vec<String> {
    text.lines()
        .skip(1) // skip header row
        .map(|l| l.trim())
        .filter(|l| !l.is_empty())
        .filter_map(|l| l.split_whitespace().next())
        .map(|s| s.to_string())
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parses_ollama_ps_rows() {
        let sample = "NAME ID SIZE PROCESSOR UNTIL\nqwen2.5vl:7b abc 6.0 GB 100% GPU 4 minutes\n";
        let models = parse_ollama_table_output(sample);
        assert_eq!(models, vec!["qwen2.5vl:7b".to_string()]);
    }

    #[test]
    fn parses_ollama_list_rows() {
        let sample = "NAME ID SIZE MODIFIED\nqwen2.5vl:7b abc 5 GB 1 day ago\n";
        let models = parse_ollama_table_output(sample);
        assert_eq!(models, vec!["qwen2.5vl:7b".to_string()]);
    }

    #[test]
    fn cleanup_handles_empty_ps_output() {
        let mock = "NAME\tID\tSIZE\tPROCESSOR\tUNTIL\n";
        let models = parse_ollama_table_output(mock);
        assert!(models.is_empty());
    }

    #[test]
    fn extracts_progress_percent() {
        assert_eq!(parse_progress_percent("pulling ... 34%"), Some(34.0));
        assert_eq!(parse_progress_percent("12.5% complete"), Some(12.5));
        assert_eq!(parse_progress_percent("done"), None);
    }

    #[test]
    fn download_state_idle() {
        let state = DownloadState::idle();
        assert_eq!(state.status, "idle");
        assert!(state.model.is_none());
        assert_eq!(state.progress_pct, 0.0);
    }

    #[test]
    fn download_state_as_view() {
        let state = DownloadState {
            status: "running".to_string(),
            model: Some("test:7b".to_string()),
            progress_pct: 50.0,
            message: "Downloading...".to_string(),
        };
        let view = state.as_view();
        assert_eq!(view.status, "running");
        assert_eq!(view.model, Some("test:7b".to_string()));
        assert_eq!(view.progress_pct, 50.0);
    }
}

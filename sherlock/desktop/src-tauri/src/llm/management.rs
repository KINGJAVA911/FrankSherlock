use std::io::{BufRead, BufReader};
use std::sync::{Arc, Mutex};
use std::time::Duration;

use crate::error::AppResult;
use crate::models::SetupDownloadStatus;

const OLLAMA_BASE: &str = "http://localhost:11434";

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

fn http_agent() -> ureq::Agent {
    ureq::Agent::config_builder()
        .timeout_recv_body(Some(Duration::from_secs(5)))
        .timeout_send_body(Some(Duration::from_secs(5)))
        .build()
        .into()
}

/// List models installed locally via Ollama HTTP API (`/api/tags`).
pub fn list_installed_models() -> Option<Vec<String>> {
    let agent = http_agent();
    let mut resp = agent
        .get(&format!("{OLLAMA_BASE}/api/tags"))
        .call()
        .ok()?;
    let body: String = resp.body_mut().read_to_string().ok()?;
    let parsed: serde_json::Value = serde_json::from_str(&body).ok()?;
    let models = parsed
        .get("models")?
        .as_array()?
        .iter()
        .filter_map(|m| {
            m.get("name")
                .or_else(|| m.get("model"))
                .and_then(|v| v.as_str())
                .map(|s| s.to_string())
        })
        .collect();
    Some(models)
}

/// List models currently loaded in Ollama via HTTP API (`/api/ps`).
/// Returns (ollama_available, loaded_model_names).
pub fn list_loaded_models() -> (bool, Vec<String>) {
    let agent = http_agent();
    let resp = agent.get(&format!("{OLLAMA_BASE}/api/ps")).call();
    match resp {
        Ok(mut resp) => {
            let body: String = match resp.body_mut().read_to_string() {
                Ok(s) => s,
                Err(_) => return (true, Vec::new()),
            };
            let parsed: serde_json::Value = match serde_json::from_str(&body) {
                Ok(v) => v,
                Err(_) => return (true, Vec::new()),
            };
            let models = parsed
                .get("models")
                .and_then(|v| v.as_array())
                .map(|arr| {
                    arr.iter()
                        .filter_map(|m| {
                            m.get("name")
                                .or_else(|| m.get("model"))
                                .and_then(|v| v.as_str())
                                .map(|s| s.to_string())
                        })
                        .collect()
                })
                .unwrap_or_default();
            (true, models)
        }
        Err(_) => (false, Vec::new()),
    }
}

/// Unload all currently loaded Ollama models via HTTP API.
pub fn cleanup_loaded_models() -> AppResult<()> {
    let (_, models) = list_loaded_models();
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_recv_body(Some(Duration::from_secs(30)))
        .timeout_send_body(Some(Duration::from_secs(10)))
        .build()
        .into();

    for model in &models {
        let payload = serde_json::json!({
            "model": model,
            "keep_alive": 0,
        });
        let _ = agent
            .post(&format!("{OLLAMA_BASE}/api/generate"))
            .send_json(&payload);
    }

    Ok(())
}

/// Pull a model via Ollama HTTP API (`/api/pull`), streaming progress.
pub async fn run_model_download(setup_state: Arc<Mutex<DownloadState>>, model: String) {
    let agent: ureq::Agent = ureq::Agent::config_builder()
        .timeout_recv_body(None) // no timeout — downloads can take a long time
        .timeout_send_body(Some(Duration::from_secs(30)))
        .build()
        .into();

    let payload = serde_json::json!({
        "name": &model,
        "stream": true,
    });

    let resp = agent
        .post(&format!("{OLLAMA_BASE}/api/pull"))
        .send_json(&payload);

    let Ok(resp) = resp else {
        let mut state = setup_state.lock().expect("setup download mutex poisoned");
        state.status = "failed".to_string();
        state.message = "Could not connect to Ollama HTTP API for pull.".to_string();
        return;
    };

    let reader = BufReader::new(resp.into_body().into_reader());
    for line in reader.lines().map_while(Result::ok) {
        let line = line.trim().to_string();
        if line.is_empty() {
            continue;
        }

        let mut state = setup_state.lock().expect("setup download mutex poisoned");
        state.model = Some(model.clone());
        state.status = "running".to_string();

        if let Ok(obj) = serde_json::from_str::<serde_json::Value>(&line) {
            if let Some(status_text) = obj.get("status").and_then(|v| v.as_str()) {
                state.message = status_text.to_string();
            }
            // Progress: {"status":"pulling ...","completed":123456,"total":789000}
            let completed = obj.get("completed").and_then(|v| v.as_f64()).unwrap_or(0.0);
            let total = obj.get("total").and_then(|v| v.as_f64()).unwrap_or(0.0);
            if total > 0.0 {
                state.progress_pct = ((completed / total) * 100.0).clamp(0.0, 100.0) as f32;
            }
            // Check for error
            if let Some(err) = obj.get("error").and_then(|v| v.as_str()) {
                state.status = "failed".to_string();
                state.message = err.to_string();
                return;
            }
        } else {
            // Fallback: try parsing percent from raw text
            if let Some(pct) = parse_progress_percent(&line) {
                state.progress_pct = pct;
            }
            state.message = line;
        }
    }

    let mut state = setup_state.lock().expect("setup download mutex poisoned");
    if state.status == "running" {
        state.status = "completed".to_string();
        state.progress_pct = 100.0;
        state.message = format!("Model {model} downloaded.");
    }
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
/// Works for both `ollama ps` and `ollama list` CLI output.
/// Kept for backward compatibility with tests.
#[allow(dead_code)]
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

    #[test]
    fn parses_api_tags_response() {
        let json = r#"{"models":[{"name":"qwen2.5vl:7b","model":"qwen2.5vl:7b","size":5000000000}]}"#;
        let parsed: serde_json::Value = serde_json::from_str(json).unwrap();
        let models: Vec<String> = parsed
            .get("models")
            .unwrap()
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|m| m.get("name").and_then(|v| v.as_str()).map(|s| s.to_string()))
            .collect();
        assert_eq!(models, vec!["qwen2.5vl:7b"]);
    }

    #[test]
    fn parses_api_ps_response() {
        let json = r#"{"models":[{"name":"qwen2.5vl:7b","model":"qwen2.5vl:7b"}]}"#;
        let parsed: serde_json::Value = serde_json::from_str(json).unwrap();
        let models: Vec<String> = parsed
            .get("models")
            .unwrap()
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|m| m.get("name").and_then(|v| v.as_str()).map(|s| s.to_string()))
            .collect();
        assert_eq!(models, vec!["qwen2.5vl:7b"]);
    }

    #[test]
    fn parses_empty_api_ps_response() {
        let json = r#"{"models":[]}"#;
        let parsed: serde_json::Value = serde_json::from_str(json).unwrap();
        let models: Vec<String> = parsed
            .get("models")
            .unwrap()
            .as_array()
            .unwrap()
            .iter()
            .filter_map(|m| m.get("name").and_then(|v| v.as_str()).map(|s| s.to_string()))
            .collect();
        assert!(models.is_empty());
    }
}

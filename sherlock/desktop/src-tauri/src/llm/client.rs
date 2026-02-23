use std::path::Path;
use std::time::Duration;

use serde_json::Value;

pub struct OllamaResponse {
    pub ok: bool,
    pub raw: String,
    #[allow(dead_code)]
    pub total_duration_s: f64,
}

impl OllamaResponse {
    pub fn error(msg: String) -> Self {
        Self {
            ok: false,
            raw: msg,
            total_duration_s: 0.0,
        }
    }
}

pub fn ollama_generate(
    model: &str,
    prompt: &str,
    image_path: Option<&Path>,
    num_predict: u32,
    timeout_secs: u64,
    json_mode: bool,
) -> OllamaResponse {
    let mut payload = serde_json::json!({
        "model": model,
        "prompt": prompt,
        "stream": false,
        "keep_alive": "5m",
        "options": {
            "temperature": 0.1,
            "num_predict": num_predict,
        }
    });

    if json_mode {
        payload["format"] = serde_json::json!("json");
    }

    if let Some(img_path) = image_path {
        match std::fs::read(img_path) {
            Ok(bytes) => {
                use base64::Engine;
                let b64 = base64::engine::general_purpose::STANDARD.encode(&bytes);
                payload["images"] = serde_json::json!([b64]);
            }
            Err(e) => {
                return OllamaResponse::error(format!("image_read_error: {e}"));
            }
        }
    }

    let agent = ureq::AgentBuilder::new()
        .timeout_read(Duration::from_secs(timeout_secs))
        .timeout_write(Duration::from_secs(30))
        .build();

    let result = agent
        .post("http://localhost:11434/api/generate")
        .send_json(&payload);

    match result {
        Ok(resp) => {
            let body: String = match resp.into_string() {
                Ok(s) => s,
                Err(e) => {
                    return OllamaResponse::error(format!("read_error: {e}"));
                }
            };
            let parsed: Value = serde_json::from_str(&body).unwrap_or(Value::Null);
            let raw = parsed
                .get("response")
                .and_then(|v| v.as_str())
                .unwrap_or("")
                .to_string();
            let dur = parsed
                .get("total_duration")
                .and_then(|v| v.as_f64())
                .unwrap_or(0.0)
                / 1_000_000_000.0;
            OllamaResponse {
                ok: true,
                raw,
                total_duration_s: dur,
            }
        }
        Err(e) => OllamaResponse::error(format!("http_error: {e}")),
    }
}

/// Extract the first balanced JSON object from free-form text.
pub fn extract_first_json_object(text: &str) -> Option<Value> {
    if text.is_empty() {
        return None;
    }
    let trimmed = text.trim();
    if trimmed.starts_with('{') && trimmed.ends_with('}') {
        if let Ok(v) = serde_json::from_str::<Value>(trimmed) {
            if v.is_object() {
                return Some(v);
            }
        }
    }
    for (start, _) in text.char_indices().filter(|(_, c)| *c == '{') {
        let mut depth = 0i32;
        for (i, ch) in text[start..].char_indices() {
            match ch {
                '{' => depth += 1,
                '}' => {
                    depth -= 1;
                    if depth == 0 {
                        let candidate = &text[start..start + i + 1];
                        if let Ok(v) = serde_json::from_str::<Value>(candidate) {
                            if v.is_object() {
                                return Some(v);
                            }
                        }
                        break;
                    }
                }
                _ => {}
            }
        }
    }
    None
}

pub fn parse_json_response(raw: &str) -> Option<Value> {
    if raw.is_empty() {
        return None;
    }
    extract_first_json_object(raw)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn extract_first_json_object_valid() {
        let input = r#"{"media_type":"anime","confidence":0.9}"#;
        let result = extract_first_json_object(input).unwrap();
        assert_eq!(result["media_type"], "anime");
    }

    #[test]
    fn extract_first_json_object_garbage_prefix() {
        let input = r#"Here is my answer: {"media_type":"photo","confidence":0.5} done"#;
        let result = extract_first_json_object(input).unwrap();
        assert_eq!(result["media_type"], "photo");
    }

    #[test]
    fn extract_first_json_object_nested_braces() {
        let input = r#"{"a":{"b":1},"c":2}"#;
        let result = extract_first_json_object(input).unwrap();
        assert_eq!(result["c"], 2);
    }

    #[test]
    fn extract_first_json_object_empty() {
        assert!(extract_first_json_object("").is_none());
    }

    #[test]
    fn extract_first_json_object_no_json() {
        assert!(extract_first_json_object("just some text").is_none());
    }
}

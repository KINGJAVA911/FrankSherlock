use std::path::{Path, PathBuf};
use std::process::Command;

use serde::Deserialize;

// ---------------------------------------------------------------------------
// Availability
// ---------------------------------------------------------------------------

/// Check whether ffmpeg and ffprobe are both found on PATH (or bundled).
pub fn is_ffmpeg_available() -> bool {
    ffprobe_path().is_some() && ffmpeg_path().is_some()
}

fn ffprobe_path() -> Option<PathBuf> {
    which::which("ffprobe").ok()
}

fn ffmpeg_path() -> Option<PathBuf> {
    which::which("ffmpeg").ok()
}

// ---------------------------------------------------------------------------
// Video metadata
// ---------------------------------------------------------------------------

#[derive(Debug, Clone, Default)]
pub struct VideoMetadata {
    pub duration_secs: Option<f64>,
    pub width: Option<u32>,
    pub height: Option<u32>,
    pub video_codec: Option<String>,
    pub audio_codec: Option<String>,
    pub bitrate: Option<u64>,
    pub framerate: Option<f64>,
    pub creation_time: Option<String>,
    pub container_format: Option<String>,
    pub subtitle_stream_count: u32,
    pub audio_stream_count: u32,
}

/// Extract video metadata by shelling out to ffprobe.
pub fn extract_metadata(video_path: &Path) -> Option<VideoMetadata> {
    let ffprobe = ffprobe_path()?;
    let output = Command::new(ffprobe)
        .args([
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
        ])
        .arg(video_path)
        .output()
        .ok()?;
    if !output.status.success() {
        log::warn!(
            "ffprobe failed for {}: {}",
            video_path.display(),
            String::from_utf8_lossy(&output.stderr)
        );
        return None;
    }
    let json_str = String::from_utf8_lossy(&output.stdout);
    let probe: FfprobeOutput = serde_json::from_str(&json_str).ok()?;

    let mut meta = VideoMetadata::default();

    // Format-level data
    if let Some(ref fmt) = probe.format {
        meta.duration_secs = fmt.duration.as_deref().and_then(|d| d.parse::<f64>().ok());
        meta.bitrate = fmt.bit_rate.as_deref().and_then(|b| b.parse::<u64>().ok());
        meta.container_format = fmt.format_name.clone();
        meta.creation_time = fmt.tags.as_ref().and_then(|t| t.creation_time.clone());
    }

    // Stream-level data
    if let Some(ref streams) = probe.streams {
        for s in streams {
            let codec_type = s.codec_type.as_deref().unwrap_or("");
            match codec_type {
                "video" => {
                    if meta.video_codec.is_none() {
                        meta.video_codec = s.codec_name.clone();
                        meta.width = s.width;
                        meta.height = s.height;
                        meta.framerate = parse_framerate(s.r_frame_rate.as_deref());
                    }
                }
                "audio" => {
                    meta.audio_stream_count += 1;
                    if meta.audio_codec.is_none() {
                        meta.audio_codec = s.codec_name.clone();
                    }
                }
                "subtitle" => {
                    meta.subtitle_stream_count += 1;
                }
                _ => {}
            }
        }
    }

    Some(meta)
}

fn parse_framerate(r_frame_rate: Option<&str>) -> Option<f64> {
    let s = r_frame_rate?;
    if let Some((num, den)) = s.split_once('/') {
        let n: f64 = num.parse().ok()?;
        let d: f64 = den.parse().ok()?;
        if d > 0.0 {
            return Some(n / d);
        }
    }
    s.parse().ok()
}

// Minimal ffprobe JSON structures
#[derive(Deserialize)]
struct FfprobeOutput {
    format: Option<FfprobeFormat>,
    streams: Option<Vec<FfprobeStream>>,
}

#[derive(Deserialize)]
struct FfprobeFormat {
    duration: Option<String>,
    bit_rate: Option<String>,
    format_name: Option<String>,
    tags: Option<FfprobeTags>,
}

#[derive(Deserialize)]
struct FfprobeTags {
    creation_time: Option<String>,
}

#[derive(Deserialize)]
struct FfprobeStream {
    codec_type: Option<String>,
    codec_name: Option<String>,
    width: Option<u32>,
    height: Option<u32>,
    r_frame_rate: Option<String>,
}

// ---------------------------------------------------------------------------
// Keyframe extraction
// ---------------------------------------------------------------------------

/// Extract representative keyframes from a video.
///
/// Returns paths to JPEG files in `tmp_dir`. The caller is responsible for
/// cleanup. Picks frames that avoid black intro/logo screens.
pub fn extract_keyframes(video_path: &Path, tmp_dir: &Path, max_frames: u32) -> Vec<PathBuf> {
    let ffmpeg = match ffmpeg_path() {
        Some(p) => p,
        None => return Vec::new(),
    };
    let _ = std::fs::create_dir_all(tmp_dir);

    let meta = extract_metadata(video_path);
    let duration = meta.as_ref().and_then(|m| m.duration_secs).unwrap_or(0.0);

    if duration < 0.5 {
        // Very short or unknown — just grab a single frame at 0s
        let out = tmp_dir.join("keyframe_000.jpg");
        let status = Command::new(&ffmpeg)
            .args(["-v", "quiet", "-ss", "0", "-i"])
            .arg(video_path)
            .args(["-frames:v", "1", "-q:v", "2"])
            .arg(&out)
            .arg("-y")
            .status();
        if status.map(|s| s.success()).unwrap_or(false) && out.exists() {
            return vec![out];
        }
        return Vec::new();
    }

    // Determine how many frames to extract based on duration
    let n_segments = if duration < 300.0 {
        3u32.min(max_frames) // <5 min
    } else if duration < 1800.0 {
        5u32.min(max_frames) // <30 min
    } else if duration < 7200.0 {
        8u32.min(max_frames) // <2 hr
    } else {
        10u32.min(max_frames) // >2 hr
    };

    // Skip the first 5% or 10s (whichever is larger) to avoid logos/intros
    let skip = (duration * 0.05).max(10.0).min(duration * 0.4);
    let usable = duration - skip;
    let segment_len = usable / n_segments as f64;

    let mut frames = Vec::new();
    for i in 0..n_segments {
        let timestamp = skip + segment_len * (i as f64 + 0.5);
        if timestamp >= duration {
            break;
        }
        let out = tmp_dir.join(format!("keyframe_{i:03}.jpg"));
        let status = Command::new(&ffmpeg)
            .args(["-v", "quiet", "-ss", &format!("{timestamp:.2}"), "-i"])
            .arg(video_path)
            .args(["-frames:v", "1", "-q:v", "2"])
            .arg(&out)
            .arg("-y")
            .status();
        if status.map(|s| s.success()).unwrap_or(false) && out.exists() {
            // Discard all-black frames (average luminance < 10)
            if !is_black_frame(&out) {
                frames.push(out);
            } else {
                let _ = std::fs::remove_file(&out);
            }
        }
    }

    frames
}

/// Quick luminance check: returns true if the image is nearly all-black.
fn is_black_frame(path: &Path) -> bool {
    let img = match image::open(path) {
        Ok(img) => img,
        Err(_) => return false,
    };
    let gray = img.to_luma8();
    let total_pixels = gray.width() as u64 * gray.height() as u64;
    if total_pixels == 0 {
        return true;
    }
    let sum: u64 = gray.pixels().map(|p| p.0[0] as u64).sum();
    let avg = sum / total_pixels;
    avg < 10
}

// ---------------------------------------------------------------------------
// Subtitle extraction
// ---------------------------------------------------------------------------

/// Extract embedded subtitle streams from a video via ffmpeg.
pub fn extract_embedded_subtitles(video_path: &Path, tmp_dir: &Path) -> String {
    let ffmpeg = match ffmpeg_path() {
        Some(p) => p,
        None => return String::new(),
    };
    let _ = std::fs::create_dir_all(tmp_dir);
    let srt_path = tmp_dir.join("_embedded_subs.srt");

    // Try to extract the first subtitle stream as SRT
    let status = Command::new(&ffmpeg)
        .args(["-v", "quiet", "-i"])
        .arg(video_path)
        .args(["-map", "0:s:0", "-c:s", "srt"])
        .arg(&srt_path)
        .arg("-y")
        .status();

    if status.map(|s| s.success()).unwrap_or(false) && srt_path.exists() {
        let text = parse_srt_to_text(&srt_path);
        let _ = std::fs::remove_file(&srt_path);
        return text;
    }
    String::new()
}

/// Find external subtitle files that match the video's stem.
///
/// Looks for files like `Movie.srt`, `Movie.en.srt`, `Movie.ass`, etc.
/// in the same directory as the video.
pub fn find_external_subtitles(video_path: &Path) -> Vec<PathBuf> {
    let parent = match video_path.parent() {
        Some(p) => p,
        None => return Vec::new(),
    };
    let stem = match video_path.file_stem() {
        Some(s) => s.to_string_lossy().to_string(),
        None => return Vec::new(),
    };
    let sub_exts = ["srt", "ass", "ssa", "sub", "vtt"];

    let mut subs = Vec::new();
    if let Ok(entries) = std::fs::read_dir(parent) {
        for entry in entries.flatten() {
            let path = entry.path();
            if !path.is_file() {
                continue;
            }
            let fname = path
                .file_name()
                .map(|n| n.to_string_lossy().to_string())
                .unwrap_or_default();
            let ext = path
                .extension()
                .map(|e| e.to_string_lossy().to_lowercase())
                .unwrap_or_default();
            if fname.starts_with(&stem) && sub_exts.contains(&ext.as_str()) {
                subs.push(path);
            }
        }
    }
    subs
}

/// Parse an SRT file into plain text, stripping timestamps and formatting tags.
pub fn parse_srt_to_text(srt_path: &Path) -> String {
    let content = match std::fs::read_to_string(srt_path) {
        Ok(c) => c,
        Err(_) => return String::new(),
    };

    let tag_re = regex::Regex::new(r"<[^>]+>").unwrap_or_else(|_| regex::Regex::new(".^").unwrap());

    let mut lines = Vec::new();
    for line in content.lines() {
        let trimmed = line.trim();
        // Skip sequence numbers, timestamps, and empty lines
        if trimmed.is_empty() {
            continue;
        }
        if trimmed.chars().all(|c| c.is_ascii_digit()) {
            continue;
        }
        if trimmed.contains("-->") {
            continue;
        }
        // Strip HTML/SRT tags like <b>, <i>, etc.
        let clean = tag_re.replace_all(trimmed, "");
        let clean = clean.trim();
        if !clean.is_empty() {
            lines.push(clean.to_string());
        }
    }
    lines.join("\n")
}

/// Collect all subtitle text for a video (embedded + external).
pub fn collect_subtitle_text(video_path: &Path, tmp_dir: &Path) -> String {
    let mut parts = Vec::new();

    // Embedded subtitles
    let embedded = extract_embedded_subtitles(video_path, tmp_dir);
    if !embedded.is_empty() {
        parts.push(embedded);
    }

    // External subtitle files
    for sub_path in find_external_subtitles(video_path) {
        let text = parse_srt_to_text(&sub_path);
        if !text.is_empty() {
            parts.push(text);
        }
    }

    parts.join("\n")
}

/// Format a duration in seconds to a human-readable string like "1h 23m" or "5m 30s".
pub fn format_duration(secs: f64) -> String {
    let total = secs.round() as u64;
    let h = total / 3600;
    let m = (total % 3600) / 60;
    let s = total % 60;
    if h > 0 {
        format!("{h}h {m:02}m")
    } else if m > 0 {
        format!("{m}m {s:02}s")
    } else {
        format!("{s}s")
    }
}

// ---------------------------------------------------------------------------
// Video file detection
// ---------------------------------------------------------------------------

const VIDEO_EXTENSIONS: &[&str] = &[
    "mp4", "mkv", "avi", "mov", "wmv", "flv", "webm", "m4v", "ts", "mpg", "mpeg",
];

/// Check if a file path has a known video extension.
pub fn is_video_file(path: &Path) -> bool {
    path.extension()
        .map(|e| e.to_string_lossy().to_lowercase())
        .map(|ext| VIDEO_EXTENSIONS.contains(&ext.as_str()))
        .unwrap_or(false)
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn parse_srt_strips_timestamps_and_tags() {
        let dir = tempfile::tempdir().expect("tempdir");
        let srt = dir.path().join("test.srt");
        std::fs::write(
            &srt,
            "1\n00:00:01,000 --> 00:00:03,000\n<b>Hello</b> world\n\n2\n00:00:04,000 --> 00:00:06,000\nSecond line\n",
        )
        .unwrap();
        let text = parse_srt_to_text(&srt);
        assert!(text.contains("Hello world"));
        assert!(text.contains("Second line"));
        assert!(!text.contains("-->"));
        assert!(!text.contains("<b>"));
    }

    #[test]
    fn parse_srt_empty_file() {
        let dir = tempfile::tempdir().expect("tempdir");
        let srt = dir.path().join("empty.srt");
        std::fs::write(&srt, "").unwrap();
        assert!(parse_srt_to_text(&srt).is_empty());
    }

    #[test]
    fn parse_srt_missing_file() {
        let missing = Path::new("/tmp/nonexistent_srt_12345.srt");
        assert!(parse_srt_to_text(missing).is_empty());
    }

    #[test]
    fn is_video_file_recognizes_extensions() {
        assert!(is_video_file(Path::new("movie.mp4")));
        assert!(is_video_file(Path::new("movie.MKV")));
        assert!(is_video_file(Path::new("clip.webm")));
        assert!(is_video_file(Path::new("show.avi")));
        assert!(is_video_file(Path::new("cam.MOV")));
        assert!(!is_video_file(Path::new("photo.jpg")));
        assert!(!is_video_file(Path::new("doc.pdf")));
        assert!(!is_video_file(Path::new("noext")));
    }

    #[test]
    fn find_external_subtitles_in_dir() {
        let dir = tempfile::tempdir().expect("tempdir");
        let video = dir.path().join("Movie.mp4");
        std::fs::write(&video, b"fake").unwrap();
        std::fs::write(dir.path().join("Movie.srt"), b"sub").unwrap();
        std::fs::write(dir.path().join("Movie.en.srt"), b"sub en").unwrap();
        std::fs::write(dir.path().join("Other.srt"), b"other").unwrap();
        std::fs::write(dir.path().join("Movie.txt"), b"txt").unwrap();

        let subs = find_external_subtitles(&video);
        assert_eq!(subs.len(), 2);
        let names: Vec<String> = subs
            .iter()
            .map(|p| p.file_name().unwrap().to_string_lossy().to_string())
            .collect();
        assert!(names.contains(&"Movie.srt".to_string()));
        assert!(names.contains(&"Movie.en.srt".to_string()));
    }

    #[test]
    fn format_duration_hours() {
        assert_eq!(format_duration(5400.0), "1h 30m");
    }

    #[test]
    fn format_duration_minutes() {
        assert_eq!(format_duration(330.0), "5m 30s");
    }

    #[test]
    fn format_duration_seconds_only() {
        assert_eq!(format_duration(45.0), "45s");
    }

    #[test]
    fn parse_framerate_fraction() {
        assert!((parse_framerate(Some("24000/1001")).unwrap() - 23.976).abs() < 0.01);
    }

    #[test]
    fn parse_framerate_integer() {
        assert!((parse_framerate(Some("30")).unwrap() - 30.0).abs() < 0.01);
    }

    #[test]
    fn parse_framerate_fraction_simple() {
        assert!((parse_framerate(Some("25/1")).unwrap() - 25.0).abs() < 0.01);
    }

    #[test]
    fn parse_framerate_none() {
        assert!(parse_framerate(None).is_none());
    }

    #[test]
    fn is_black_frame_with_test_image() {
        let dir = tempfile::tempdir().expect("tempdir");
        // Create a small black image
        let path = dir.path().join("black.jpg");
        let img = image::RgbImage::from_pixel(100, 100, image::Rgb([0, 0, 0]));
        image::DynamicImage::ImageRgb8(img).save(&path).unwrap();
        assert!(is_black_frame(&path));

        // Create a bright image
        let bright_path = dir.path().join("bright.jpg");
        let img = image::RgbImage::from_pixel(100, 100, image::Rgb([200, 200, 200]));
        image::DynamicImage::ImageRgb8(img)
            .save(&bright_path)
            .unwrap();
        assert!(!is_black_frame(&bright_path));
    }

    // Tests that require ffmpeg on PATH — gated at runtime
    #[test]
    fn extract_metadata_returns_none_without_ffmpeg() {
        if is_ffmpeg_available() {
            // Can't test without a real video file in unit tests
            return;
        }
        let result = extract_metadata(Path::new("/tmp/nonexistent.mp4"));
        assert!(result.is_none());
    }

    #[test]
    fn extract_keyframes_returns_empty_without_ffmpeg() {
        if is_ffmpeg_available() {
            return;
        }
        let dir = tempfile::tempdir().expect("tempdir");
        let frames = extract_keyframes(Path::new("/tmp/nonexistent.mp4"), dir.path(), 5);
        assert!(frames.is_empty());
    }

    #[test]
    fn video_extensions_list_complete() {
        // Verify all planned video extensions are covered
        assert!(VIDEO_EXTENSIONS.contains(&"mp4"));
        assert!(VIDEO_EXTENSIONS.contains(&"mkv"));
        assert!(VIDEO_EXTENSIONS.contains(&"avi"));
        assert!(VIDEO_EXTENSIONS.contains(&"mov"));
        assert!(VIDEO_EXTENSIONS.contains(&"webm"));
        assert!(VIDEO_EXTENSIONS.contains(&"ts"));
    }
}

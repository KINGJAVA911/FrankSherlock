use std::process::Command;

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "lowercase")]
#[allow(dead_code)]
pub enum GpuVendor {
    Nvidia,
    Amd,
    Apple,
    Unknown,
}

#[derive(Debug, Clone, serde::Serialize)]
#[serde(rename_all = "camelCase")]
pub struct GpuInfo {
    pub vendor: GpuVendor,
    pub vram_used_mib: Option<u64>,
    pub vram_total_mib: Option<u64>,
    pub unified_memory: bool,
    pub system_ram_mib: u64,
}

fn detect_system_ram_mib() -> u64 {
    use sysinfo::{MemoryRefreshKind, RefreshKind, System};
    let sys = System::new_with_specifics(
        RefreshKind::nothing().with_memory(MemoryRefreshKind::everything()),
    );
    sys.total_memory() / (1024 * 1024)
}

/// Detect GPU and system memory information.
///
/// - macOS: Apple Silicon unified memory (vendor=Apple, unified=true)
/// - Linux/Windows: tries NVIDIA (nvidia-smi), then AMD (rocm-smi on Linux), else Unknown
pub fn detect_gpu_memory() -> GpuInfo {
    let system_ram_mib = detect_system_ram_mib();

    #[cfg(target_os = "macos")]
    {
        GpuInfo {
            vendor: GpuVendor::Apple,
            vram_used_mib: None,
            vram_total_mib: None,
            unified_memory: true,
            system_ram_mib,
        }
    }

    #[cfg(not(target_os = "macos"))]
    {
        // Try NVIDIA first
        if let Some(info) = detect_nvidia_gpu(system_ram_mib) {
            return info;
        }

        // Try AMD (Linux only)
        #[cfg(target_os = "linux")]
        if let Some(info) = detect_amd_gpu(system_ram_mib) {
            return info;
        }

        // Fallback: unknown GPU
        GpuInfo {
            vendor: GpuVendor::Unknown,
            vram_used_mib: None,
            vram_total_mib: None,
            unified_memory: false,
            system_ram_mib,
        }
    }
}

#[cfg(not(target_os = "macos"))]
fn detect_nvidia_gpu(system_ram_mib: u64) -> Option<GpuInfo> {
    let output = Command::new("nvidia-smi")
        .args([
            "--query-gpu=memory.used,memory.total",
            "--format=csv,noheader,nounits",
        ])
        .output()
        .ok()?;

    if !output.status.success() {
        return None;
    }

    let (used, total) = parse_nvidia_smi_output(&String::from_utf8_lossy(&output.stdout));
    if used.is_none() && total.is_none() {
        return None;
    }

    Some(GpuInfo {
        vendor: GpuVendor::Nvidia,
        vram_used_mib: used,
        vram_total_mib: total,
        unified_memory: false,
        system_ram_mib,
    })
}

#[cfg(not(target_os = "macos"))]
fn parse_nvidia_smi_output(text: &str) -> (Option<u64>, Option<u64>) {
    let Some(first_line) = text.lines().next() else {
        return (None, None);
    };
    let mut parts = first_line.split(',');
    let used = parts.next().and_then(|v| v.trim().parse::<u64>().ok());
    let total = parts.next().and_then(|v| v.trim().parse::<u64>().ok());
    (used, total)
}

#[cfg(target_os = "linux")]
fn detect_amd_gpu(system_ram_mib: u64) -> Option<GpuInfo> {
    let output = Command::new("rocm-smi")
        .args(["--showmeminfo", "vram", "--csv"])
        .output()
        .ok()?;

    if !output.status.success() {
        return None;
    }

    let (used, total) = parse_rocm_smi_output(&String::from_utf8_lossy(&output.stdout));
    if used.is_none() && total.is_none() {
        return None;
    }

    Some(GpuInfo {
        vendor: GpuVendor::Amd,
        vram_used_mib: used,
        vram_total_mib: total,
        unified_memory: false,
        system_ram_mib,
    })
}

/// Parse rocm-smi CSV output for VRAM usage.
///
/// Expected format (bytes):
/// ```text
/// GPU, VRAM Total Used (B), VRAM Total (B)
/// 0, 1073741824, 17179869184
/// ```
#[cfg(target_os = "linux")]
fn parse_rocm_smi_output(text: &str) -> (Option<u64>, Option<u64>) {
    // Skip header line, take first data line
    let Some(data_line) = text.lines().skip(1).find(|l| !l.trim().is_empty()) else {
        return (None, None);
    };
    let parts: Vec<&str> = data_line.split(',').collect();
    if parts.len() < 3 {
        return (None, None);
    }
    // rocm-smi reports bytes; convert to MiB
    let used_bytes = parts[1].trim().parse::<u64>().ok();
    let total_bytes = parts[2].trim().parse::<u64>().ok();
    let used_mib = used_bytes.map(|b| b / (1024 * 1024));
    let total_mib = total_bytes.map(|b| b / (1024 * 1024));
    (used_mib, total_mib)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn parses_nvidia_memory() {
        let sample = "1024, 24564\n";
        let (used, total) = parse_nvidia_smi_output(sample);
        assert_eq!(used, Some(1024));
        assert_eq!(total, Some(24564));
    }

    #[cfg(not(target_os = "macos"))]
    #[test]
    fn parses_nvidia_empty() {
        let (used, total) = parse_nvidia_smi_output("");
        assert!(used.is_none());
        assert!(total.is_none());
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn parses_rocm_smi_output() {
        let sample = "GPU, VRAM Total Used (B), VRAM Total (B)\n0, 1073741824, 17179869184\n";
        let (used, total) = parse_rocm_smi_output(sample);
        assert_eq!(used, Some(1024)); // 1 GiB in MiB
        assert_eq!(total, Some(16384)); // 16 GiB in MiB
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn parses_rocm_smi_empty() {
        let (used, total) = parse_rocm_smi_output("");
        assert!(used.is_none());
        assert!(total.is_none());
    }

    #[cfg(target_os = "linux")]
    #[test]
    fn parses_rocm_smi_header_only() {
        let sample = "GPU, VRAM Total Used (B), VRAM Total (B)\n";
        let (used, total) = parse_rocm_smi_output(sample);
        assert!(used.is_none());
        assert!(total.is_none());
    }

    #[cfg(target_os = "macos")]
    #[test]
    fn macos_returns_apple_unified() {
        let info = detect_gpu_memory();
        assert_eq!(info.vendor, GpuVendor::Apple);
        assert!(info.unified_memory);
        assert!(info.vram_used_mib.is_none());
        assert!(info.vram_total_mib.is_none());
        assert!(info.system_ram_mib > 0);
    }

    #[test]
    fn system_ram_detection_returns_nonzero() {
        let ram = detect_system_ram_mib();
        assert!(ram > 0);
    }

    #[test]
    fn gpu_vendor_serializes() {
        assert_eq!(
            serde_json::to_string(&GpuVendor::Nvidia).unwrap(),
            "\"nvidia\""
        );
        assert_eq!(serde_json::to_string(&GpuVendor::Amd).unwrap(), "\"amd\"");
        assert_eq!(
            serde_json::to_string(&GpuVendor::Apple).unwrap(),
            "\"apple\""
        );
        assert_eq!(
            serde_json::to_string(&GpuVendor::Unknown).unwrap(),
            "\"unknown\""
        );
    }
}

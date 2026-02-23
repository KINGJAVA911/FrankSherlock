use crate::platform::gpu::{GpuInfo, GpuVendor};

pub const MODEL_SMALL: &str = "qwen2.5vl:3b";
pub const MODEL_MEDIUM: &str = "qwen2.5vl:7b";
pub const MODEL_LARGE: &str = "qwen2.5vl:32b";

/// Minimum effective memory (MiB) for the large model tier.
const LARGE_THRESHOLD_MIB: u64 = 48 * 1024; // 48 GiB
/// Minimum effective memory (MiB) for the medium model tier.
const MEDIUM_THRESHOLD_MIB: u64 = 8 * 1024; // 8 GiB

#[derive(Debug, Clone, Copy, PartialEq, Eq, serde::Serialize)]
#[serde(rename_all = "lowercase")]
pub enum ModelTier {
    Small,
    Medium,
    Large,
}

impl ModelTier {
    pub fn as_str(&self) -> &'static str {
        match self {
            ModelTier::Small => "small",
            ModelTier::Medium => "medium",
            ModelTier::Large => "large",
        }
    }

    pub fn model_tag(&self) -> &'static str {
        match self {
            ModelTier::Small => MODEL_SMALL,
            ModelTier::Medium => MODEL_MEDIUM,
            ModelTier::Large => MODEL_LARGE,
        }
    }
}

/// Estimate the effective memory available for model loading (in MiB).
///
/// - Unified memory (Apple Silicon): 75% of system RAM (OS + apps use the rest)
/// - Discrete GPU: VRAM total (model loads entirely into VRAM)
/// - No GPU / unknown: system RAM (Ollama will use CPU mode)
fn effective_memory_mib(gpu: &GpuInfo) -> u64 {
    if gpu.unified_memory {
        // Apple Silicon shares RAM between CPU and GPU; ~75% is realistic for model use
        (gpu.system_ram_mib as f64 * 0.75) as u64
    } else if let Some(vram) = gpu.vram_total_mib {
        vram
    } else {
        // CPU-only fallback: Ollama uses system RAM
        gpu.system_ram_mib
    }
}

fn select_tier(gpu: &GpuInfo) -> ModelTier {
    let mem = effective_memory_mib(gpu);
    // Large tier only for unified memory systems (Apple Silicon, AMD APU)
    // since discrete GPUs pay a heavy speed penalty for 32b
    if mem >= LARGE_THRESHOLD_MIB && gpu.unified_memory {
        ModelTier::Large
    } else if mem >= MEDIUM_THRESHOLD_MIB {
        ModelTier::Medium
    } else {
        ModelTier::Small
    }
}

/// Select the recommended model based on detected hardware.
///
/// Returns (model_tag, tier, human-readable reason).
pub fn recommended_model(gpu: &GpuInfo) -> (&'static str, ModelTier, String) {
    let tier = select_tier(gpu);
    let reason = match (tier, gpu.vendor) {
        (ModelTier::Large, GpuVendor::Apple) => format!(
            "Apple unified memory ({} GiB) supports 32b model",
            gpu.system_ram_mib / 1024
        ),
        (ModelTier::Large, _) => format!(
            "Unified memory ({} GiB) supports 32b model",
            gpu.system_ram_mib / 1024
        ),
        (ModelTier::Medium, GpuVendor::Nvidia) => {
            let vram = gpu.vram_total_mib.unwrap_or(0);
            format!("NVIDIA GPU ({} GiB VRAM) — 7b is optimal", vram / 1024)
        }
        (ModelTier::Medium, GpuVendor::Amd) => {
            let vram = gpu.vram_total_mib.unwrap_or(0);
            format!("AMD GPU ({} GiB VRAM) — 7b is optimal", vram / 1024)
        }
        (ModelTier::Medium, GpuVendor::Apple) => format!(
            "Apple unified memory ({} GiB) — 7b is optimal",
            gpu.system_ram_mib / 1024
        ),
        (ModelTier::Medium, GpuVendor::Unknown) => format!(
            "System RAM ({} GiB) — 7b is optimal",
            gpu.system_ram_mib / 1024
        ),
        (ModelTier::Small, _) => format!(
            "Limited memory ({} GiB) — using lightweight 3b model",
            gpu.system_ram_mib / 1024
        ),
    };
    (tier.model_tag(), tier, reason)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn make_gpu(vendor: GpuVendor, vram_total: Option<u64>, unified: bool, ram: u64) -> GpuInfo {
        GpuInfo {
            vendor,
            vram_used_mib: None,
            vram_total_mib: vram_total,
            unified_memory: unified,
            system_ram_mib: ram,
        }
    }

    #[test]
    fn nvidia_24gb_selects_medium() {
        let gpu = make_gpu(GpuVendor::Nvidia, Some(24 * 1024), false, 32 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_MEDIUM);
        assert_eq!(tier, ModelTier::Medium);
    }

    #[test]
    fn nvidia_4gb_selects_small() {
        let gpu = make_gpu(GpuVendor::Nvidia, Some(4 * 1024), false, 16 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_SMALL);
        assert_eq!(tier, ModelTier::Small);
    }

    #[test]
    fn apple_64gb_selects_large() {
        let gpu = make_gpu(GpuVendor::Apple, None, true, 64 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_LARGE);
        assert_eq!(tier, ModelTier::Large);
    }

    #[test]
    fn apple_32gb_selects_medium() {
        // 32 GiB * 0.75 = 24 GiB effective, below 48 GiB threshold
        let gpu = make_gpu(GpuVendor::Apple, None, true, 32 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_MEDIUM);
        assert_eq!(tier, ModelTier::Medium);
    }

    #[test]
    fn apple_8gb_selects_small() {
        // 8 GiB * 0.75 = 6 GiB effective, below 8 GiB threshold
        let gpu = make_gpu(GpuVendor::Apple, None, true, 8 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_SMALL);
        assert_eq!(tier, ModelTier::Small);
    }

    #[test]
    fn no_gpu_16gb_ram_selects_medium() {
        let gpu = make_gpu(GpuVendor::Unknown, None, false, 16 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_MEDIUM);
        assert_eq!(tier, ModelTier::Medium);
    }

    #[test]
    fn no_gpu_4gb_ram_selects_small() {
        let gpu = make_gpu(GpuVendor::Unknown, None, false, 4 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_SMALL);
        assert_eq!(tier, ModelTier::Small);
    }

    #[test]
    fn amd_16gb_selects_medium() {
        let gpu = make_gpu(GpuVendor::Amd, Some(16 * 1024), false, 32 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_MEDIUM);
        assert_eq!(tier, ModelTier::Medium);
    }

    #[test]
    fn discrete_gpu_48gb_does_not_select_large() {
        // Discrete GPUs should NOT get large tier (29x slower per A/B testing)
        let gpu = make_gpu(GpuVendor::Nvidia, Some(48 * 1024), false, 64 * 1024);
        let (tag, tier, _) = recommended_model(&gpu);
        assert_eq!(tag, MODEL_MEDIUM);
        assert_eq!(tier, ModelTier::Medium);
    }

    #[test]
    fn effective_memory_unified() {
        let gpu = make_gpu(GpuVendor::Apple, None, true, 64 * 1024);
        let mem = effective_memory_mib(&gpu);
        assert_eq!(mem, (64.0 * 1024.0 * 0.75) as u64);
    }

    #[test]
    fn effective_memory_discrete() {
        let gpu = make_gpu(GpuVendor::Nvidia, Some(24 * 1024), false, 64 * 1024);
        let mem = effective_memory_mib(&gpu);
        assert_eq!(mem, 24 * 1024);
    }

    #[test]
    fn effective_memory_no_gpu() {
        let gpu = make_gpu(GpuVendor::Unknown, None, false, 16 * 1024);
        let mem = effective_memory_mib(&gpu);
        assert_eq!(mem, 16 * 1024);
    }

    #[test]
    fn reason_string_is_not_empty() {
        let gpu = make_gpu(GpuVendor::Nvidia, Some(24 * 1024), false, 32 * 1024);
        let (_, _, reason) = recommended_model(&gpu);
        assert!(!reason.is_empty());
    }

    #[test]
    fn model_tier_as_str() {
        assert_eq!(ModelTier::Small.as_str(), "small");
        assert_eq!(ModelTier::Medium.as_str(), "medium");
        assert_eq!(ModelTier::Large.as_str(), "large");
    }
}

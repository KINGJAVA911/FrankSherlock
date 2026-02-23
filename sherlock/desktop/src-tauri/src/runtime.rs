use crate::models::RuntimeStatus;

pub fn gather_runtime_status() -> RuntimeStatus {
    let (ollama_available, loaded_models) = crate::llm::list_loaded_models();
    let gpu = crate::platform::gpu::detect_gpu_memory();

    RuntimeStatus {
        current_model: loaded_models.first().cloned(),
        loaded_models,
        vram_used_mib: gpu.vram_used_mib,
        vram_total_mib: gpu.vram_total_mib,
        gpu_vendor: gpu.vendor,
        unified_memory: gpu.unified_memory,
        system_ram_mib: gpu.system_ram_mib,
        ollama_available,
    }
}

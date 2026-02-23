pub mod client;
pub mod management;
pub mod model_selection;

pub use client::{ollama_generate, parse_json_response};
pub use management::{
    cleanup_loaded_models, list_installed_models, list_loaded_models, DownloadState,
};
pub use model_selection::recommended_model;

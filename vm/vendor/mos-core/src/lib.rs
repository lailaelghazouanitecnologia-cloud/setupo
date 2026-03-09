//! Mos Core - Headless VNC/RFB protocol implementation
//!
//! This crate provides a platform-independent, headless implementation of the
//! VNC/RFB protocol. It can be used standalone or integrated with UI frameworks
//! like Tauri.

pub mod utils;
pub mod network;
pub mod core;
pub mod auth;
pub mod encodings;

// Re-export commonly used types
pub use crate::core::{ClientState, ConnectionConfig, RfbClient};
pub use encodings::{Decoder, EncodingType};
pub use utils::{MosError, MosResult};

/// Mos Core version
pub const VERSION: &str = env!("CARGO_PKG_VERSION");

/// Supported RFB protocol versions
pub const RFB_VERSIONS: &[&str] = &["3.3", "3.7", "3.8"];

/// Prelude module for convenient imports
pub mod prelude {
    pub use crate::core::{ClientState, ConnectionConfig, RfbClient};
    pub use crate::encodings::{Decoder, EncodingType};
    pub use crate::utils::{MosError, MosResult};
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version() {
        assert!(!VERSION.is_empty());
    }

    #[test]
    fn test_rfb_versions() {
        assert!(!RFB_VERSIONS.is_empty());
        assert!(RFB_VERSIONS.contains(&"3.8"));
    }
}

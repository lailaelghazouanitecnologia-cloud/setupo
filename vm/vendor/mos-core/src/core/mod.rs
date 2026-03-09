//! Core VNC/RFB protocol implementation
//!
//! This module provides the core VNC/RFB protocol implementation including
//! types, constants, configuration, protocol handshake, and RFB client.

pub mod types;
pub mod constants;
pub mod config;
pub mod protocol;
pub mod client;

// Re-exports for convenience
pub use types::{ConnectionState, PixelFormat, ProtocolVersion, SecurityType, ServerInit};
pub use config::ConnectionConfig;
pub use protocol::Handshake;
pub use client::{RfbClient, ClientState};

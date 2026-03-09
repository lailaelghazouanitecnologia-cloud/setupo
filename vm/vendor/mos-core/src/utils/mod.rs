//! Utility modules for Mos VNC client
//!
//! Provides common utilities used across the application including
//! error handling, logging, byte manipulation, and timing.

pub mod error;
pub mod logging;
pub mod bytes;
pub mod time;
pub mod metrics;
pub mod pool;

// Re-export commonly used items
pub use error::{MosError, MosResult};
pub use bytes::{ByteOps, ByteWriter};
pub use time::Timestamp;

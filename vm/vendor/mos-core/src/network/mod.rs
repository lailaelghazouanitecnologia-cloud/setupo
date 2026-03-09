//! Network layer for VNC connections
//!
//! Provides TCP connections, buffering, and async I/O primitives.

pub mod types;
pub mod error;
pub mod buffer;
pub mod tcp;

// Re-exports
pub use buffer::{Buffer, RingBuffer};
pub use tcp::TcpConnection;
pub use types::NetworkConfig;
pub use error::NetworkError;

use crate::utils::MosResult;

/// Trait for network streams
#[async_trait::async_trait]
pub trait NetworkStream: Send + Sync {
    /// Read bytes from the stream
    async fn read(&mut self, buf: &mut [u8]) -> MosResult<usize>;

    /// Write bytes to the stream
    async fn write(&mut self, buf: &[u8]) -> MosResult<usize>;

    /// Flush any buffered data
    async fn flush(&mut self) -> MosResult<()>;

    /// Shutdown the stream
    async fn shutdown(&mut self) -> MosResult<()>;
}

//! Network-specific error types

use crate::utils::MosError;
use std::io;

/// Network error type
#[derive(Debug, thiserror::Error)]
pub enum NetworkError {
    #[error("Connection failed: {0}")]
    ConnectionFailed(String),

    #[error("Connection timeout: {0}")]
    Timeout(String),

    #[error("Connection closed")]
    ConnectionClosed,

    #[error("Buffer overflow: {0}")]
    BufferOverflow(String),

    #[error("Invalid data: {0}")]
    InvalidData(String),

    #[error("IO error: {0}")]
    Io(#[from] io::Error),
}

impl From<NetworkError> for MosError {
    fn from(err: NetworkError) -> Self {
        match err {
            NetworkError::Timeout(msg) => MosError::timeout(msg),
            NetworkError::ConnectionClosed => MosError::connection("connection closed"),
            NetworkError::ConnectionFailed(msg) => MosError::connection(msg),
            NetworkError::BufferOverflow(msg) => MosError::buffer(msg),
            NetworkError::InvalidData(msg) => MosError::protocol(msg),
            NetworkError::Io(e) => MosError::Io(e),
        }
    }
}

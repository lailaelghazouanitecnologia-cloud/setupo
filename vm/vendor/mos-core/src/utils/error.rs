//! Error types for Mos VNC client
//!
//! Provides a comprehensive error type hierarchy using `thiserror`.

use std::io;
use thiserror::Error;

/// Result type alias for Mos operations
pub type MosResult<T> = std::result::Result<T, MosError>;

/// Main error type for Mos VNC client
#[derive(Error, Debug)]
pub enum MosError {
    #[error("Connection error: {0}")]
    Connection(String),

    #[error("Protocol error: {0}")]
    Protocol(String),

    #[error("Authentication failed: {0}")]
    Authentication(String),

    #[error("Security error: {0}")]
    Security(String),

    #[error("Encoding error: {0}")]
    Encoding(String),

    #[error("Decoding error in {encoding}: {message}")]
    Decoding {
        encoding: String,
        message: String,
    },

    #[error("Network error: {0}")]
    Network(String),

    #[error("Invalid state: {0}")]
    InvalidState(String),

    #[error("Timeout: {0}")]
    Timeout(String),

    #[error("Configuration error: {0}")]
    Config(String),

    #[error("Render error: {0}")]
    Render(String),

    #[error("Clipboard error: {0}")]
    Clipboard(String),

    #[error("Buffer error: {0}")]
    Buffer(String),

    #[error("Unsupported: {0}")]
    Unsupported(String),

    #[error("I/O error: {0}")]
    Io(#[from] io::Error),

    #[error("Protobuf error: {0}")]
    Protobuf(#[from] prost::DecodeError),

    #[error("{context}: {source}")]
    WithContext {
        context: String,
        source: Box<MosError>,
    },

    #[error("Unknown error: {0}")]
    Unknown(String),
}

impl MosError {
    pub fn connection(msg: impl Into<String>) -> Self {
        Self::Connection(msg.into())
    }

    pub fn protocol(msg: impl Into<String>) -> Self {
        Self::Protocol(msg.into())
    }

    pub fn auth(msg: impl Into<String>) -> Self {
        Self::Authentication(msg.into())
    }

    pub fn security(msg: impl Into<String>) -> Self {
        Self::Security(msg.into())
    }

    pub fn decoding(encoding: impl Into<String>, msg: impl Into<String>) -> Self {
        Self::Decoding {
            encoding: encoding.into(),
            message: msg.into(),
        }
    }

    pub fn buffer(msg: impl Into<String>) -> Self {
        Self::Buffer(msg.into())
    }

    pub fn invalid_state(msg: impl Into<String>) -> Self {
        Self::InvalidState(msg.into())
    }

    /// Alias for invalid_state
    pub fn state(msg: impl Into<String>) -> Self {
        Self::InvalidState(msg.into())
    }

    pub fn timeout(msg: impl Into<String>) -> Self {
        Self::Timeout(msg.into())
    }

    pub fn unsupported(msg: impl Into<String>) -> Self {
        Self::Unsupported(msg.into())
    }

    pub fn context(self, context: impl Into<String>) -> Self {
        Self::WithContext {
            context: context.into(),
            source: Box::new(self),
        }
    }

    pub fn is_timeout(&self) -> bool {
        matches!(self, MosError::Timeout(_))
    }

    pub fn is_connection(&self) -> bool {
        matches!(self, MosError::Connection(_))
    }

    pub fn is_auth(&self) -> bool {
        matches!(self, MosError::Authentication(_))
    }
}

impl From<String> for MosError {
    fn from(s: String) -> Self {
        MosError::Unknown(s)
    }
}

impl From<&str> for MosError {
    fn from(s: &str) -> Self {
        MosError::Unknown(s.to_string())
    }
}

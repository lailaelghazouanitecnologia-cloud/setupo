//! No authentication implementation
//!
//! This is the simplest authentication method - no authentication required.

use crate::network::TcpConnection;
use crate::utils::MosResult;

/// No authentication handler
pub struct NoneAuth;

impl NoneAuth {
    /// Create a new None authenticator
    pub fn new() -> Self {
        Self
    }

    /// Perform authentication (no-op for None)
    pub async fn authenticate(&self, _conn: &mut TcpConnection) -> MosResult<()> {
        tracing::info!("No authentication required");
        Ok(())
    }
}

impl Default for NoneAuth {
    fn default() -> Self {
        Self::new()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_none_auth_creation() {
        let auth = NoneAuth::new();
        // Just verify it can be created
        let _ = auth;
    }
}

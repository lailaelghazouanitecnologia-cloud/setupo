//! VNC Authentication (DES challenge-response)
//!
//! VNC authentication uses a DES-encrypted challenge-response mechanism.

mod des;
use des::des_encrypt_challenge;

use crate::network::TcpConnection;
use crate::utils::MosResult;

/// VNC authentication handler
pub struct VncAuth {
    password: String,
}

impl VncAuth {
    /// Create a new VNC authenticator with password
    pub fn new(password: impl Into<String>) -> Self {
        Self {
            password: password.into(),
        }
    }

    /// Perform VNC authentication
    pub async fn authenticate(&self, conn: &mut TcpConnection) -> MosResult<()> {
        tracing::info!("Performing VNC authentication");

        // Read 16-byte challenge
        let mut challenge = [0u8; 16];
        conn.read_exact(&mut challenge).await?;

        tracing::debug!("Received authentication challenge");

        // Encrypt challenge with password
        let response = des_encrypt_challenge(&challenge, &self.password)?;

        // Send encrypted response
        conn.write_all(&response).await?;
        conn.flush().await?;

        tracing::debug!("Sent authentication response");
        Ok(())
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_vnc_auth_creation() {
        let auth = VncAuth::new("password");
        assert_eq!(auth.password, "password");
    }
}

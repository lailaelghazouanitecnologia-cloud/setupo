//! VNC authentication methods
//!
//! Provides authentication implementations for different VNC security types.

pub mod types;
pub mod none;
pub mod vnc;

pub use types::Credentials;
pub use none::NoneAuth;
pub use vnc::VncAuth;

use crate::core::SecurityType;
use crate::network::TcpConnection;
use crate::utils::MosResult;

/// Authentication handler factory
pub struct AuthHandler;

impl AuthHandler {
    /// Perform authentication based on security type
    pub async fn authenticate(
        security_type: SecurityType,
        conn: &mut TcpConnection,
        password: Option<&str>,
    ) -> MosResult<()> {
        match security_type {
            SecurityType::None => {
                let auth = NoneAuth::new();
                auth.authenticate(conn).await
            }
            SecurityType::VncAuth => {
                let password = password.ok_or_else(|| {
                    crate::utils::MosError::auth("Password required for VNC authentication")
                })?;
                let auth = VncAuth::new(password);
                auth.authenticate(conn).await
            }
            _ => Err(crate::utils::MosError::unsupported(format!(
                "Authentication method not implemented: {:?}",
                security_type
            ))),
        }
    }
}

// Re-export for compatibility
pub use crate::core::SecurityType as AuthMethod;

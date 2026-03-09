//! RFB protocol handshake implementation
//!
//! Implements the VNC/RFB handshake sequence:
//! 1. Protocol version negotiation
//! 2. Security type selection
//! 3. Authentication (handled by auth module)
//! 4. Client/Server initialization

use crate::core::constants::{VERSION_STRING_LENGTH, security_result};
use crate::core::types::{PixelFormat, ProtocolVersion, SecurityType, ServerInit};
use crate::network::TcpConnection;
use crate::utils::{ByteOps, MosError, MosResult};

/// Handshake handler
pub struct Handshake;

impl Handshake {
    /// Read protocol version from server
    pub async fn read_version(conn: &mut TcpConnection) -> MosResult<ProtocolVersion> {
        let mut buf = vec![0u8; VERSION_STRING_LENGTH];
        conn.read_exact(&mut buf).await?;

        let version_str = String::from_utf8(buf)
            .map_err(|e| MosError::protocol(format!("Invalid version string: {}", e)))?;

        tracing::debug!("Server version: {}", version_str.trim());

        ProtocolVersion::from_str(&version_str)
            .ok_or_else(|| MosError::protocol(format!("Unsupported version: {}", version_str)))
    }

    /// Send protocol version to server
    pub async fn send_version(
        conn: &mut TcpConnection,
        version: ProtocolVersion,
    ) -> MosResult<()> {
        let version_str = version.as_str();
        tracing::debug!("Sending version: {}", version_str.trim());
        conn.write_all(version_str.as_bytes()).await?;
        conn.flush().await?;
        Ok(())
    }

    /// Read security types from server (RFB 3.7+)
    pub async fn read_security_types(conn: &mut TcpConnection) -> MosResult<Vec<SecurityType>> {
        // Read number of security types
        let mut count_buf = [0u8; 1];
        conn.read_exact(&mut count_buf).await?;
        let count = count_buf[0];

        if count == 0 {
            // Server rejected connection, read reason
            let mut reason_len_buf = [0u8; 4];
            conn.read_exact(&mut reason_len_buf).await?;
            let reason_len = reason_len_buf.read_u32_be(0)?;

            let mut reason_buf = vec![0u8; reason_len as usize];
            conn.read_exact(&mut reason_buf).await?;
            let reason = String::from_utf8_lossy(&reason_buf);

            return Err(MosError::security(format!("Connection rejected: {}", reason)));
        }

        // Read security types
        let mut types_buf = vec![0u8; count as usize];
        conn.read_exact(&mut types_buf).await?;

        let types: Vec<SecurityType> = types_buf
            .iter()
            .filter_map(|&b| SecurityType::from_u8(b))
            .collect();

        tracing::debug!("Available security types: {:?}", types);

        if types.is_empty() {
            return Err(MosError::security("No supported security types"));
        }

        Ok(types)
    }

    /// Read security type from server (RFB 3.3)
    pub async fn read_security_type_33(conn: &mut TcpConnection) -> MosResult<SecurityType> {
        let mut buf = [0u8; 4];
        conn.read_exact(&mut buf).await?;
        let type_u32 = buf.read_u32_be(0)?;

        SecurityType::from_u8(type_u32 as u8)
            .ok_or_else(|| MosError::security(format!("Unsupported security type: {}", type_u32)))
    }

    /// Send selected security type to server
    pub async fn send_security_type(
        conn: &mut TcpConnection,
        security_type: SecurityType,
    ) -> MosResult<()> {
        tracing::debug!("Selecting security type: {:?}", security_type);
        let buf = [security_type.to_u8()];
        conn.write_all(&buf).await?;
        conn.flush().await?;
        Ok(())
    }

    /// Read security result from server
    pub async fn read_security_result(conn: &mut TcpConnection) -> MosResult<()> {
        let mut buf = [0u8; 4];
        conn.read_exact(&mut buf).await?;
        let result = buf.read_u32_be(0)?;

        match result {
            security_result::OK => {
                tracing::info!("Security handshake successful");
                Ok(())
            }
            security_result::FAILED => {
                // Read failure reason (RFB 3.8+)
                let mut reason_len_buf = [0u8; 4];
                if conn.read_exact(&mut reason_len_buf).await.is_ok() {
                    let reason_len = reason_len_buf.read_u32_be(0)?;
                    let mut reason_buf = vec![0u8; reason_len as usize];
                    if conn.read_exact(&mut reason_buf).await.is_ok() {
                        let reason = String::from_utf8_lossy(&reason_buf);
                        return Err(MosError::auth(format!("Authentication failed: {}", reason)));
                    }
                }
                Err(MosError::auth("Authentication failed"))
            }
            _ => Err(MosError::security(format!("Unknown security result: {}", result))),
        }
    }

    /// Send client initialization
    pub async fn send_client_init(conn: &mut TcpConnection, shared: bool) -> MosResult<()> {
        let flag = if shared { 1u8 } else { 0u8 };
        tracing::debug!("Sending client init (shared: {})", shared);
        conn.write_all(&[flag]).await?;
        conn.flush().await?;
        Ok(())
    }

    /// Read server initialization
    pub async fn read_server_init(conn: &mut TcpConnection) -> MosResult<ServerInit> {
        let mut buf = [0u8; 24]; // ServerInit header
        conn.read_exact(&mut buf).await?;

        let width = buf.read_u16_be(0)?;
        let height = buf.read_u16_be(2)?;

        // Parse pixel format (16 bytes starting at offset 4)
        let pixel_format = PixelFormat {
            bits_per_pixel: buf.read_u8(4)?,
            depth: buf.read_u8(5)?,
            big_endian: buf.read_u8(6)? != 0,
            true_color: buf.read_u8(7)? != 0,
            red_max: buf.read_u16_be(8)?,
            green_max: buf.read_u16_be(10)?,
            blue_max: buf.read_u16_be(12)?,
            red_shift: buf.read_u8(14)?,
            green_shift: buf.read_u8(15)?,
            blue_shift: buf.read_u8(16)?,
        };

        // Read desktop name
        let name_length = buf.read_u32_be(20)? as usize;
        let mut name_buf = vec![0u8; name_length];
        conn.read_exact(&mut name_buf).await?;
        let name = String::from_utf8_lossy(&name_buf).to_string();

        tracing::info!(
            "Server initialized: {}x{}, name: '{}', pixel format: {:?}",
            width,
            height,
            name,
            pixel_format
        );

        Ok(ServerInit {
            width,
            height,
            pixel_format,
            name,
        })
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_version_parsing() {
        // These are unit tests for parsing logic
        assert_eq!(
            ProtocolVersion::from_str("RFB 003.008"),
            Some(ProtocolVersion::Rfb38)
        );
        assert_eq!(
            ProtocolVersion::from_str("RFB 003.007"),
            Some(ProtocolVersion::Rfb37)
        );
    }

    #[test]
    fn test_security_type_conversion() {
        assert_eq!(SecurityType::from_u8(1), Some(SecurityType::None));
        assert_eq!(SecurityType::from_u8(2), Some(SecurityType::VncAuth));
        assert_eq!(SecurityType::None.to_u8(), 1);
    }
}

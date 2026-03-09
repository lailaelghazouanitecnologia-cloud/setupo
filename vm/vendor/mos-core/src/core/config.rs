//! Connection configuration

use super::types::{PixelFormat, ProtocolVersion, SecurityType};
use crate::network::NetworkConfig;

/// VNC connection configuration
#[derive(Debug, Clone)]
pub struct ConnectionConfig {
    /// Server hostname or IP
    pub host: String,

    /// Server port (default: 5900)
    pub port: u16,

    /// Password for authentication
    pub password: Option<String>,

    /// Preferred protocol version
    pub preferred_version: ProtocolVersion,

    /// Preferred security types (in order of preference)
    pub preferred_security: Vec<SecurityType>,

    /// Preferred encodings (in order of preference)
    pub preferred_encodings: Vec<i32>,

    /// Shared flag (allow other clients)
    pub shared: bool,

    /// View only mode
    pub view_only: bool,

    /// Pixel format to request
    pub pixel_format: PixelFormat,

    /// Network configuration
    pub network: NetworkConfig,

    /// Quality level (0-9, for JPEG)
    pub quality_level: Option<u8>,

    /// Compression level (0-9)
    pub compression_level: Option<u8>,
}

impl ConnectionConfig {
    /// Create a new configuration
    pub fn new(host: impl Into<String>, port: u16) -> Self {
        Self {
            host: host.into(),
            port,
            password: None,
            preferred_version: ProtocolVersion::Rfb38,
            preferred_security: vec![SecurityType::VncAuth, SecurityType::None],
            preferred_encodings: default_encodings(),
            shared: false,
            view_only: false,
            pixel_format: PixelFormat::rgba(),
            network: NetworkConfig::default(),
            quality_level: Some(6),
            compression_level: Some(2),
        }
    }

    /// Set password
    pub fn with_password(mut self, password: impl Into<String>) -> Self {
        self.password = Some(password.into());
        self
    }

    /// Set shared flag
    pub fn with_shared(mut self, shared: bool) -> Self {
        self.shared = shared;
        self
    }

    /// Set view only
    pub fn with_view_only(mut self, view_only: bool) -> Self {
        self.view_only = view_only;
        self
    }

    /// Set quality level
    pub fn with_quality(mut self, quality: u8) -> Self {
        self.quality_level = Some(quality.min(9));
        self
    }

    /// Set compression level
    pub fn with_compression(mut self, compression: u8) -> Self {
        self.compression_level = Some(compression.min(9));
        self
    }

    /// Get full address
    pub fn address(&self) -> String {
        format!("{}:{}", self.host, self.port)
    }

    /// Validate configuration
    pub fn validate(&self) -> Result<(), String> {
        if self.host.is_empty() {
            return Err("Host cannot be empty".to_string());
        }

        if self.port == 0 {
            return Err("Port cannot be zero".to_string());
        }

        if self.preferred_security.is_empty() {
            return Err("At least one security type must be specified".to_string());
        }

        Ok(())
    }
}

impl Default for ConnectionConfig {
    fn default() -> Self {
        Self::new("localhost", 5900)
    }
}

/// Default encoding preferences
fn default_encodings() -> Vec<i32> {
    use crate::core::constants::{encoding, pseudo_encoding};

    vec![
        // Data encodings (in order of preference)
        encoding::COPY_RECT,
        encoding::TIGHT,
        encoding::ZRLE,
        encoding::HEXTILE,
        encoding::RRE,
        encoding::RAW,

        // Pseudo-encodings
        pseudo_encoding::CURSOR,
        pseudo_encoding::DESKTOP_SIZE,
        pseudo_encoding::EXTENDED_DESKTOP_SIZE,
        pseudo_encoding::DESKTOP_NAME,
        pseudo_encoding::LAST_RECT,
        pseudo_encoding::QEMU_EXTENDED_KEY_EVENT,
    ]
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_config_builder() {
        let config = ConnectionConfig::new("example.com", 5900)
            .with_password("secret")
            .with_shared(true)
            .with_quality(7);

        assert_eq!(config.host, "example.com");
        assert_eq!(config.port, 5900);
        assert_eq!(config.password, Some("secret".to_string()));
        assert_eq!(config.shared, true);
        assert_eq!(config.quality_level, Some(7));
    }

    #[test]
    fn test_validation() {
        let config = ConnectionConfig::new("localhost", 5900);
        assert!(config.validate().is_ok());

        let config = ConnectionConfig::new("", 5900);
        assert!(config.validate().is_err());

        let config = ConnectionConfig::new("localhost", 0);
        assert!(config.validate().is_err());
    }

    #[test]
    fn test_address() {
        let config = ConnectionConfig::new("192.168.1.100", 5901);
        assert_eq!(config.address(), "192.168.1.100:5901");
    }

    #[test]
    fn test_default_encodings() {
        let encodings = default_encodings();
        assert!(!encodings.is_empty());
        assert_eq!(encodings[0], crate::core::constants::encoding::COPY_RECT);
    }
}

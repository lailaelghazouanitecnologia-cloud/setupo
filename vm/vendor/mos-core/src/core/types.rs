//! Core VNC/RFB protocol types

use serde::{Deserialize, Serialize};

/// RFB protocol version
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ProtocolVersion {
    /// RFB 3.3
    Rfb33,
    /// RFB 3.7
    Rfb37,
    /// RFB 3.8 (most common)
    Rfb38,
}

impl ProtocolVersion {
    /// Parse version from string (e.g., "RFB 003.008\n")
    pub fn from_str(s: &str) -> Option<Self> {
        match s.trim() {
            "RFB 003.003" => Some(Self::Rfb33),
            "RFB 003.007" => Some(Self::Rfb37),
            "RFB 003.008" => Some(Self::Rfb38),
            _ => None,
        }
    }

    /// Get version string
    pub fn as_str(&self) -> &'static str {
        match self {
            Self::Rfb33 => "RFB 003.003\n",
            Self::Rfb37 => "RFB 003.007\n",
            Self::Rfb38 => "RFB 003.008\n",
        }
    }

    /// Check if this version supports a feature
    pub fn supports_security_types(&self) -> bool {
        matches!(self, Self::Rfb37 | Self::Rfb38)
    }
}

/// Security type (authentication method)
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
#[repr(u8)]
pub enum SecurityType {
    Invalid = 0,
    None = 1,
    VncAuth = 2,
    RA2 = 5,
    RA2ne = 6,
    Tight = 16,
    Ultra = 17,
    TLS = 18,
    VeNCrypt = 19,
    SASL = 20,
    MD5 = 21,
    XVP = 22,
    ARD = 30,
    MSLogonII = 113,
}

impl SecurityType {
    pub fn from_u8(value: u8) -> Option<Self> {
        match value {
            0 => Some(Self::Invalid),
            1 => Some(Self::None),
            2 => Some(Self::VncAuth),
            5 => Some(Self::RA2),
            6 => Some(Self::RA2ne),
            16 => Some(Self::Tight),
            17 => Some(Self::Ultra),
            18 => Some(Self::TLS),
            19 => Some(Self::VeNCrypt),
            20 => Some(Self::SASL),
            21 => Some(Self::MD5),
            22 => Some(Self::XVP),
            30 => Some(Self::ARD),
            113 => Some(Self::MSLogonII),
            _ => None,
        }
    }

    pub fn to_u8(self) -> u8 {
        self as u8
    }

    pub fn name(&self) -> &'static str {
        match self {
            Self::Invalid => "Invalid",
            Self::None => "None",
            Self::VncAuth => "VNC Authentication",
            Self::RA2 => "RA2",
            Self::RA2ne => "RA2ne",
            Self::Tight => "Tight",
            Self::Ultra => "Ultra",
            Self::TLS => "TLS",
            Self::VeNCrypt => "VeNCrypt",
            Self::SASL => "SASL",
            Self::MD5 => "MD5",
            Self::XVP => "XVP",
            Self::ARD => "Apple Remote Desktop",
            Self::MSLogonII => "MS-Logon-II",
        }
    }
}

/// Pixel format
#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
pub struct PixelFormat {
    pub bits_per_pixel: u8,
    pub depth: u8,
    pub big_endian: bool,
    pub true_color: bool,
    pub red_max: u16,
    pub green_max: u16,
    pub blue_max: u16,
    pub red_shift: u8,
    pub green_shift: u8,
    pub blue_shift: u8,
}

impl PixelFormat {
    /// Standard 32-bit RGB888 format (RGBA with alpha ignored)
    pub fn rgb888() -> Self {
        Self {
            bits_per_pixel: 32,
            depth: 24,
            big_endian: false,
            true_color: true,
            red_max: 255,
            green_max: 255,
            blue_max: 255,
            red_shift: 0,
            green_shift: 8,
            blue_shift: 16,
        }
    }

    /// RGB888 big-endian variant
    pub fn rgb888_be() -> Self {
        Self {
            bits_per_pixel: 32,
            depth: 24,
            big_endian: true,
            true_color: true,
            red_max: 255,
            green_max: 255,
            blue_max: 255,
            red_shift: 0,
            green_shift: 8,
            blue_shift: 16,
        }
    }

    /// Alias for rgb888 (backwards compatibility)
    pub fn rgba() -> Self {
        Self::rgb888()
    }

    /// Bytes per pixel
    pub fn bytes_per_pixel(&self) -> usize {
        (self.bits_per_pixel / 8) as usize
    }
}

impl Default for PixelFormat {
    fn default() -> Self {
        Self::rgb888()
    }
}

/// Server initialization message
#[derive(Debug, Clone)]
pub struct ServerInit {
    pub width: u16,
    pub height: u16,
    pub pixel_format: PixelFormat,
    pub name: String,
}

/// Connection state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ConnectionState {
    Disconnected,
    Connecting,
    ProtocolVersion,
    Security,
    Authentication,
    SecurityResult,
    ClientInit,
    ServerInit,
    Connected,
    Failed,
}

impl ConnectionState {
    pub fn is_connected(&self) -> bool {
        matches!(self, Self::Connected)
    }

    pub fn is_active(&self) -> bool {
        !matches!(self, Self::Disconnected | Self::Failed)
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_protocol_version() {
        let v = ProtocolVersion::Rfb38;
        assert_eq!(v.as_str(), "RFB 003.008\n");
        assert!(v.supports_security_types());

        let parsed = ProtocolVersion::from_str("RFB 003.008");
        assert_eq!(parsed, Some(ProtocolVersion::Rfb38));
    }

    #[test]
    fn test_security_type() {
        let st = SecurityType::VncAuth;
        assert_eq!(st.to_u8(), 2);
        assert_eq!(SecurityType::from_u8(2), Some(SecurityType::VncAuth));
        assert_eq!(st.name(), "VNC Authentication");
    }

    #[test]
    fn test_pixel_format() {
        let pf = PixelFormat::rgba();
        assert_eq!(pf.bytes_per_pixel(), 4);
        assert_eq!(pf.bits_per_pixel, 32);
    }

    #[test]
    fn test_connection_state() {
        let state = ConnectionState::Connected;
        assert!(state.is_connected());
        assert!(state.is_active());

        let state = ConnectionState::Disconnected;
        assert!(!state.is_connected());
        assert!(!state.is_active());
    }
}

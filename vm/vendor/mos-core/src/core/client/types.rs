//! Client types

use crate::encodings::EncodingType;

/// RFB Client state
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ClientState {
    Disconnected,
    Handshaking,
    Authenticating,
    Initializing,
    Connected,
    Error,
}

/// Framebuffer rectangle update
#[derive(Debug, Clone)]
pub struct Rectangle {
    pub x: u16,
    pub y: u16,
    pub width: u16,
    pub height: u16,
    pub encoding: EncodingType,
}

/// Cursor shape data from server
#[derive(Debug, Clone)]
pub struct CursorShape {
    /// Cursor width in pixels
    pub width: u16,
    /// Cursor height in pixels
    pub height: u16,
    /// Hotspot X coordinate (point that represents actual cursor position)
    pub hotspot_x: u16,
    /// Hotspot Y coordinate
    pub hotspot_y: u16,
    /// Pixel data in framebuffer format (width*height*bytes_per_pixel)
    pub pixels: Vec<u8>,
    /// Bitmask (1 bit per pixel, 1 = visible, 0 = transparent)
    /// Scan lines are padded to whole bytes
    pub mask: Vec<u8>,
}

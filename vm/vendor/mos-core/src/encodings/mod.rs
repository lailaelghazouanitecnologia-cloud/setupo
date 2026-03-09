//! VNC encoding decoders
//!
//! Implements decoders for various VNC encodings.

pub mod raw;
pub mod copyrect;
pub mod rre;
pub mod hextile;
pub mod tight;
pub mod zlib;
pub mod zrle;
pub mod jpeg;

pub use raw::RawDecoder;
pub use copyrect::CopyRectDecoder;
pub use rre::RreDecoder;
pub use hextile::HextileDecoder;
pub use tight::TightDecoder;
pub use zlib::ZlibDecoder;
pub use zrle::ZrleDecoder;
pub use jpeg::JpegEncodingDecoder;

use crate::core::PixelFormat;
use crate::utils::MosResult;

/// Encoding types supported by Mos
#[derive(Debug, Clone, Copy, PartialEq, Eq, Hash)]
#[repr(i32)]
pub enum EncodingType {
    // Standard encodings (positive values)
    Raw = 0,
    CopyRect = 1,
    Rre = 2,
    Hextile = 5,
    Zlib = 6,
    Tight = 7,
    Zrle = 16,
    Jpeg = 21,

    // Pseudo-encodings (negative values)
    Cursor = -239,
    DesktopSize = -223,
}

impl EncodingType {
    pub fn from_i32(value: i32) -> Option<Self> {
        match value {
            0 => Some(Self::Raw),
            1 => Some(Self::CopyRect),
            2 => Some(Self::Rre),
            5 => Some(Self::Hextile),
            6 => Some(Self::Zlib),
            7 => Some(Self::Tight),
            16 => Some(Self::Zrle),
            21 => Some(Self::Jpeg),
            -239 => Some(Self::Cursor),
            -223 => Some(Self::DesktopSize),
            _ => None,
        }
    }

    pub fn is_pseudo_encoding(&self) -> bool {
        matches!(self, Self::Cursor | Self::DesktopSize)
    }

    pub fn to_i32(self) -> i32 {
        self as i32
    }

    pub fn name(&self) -> &'static str {
        match self {
            Self::Raw => "Raw",
            Self::CopyRect => "CopyRect",
            Self::Rre => "RRE",
            Self::Hextile => "Hextile",
            Self::Zlib => "Zlib",
            Self::Tight => "Tight",
            Self::Zrle => "ZRLE",
            Self::Jpeg => "JPEG",
            Self::Cursor => "Cursor",
            Self::DesktopSize => "DesktopSize",
        }
    }
}

/// Trait for all encoding decoders
pub trait Decoder: Send + Sync {
    /// Decode rectangle data into framebuffer
    fn decode(
        &mut self,
        data: &[u8],
        x: u16,
        y: u16,
        width: u16,
        height: u16,
        framebuffer: &mut [u8],
        fb_width: u16,
        pixel_format: &PixelFormat,
    ) -> MosResult<usize>;

    /// Reset decoder state
    fn reset(&mut self);

    /// Get encoding type
    fn encoding_type(&self) -> EncodingType;
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_encoding_type_conversion() {
        assert_eq!(EncodingType::from_i32(0), Some(EncodingType::Raw));
        assert_eq!(EncodingType::Raw.to_i32(), 0);
        assert_eq!(EncodingType::Raw.name(), "Raw");
    }
}

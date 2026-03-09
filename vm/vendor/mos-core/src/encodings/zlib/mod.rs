//! Zlib encoding decoder
//!
//! Zlib encoding uses standard zlib compression on raw pixel data.
//! Simpler than Tight encoding - no RLE, no palettes, just straight compression.
//!
//! Encoding: 6
//!
//! Format:
//! - 4 bytes: compressed data length (big-endian)
//! - N bytes: zlib-compressed raw pixel data

use crate::core::PixelFormat;
use crate::encodings::{Decoder, EncodingType};
use crate::utils::{ByteOps, MosError, MosResult};
use flate2::read::ZlibDecoder as FlateDecoder;
use std::io::Read;

/// Zlib encoding decoder
#[derive(Debug)]
pub struct ZlibDecoder {}

impl ZlibDecoder {
    /// Create a new Zlib decoder
    pub fn new() -> Self {
        Self {}
    }

    /// Decompress zlib data
    fn decompress_zlib(compressed: &[u8]) -> MosResult<Vec<u8>> {
        let mut decoder = FlateDecoder::new(compressed);
        let mut decompressed = Vec::new();

        decoder
            .read_to_end(&mut decompressed)
            .map_err(|e| MosError::decoding("Zlib", format!("Decompression failed: {}", e)))?;

        Ok(decompressed)
    }
}

impl Default for ZlibDecoder {
    fn default() -> Self {
        Self::new()
    }
}

impl Decoder for ZlibDecoder {
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
    ) -> MosResult<usize> {
        // Read compressed length (4 bytes, big-endian)
        if data.len() < 4 {
            return Err(MosError::decoding("Zlib", "Insufficient data for length"));
        }
        let compressed_len = data.read_u32_be(0)? as usize;

        if 4 + compressed_len > data.len() {
            return Err(MosError::decoding("Zlib", "Insufficient compressed data"));
        }

        // Decompress zlib stream
        let compressed_data = &data[4..4 + compressed_len];
        let decompressed = Self::decompress_zlib(compressed_data)?;

        // Verify decompressed size
        let bytes_per_pixel = pixel_format.bytes_per_pixel();
        let expected_size = (width as usize) * (height as usize) * bytes_per_pixel;

        if decompressed.len() != expected_size {
            return Err(MosError::decoding(
                "Zlib",
                format!(
                    "Decompressed size mismatch: expected {}, got {}",
                    expected_size,
                    decompressed.len()
                ),
            ));
        }

        // Copy decompressed pixels to framebuffer
        let mut src_offset = 0;
        for row in 0..height as usize {
            for col in 0..width as usize {
                let dst_y = y as usize + row;
                let dst_x = x as usize + col;
                let dst_offset = (dst_y * fb_width as usize + dst_x) * bytes_per_pixel;

                if dst_offset + bytes_per_pixel <= framebuffer.len() {
                    framebuffer[dst_offset..dst_offset + bytes_per_pixel]
                        .copy_from_slice(&decompressed[src_offset..src_offset + bytes_per_pixel]);
                }

                src_offset += bytes_per_pixel;
            }
        }

        Ok(4 + compressed_len)
    }

    fn reset(&mut self) {
        // No state to reset
    }

    fn encoding_type(&self) -> EncodingType {
        EncodingType::Zlib
    }
}

#[cfg(test)]
mod tests;

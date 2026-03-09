//! Raw encoding decoder
//!
//! Raw encoding is the simplest - pixels are sent uncompressed.

use super::{Decoder, EncodingType};
use crate::core::PixelFormat;
use crate::utils::{MosError, MosResult};

/// Raw encoding decoder
pub struct RawDecoder;

impl RawDecoder {
    /// Create a new Raw decoder
    pub fn new() -> Self {
        Self
    }

    /// Calculate bytes needed for a rectangle
    fn bytes_needed(width: u16, height: u16, pixel_format: &PixelFormat) -> usize {
        width as usize * height as usize * pixel_format.bytes_per_pixel()
    }
}

impl Default for RawDecoder {
    fn default() -> Self {
        Self::new()
    }
}

impl Decoder for RawDecoder {
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
        let bytes_per_pixel = pixel_format.bytes_per_pixel();
        let bytes_needed = Self::bytes_needed(width, height, pixel_format);

        if data.len() < bytes_needed {
            return Err(MosError::decoding(
                "Raw",
                format!(
                    "Not enough data: expected {}, got {}",
                    bytes_needed,
                    data.len()
                ),
            ));
        }

        // Copy pixels row by row into framebuffer
        for row in 0..height {
            let src_offset = (row as usize * width as usize) * bytes_per_pixel;
            let dst_y = y as usize + row as usize;
            let dst_offset = (dst_y * fb_width as usize + x as usize) * bytes_per_pixel;

            let row_bytes = width as usize * bytes_per_pixel;
            let src_slice = &data[src_offset..src_offset + row_bytes];
            let dst_slice = &mut framebuffer[dst_offset..dst_offset + row_bytes];

            dst_slice.copy_from_slice(src_slice);
        }

        Ok(bytes_needed)
    }

    fn reset(&mut self) {
        // No state to reset for Raw decoder
    }

    fn encoding_type(&self) -> EncodingType {
        EncodingType::Raw
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn test_pixel_format() -> PixelFormat {
        PixelFormat {
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

    #[test]
    fn test_raw_decoder_creation() {
        let decoder = RawDecoder::new();
        assert_eq!(decoder.encoding_type(), EncodingType::Raw);
    }

    #[test]
    fn test_bytes_needed() {
        let pf = test_pixel_format();
        assert_eq!(RawDecoder::bytes_needed(10, 10, &pf), 400); // 10*10*4
        assert_eq!(RawDecoder::bytes_needed(1, 1, &pf), 4);
    }

    #[test]
    fn test_decode_simple() {
        let mut decoder = RawDecoder::new();
        let pf = test_pixel_format();

        // Create 2x2 pixel data (32-bit RGBA)
        let data = vec![
            255, 0, 0, 255, // Red pixel
            0, 255, 0, 255, // Green pixel
            0, 0, 255, 255, // Blue pixel
            255, 255, 255, 255, // White pixel
        ];

        // Framebuffer for 4x4 image
        let mut fb = vec![0u8; 4 * 4 * 4];

        let bytes_read = decoder.decode(&data, 0, 0, 2, 2, &mut fb, 4, &pf).unwrap();

        assert_eq!(bytes_read, 16); // 2*2*4
        assert_eq!(fb[0], 255); // Red pixel R
        assert_eq!(fb[1], 0); // Red pixel G
        assert_eq!(fb[2], 0); // Red pixel B
    }

    #[test]
    fn test_decode_not_enough_data() {
        let mut decoder = RawDecoder::new();
        let pf = test_pixel_format();

        let data = vec![1, 2, 3]; // Not enough data
        let mut fb = vec![0u8; 100];

        let result = decoder.decode(&data, 0, 0, 10, 10, &mut fb, 10, &pf);
        assert!(result.is_err());
    }

    #[test]
    fn test_decode_with_offset() {
        let mut decoder = RawDecoder::new();
        let pf = test_pixel_format();

        // Single red pixel
        let data = vec![255, 0, 0, 255];

        // 4x4 framebuffer
        let mut fb = vec![0u8; 4 * 4 * 4];

        // Decode at position (1, 1)
        decoder.decode(&data, 1, 1, 1, 1, &mut fb, 4, &pf).unwrap();

        // Check pixel at (1,1)
        let offset = (1 * 4 + 1) * 4;
        assert_eq!(fb[offset], 255); // Red
        assert_eq!(fb[offset + 1], 0); // Green
        assert_eq!(fb[offset + 2], 0); // Blue
    }
}

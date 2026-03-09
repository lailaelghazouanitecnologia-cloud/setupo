//! CopyRect encoding decoder
//!
//! CopyRect is a simple encoding that copies a rectangle from one part
//! of the framebuffer to another. Very efficient for scrolling and
//! window movements.
//!
//! Encoding: 1
//!
//! Format:
//! - src-x-position: u16 (2 bytes)
//! - src-y-position: u16 (2 bytes)
//!
//! Total: 4 bytes of data

use crate::core::PixelFormat;
use crate::encodings::{Decoder, EncodingType};
use crate::utils::{ByteOps, MosError, MosResult};

/// CopyRect encoding decoder
///
/// Copies a rectangle from one framebuffer location to another.
/// This is very efficient for operations like scrolling or moving windows.
#[derive(Debug, Default)]
pub struct CopyRectDecoder;

impl CopyRectDecoder {
    /// Create a new CopyRect decoder
    pub fn new() -> Self {
        Self
    }
}

impl Decoder for CopyRectDecoder {
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
        // CopyRect data is just 4 bytes: src-x (u16) + src-y (u16)
        if data.len() < 4 {
            return Err(MosError::decoding(
                "CopyRect",
                format!("Need 4 bytes, got {}", data.len()),
            ));
        }

        let src_x = data.read_u16_be(0)?;
        let src_y = data.read_u16_be(2)?;

        let bytes_per_pixel = pixel_format.bytes_per_pixel();

        // Validate coordinates
        if src_x as usize + width as usize > fb_width as usize {
            return Err(MosError::decoding(
                "CopyRect",
                format!(
                    "Source x + width ({} + {}) exceeds framebuffer width ({})",
                    src_x, width, fb_width
                ),
            ));
        }

        if x as usize + width as usize > fb_width as usize {
            return Err(MosError::decoding(
                "CopyRect",
                format!(
                    "Dest x + width ({} + {}) exceeds framebuffer width ({})",
                    x, width, fb_width
                ),
            ));
        }

        // Copy rectangle row by row
        // We need to handle overlapping regions carefully
        if src_y == y && src_x < x {
            // Copying right within same row - copy backwards
            for row in 0..height {
                let src_row = src_y as usize + row as usize;
                let dst_row = y as usize + row as usize;

                for col in (0..width).rev() {
                    let src_offset =
                        (src_row * fb_width as usize + (src_x as usize + col as usize))
                            * bytes_per_pixel;
                    let dst_offset =
                        (dst_row * fb_width as usize + (x as usize + col as usize))
                            * bytes_per_pixel;

                    // Bounds check
                    if src_offset + bytes_per_pixel > framebuffer.len()
                        || dst_offset + bytes_per_pixel > framebuffer.len()
                    {
                        return Err(MosError::decoding(
                            "CopyRect",
                            "Framebuffer bounds exceeded",
                        ));
                    }

                    // Copy pixel
                    framebuffer.copy_within(
                        src_offset..src_offset + bytes_per_pixel,
                        dst_offset,
                    );
                }
            }
        } else {
            // Normal forward copy
            for row in 0..height {
                let src_row = src_y as usize + row as usize;
                let dst_row = y as usize + row as usize;

                let src_offset =
                    (src_row * fb_width as usize + src_x as usize) * bytes_per_pixel;
                let dst_offset = (dst_row * fb_width as usize + x as usize) * bytes_per_pixel;
                let row_bytes = width as usize * bytes_per_pixel;

                // Bounds check
                if src_offset + row_bytes > framebuffer.len()
                    || dst_offset + row_bytes > framebuffer.len()
                {
                    return Err(MosError::decoding(
                        "CopyRect",
                        "Framebuffer bounds exceeded",
                    ));
                }

                // Copy row
                framebuffer.copy_within(src_offset..src_offset + row_bytes, dst_offset);
            }
        }

        Ok(4) // Always 4 bytes consumed
    }

    fn reset(&mut self) {
        // No state to reset
    }

    fn encoding_type(&self) -> EncodingType {
        EncodingType::CopyRect
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    fn create_test_pixel_format() -> PixelFormat {
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
    fn test_copyrect_basic() {
        let mut decoder = CopyRectDecoder::new();
        let pixel_format = create_test_pixel_format();

        // Create 4x4 framebuffer with pattern
        let mut fb = vec![0u8; 4 * 4 * 4]; // 4x4 pixels, 4 bytes each

        // Fill source area (0,0) 2x2 with red
        for y in 0..2 {
            for x in 0..2 {
                let offset = (y * 4 + x) * 4;
                fb[offset] = 255; // Red
                fb[offset + 1] = 0;
                fb[offset + 2] = 0;
                fb[offset + 3] = 255;
            }
        }

        // Copy from (0,0) to (2,2), 2x2
        let data = vec![
            0, 0, // src_x = 0
            0, 0, // src_y = 0
        ];

        let bytes_read = decoder
            .decode(&data, 2, 2, 2, 2, &mut fb, 4, &pixel_format)
            .unwrap();

        assert_eq!(bytes_read, 4);

        // Check destination has red pixels
        for y in 2..4 {
            for x in 2..4 {
                let offset = (y * 4 + x) * 4;
                assert_eq!(fb[offset], 255, "Red channel at ({}, {})", x, y);
                assert_eq!(fb[offset + 1], 0, "Green channel at ({}, {})", x, y);
                assert_eq!(fb[offset + 2], 0, "Blue channel at ({}, {})", x, y);
            }
        }
    }

    #[test]
    fn test_copyrect_insufficient_data() {
        let mut decoder = CopyRectDecoder::new();
        let pixel_format = create_test_pixel_format();
        let mut fb = vec![0u8; 4 * 4 * 4];

        // Only 3 bytes
        let data = vec![0, 0, 0];

        let result = decoder.decode(&data, 0, 0, 2, 2, &mut fb, 4, &pixel_format);
        assert!(result.is_err());
    }

    #[test]
    fn test_copyrect_bounds_check() {
        let mut decoder = CopyRectDecoder::new();
        let pixel_format = create_test_pixel_format();
        let mut fb = vec![0u8; 4 * 4 * 4];

        // Try to copy from out of bounds
        let data = vec![
            0, 10, // src_x = 10 (out of bounds for 4x4 fb)
            0, 0,  // src_y = 0
        ];

        let result = decoder.decode(&data, 0, 0, 2, 2, &mut fb, 4, &pixel_format);
        assert!(result.is_err());
    }

    #[test]
    fn test_copyrect_encoding_type() {
        let decoder = CopyRectDecoder::new();
        assert_eq!(decoder.encoding_type(), EncodingType::CopyRect);
    }

    #[test]
    fn test_copyrect_overlapping_right() {
        let mut decoder = CopyRectDecoder::new();
        let pixel_format = create_test_pixel_format();

        let mut fb = vec![0u8; 4 * 4 * 4];

        // Fill position (0,0) with red
        fb[0] = 255; // Red
        fb[1] = 0;
        fb[2] = 0;
        fb[3] = 255;

        // Copy from (0,0) to (1,0) - overlapping to the right
        let data = vec![0, 0, 0, 0];

        decoder
            .decode(&data, 1, 0, 1, 1, &mut fb, 4, &pixel_format)
            .unwrap();

        // Check pixel at (1,0) is now red
        let offset = (0 * 4 + 1) * 4;
        assert_eq!(fb[offset], 255);
    }
}

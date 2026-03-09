//! RRE (Rise-and-Run-length Encoding) decoder
//!
//! RRE encoding represents a rectangle as a background color
//! plus a series of subrectangles with solid colors.
//!
//! Encoding: 2
//!
//! Format:
//! - number-of-subrectangles: u32 (4 bytes)
//! - background-pixel-value: pixel (bytes_per_pixel)
//! - For each subrectangle:
//!   - pixel-value: pixel (bytes_per_pixel)
//!   - x-position: u16 (2 bytes)
//!   - y-position: u16 (2 bytes)
//!   - width: u16 (2 bytes)
//!   - height: u16 (2 bytes)

use crate::core::PixelFormat;
use crate::encodings::{Decoder, EncodingType};
use crate::utils::{ByteOps, MosError, MosResult};

/// RRE encoding decoder
#[derive(Debug, Default)]
pub struct RreDecoder;

impl RreDecoder {
    /// Create a new RRE decoder
    pub fn new() -> Self {
        Self
    }

    /// Fill a rectangle with a solid color
    fn fill_rect(
        framebuffer: &mut [u8],
        fb_width: u16,
        x: u16,
        y: u16,
        width: u16,
        height: u16,
        pixel: &[u8],
        bytes_per_pixel: usize,
    ) -> MosResult<()> {
        for row in 0..height {
            let dst_y = y as usize + row as usize;

            for col in 0..width {
                let dst_x = x as usize + col as usize;
                let offset = (dst_y * fb_width as usize + dst_x) * bytes_per_pixel;

                if offset + bytes_per_pixel > framebuffer.len() {
                    return Err(MosError::decoding(
                        "RRE",
                        "Framebuffer bounds exceeded",
                    ));
                }

                framebuffer[offset..offset + bytes_per_pixel]
                    .copy_from_slice(pixel);
            }
        }

        Ok(())
    }
}

impl Decoder for RreDecoder {
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

        // Need at least 4 bytes for subrect count + background pixel
        if data.len() < 4 + bytes_per_pixel {
            return Err(MosError::decoding(
                "RRE",
                format!(
                    "Need at least {} bytes, got {}",
                    4 + bytes_per_pixel,
                    data.len()
                ),
            ));
        }

        // Read number of subrectangles
        let num_subrects = data.read_u32_be(0)? as usize;
        let mut offset = 4;

        // Read background pixel
        let background_pixel = &data[offset..offset + bytes_per_pixel];
        offset += bytes_per_pixel;

        // Fill entire rectangle with background color
        Self::fill_rect(
            framebuffer,
            fb_width,
            x,
            y,
            width,
            height,
            background_pixel,
            bytes_per_pixel,
        )?;

        // Process each subrectangle
        let subrect_size = bytes_per_pixel + 8; // pixel + x + y + w + h
        for i in 0..num_subrects {
            if offset + subrect_size > data.len() {
                return Err(MosError::decoding(
                    "RRE",
                    format!(
                        "Insufficient data for subrectangle {} (need {} bytes)",
                        i, subrect_size
                    ),
                ));
            }

            // Read subrectangle pixel value
            let pixel = &data[offset..offset + bytes_per_pixel];
            offset += bytes_per_pixel;

            // Read subrectangle position and size
            let sub_x = data.read_u16_be(offset)?;
            offset += 2;
            let sub_y = data.read_u16_be(offset)?;
            offset += 2;
            let sub_width = data.read_u16_be(offset)?;
            offset += 2;
            let sub_height = data.read_u16_be(offset)?;
            offset += 2;

            // Validate subrectangle is within bounds
            if sub_x + sub_width > width || sub_y + sub_height > height {
                return Err(MosError::decoding(
                    "RRE",
                    format!(
                        "Subrectangle out of bounds: {}x{} at ({},{})",
                        sub_width, sub_height, sub_x, sub_y
                    ),
                ));
            }

            // Fill subrectangle
            Self::fill_rect(
                framebuffer,
                fb_width,
                x + sub_x,
                y + sub_y,
                sub_width,
                sub_height,
                pixel,
                bytes_per_pixel,
            )?;
        }

        Ok(offset)
    }

    fn reset(&mut self) {
        // No state to reset
    }

    fn encoding_type(&self) -> EncodingType {
        EncodingType::Rre
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
    fn test_rre_no_subrects() {
        let mut decoder = RreDecoder::new();
        let pixel_format = create_test_pixel_format();

        let mut fb = vec![0u8; 4 * 4 * 4]; // 4x4 pixels, 4 bytes each

        // RRE with no subrectangles, just blue background
        let data = vec![
            0, 0, 0, 0, // 0 subrectangles
            0, 0, 255, 255, // Blue background
        ];

        let bytes_read = decoder
            .decode(&data, 0, 0, 4, 4, &mut fb, 4, &pixel_format)
            .unwrap();

        assert_eq!(bytes_read, 8);

        // Check all pixels are blue
        for i in 0..16 {
            let offset = i * 4;
            assert_eq!(fb[offset], 0); // Red
            assert_eq!(fb[offset + 1], 0); // Green
            assert_eq!(fb[offset + 2], 255); // Blue
        }
    }

    #[test]
    fn test_rre_with_subrects() {
        let mut decoder = RreDecoder::new();
        let pixel_format = create_test_pixel_format();

        let mut fb = vec![0u8; 4 * 4 * 4];

        // RRE: blue background with one red 2x2 subrect at (1,1)
        let data = vec![
            0, 0, 0, 1, // 1 subrectangle
            0, 0, 255, 255, // Blue background
            255, 0, 0, 255, // Red pixel
            0, 1, // x=1
            0, 1, // y=1
            0, 2, // width=2
            0, 2, // height=2
        ];

        decoder
            .decode(&data, 0, 0, 4, 4, &mut fb, 4, &pixel_format)
            .unwrap();

        // Check corners are blue (background)
        let offset = 0; // (0,0)
        assert_eq!(fb[offset + 2], 255); // Blue

        let offset = (3 * 4 + 3) * 4; // (3,3)
        assert_eq!(fb[offset + 2], 255); // Blue

        // Check center is red (subrectangle)
        let offset = (1 * 4 + 1) * 4; // (1,1)
        assert_eq!(fb[offset], 255); // Red
        assert_eq!(fb[offset + 1], 0);
        assert_eq!(fb[offset + 2], 0);

        let offset = (2 * 4 + 2) * 4; // (2,2)
        assert_eq!(fb[offset], 255); // Red
    }

    #[test]
    fn test_rre_insufficient_data() {
        let mut decoder = RreDecoder::new();
        let pixel_format = create_test_pixel_format();
        let mut fb = vec![0u8; 4 * 4 * 4];

        // Only 2 bytes
        let data = vec![0, 0];

        let result = decoder.decode(&data, 0, 0, 4, 4, &mut fb, 4, &pixel_format);
        assert!(result.is_err());
    }

    #[test]
    fn test_rre_subrect_out_of_bounds() {
        let mut decoder = RreDecoder::new();
        let pixel_format = create_test_pixel_format();
        let mut fb = vec![0u8; 4 * 4 * 4];

        // Subrect extends beyond rectangle bounds
        let data = vec![
            0, 0, 0, 1, // 1 subrectangle
            0, 0, 255, 255, // Blue background
            255, 0, 0, 255, // Red pixel
            0, 3, // x=3
            0, 3, // y=3
            0, 3, // width=3 (out of bounds!)
            0, 3, // height=3
        ];

        let result = decoder.decode(&data, 0, 0, 4, 4, &mut fb, 4, &pixel_format);
        assert!(result.is_err());
    }

    #[test]
    fn test_rre_encoding_type() {
        let decoder = RreDecoder::new();
        assert_eq!(decoder.encoding_type(), EncodingType::Rre);
    }

    #[test]
    fn test_rre_multiple_subrects() {
        let mut decoder = RreDecoder::new();
        let pixel_format = create_test_pixel_format();
        let mut fb = vec![0u8; 4 * 4 * 4];

        // White background with 2 colored squares
        let data = vec![
            0, 0, 0, 2, // 2 subrectangles
            255, 255, 255, 255, // White background
            // First subrect: red 1x1 at (0,0)
            255, 0, 0, 255, 0, 0, 0, 0, 0, 1, 0, 1,
            // Second subrect: green 1x1 at (3,3)
            0, 255, 0, 255, 0, 3, 0, 3, 0, 1, 0, 1,
        ];

        decoder
            .decode(&data, 0, 0, 4, 4, &mut fb, 4, &pixel_format)
            .unwrap();

        // Check (0,0) is red
        assert_eq!(fb[0], 255);
        assert_eq!(fb[1], 0);
        assert_eq!(fb[2], 0);

        // Check (3,3) is green
        let offset = (3 * 4 + 3) * 4;
        assert_eq!(fb[offset], 0);
        assert_eq!(fb[offset + 1], 255);
        assert_eq!(fb[offset + 2], 0);

        // Check (1,1) is white (background)
        let offset = (1 * 4 + 1) * 4;
        assert_eq!(fb[offset], 255);
        assert_eq!(fb[offset + 1], 255);
        assert_eq!(fb[offset + 2], 255);
    }
}

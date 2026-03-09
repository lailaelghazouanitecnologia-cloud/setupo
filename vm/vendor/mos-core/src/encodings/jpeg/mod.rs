//! JPEG encoding decoder
//!
//! JPEG encoding (type 21) uses JPEG compression for entire rectangles.
//! This is useful for photographic content and continuous-tone images.
//!
//! Encoding: 21 (IANA registered)
//!
//! Data format:
//! - 4 bytes: Length of JPEG data (big-endian u32)
//! - N bytes: JPEG-compressed image data
//!
//! The JPEG image dimensions must match the rectangle width/height.
//! The decoded JPEG is converted to the client's pixel format and
//! copied to the framebuffer at the specified position.

use crate::core::PixelFormat;
use crate::encodings::{Decoder, EncodingType};
use crate::utils::{ByteOps, MosError, MosResult};
use jpeg_decoder::Decoder as JpegDecoder;

/// JPEG encoding decoder
#[derive(Debug)]
pub struct JpegEncodingDecoder {}

impl JpegEncodingDecoder {
    /// Create a new JPEG decoder
    pub fn new() -> Self {
        Self {}
    }

    /// Decompress JPEG data
    fn decompress_jpeg(data: &[u8]) -> MosResult<(Vec<u8>, u16, u16)> {
        let mut decoder = JpegDecoder::new(data);

        let pixels = decoder
            .decode()
            .map_err(|e| MosError::decoding("JPEG", format!("JPEG decompression failed: {}", e)))?;

        let info = decoder.info().ok_or_else(|| {
            MosError::decoding("JPEG", "Failed to get JPEG image info")
        })?;

        Ok((pixels, info.width, info.height))
    }

    /// Convert RGB/RGBA pixels to framebuffer pixel format
    fn convert_pixels(
        rgb_data: &[u8],
        pixel_format: &PixelFormat,
        components: u8,
    ) -> Vec<u8> {
        let bytes_per_pixel = (pixel_format.bits_per_pixel / 8) as usize;
        let pixel_count = rgb_data.len() / (components as usize);
        let mut converted = Vec::with_capacity(pixel_count * bytes_per_pixel);

        for i in 0..pixel_count {
            let offset = i * (components as usize);

            // Handle grayscale (1 component) and RGB (3 components)
            let (r, g, b) = if components == 1 {
                let gray = rgb_data[offset] as u32;
                (gray, gray, gray)
            } else {
                (
                    rgb_data[offset] as u32,
                    rgb_data[offset + 1] as u32,
                    rgb_data[offset + 2] as u32,
                )
            };

            // Convert to pixel format
            let red = (r >> (8 - pixel_format.red_max.count_ones())) << pixel_format.red_shift;
            let green = (g >> (8 - pixel_format.green_max.count_ones())) << pixel_format.green_shift;
            let blue = (b >> (8 - pixel_format.blue_max.count_ones())) << pixel_format.blue_shift;
            let pixel = red | green | blue;

            // Write pixel in correct byte order
            if pixel_format.big_endian {
                for j in (0..bytes_per_pixel).rev() {
                    converted.push(((pixel >> (j * 8)) & 0xFF) as u8);
                }
            } else {
                for j in 0..bytes_per_pixel {
                    converted.push(((pixel >> (j * 8)) & 0xFF) as u8);
                }
            }
        }

        converted
    }
}

impl Default for JpegEncodingDecoder {
    fn default() -> Self {
        Self::new()
    }
}

impl Decoder for JpegEncodingDecoder {
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
        if data.len() < 4 {
            return Err(MosError::decoding("JPEG", "Insufficient data for length header"));
        }

        // Read JPEG data length (4 bytes, big-endian)
        let jpeg_len = data.read_u32_be(0)? as usize;

        if data.len() < 4 + jpeg_len {
            return Err(MosError::decoding(
                "JPEG",
                format!("Insufficient data: need {} bytes, have {}", 4 + jpeg_len, data.len()),
            ));
        }

        // Decompress JPEG
        let jpeg_data = &data[4..4 + jpeg_len];
        let (rgb_pixels, jpeg_width, jpeg_height) = Self::decompress_jpeg(jpeg_data)?;

        // Verify dimensions match
        if jpeg_width != width || jpeg_height != height {
            return Err(MosError::decoding(
                "JPEG",
                format!(
                    "JPEG dimensions {}x{} don't match rectangle {}x{}",
                    jpeg_width, jpeg_height, width, height
                ),
            ));
        }

        // Detect component count (RGB or grayscale)
        let components = (rgb_pixels.len() / (width as usize * height as usize)) as u8;
        if components != 1 && components != 3 {
            return Err(MosError::decoding(
                "JPEG",
                format!("Unsupported JPEG component count: {}", components),
            ));
        }

        // Convert to framebuffer pixel format
        let converted_pixels = Self::convert_pixels(&rgb_pixels, pixel_format, components);

        // Copy to framebuffer
        let bytes_per_pixel = (pixel_format.bits_per_pixel / 8) as usize;
        let fb_stride = fb_width as usize * bytes_per_pixel;

        for row in 0..height as usize {
            let src_offset = row * width as usize * bytes_per_pixel;
            let dst_offset = (y as usize + row) * fb_stride + x as usize * bytes_per_pixel;
            let row_bytes = width as usize * bytes_per_pixel;

            framebuffer[dst_offset..dst_offset + row_bytes]
                .copy_from_slice(&converted_pixels[src_offset..src_offset + row_bytes]);
        }

        Ok(4 + jpeg_len)
    }

    fn reset(&mut self) {
        // JPEG decoder is stateless
    }

    fn encoding_type(&self) -> EncodingType {
        EncodingType::Jpeg
    }
}

#[cfg(test)]
mod tests;

//! Tight encoding decoder
//!
//! Tight encoding is one of the most efficient VNC encodings, combining
//! multiple compression techniques including zlib, palette encoding, and JPEG.
//!
//! Encoding: 7
//!
//! Compression types:
//! - Fill: Solid color (most efficient for solid areas)
//! - Copy: Zlib-compressed raw data
//! - Palette: Indexed colors (2-255 unique colors)
//! - JPEG: JPEG-compressed images (optional, future)

use crate::core::PixelFormat;
use crate::encodings::{Decoder, EncodingType};
use crate::utils::{MosError, MosResult};
use flate2::read::ZlibDecoder;
use std::io::Read;

// Compression control byte masks
const STREAM_ID_MASK: u8 = 0x03; // Bits 0-1 (we'll use stream 0 for simplicity)
const RESET_STREAM_0: u8 = 0x01;
const RESET_STREAM_1: u8 = 0x02;
const RESET_STREAM_2: u8 = 0x04;
const RESET_STREAM_3: u8 = 0x08;

// Compression types (bits 4-7)
const FILL_COMPRESSION: u8 = 0x08;
const JPEG_COMPRESSION: u8 = 0x09;
const BASIC_COMPRESSION: u8 = 0x00; // Max value 0x07

// Filter types
const COPY_FILTER: u8 = 0x00;
const PALETTE_FILTER: u8 = 0x01;
const GRADIENT_FILTER: u8 = 0x02;

/// Tight encoding decoder
#[derive(Debug)]
pub struct TightDecoder {
    // Could maintain zlib streams here for efficiency
    // For now, we'll decompress on demand
}

impl TightDecoder {
    /// Create a new Tight decoder
    pub fn new() -> Self {
        Self {}
    }

    /// Read compact length encoding
    /// Returns (length, bytes_read)
    fn read_compact_length(data: &[u8], offset: usize) -> MosResult<(usize, usize)> {
        if offset >= data.len() {
            return Err(MosError::decoding("Tight", "Insufficient data for length"));
        }

        let b1 = data[offset];

        if b1 & 0x80 == 0 {
            // Single byte: 0-127
            Ok((b1 as usize, 1))
        } else if b1 & 0x40 == 0 {
            // Two bytes: 128-16383
            if offset + 1 >= data.len() {
                return Err(MosError::decoding("Tight", "Insufficient data for 2-byte length"));
            }
            let b2 = data[offset + 1];
            let len = ((b1 & 0x7F) as usize) | ((b2 as usize) << 7);
            Ok((len, 2))
        } else {
            // Three bytes: 16384+
            if offset + 2 >= data.len() {
                return Err(MosError::decoding("Tight", "Insufficient data for 3-byte length"));
            }
            let b2 = data[offset + 1];
            let b3 = data[offset + 2];
            let len = ((b1 & 0x3F) as usize) | ((b2 as usize) << 6) | ((b3 as usize) << 14);
            Ok((len, 3))
        }
    }

    /// Decompress zlib data
    fn decompress_zlib(compressed: &[u8], expected_size: usize) -> MosResult<Vec<u8>> {
        let mut decoder = ZlibDecoder::new(compressed);
        let mut decompressed = Vec::with_capacity(expected_size);

        decoder
            .read_to_end(&mut decompressed)
            .map_err(|e| MosError::decoding("Tight", format!("Zlib decompression failed: {}", e)))?;

        if decompressed.len() != expected_size {
            return Err(MosError::decoding(
                "Tight",
                format!("Decompressed size mismatch: got {}, expected {}",
                    decompressed.len(), expected_size),
            ));
        }

        Ok(decompressed)
    }

    /// Decode Fill compression (solid color)
    fn decode_fill(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        x: u16,
        y: u16,
        width: u16,
        height: u16,
        framebuffer: &mut [u8],
        fb_width: u16,
        bytes_per_pixel: usize,
    ) -> MosResult<()> {
        // Fill: just read the pixel value and fill the rectangle
        if *offset + bytes_per_pixel > data.len() {
            return Err(MosError::decoding("Tight", "Insufficient data for fill pixel"));
        }

        let pixel = &data[*offset..*offset + bytes_per_pixel];
        *offset += bytes_per_pixel;

        // Fill the rectangle with this color
        for row in 0..height {
            for col in 0..width {
                let dst_y = y as usize + row as usize;
                let dst_x = x as usize + col as usize;
                let dst_offset = (dst_y * fb_width as usize + dst_x) * bytes_per_pixel;

                if dst_offset + bytes_per_pixel <= framebuffer.len() {
                    framebuffer[dst_offset..dst_offset + bytes_per_pixel]
                        .copy_from_slice(pixel);
                }
            }
        }

        Ok(())
    }

    /// Decode Copy filter (raw data with zlib compression)
    fn decode_copy(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        x: u16,
        y: u16,
        width: u16,
        height: u16,
        framebuffer: &mut [u8],
        fb_width: u16,
        bytes_per_pixel: usize,
    ) -> MosResult<()> {
        // Read compressed length
        let (compressed_len, len_bytes) = Self::read_compact_length(data, *offset)?;
        *offset += len_bytes;

        if *offset + compressed_len > data.len() {
            return Err(MosError::decoding("Tight", "Insufficient compressed data"));
        }

        // Decompress
        let expected_size = width as usize * height as usize * bytes_per_pixel;
        let compressed_data = &data[*offset..*offset + compressed_len];
        *offset += compressed_len;

        let decompressed = Self::decompress_zlib(compressed_data, expected_size)?;

        // Copy to framebuffer
        for row in 0..height {
            let src_offset = (row as usize * width as usize) * bytes_per_pixel;
            let dst_y = y as usize + row as usize;
            let dst_offset = (dst_y * fb_width as usize + x as usize) * bytes_per_pixel;
            let row_bytes = width as usize * bytes_per_pixel;

            if dst_offset + row_bytes <= framebuffer.len()
                && src_offset + row_bytes <= decompressed.len() {
                framebuffer[dst_offset..dst_offset + row_bytes]
                    .copy_from_slice(&decompressed[src_offset..src_offset + row_bytes]);
            }
        }

        Ok(())
    }

    /// Decode Palette filter (indexed colors)
    fn decode_palette(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        x: u16,
        y: u16,
        width: u16,
        height: u16,
        framebuffer: &mut [u8],
        fb_width: u16,
        bytes_per_pixel: usize,
    ) -> MosResult<()> {
        // Read palette size (number of colors - 1)
        if *offset >= data.len() {
            return Err(MosError::decoding("Tight", "No palette size byte"));
        }
        let palette_size = data[*offset] as usize + 1;
        *offset += 1;

        if palette_size > 256 {
            return Err(MosError::decoding("Tight", "Invalid palette size"));
        }

        // Read palette
        let palette_bytes = palette_size * bytes_per_pixel;
        if *offset + palette_bytes > data.len() {
            return Err(MosError::decoding("Tight", "Insufficient palette data"));
        }

        let palette = &data[*offset..*offset + palette_bytes];
        *offset += palette_bytes;

        // Determine index size (1 or 2 bits per pixel for small palettes)
        let bits_per_pixel = if palette_size <= 2 {
            1
        } else if palette_size <= 4 {
            2
        } else {
            8
        };

        // Calculate size of index data
        let pixels = width as usize * height as usize;
        let index_size = (pixels * bits_per_pixel + 7) / 8;

        // Read compressed length
        let (compressed_len, len_bytes) = Self::read_compact_length(data, *offset)?;
        *offset += len_bytes;

        if *offset + compressed_len > data.len() {
            return Err(MosError::decoding("Tight", "Insufficient palette index data"));
        }

        // Decompress indices
        let compressed_data = &data[*offset..*offset + compressed_len];
        *offset += compressed_len;

        let indices = Self::decompress_zlib(compressed_data, index_size)?;

        // Decode indices to pixels
        let mut pixel_idx = 0;
        for row in 0..height {
            for col in 0..width {
                let index = if bits_per_pixel == 8 {
                    indices[pixel_idx]
                } else {
                    // Extract sub-byte index
                    let byte_idx = (pixel_idx * bits_per_pixel) / 8;
                    let bit_offset = (pixel_idx * bits_per_pixel) % 8;
                    let mask = (1 << bits_per_pixel) - 1;
                    (indices[byte_idx] >> (8 - bit_offset - bits_per_pixel)) & mask
                } as usize;

                if index >= palette_size {
                    return Err(MosError::decoding("Tight", "Palette index out of bounds"));
                }

                // Copy palette color to framebuffer
                let pixel = &palette[index * bytes_per_pixel..(index + 1) * bytes_per_pixel];
                let dst_y = y as usize + row as usize;
                let dst_x = x as usize + col as usize;
                let dst_offset = (dst_y * fb_width as usize + dst_x) * bytes_per_pixel;

                if dst_offset + bytes_per_pixel <= framebuffer.len() {
                    framebuffer[dst_offset..dst_offset + bytes_per_pixel]
                        .copy_from_slice(pixel);
                }

                pixel_idx += 1;
            }
        }

        Ok(())
    }
}

impl Default for TightDecoder {
    fn default() -> Self {
        Self::new()
    }
}

impl Decoder for TightDecoder {
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
        let mut offset = 0;

        // Read compression control byte
        if offset >= data.len() {
            return Err(MosError::decoding("Tight", "No compression control byte"));
        }
        let control = data[offset];
        offset += 1;

        // Check for stream resets (we ignore for now)
        let _stream_resets = control & 0x0F;

        // Get compression type
        let compression_type = (control >> 4) & 0x0F;

        match compression_type {
            FILL_COMPRESSION => {
                self.decode_fill(data, &mut offset, x, y, width, height,
                    framebuffer, fb_width, bytes_per_pixel)?;
            }
            JPEG_COMPRESSION => {
                return Err(MosError::decoding("Tight", "JPEG compression not yet supported"));
            }
            _ if compression_type <= 0x07 => {
                // Basic compression - read filter type
                if offset >= data.len() {
                    return Err(MosError::decoding("Tight", "No filter type byte"));
                }
                let filter = data[offset];
                offset += 1;

                match filter {
                    COPY_FILTER => {
                        self.decode_copy(data, &mut offset, x, y, width, height,
                            framebuffer, fb_width, bytes_per_pixel)?;
                    }
                    PALETTE_FILTER => {
                        self.decode_palette(data, &mut offset, x, y, width, height,
                            framebuffer, fb_width, bytes_per_pixel)?;
                    }
                    GRADIENT_FILTER => {
                        return Err(MosError::decoding("Tight", "Gradient filter not yet supported"));
                    }
                    _ => {
                        return Err(MosError::decoding("Tight", format!("Unknown filter type: {}", filter)));
                    }
                }
            }
            _ => {
                return Err(MosError::decoding("Tight", format!("Unknown compression type: {}", compression_type)));
            }
        }

        Ok(offset)
    }

    fn reset(&mut self) {
        // Could reset zlib streams here if we maintain them
    }

    fn encoding_type(&self) -> EncodingType {
        EncodingType::Tight
    }
}

#[cfg(test)]
mod tests;

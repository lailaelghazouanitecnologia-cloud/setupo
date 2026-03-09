//! ZRLE encoding decoder
//!
//! ZRLE (Zlib Run-Length Encoding) combines zlib compression with RLE.
//! Uses 64x64 tiles and various sub-encodings for different content types.
//!
//! Encoding: 16
//!
//! Sub-encoding types:
//! - 0: Raw pixels (uncompressed within zlib stream)
//! - 1: Solid color (single pixel for entire tile)
//! - 2-16: Palette RLE (palette with RLE indices)
//! - 128: Plain RLE (run-length with full pixels)
//! - 130+: Packed palette (bit-packed indices)

use crate::core::PixelFormat;
use crate::encodings::{Decoder, EncodingType};
use crate::utils::{ByteOps, MosError, MosResult};
use flate2::read::ZlibDecoder;
use std::io::Read;

const TILE_SIZE: u16 = 64;

// Sub-encoding types
const RAW_SUBENCODING: u8 = 0;
const SOLID_SUBENCODING: u8 = 1;
const PACKED_PALETTE_START: u8 = 2;
const PACKED_PALETTE_END: u8 = 16;
const PLAIN_RLE: u8 = 128;
const PALETTE_RLE: u8 = 129;
const PACKED_PALETTE_RLE_START: u8 = 130;

/// ZRLE encoding decoder
#[derive(Debug)]
pub struct ZrleDecoder {}

impl ZrleDecoder {
    /// Create a new ZRLE decoder
    pub fn new() -> Self {
        Self {}
    }

    /// Read CPIXEL (compact pixel) from data
    /// Returns (pixel_bytes, bytes_read)
    fn read_cpixel(data: &[u8], offset: usize, cpixel_size: usize) -> MosResult<(Vec<u8>, usize)> {
        if offset + cpixel_size > data.len() {
            return Err(MosError::decoding("ZRLE", "Insufficient data for CPIXEL"));
        }

        let pixel = data[offset..offset + cpixel_size].to_vec();
        Ok((pixel, cpixel_size))
    }

    /// Expand CPIXEL to full pixel format
    fn expand_cpixel(cpixel: &[u8], pixel_format: &PixelFormat) -> Vec<u8> {
        let bytes_per_pixel = pixel_format.bytes_per_pixel();

        if cpixel.len() >= bytes_per_pixel {
            // Already full size
            return cpixel[..bytes_per_pixel].to_vec();
        }

        // Expand from CPIXEL to full format
        // For 24-bit true color: CPIXEL is 3 bytes RGB
        let mut pixel = vec![0u8; bytes_per_pixel];
        pixel[..cpixel.len()].copy_from_slice(cpixel);
        pixel
    }

    /// Decode raw sub-encoding (type 0)
    fn decode_raw_tile(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        tile_width: u16,
        tile_height: u16,
        cpixel_size: usize,
        pixel_format: &PixelFormat,
    ) -> MosResult<Vec<Vec<u8>>> {
        let pixels_needed = tile_width as usize * tile_height as usize;
        let mut pixels = Vec::with_capacity(pixels_needed);

        for _ in 0..pixels_needed {
            let (cpixel, bytes_read) = Self::read_cpixel(data, *offset, cpixel_size)?;
            *offset += bytes_read;
            pixels.push(Self::expand_cpixel(&cpixel, pixel_format));
        }

        Ok(pixels)
    }

    /// Decode solid sub-encoding (type 1)
    fn decode_solid_tile(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        tile_width: u16,
        tile_height: u16,
        cpixel_size: usize,
        pixel_format: &PixelFormat,
    ) -> MosResult<Vec<Vec<u8>>> {
        let (cpixel, bytes_read) = Self::read_cpixel(data, *offset, cpixel_size)?;
        *offset += bytes_read;

        let pixel = Self::expand_cpixel(&cpixel, pixel_format);
        let pixels_needed = tile_width as usize * tile_height as usize;

        Ok(vec![pixel; pixels_needed])
    }

    /// Decode plain RLE sub-encoding (type 128)
    fn decode_plain_rle_tile(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        tile_width: u16,
        tile_height: u16,
        cpixel_size: usize,
        pixel_format: &PixelFormat,
    ) -> MosResult<Vec<Vec<u8>>> {
        let pixels_needed = tile_width as usize * tile_height as usize;
        let mut pixels = Vec::with_capacity(pixels_needed);

        while pixels.len() < pixels_needed {
            // Read run length
            if *offset >= data.len() {
                return Err(MosError::decoding("ZRLE", "Insufficient data for RLE length"));
            }
            let run_length = data[*offset] as usize + 1;
            *offset += 1;

            // Read pixel
            let (cpixel, bytes_read) = Self::read_cpixel(data, *offset, cpixel_size)?;
            *offset += bytes_read;
            let pixel = Self::expand_cpixel(&cpixel, pixel_format);

            // Repeat pixel run_length times
            for _ in 0..run_length {
                if pixels.len() >= pixels_needed {
                    break;
                }
                pixels.push(pixel.clone());
            }
        }

        Ok(pixels)
    }

    /// Decode packed palette sub-encoding (types 2-16)
    fn decode_packed_palette_tile(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        tile_width: u16,
        tile_height: u16,
        cpixel_size: usize,
        pixel_format: &PixelFormat,
        palette_size: usize,
    ) -> MosResult<Vec<Vec<u8>>> {
        // Read palette
        let mut palette = Vec::with_capacity(palette_size);
        for _ in 0..palette_size {
            let (cpixel, bytes_read) = Self::read_cpixel(data, *offset, cpixel_size)?;
            *offset += bytes_read;
            palette.push(Self::expand_cpixel(&cpixel, pixel_format));
        }

        // Determine bits per pixel
        let bits_per_pixel = if palette_size <= 2 {
            1
        } else if palette_size <= 4 {
            2
        } else {
            4
        };

        // Read packed indices
        let pixels_needed = tile_width as usize * tile_height as usize;
        let mut pixels = Vec::with_capacity(pixels_needed);

        let mut bit_pos = 0;
        let mut current_byte = 0u8;

        for _ in 0..pixels_needed {
            if bit_pos == 0 {
                if *offset >= data.len() {
                    return Err(MosError::decoding("ZRLE", "Insufficient data for packed indices"));
                }
                current_byte = data[*offset];
                *offset += 1;
            }

            // Extract index from current byte
            let shift = 8 - bits_per_pixel - bit_pos;
            let mask = (1 << bits_per_pixel) - 1;
            let index = ((current_byte >> shift) & mask) as usize;

            bit_pos += bits_per_pixel;
            if bit_pos >= 8 {
                bit_pos = 0;
            }

            if index >= palette.len() {
                return Err(MosError::decoding("ZRLE", "Palette index out of bounds"));
            }

            pixels.push(palette[index].clone());
        }

        Ok(pixels)
    }

    /// Decode palette RLE sub-encoding (type 129)
    fn decode_palette_rle_tile(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        tile_width: u16,
        tile_height: u16,
        cpixel_size: usize,
        pixel_format: &PixelFormat,
    ) -> MosResult<Vec<Vec<u8>>> {
        // Read palette size
        if *offset >= data.len() {
            return Err(MosError::decoding("ZRLE", "Insufficient data for palette size"));
        }
        let palette_size = data[*offset] as usize + 1;
        *offset += 1;

        // Read palette
        let mut palette = Vec::with_capacity(palette_size);
        for _ in 0..palette_size {
            let (cpixel, bytes_read) = Self::read_cpixel(data, *offset, cpixel_size)?;
            *offset += bytes_read;
            palette.push(Self::expand_cpixel(&cpixel, pixel_format));
        }

        // Read RLE-encoded palette indices
        let pixels_needed = tile_width as usize * tile_height as usize;
        let mut pixels = Vec::with_capacity(pixels_needed);

        while pixels.len() < pixels_needed {
            if *offset >= data.len() {
                return Err(MosError::decoding("ZRLE", "Insufficient data for palette RLE"));
            }

            let index_byte = data[*offset];
            *offset += 1;

            let index = (index_byte & 0x7F) as usize;
            if index >= palette.len() {
                return Err(MosError::decoding("ZRLE", "Palette index out of bounds"));
            }

            let run_length = if (index_byte & 0x80) != 0 {
                // Run length follows
                if *offset >= data.len() {
                    return Err(MosError::decoding("ZRLE", "Insufficient data for RLE run length"));
                }
                let run = data[*offset] as usize + 1;
                *offset += 1;
                run
            } else {
                1
            };

            for _ in 0..run_length {
                if pixels.len() >= pixels_needed {
                    break;
                }
                pixels.push(palette[index].clone());
            }
        }

        Ok(pixels)
    }

    /// Decode a single 64x64 tile
    fn decode_tile(
        &mut self,
        data: &[u8],
        offset: &mut usize,
        tile_x: u16,
        tile_y: u16,
        tile_width: u16,
        tile_height: u16,
        framebuffer: &mut [u8],
        fb_width: u16,
        pixel_format: &PixelFormat,
    ) -> MosResult<()> {
        // Read subencoding type
        if *offset >= data.len() {
            return Err(MosError::decoding("ZRLE", "No subencoding byte"));
        }
        let subencoding = data[*offset];
        *offset += 1;

        // CPIXEL size depends on pixel format
        let cpixel_size = if pixel_format.bits_per_pixel == 32 && pixel_format.depth <= 24 {
            3 // 24-bit true color uses 3-byte CPIXEL
        } else {
            pixel_format.bytes_per_pixel()
        };

        // Decode tile based on subencoding
        let tile_pixels = match subencoding {
            RAW_SUBENCODING => {
                self.decode_raw_tile(data, offset, tile_width, tile_height, cpixel_size, pixel_format)?
            }
            SOLID_SUBENCODING => {
                self.decode_solid_tile(data, offset, tile_width, tile_height, cpixel_size, pixel_format)?
            }
            PACKED_PALETTE_START..=PACKED_PALETTE_END => {
                let palette_size = subencoding as usize;
                self.decode_packed_palette_tile(data, offset, tile_width, tile_height, cpixel_size, pixel_format, palette_size)?
            }
            PLAIN_RLE => {
                self.decode_plain_rle_tile(data, offset, tile_width, tile_height, cpixel_size, pixel_format)?
            }
            PALETTE_RLE => {
                self.decode_palette_rle_tile(data, offset, tile_width, tile_height, cpixel_size, pixel_format)?
            }
            PACKED_PALETTE_RLE_START.. => {
                return Err(MosError::decoding("ZRLE",
                    format!("Reserved subencoding {} (types 130+ are reserved)", subencoding)));
            }
            _ => {
                return Err(MosError::decoding("ZRLE",
                    format!("Unknown subencoding type: {}", subencoding)));
            }
        };

        // Copy pixels to framebuffer
        let bytes_per_pixel = pixel_format.bytes_per_pixel();
        for (i, pixel) in tile_pixels.iter().enumerate() {
            let row = i / tile_width as usize;
            let col = i % tile_width as usize;
            let dst_y = tile_y as usize + row;
            let dst_x = tile_x as usize + col;
            let dst_offset = (dst_y * fb_width as usize + dst_x) * bytes_per_pixel;

            if dst_offset + bytes_per_pixel <= framebuffer.len() {
                framebuffer[dst_offset..dst_offset + bytes_per_pixel]
                    .copy_from_slice(&pixel[..bytes_per_pixel]);
            }
        }

        Ok(())
    }
}

impl Default for ZrleDecoder {
    fn default() -> Self {
        Self::new()
    }
}

impl Decoder for ZrleDecoder {
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
            return Err(MosError::decoding("ZRLE", "Insufficient data for length"));
        }
        let compressed_len = data.read_u32_be(0)? as usize;

        if 4 + compressed_len > data.len() {
            return Err(MosError::decoding("ZRLE", "Insufficient compressed data"));
        }

        // Decompress zlib stream
        let compressed_data = &data[4..4 + compressed_len];
        let mut decoder = ZlibDecoder::new(compressed_data);
        let mut decompressed = Vec::new();

        decoder
            .read_to_end(&mut decompressed)
            .map_err(|e| MosError::decoding("ZRLE", format!("Zlib decompression failed: {}", e)))?;

        // Process tiles (64x64)
        let mut offset = 0;
        let mut tile_y = 0;

        while tile_y < height {
            let mut tile_x = 0;
            while tile_x < width {
                let tile_width = TILE_SIZE.min(width - tile_x);
                let tile_height = TILE_SIZE.min(height - tile_y);

                self.decode_tile(
                    &decompressed,
                    &mut offset,
                    x + tile_x,
                    y + tile_y,
                    tile_width,
                    tile_height,
                    framebuffer,
                    fb_width,
                    pixel_format,
                )?;

                tile_x += TILE_SIZE;
            }
            tile_y += TILE_SIZE;
        }

        Ok(4 + compressed_len)
    }

    fn reset(&mut self) {
        // No state to reset
    }

    fn encoding_type(&self) -> EncodingType {
        EncodingType::Zrle
    }
}

#[cfg(test)]
mod tests;

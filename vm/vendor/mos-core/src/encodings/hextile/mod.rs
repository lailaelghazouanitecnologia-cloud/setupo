//! Hextile encoding decoder
//!
//! Hextile encoding divides a rectangle into 16x16 tiles and encodes
//! each tile separately with various optimization strategies.
//!
//! Encoding: 5
//!
//! Each tile has a subencoding byte that specifies how it's encoded:
//! - Bit 0 (Raw): Tile contains raw pixel data
//! - Bit 1 (BackgroundSpecified): New background color follows
//! - Bit 2 (ForegroundSpecified): New foreground color follows
//! - Bit 3 (AnySubrects): Tile contains subrectangles
//! - Bit 4 (SubrectsColoured): Each subrect has its own color

use crate::core::PixelFormat;
use crate::encodings::{Decoder, EncodingType};
use crate::utils::{MosError, MosResult};

const TILE_SIZE: u16 = 16;

// Subencoding mask bits
const RAW: u8 = 0x01;
const BACKGROUND_SPECIFIED: u8 = 0x02;
const FOREGROUND_SPECIFIED: u8 = 0x04;
const ANY_SUBRECTS: u8 = 0x08;
const SUBRECTS_COLOURED: u8 = 0x10;

/// Hextile encoding decoder
#[derive(Debug)]
pub struct HextileDecoder {
    background: Vec<u8>,
    foreground: Vec<u8>,
}

impl HextileDecoder {
    /// Create a new Hextile decoder
    pub fn new() -> Self {
        Self {
            background: vec![0; 4], // Default to 4 bytes per pixel
            foreground: vec![0; 4],
        }
    }

    /// Decode a single tile
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
        bytes_per_pixel: usize,
    ) -> MosResult<()> {
        // Read subencoding byte
        if *offset >= data.len() {
            return Err(MosError::decoding(
                "Hextile",
                "Insufficient data for subencoding",
            ));
        }
        let subencoding = data[*offset];
        *offset += 1;

        // Raw tile
        if subencoding & RAW != 0 {
            let tile_bytes =
                tile_width as usize * tile_height as usize * bytes_per_pixel;
            if *offset + tile_bytes > data.len() {
                return Err(MosError::decoding("Hextile", "Insufficient data for raw tile"));
            }

            // Copy raw pixel data
            for row in 0..tile_height {
                let src_offset =
                    *offset + (row as usize * tile_width as usize) * bytes_per_pixel;
                let dst_y = tile_y as usize + row as usize;
                let dst_offset =
                    (dst_y * fb_width as usize + tile_x as usize) * bytes_per_pixel;
                let row_bytes = tile_width as usize * bytes_per_pixel;

                framebuffer[dst_offset..dst_offset + row_bytes]
                    .copy_from_slice(&data[src_offset..src_offset + row_bytes]);
            }

            *offset += tile_bytes;
            return Ok(());
        }

        // Update background color
        if subencoding & BACKGROUND_SPECIFIED != 0 {
            if *offset + bytes_per_pixel > data.len() {
                return Err(MosError::decoding(
                    "Hextile",
                    "Insufficient data for background",
                ));
            }
            self.background[..bytes_per_pixel]
                .copy_from_slice(&data[*offset..*offset + bytes_per_pixel]);
            *offset += bytes_per_pixel;
        }

        // Fill tile with background color
        for row in 0..tile_height {
            for col in 0..tile_width {
                let dst_y = tile_y as usize + row as usize;
                let dst_x = tile_x as usize + col as usize;
                let dst_offset =
                    (dst_y * fb_width as usize + dst_x) * bytes_per_pixel;

                framebuffer[dst_offset..dst_offset + bytes_per_pixel]
                    .copy_from_slice(&self.background[..bytes_per_pixel]);
            }
        }

        // Update foreground color
        if subencoding & FOREGROUND_SPECIFIED != 0 {
            if *offset + bytes_per_pixel > data.len() {
                return Err(MosError::decoding(
                    "Hextile",
                    "Insufficient data for foreground",
                ));
            }
            self.foreground[..bytes_per_pixel]
                .copy_from_slice(&data[*offset..*offset + bytes_per_pixel]);
            *offset += bytes_per_pixel;
        }

        // Process subrectangles
        if subencoding & ANY_SUBRECTS != 0 {
            if *offset >= data.len() {
                return Err(MosError::decoding(
                    "Hextile",
                    "Insufficient data for subrect count",
                ));
            }
            let num_subrects = data[*offset] as usize;
            *offset += 1;

            let subrects_coloured = subencoding & SUBRECTS_COLOURED != 0;

            for _ in 0..num_subrects {
                // Read color if specified
                let color = if subrects_coloured {
                    if *offset + bytes_per_pixel > data.len() {
                        return Err(MosError::decoding(
                            "Hextile",
                            "Insufficient data for subrect color",
                        ));
                    }
                    let color = &data[*offset..*offset + bytes_per_pixel];
                    *offset += bytes_per_pixel;
                    color
                } else {
                    &self.foreground[..bytes_per_pixel]
                };

                // Read xy and wh
                if *offset + 2 > data.len() {
                    return Err(MosError::decoding(
                        "Hextile",
                        "Insufficient data for subrect geometry",
                    ));
                }
                let xy = data[*offset];
                let wh = data[*offset + 1];
                *offset += 2;

                let sub_x = (xy >> 4) as u16;
                let sub_y = (xy & 0x0F) as u16;
                let sub_width = ((wh >> 4) + 1) as u16;
                let sub_height = ((wh & 0x0F) + 1) as u16;

                // Draw subrectangle
                for row in 0..sub_height {
                    for col in 0..sub_width {
                        let dst_y = tile_y as usize + sub_y as usize + row as usize;
                        let dst_x = tile_x as usize + sub_x as usize + col as usize;
                        let dst_offset =
                            (dst_y * fb_width as usize + dst_x) * bytes_per_pixel;

                        if dst_offset + bytes_per_pixel <= framebuffer.len() {
                            framebuffer[dst_offset..dst_offset + bytes_per_pixel]
                                .copy_from_slice(color);
                        }
                    }
                }
            }
        }

        Ok(())
    }
}

impl Default for HextileDecoder {
    fn default() -> Self {
        Self::new()
    }
}

impl Decoder for HextileDecoder {
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

        // Ensure background/foreground buffers are sized correctly
        if self.background.len() < bytes_per_pixel {
            self.background.resize(bytes_per_pixel, 0);
        }
        if self.foreground.len() < bytes_per_pixel {
            self.foreground.resize(bytes_per_pixel, 0);
        }

        let mut offset = 0;

        // Process tiles
        let mut tile_y = 0;
        while tile_y < height {
            let mut tile_x = 0;
            while tile_x < width {
                let tile_width = TILE_SIZE.min(width - tile_x);
                let tile_height = TILE_SIZE.min(height - tile_y);

                self.decode_tile(
                    data,
                    &mut offset,
                    x + tile_x,
                    y + tile_y,
                    tile_width,
                    tile_height,
                    framebuffer,
                    fb_width,
                    bytes_per_pixel,
                )?;

                tile_x += TILE_SIZE;
            }
            tile_y += TILE_SIZE;
        }

        Ok(offset)
    }

    fn reset(&mut self) {
        self.background.fill(0);
        self.foreground.fill(0);
    }

    fn encoding_type(&self) -> EncodingType {
        EncodingType::Hextile
    }
}

#[cfg(test)]
mod tests;

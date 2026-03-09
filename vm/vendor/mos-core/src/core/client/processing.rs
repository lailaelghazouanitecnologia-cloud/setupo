//! Server message processing

use super::RfbClient;
use crate::core::constants;
use crate::encodings::EncodingType;
use crate::network::TcpConnection;
use crate::utils::{ByteOps, MosError, MosResult};

impl RfbClient {
    /// Process one server message
    pub async fn process_message(&mut self) -> MosResult<bool> {
        // Read message type
        let mut msg_type_buf = [0u8; 1];
        {
            let conn = self.conn.as_mut().ok_or_else(|| {
                MosError::state("Not connected")
            })?;
            conn.read_exact(&mut msg_type_buf).await?;
        }
        let msg_type = msg_type_buf[0];

        match msg_type {
            constants::server_msg::FRAMEBUFFER_UPDATE => {
                self.handle_framebuffer_update().await?;
                Ok(true)
            }
            constants::server_msg::SERVER_CUT_TEXT => {
                self.handle_server_cut_text().await?;
                Ok(false)
            }
            constants::server_msg::BELL => {
                tracing::info!("Server bell (beep)");
                Ok(false)
            }
            _ => {
                tracing::warn!("Unknown server message type: {}", msg_type);
                Ok(false)
            }
        }
    }

    /// Handle framebuffer update message
    async fn handle_framebuffer_update(&mut self) -> MosResult<()> {
        let conn = self.conn.as_mut().ok_or_else(|| {
            MosError::state("Not connected")
        })?;
        // Skip padding byte
        let mut padding = [0u8; 1];
        conn.read_exact(&mut padding).await?;

        // Read number of rectangles
        let mut count_buf = [0u8; 2];
        conn.read_exact(&mut count_buf).await?;
        let num_rectangles = u16::from_be_bytes(count_buf);

        tracing::debug!("Processing {} rectangles", num_rectangles);

        for _ in 0..num_rectangles {
            self.process_rectangle().await?;
        }

        Ok(())
    }

    /// Process a single rectangle
    async fn process_rectangle(&mut self) -> MosResult<()> {
        let conn = self.conn.as_mut().ok_or_else(|| {
            MosError::state("Not connected")
        })?;
        // Read rectangle header (12 bytes)
        let mut header = [0u8; 12];
        conn.read_exact(&mut header).await?;

        let x = header.read_u16_be(0)?;
        let y = header.read_u16_be(2)?;
        let width = header.read_u16_be(4)?;
        let height = header.read_u16_be(6)?;
        let encoding_type = header.read_i32_be(8)?;

        let encoding = EncodingType::from_i32(encoding_type).ok_or_else(|| {
            MosError::protocol(format!("Unknown encoding type: {}", encoding_type))
        })?;

        tracing::debug!(
            "Rectangle: {}x{} at ({},{}) encoding={:?}",
            width,
            height,
            x,
            y,
            encoding
        );

        // Handle pseudo-encodings separately
        if encoding.is_pseudo_encoding() {
            return self.handle_pseudo_encoding(encoding, x, y, width, height).await;
        }

        // Get decoder for standard encodings
        let decoder = self.decoders.get_mut(&encoding).ok_or_else(|| {
            MosError::decoding(encoding.name(), "Decoder not available")
        })?;

        // Read and decode based on encoding type
        let data = match encoding {
            EncodingType::Raw => {
                // Fixed size: width * height * bytes_per_pixel
                let bytes_needed =
                    width as usize * height as usize * self.pixel_format.bytes_per_pixel();
                let mut buf = vec![0u8; bytes_needed];
                conn.read_exact(&mut buf).await?;
                buf
            }
            EncodingType::CopyRect => {
                // Fixed size: 4 bytes (src-x, src-y)
                let mut buf = vec![0u8; 4];
                conn.read_exact(&mut buf).await?;
                buf
            }
            EncodingType::Rre => {
                // Variable size: read header first, then calculate total size
                let bytes_per_pixel = self.pixel_format.bytes_per_pixel();

                // Read subrect count (4 bytes) + background pixel
                let header_size = 4 + bytes_per_pixel;
                let mut buf = vec![0u8; header_size];
                conn.read_exact(&mut buf).await?;

                // Parse subrect count
                let num_subrects = buf.read_u32_be(0)? as usize;

                // Calculate remaining data size
                let subrect_size = bytes_per_pixel + 8; // pixel + x + y + w + h
                let remaining_size = num_subrects * subrect_size;

                // Read remaining data
                buf.reserve(remaining_size);
                buf.resize(header_size + remaining_size, 0);
                conn.read_exact(&mut buf[header_size..]).await?;

                buf
            }
            EncodingType::Hextile => {
                // Variable size: read tile by tile
                let bytes_per_pixel = self.pixel_format.bytes_per_pixel();
                Self::read_hextile_data(conn, width, height, bytes_per_pixel).await?
            }
            _ => {
                return Err(MosError::decoding(
                    encoding.name(),
                    "Encoding not yet implemented",
                ));
            }
        };

        // Decode into framebuffer
        decoder.decode(
            &data,
            x,
            y,
            width,
            height,
            &mut self.framebuffer,
            self.fb_width,
            &self.pixel_format,
        )?;

        Ok(())
    }

    /// Read Hextile encoding data tile by tile
    async fn read_hextile_data(
        conn: &mut TcpConnection,
        width: u16,
        height: u16,
        bytes_per_pixel: usize,
    ) -> MosResult<Vec<u8>> {
        const TILE_SIZE: u16 = 16;
        const RAW: u8 = 0x01;
        const BACKGROUND_SPECIFIED: u8 = 0x02;
        const FOREGROUND_SPECIFIED: u8 = 0x04;
        const ANY_SUBRECTS: u8 = 0x08;
        const SUBRECTS_COLOURED: u8 = 0x10;
        let mut buf = Vec::new();

        // Process tiles
        let mut tile_y = 0;
        while tile_y < height {
            let mut tile_x = 0;
            while tile_x < width {
                let tile_width = TILE_SIZE.min(width - tile_x);
                let tile_height = TILE_SIZE.min(height - tile_y);

                // Read subencoding byte
                let mut subencoding = [0u8; 1];
                conn.read_exact(&mut subencoding).await?;
                buf.push(subencoding[0]);

                // Raw tile
                if subencoding[0] & RAW != 0 {
                    let tile_bytes =
                        tile_width as usize * tile_height as usize * bytes_per_pixel;
                    let start = buf.len();
                    buf.resize(start + tile_bytes, 0);
                    conn.read_exact(&mut buf[start..]).await?;
                    tile_x += TILE_SIZE;
                    continue;
                }

                // Background
                if subencoding[0] & BACKGROUND_SPECIFIED != 0 {
                    let start = buf.len();
                    buf.resize(start + bytes_per_pixel, 0);
                    conn.read_exact(&mut buf[start..]).await?;
                }

                // Foreground
                if subencoding[0] & FOREGROUND_SPECIFIED != 0 {
                    let start = buf.len();
                    buf.resize(start + bytes_per_pixel, 0);
                    conn.read_exact(&mut buf[start..]).await?;
                }

                // Subrectangles
                if subencoding[0] & ANY_SUBRECTS != 0 {
                    let mut num_subrects = [0u8; 1];
                    conn.read_exact(&mut num_subrects).await?;
                    buf.push(num_subrects[0]);

                    let subrects_coloured = subencoding[0] & SUBRECTS_COLOURED != 0;

                    for _ in 0..num_subrects[0] {
                        // Color if specified
                        if subrects_coloured {
                            let start = buf.len();
                            buf.resize(start + bytes_per_pixel, 0);
                            conn.read_exact(&mut buf[start..]).await?;
                        }

                        // xy and wh (2 bytes)
                        let start = buf.len();
                        buf.resize(start + 2, 0);
                        conn.read_exact(&mut buf[start..]).await?;
                    }
                }

                tile_x += TILE_SIZE;
            }
            tile_y += TILE_SIZE;
        }

        Ok(buf)
    }

    /// Handle pseudo-encodings (Cursor, DesktopSize, etc.)
    async fn handle_pseudo_encoding(
        &mut self,
        encoding: EncodingType,
        x: u16,
        y: u16,
        width: u16,
        height: u16,
    ) -> MosResult<()> {
        let conn = self.conn.as_mut().ok_or_else(|| {
            MosError::state("Not connected")
        })?;

        match encoding {
            EncodingType::Cursor => {
                // Cursor pseudo-encoding: x,y = hotspot, width/height = cursor size
                tracing::debug!("Cursor update: {}x{} hotspot=({},{})", width, height, x, y);

                let bytes_per_pixel = self.pixel_format.bytes_per_pixel();

                // Read cursor pixels
                let pixel_data_size = width as usize * height as usize * bytes_per_pixel;
                let mut pixels = vec![0u8; pixel_data_size];
                conn.read_exact(&mut pixels).await?;

                // Read bitmask (1 bit per pixel, padded to whole bytes per scan line)
                let bytes_per_row = (width as usize + 7) / 8;
                let mask_size = bytes_per_row * height as usize;
                let mut mask = vec![0u8; mask_size];
                conn.read_exact(&mut mask).await?;

                // Store cursor shape
                self.cursor = Some(super::CursorShape {
                    width,
                    height,
                    hotspot_x: x,
                    hotspot_y: y,
                    pixels,
                    mask,
                });

                tracing::info!("Cursor shape updated: {}x{}", width, height);
                Ok(())
            }
            EncodingType::DesktopSize => {
                // DesktopSize pseudo-encoding: width/height = new framebuffer size
                tracing::info!("Desktop resize: {}x{}", width, height);

                // Resize framebuffer
                self.fb_width = width;
                self.fb_height = height;

                let fb_size = (width as usize) * (height as usize) * self.pixel_format.bytes_per_pixel();
                self.framebuffer.resize(fb_size, 0);

                tracing::info!("Framebuffer resized to {}x{}", width, height);
                Ok(())
            }
            _ => {
                Err(MosError::protocol(format!(
                    "Unhandled pseudo-encoding: {:?}",
                    encoding
                )))
            }
        }
    }

    /// Handle ServerCutText message (clipboard sync from server)
    async fn handle_server_cut_text(&mut self) -> MosResult<()> {
        let conn = self.conn.as_mut().ok_or_else(|| {
            MosError::state("Not connected")
        })?;

        // Read padding (3 bytes)
        let mut padding = [0u8; 3];
        conn.read_exact(&mut padding).await?;

        // Read text length (4 bytes, big-endian)
        let mut len_buf = [0u8; 4];
        conn.read_exact(&mut len_buf).await?;
        let text_len = u32::from_be_bytes(len_buf) as usize;

        // Read text
        let mut text_buf = vec![0u8; text_len];
        conn.read_exact(&mut text_buf).await?;

        // Convert to UTF-8 string (VNC uses ISO 8859-1/Latin-1, but UTF-8 is common)
        let text = String::from_utf8_lossy(&text_buf).to_string();

        tracing::info!("Server clipboard update: {} bytes", text_len);
        tracing::debug!("Clipboard text: {}", text);

        // Store clipboard
        self.clipboard = Some(text);

        Ok(())
    }
}

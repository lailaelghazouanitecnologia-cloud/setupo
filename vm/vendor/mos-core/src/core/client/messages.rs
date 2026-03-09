//! Client message sending methods

use super::RfbClient;
use crate::core::{protocol, types::PixelFormat};
use crate::network::TcpConnection;
use crate::utils::{MosError, MosResult};

impl RfbClient {
    /// Send SetEncodings message
    pub(super) async fn send_set_encodings(
        &self,
        conn: &mut TcpConnection,
        encodings: &[i32],
    ) -> MosResult<()> {
        let mut buf = Vec::new();
        protocol::messages::write_set_encodings(&mut buf, encodings);
        conn.write_all(&buf).await?;
        conn.flush().await?;
        Ok(())
    }

    /// Send SetPixelFormat message
    pub(super) async fn send_set_pixel_format(
        &self,
        conn: &mut TcpConnection,
        pixel_format: &PixelFormat,
    ) -> MosResult<()> {
        let mut buf = Vec::new();
        protocol::messages::write_set_pixel_format(&mut buf, pixel_format);
        conn.write_all(&buf).await?;
        conn.flush().await?;
        Ok(())
    }

    /// Request framebuffer update
    pub async fn request_update(
        &mut self,
        incremental: bool,
        x: u16,
        y: u16,
        width: u16,
        height: u16,
    ) -> MosResult<()> {
        let conn = self.conn.as_mut().ok_or_else(|| {
            MosError::state("Not connected")
        })?;

        let mut buf = Vec::new();
        protocol::messages::write_framebuffer_update_request(
            &mut buf,
            incremental,
            x,
            y,
            width,
            height,
        );
        conn.write_all(&buf).await?;
        conn.flush().await?;
        Ok(())
    }

    /// Send key event
    pub async fn send_key_event(&mut self, down: bool, key: u32) -> MosResult<()> {
        let conn = self.conn.as_mut().ok_or_else(|| {
            MosError::state("Not connected")
        })?;

        let mut buf = Vec::new();
        protocol::messages::write_key_event(&mut buf, down, key);
        conn.write_all(&buf).await?;
        conn.flush().await?;
        Ok(())
    }

    /// Send pointer event
    pub async fn send_pointer_event(
        &mut self,
        button_mask: u8,
        x: u16,
        y: u16,
    ) -> MosResult<()> {
        let conn = self.conn.as_mut().ok_or_else(|| {
            MosError::state("Not connected")
        })?;

        let mut buf = Vec::new();
        protocol::messages::write_pointer_event(&mut buf, button_mask, x, y);
        conn.write_all(&buf).await?;
        conn.flush().await?;
        Ok(())
    }

    /// Send client cut text (clipboard)
    pub async fn send_clipboard_text(&mut self, text: &str) -> MosResult<()> {
        let conn = self.conn.as_mut().ok_or_else(|| {
            MosError::state("Not connected")
        })?;

        let mut buf = Vec::new();
        protocol::messages::write_client_cut_text(&mut buf, text);
        conn.write_all(&buf).await?;
        conn.flush().await?;

        tracing::debug!("Sent clipboard text: {} bytes", text.len());
        Ok(())
    }
}

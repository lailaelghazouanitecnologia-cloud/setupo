//! RFB Client - Main VNC client implementation
//!
//! Integrates all components: network, protocol, auth, decoders.

mod types;
mod connection;
mod messages;
mod processing;

pub use types::{ClientState, CursorShape, Rectangle};

use crate::core::config::ConnectionConfig;
use crate::core::protocol::ServerInit;
use crate::core::types::PixelFormat;
use crate::encodings::{
    CopyRectDecoder, Decoder, EncodingType, HextileDecoder, JpegEncodingDecoder, RawDecoder,
    RreDecoder, TightDecoder, ZlibDecoder, ZrleDecoder,
};
use crate::network::TcpConnection;
use std::collections::HashMap;

/// RFB Client
pub struct RfbClient {
    pub(super) config: ConnectionConfig,
    pub(super) conn: Option<TcpConnection>,
    pub(super) state: ClientState,
    pub(super) server_init: Option<ServerInit>,
    pub(super) framebuffer: Vec<u8>,
    pub(super) fb_width: u16,
    pub(super) fb_height: u16,
    pub(super) pixel_format: PixelFormat,
    pub(super) decoders: HashMap<EncodingType, Box<dyn Decoder>>,
    pub(super) cursor: Option<CursorShape>,
    pub(super) clipboard: Option<String>,
}

impl RfbClient {
    /// Create a new RFB client
    pub fn new(config: ConnectionConfig) -> Self {
        // Create decoders
        let mut decoders: HashMap<EncodingType, Box<dyn Decoder>> = HashMap::new();
        decoders.insert(EncodingType::Raw, Box::new(RawDecoder::new()));
        decoders.insert(EncodingType::CopyRect, Box::new(CopyRectDecoder::new()));
        decoders.insert(EncodingType::Rre, Box::new(RreDecoder::new()));
        decoders.insert(EncodingType::Hextile, Box::new(HextileDecoder::new()));
        decoders.insert(EncodingType::Tight, Box::new(TightDecoder::new()));
        decoders.insert(EncodingType::Zlib, Box::new(ZlibDecoder::new()));
        decoders.insert(EncodingType::Zrle, Box::new(ZrleDecoder::new()));
        decoders.insert(EncodingType::Jpeg, Box::new(JpegEncodingDecoder::new()));

        Self {
            config,
            conn: None,
            state: ClientState::Disconnected,
            server_init: None,
            framebuffer: Vec::new(),
            fb_width: 0,
            fb_height: 0,
            pixel_format: PixelFormat::default(),
            decoders,
            cursor: None,
            clipboard: None,
        }
    }

    /// Get current client state
    pub fn state(&self) -> ClientState {
        self.state
    }

    /// Get framebuffer dimensions
    pub fn framebuffer_size(&self) -> (u16, u16) {
        (self.fb_width, self.fb_height)
    }

    /// Get framebuffer data
    pub fn framebuffer(&self) -> &[u8] {
        &self.framebuffer
    }

    /// Get server information
    pub fn server_info(&self) -> Option<&ServerInit> {
        self.server_init.as_ref()
    }

    /// Get current cursor shape (if server sent one)
    pub fn cursor(&self) -> Option<&CursorShape> {
        self.cursor.as_ref()
    }

    /// Get current clipboard text (if server sent one)
    pub fn clipboard(&self) -> Option<&str> {
        self.clipboard.as_deref()
    }
}

impl Drop for RfbClient {
    fn drop(&mut self) {
        // Connection cleanup handled by TcpConnection drop
    }
}

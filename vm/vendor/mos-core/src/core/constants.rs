//! RFB protocol constants

/// Protocol version strings
pub const RFB_VERSION_33: &str = "RFB 003.003\n";
pub const RFB_VERSION_37: &str = "RFB 003.007\n";
pub const RFB_VERSION_38: &str = "RFB 003.008\n";

/// Version string length (12 bytes including \n)
pub const VERSION_STRING_LENGTH: usize = 12;

/// Client-to-server message types
pub mod client_msg {
    pub const SET_PIXEL_FORMAT: u8 = 0;
    pub const SET_ENCODINGS: u8 = 2;
    pub const FRAMEBUFFER_UPDATE_REQUEST: u8 = 3;
    pub const KEY_EVENT: u8 = 4;
    pub const POINTER_EVENT: u8 = 5;
    pub const CLIENT_CUT_TEXT: u8 = 6;

    // Extended messages
    pub const ENABLE_CONTINUOUS_UPDATES: u8 = 150;
    pub const CLIENT_FENCE: u8 = 248;
    pub const SET_DESKTOP_SIZE: u8 = 251;
    pub const QEMU_CLIENT_MESSAGE: u8 = 255;
}

/// Server-to-client message types
pub mod server_msg {
    pub const FRAMEBUFFER_UPDATE: u8 = 0;
    pub const SET_COLOUR_MAP_ENTRIES: u8 = 1;
    pub const BELL: u8 = 2;
    pub const SERVER_CUT_TEXT: u8 = 3;

    // Extended messages
    pub const END_OF_CONTINUOUS_UPDATES: u8 = 150;
    pub const SERVER_FENCE: u8 = 248;
    pub const XVP_SERVER_MESSAGE: u8 = 250;
    pub const QEMU_SERVER_MESSAGE: u8 = 255;
}

/// Encoding types
pub mod encoding {
    pub const RAW: i32 = 0;
    pub const COPY_RECT: i32 = 1;
    pub const RRE: i32 = 2;
    pub const HEXTILE: i32 = 5;
    pub const ZLIB: i32 = 6;
    pub const TIGHT: i32 = 7;
    pub const ZLIBHEX: i32 = 8;
    pub const TRLE: i32 = 15;
    pub const ZRLE: i32 = 16;
    pub const HITACHI_ZYWRLE: i32 = 17;
    pub const JPEG: i32 = 21;
    pub const JRLE: i32 = 22;
    pub const H264: i32 = 50;
}

/// Pseudo-encodings
pub mod pseudo_encoding {
    pub const CURSOR: i32 = -239;
    pub const DESKTOP_SIZE: i32 = -223;
    pub const LAST_RECT: i32 = -224;
    pub const POINTER_POS: i32 = -232;
    pub const DESKTOP_NAME: i32 = -307;
    pub const EXTENDED_DESKTOP_SIZE: i32 = -308;
    pub const XVP: i32 = -309;

    // Quality levels (JPEG)
    pub const QUALITY_LEVEL_0: i32 = -32;
    pub const QUALITY_LEVEL_9: i32 = -23;

    // Compression levels
    pub const COMPRESS_LEVEL_0: i32 = -256;
    pub const COMPRESS_LEVEL_9: i32 = -247;

    // Extended features
    pub const QEMU_EXTENDED_KEY_EVENT: i32 = -258;
    pub const EXTENDED_CLIPBOARD: i32 = -1063131698;
    pub const CONTINUOUS_UPDATES: i32 = -313;
    pub const VMWARE_CURSOR: i32 = 0x574d5664; // "WMVd"
    pub const VMWARE_CURSOR_STATE: i32 = 0x574d5663; // "WMVc"
    pub const VMWARE_CURSOR_POSITION: i32 = 0x574d5668; // "WMVh"
}

/// Security result codes
pub mod security_result {
    pub const OK: u32 = 0;
    pub const FAILED: u32 = 1;
}

/// Key event constants
pub mod key {
    pub const DOWN: u8 = 1;
    pub const UP: u8 = 0;
}

/// Mouse button masks
pub mod mouse {
    pub const BUTTON1: u8 = 1 << 0; // Left
    pub const BUTTON2: u8 = 1 << 1; // Middle
    pub const BUTTON3: u8 = 1 << 2; // Right
    pub const BUTTON4: u8 = 1 << 3; // Scroll up
    pub const BUTTON5: u8 = 1 << 4; // Scroll down
    pub const BUTTON6: u8 = 1 << 5; // Scroll left
    pub const BUTTON7: u8 = 1 << 6; // Scroll right
    pub const BUTTON8: u8 = 1 << 7; // Extended
}

/// Buffer sizes
pub const DEFAULT_FRAMEBUFFER_SIZE: usize = 1920 * 1080 * 4; // Full HD RGBA
pub const MAX_MESSAGE_SIZE: usize = 64 * 1024 * 1024; // 64 MB

/// Timeouts (in milliseconds)
pub const HANDSHAKE_TIMEOUT_MS: u64 = 10_000;
pub const AUTH_TIMEOUT_MS: u64 = 30_000;
pub const MESSAGE_TIMEOUT_MS: u64 = 60_000;

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_constants() {
        assert_eq!(VERSION_STRING_LENGTH, 12);
        assert_eq!(client_msg::SET_PIXEL_FORMAT, 0);
        assert_eq!(server_msg::FRAMEBUFFER_UPDATE, 0);
        assert_eq!(encoding::RAW, 0);
        assert_eq!(pseudo_encoding::CURSOR, -239);
    }

    #[test]
    fn test_mouse_buttons() {
        assert_eq!(mouse::BUTTON1, 0b0000_0001);
        assert_eq!(mouse::BUTTON2, 0b0000_0010);
        assert_eq!(mouse::BUTTON3, 0b0000_0100);
    }
}

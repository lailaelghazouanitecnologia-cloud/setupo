//! RFB protocol message builders
//!
//! Functions for constructing client-to-server messages.

use crate::core::constants::client_msg;
use crate::core::types::PixelFormat;
use crate::utils::ByteWriter;

/// Write ClientInit message
pub fn write_client_init(buf: &mut Vec<u8>, shared: bool) {
    buf.write_u8(if shared { 1 } else { 0 });
}

/// Write SetPixelFormat message
pub fn write_set_pixel_format(buf: &mut Vec<u8>, pf: &PixelFormat) {
    buf.write_u8(client_msg::SET_PIXEL_FORMAT);
    buf.write_bytes(&[0, 0, 0]); // Padding

    buf.write_u8(pf.bits_per_pixel);
    buf.write_u8(pf.depth);
    buf.write_u8(if pf.big_endian { 1 } else { 0 });
    buf.write_u8(if pf.true_color { 1 } else { 0 });
    buf.write_u16_be(pf.red_max);
    buf.write_u16_be(pf.green_max);
    buf.write_u16_be(pf.blue_max);
    buf.write_u8(pf.red_shift);
    buf.write_u8(pf.green_shift);
    buf.write_u8(pf.blue_shift);
    buf.write_bytes(&[0, 0, 0]); // Padding
}

/// Write SetEncodings message
pub fn write_set_encodings(buf: &mut Vec<u8>, encodings: &[i32]) {
    buf.write_u8(client_msg::SET_ENCODINGS);
    buf.write_u8(0); // Padding

    buf.write_u16_be(encodings.len() as u16);
    for &encoding in encodings {
        buf.write_i32_be(encoding);
    }
}

/// Write FramebufferUpdateRequest message
pub fn write_framebuffer_update_request(
    buf: &mut Vec<u8>,
    incremental: bool,
    x: u16,
    y: u16,
    width: u16,
    height: u16,
) {
    buf.write_u8(client_msg::FRAMEBUFFER_UPDATE_REQUEST);
    buf.write_u8(if incremental { 1 } else { 0 });
    buf.write_u16_be(x);
    buf.write_u16_be(y);
    buf.write_u16_be(width);
    buf.write_u16_be(height);
}

/// Write KeyEvent message
pub fn write_key_event(buf: &mut Vec<u8>, down: bool, key: u32) {
    buf.write_u8(client_msg::KEY_EVENT);
    buf.write_u8(if down { 1 } else { 0 });
    buf.write_u16_be(0); // Padding
    buf.write_u32_be(key);
}

/// Write PointerEvent message
pub fn write_pointer_event(buf: &mut Vec<u8>, button_mask: u8, x: u16, y: u16) {
    buf.write_u8(client_msg::POINTER_EVENT);
    buf.write_u8(button_mask);
    buf.write_u16_be(x);
    buf.write_u16_be(y);
}

/// Write ClientCutText message
pub fn write_client_cut_text(buf: &mut Vec<u8>, text: &str) {
    buf.write_u8(client_msg::CLIENT_CUT_TEXT);
    buf.write_bytes(&[0, 0, 0]); // Padding
    buf.write_u32_be(text.len() as u32);
    buf.write_string(text);
}

/// Read message type from buffer
pub fn read_message_type(buf: &[u8]) -> Option<u8> {
    buf.first().copied()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_write_client_init() {
        let mut buf = Vec::new();
        write_client_init(&mut buf, true);
        assert_eq!(buf, vec![1]);

        let mut buf = Vec::new();
        write_client_init(&mut buf, false);
        assert_eq!(buf, vec![0]);
    }

    #[test]
    fn test_write_set_encodings() {
        let mut buf = Vec::new();
        let encodings = vec![0, 1, 2];
        write_set_encodings(&mut buf, &encodings);

        assert_eq!(buf[0], client_msg::SET_ENCODINGS);
        assert_eq!(buf[1], 0); // Padding
        // Count should be 3
        assert_eq!(u16::from_be_bytes([buf[2], buf[3]]), 3);
    }

    #[test]
    fn test_write_framebuffer_update_request() {
        let mut buf = Vec::new();
        write_framebuffer_update_request(&mut buf, true, 0, 0, 800, 600);

        assert_eq!(buf[0], client_msg::FRAMEBUFFER_UPDATE_REQUEST);
        assert_eq!(buf[1], 1); // Incremental
    }

    #[test]
    fn test_write_key_event() {
        let mut buf = Vec::new();
        write_key_event(&mut buf, true, 0x41); // 'A' key down

        assert_eq!(buf[0], client_msg::KEY_EVENT);
        assert_eq!(buf[1], 1); // Down
    }

    #[test]
    fn test_write_pointer_event() {
        let mut buf = Vec::new();
        write_pointer_event(&mut buf, 0b001, 100, 200); // Button 1 pressed

        assert_eq!(buf[0], client_msg::POINTER_EVENT);
        assert_eq!(buf[1], 0b001); // Button mask
    }

    #[test]
    fn test_read_message_type() {
        let buf = vec![0, 1, 2, 3];
        assert_eq!(read_message_type(&buf), Some(0));

        let empty: Vec<u8> = vec![];
        assert_eq!(read_message_type(&empty), None);
    }
}

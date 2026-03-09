//! Byte manipulation utilities
//!
//! Provides helpers for reading and writing binary data in network byte order.

use crate::utils::error::{MosError, MosResult};

/// Trait for byte operations on slices
pub trait ByteOps {
    /// Read a u8 from the current position
    fn read_u8(&self, offset: usize) -> MosResult<u8>;

    /// Read a u16 in big-endian (network byte order)
    fn read_u16_be(&self, offset: usize) -> MosResult<u16>;

    /// Read a u32 in big-endian
    fn read_u32_be(&self, offset: usize) -> MosResult<u32>;

    /// Read a i32 in big-endian
    fn read_i32_be(&self, offset: usize) -> MosResult<i32>;

    /// Read bytes into a buffer
    fn read_bytes(&self, offset: usize, len: usize) -> MosResult<&[u8]>;

    /// Read a string of given length
    fn read_string(&self, offset: usize, len: usize) -> MosResult<String>;
}

impl ByteOps for [u8] {
    fn read_u8(&self, offset: usize) -> MosResult<u8> {
        self.get(offset)
            .copied()
            .ok_or_else(|| MosError::buffer("read_u8: offset out of bounds"))
    }

    fn read_u16_be(&self, offset: usize) -> MosResult<u16> {
        let bytes = self
            .get(offset..offset + 2)
            .ok_or_else(|| MosError::buffer("read_u16_be: offset out of bounds"))?;
        Ok(u16::from_be_bytes([bytes[0], bytes[1]]))
    }

    fn read_u32_be(&self, offset: usize) -> MosResult<u32> {
        let bytes = self
            .get(offset..offset + 4)
            .ok_or_else(|| MosError::buffer("read_u32_be: offset out of bounds"))?;
        Ok(u32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
    }

    fn read_i32_be(&self, offset: usize) -> MosResult<i32> {
        let bytes = self
            .get(offset..offset + 4)
            .ok_or_else(|| MosError::buffer("read_i32_be: offset out of bounds"))?;
        Ok(i32::from_be_bytes([bytes[0], bytes[1], bytes[2], bytes[3]]))
    }

    fn read_bytes(&self, offset: usize, len: usize) -> MosResult<&[u8]> {
        self.get(offset..offset + len)
            .ok_or_else(|| MosError::buffer("read_bytes: offset or length out of bounds"))
    }

    fn read_string(&self, offset: usize, len: usize) -> MosResult<String> {
        let bytes = self.read_bytes(offset, len)?;
        String::from_utf8(bytes.to_vec())
            .map_err(|e| MosError::protocol(format!("Invalid UTF-8: {}", e)))
    }
}

/// Trait for writing bytes
pub trait ByteWriter {
    /// Write a u8
    fn write_u8(&mut self, value: u8);

    /// Write a u16 in big-endian
    fn write_u16_be(&mut self, value: u16);

    /// Write a u32 in big-endian
    fn write_u32_be(&mut self, value: u32);

    /// Write a i32 in big-endian
    fn write_i32_be(&mut self, value: i32);

    /// Write bytes
    fn write_bytes(&mut self, bytes: &[u8]);

    /// Write a string (without length prefix)
    fn write_string(&mut self, s: &str);
}

impl ByteWriter for Vec<u8> {
    fn write_u8(&mut self, value: u8) {
        self.push(value);
    }

    fn write_u16_be(&mut self, value: u16) {
        self.extend_from_slice(&value.to_be_bytes());
    }

    fn write_u32_be(&mut self, value: u32) {
        self.extend_from_slice(&value.to_be_bytes());
    }

    fn write_i32_be(&mut self, value: i32) {
        self.extend_from_slice(&value.to_be_bytes());
    }

    fn write_bytes(&mut self, bytes: &[u8]) {
        self.extend_from_slice(bytes);
    }

    fn write_string(&mut self, s: &str) {
        self.extend_from_slice(s.as_bytes());
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_read_u8() {
        let data = vec![0x42, 0xFF];
        assert_eq!(data.read_u8(0).unwrap(), 0x42);
        assert_eq!(data.read_u8(1).unwrap(), 0xFF);
        assert!(data.read_u8(2).is_err());
    }

    #[test]
    fn test_read_u16_be() {
        let data = vec![0x12, 0x34, 0x56, 0x78];
        assert_eq!(data.read_u16_be(0).unwrap(), 0x1234);
        assert_eq!(data.read_u16_be(2).unwrap(), 0x5678);
        assert!(data.read_u16_be(3).is_err());
    }

    #[test]
    fn test_read_u32_be() {
        let data = vec![0x12, 0x34, 0x56, 0x78];
        assert_eq!(data.read_u32_be(0).unwrap(), 0x12345678);
        assert!(data.read_u32_be(1).is_err());
    }

    #[test]
    fn test_read_string() {
        let data = b"Hello, World!";
        assert_eq!(data.read_string(0, 5).unwrap(), "Hello");
        assert_eq!(data.read_string(7, 6).unwrap(), "World!");
    }

    #[test]
    fn test_write_operations() {
        let mut buf = Vec::new();
        buf.write_u8(0x42);
        buf.write_u16_be(0x1234);
        buf.write_u32_be(0x56789ABC);
        buf.write_string("test");

        assert_eq!(buf[0], 0x42);
        assert_eq!(&buf[1..3], &[0x12, 0x34]);
        assert_eq!(&buf[3..7], &[0x56, 0x78, 0x9A, 0xBC]);
        assert_eq!(&buf[7..11], b"test");
    }
}

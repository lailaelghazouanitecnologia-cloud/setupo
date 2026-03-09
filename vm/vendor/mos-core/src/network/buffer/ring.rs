//! Ring buffer implementation for efficient network I/O
//!
//! Provides a circular buffer that minimizes allocations and copies.

use super::Buffer;
use crate::utils::{MosError, MosResult};

/// Ring buffer for network data
pub struct RingBuffer {
    data: Vec<u8>,
    read_pos: usize,
    write_pos: usize,
    size: usize,
}

impl RingBuffer {
    /// Create a new ring buffer with given capacity
    pub fn new(capacity: usize) -> Self {
        Self {
            data: vec![0; capacity],
            read_pos: 0,
            write_pos: 0,
            size: 0,
        }
    }

    /// Get buffer capacity
    pub fn capacity(&self) -> usize {
        self.data.len()
    }

    /// Check if buffer is empty
    pub fn is_empty(&self) -> bool {
        self.size == 0
    }

    /// Check if buffer is full
    pub fn is_full(&self) -> bool {
        self.size == self.data.len()
    }

    /// Compact the buffer (move data to beginning)
    pub fn compact(&mut self) {
        if self.read_pos == 0 {
            return; // Already compact
        }

        self.data.copy_within(self.read_pos..self.read_pos + self.size, 0);
        self.read_pos = 0;
        self.write_pos = self.size;
    }
}

impl Buffer for RingBuffer {
    fn available(&self) -> usize {
        self.size
    }

    fn remaining(&self) -> usize {
        self.data.len() - self.size
    }

    fn read_bytes(&mut self, buf: &mut [u8]) -> MosResult<usize> {
        let to_read = buf.len().min(self.size);
        if to_read == 0 {
            return Ok(0);
        }

        buf[..to_read].copy_from_slice(&self.data[self.read_pos..self.read_pos + to_read]);
        self.read_pos += to_read;
        self.size -= to_read;

        // Reset positions if buffer is empty
        if self.size == 0 {
            self.read_pos = 0;
            self.write_pos = 0;
        }

        Ok(to_read)
    }

    fn write_bytes(&mut self, buf: &[u8]) -> MosResult<usize> {
        let available_space = self.remaining();
        if available_space == 0 {
            return Err(MosError::buffer("ring buffer full"));
        }

        // Compact if needed
        if self.write_pos + buf.len() > self.data.len() && available_space >= buf.len() {
            self.compact();
        }

        let to_write = buf.len().min(available_space);
        self.data[self.write_pos..self.write_pos + to_write].copy_from_slice(&buf[..to_write]);
        self.write_pos += to_write;
        self.size += to_write;

        Ok(to_write)
    }

    fn peek_bytes(&self, len: usize) -> MosResult<&[u8]> {
        if len > self.size {
            return Err(MosError::buffer("not enough data in buffer"));
        }
        Ok(&self.data[self.read_pos..self.read_pos + len])
    }

    fn consume(&mut self, len: usize) -> MosResult<()> {
        if len > self.size {
            return Err(MosError::buffer("cannot consume more than available"));
        }

        self.read_pos += len;
        self.size -= len;

        if self.size == 0 {
            self.read_pos = 0;
            self.write_pos = 0;
        }

        Ok(())
    }

    fn clear(&mut self) {
        self.read_pos = 0;
        self.write_pos = 0;
        self.size = 0;
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_ring_buffer_basic() {
        let mut buf = RingBuffer::new(16);
        assert_eq!(buf.capacity(), 16);
        assert_eq!(buf.available(), 0);
        assert_eq!(buf.remaining(), 16);
        assert!(buf.is_empty());

        // Write some data
        let data = b"Hello";
        assert_eq!(buf.write_bytes(data).unwrap(), 5);
        assert_eq!(buf.available(), 5);
        assert_eq!(buf.remaining(), 11);

        // Read back
        let mut read_buf = vec![0u8; 5];
        assert_eq!(buf.read_bytes(&mut read_buf).unwrap(), 5);
        assert_eq!(&read_buf, b"Hello");
        assert!(buf.is_empty());
    }

    #[test]
    fn test_ring_buffer_wrap() {
        let mut buf = RingBuffer::new(8);

        // Fill buffer
        buf.write_bytes(b"12345678").unwrap();
        assert!(buf.is_full());

        // Read some
        let mut read_buf = vec![0u8; 4];
        buf.read_bytes(&mut read_buf).unwrap();
        assert_eq!(&read_buf, b"1234");

        // Write more (should wrap)
        buf.write_bytes(b"ABCD").unwrap();
        assert_eq!(buf.available(), 8);
    }

    #[test]
    fn test_peek_and_consume() {
        let mut buf = RingBuffer::new(16);
        buf.write_bytes(b"Hello, World!").unwrap();

        let peeked = buf.peek_bytes(5).unwrap();
        assert_eq!(peeked, b"Hello");
        assert_eq!(buf.available(), 13); // Still there

        buf.consume(7).unwrap(); // Consume "Hello, "
        let peeked = buf.peek_bytes(6).unwrap();
        assert_eq!(peeked, b"World!");
    }
}

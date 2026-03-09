//! Network buffer implementations

mod ring;
pub use ring::RingBuffer;

use crate::utils::MosResult;

/// Trait for buffer operations
pub trait Buffer {
    /// Available bytes to read
    fn available(&self) -> usize;

    /// Remaining space for writing
    fn remaining(&self) -> usize;

    /// Read bytes into a slice
    fn read_bytes(&mut self, buf: &mut [u8]) -> MosResult<usize>;

    /// Write bytes from a slice
    fn write_bytes(&mut self, buf: &[u8]) -> MosResult<usize>;

    /// Peek at bytes without consuming
    fn peek_bytes(&self, len: usize) -> MosResult<&[u8]>;

    /// Consume bytes without reading
    fn consume(&mut self, len: usize) -> MosResult<()>;

    /// Clear the buffer
    fn clear(&mut self);
}

//! TCP connection wrapper with buffering

use crate::network::buffer::{Buffer, RingBuffer};
use crate::network::types::NetworkConfig;
use crate::utils::{MosError, MosResult};
use tokio::io::{AsyncReadExt, AsyncWriteExt};
use tokio::net::TcpStream;

/// TCP connection with buffering
pub struct TcpConnection {
    stream: TcpStream,
    recv_buffer: RingBuffer,
    send_buffer: RingBuffer,
    config: NetworkConfig,
}

impl TcpConnection {
    /// Create a new TCP connection from a stream
    pub fn new(stream: TcpStream) -> Self {
        Self::with_config(stream, NetworkConfig::default())
    }

    /// Create a new TCP connection with custom config
    pub fn with_config(stream: TcpStream, config: NetworkConfig) -> Self {
        Self {
            stream,
            recv_buffer: RingBuffer::new(config.recv_buffer_size),
            send_buffer: RingBuffer::new(config.send_buffer_size),
            config,
        }
    }

    /// Connect to a server and create a new TCP connection
    pub async fn connect(
        host: &str,
        port: u16,
        config: NetworkConfig,
    ) -> MosResult<Self> {
        let addr = format!("{}:{}", host, port);

        // Apply connection timeout
        let stream = tokio::time::timeout(config.connect_timeout, TcpStream::connect(&addr))
            .await
            .map_err(|_| MosError::timeout(format!("Connection to {} timed out", addr)))?
            .map_err(|e| MosError::connection(format!("Failed to connect to {}: {}", addr, e)))?;

        // Configure TCP options
        if config.tcp_nodelay {
            stream.set_nodelay(true)
                .map_err(|e| MosError::connection(format!("Failed to set TCP_NODELAY: {}", e)))?;
        }

        Ok(Self::with_config(stream, config))
    }

    /// Read bytes from the connection
    ///
    /// Reads data from the receive buffer. If not enough data is available,
    /// it will read more from the network.
    pub async fn read(&mut self, buf: &mut [u8]) -> MosResult<usize> {
        // First, try to read from buffer
        if self.recv_buffer.available() >= buf.len() {
            return self.recv_buffer.read_bytes(buf);
        }

        // Need to read more from network
        self.fill_recv_buffer().await?;

        // Now read from buffer
        self.recv_buffer.read_bytes(buf)
    }

    /// Read exact number of bytes
    pub async fn read_exact(&mut self, buf: &mut [u8]) -> MosResult<()> {
        let mut offset = 0;
        while offset < buf.len() {
            let n = self.read(&mut buf[offset..]).await?;
            if n == 0 {
                return Err(MosError::connection("unexpected EOF"));
            }
            offset += n;
        }
        Ok(())
    }

    /// Peek at bytes without consuming them
    pub async fn peek(&mut self, len: usize) -> MosResult<Vec<u8>> {
        // Ensure we have enough data
        while self.recv_buffer.available() < len {
            self.fill_recv_buffer().await?;
        }

        let bytes = self.recv_buffer.peek_bytes(len)?;
        Ok(bytes.to_vec())
    }

    /// Write bytes to the connection
    pub async fn write(&mut self, buf: &[u8]) -> MosResult<usize> {
        // Try to write to buffer
        let written = self.send_buffer.write_bytes(buf)?;

        // If buffer is getting full, flush it
        if self.send_buffer.remaining() < self.config.send_buffer_size / 2 {
            self.flush().await?;
        }

        Ok(written)
    }

    /// Write all bytes
    pub async fn write_all(&mut self, buf: &[u8]) -> MosResult<()> {
        let mut offset = 0;
        while offset < buf.len() {
            let n = self.write(&buf[offset..]).await?;
            offset += n;
        }
        Ok(())
    }

    /// Flush the send buffer
    pub async fn flush(&mut self) -> MosResult<()> {
        while self.send_buffer.available() > 0 {
            let mut buf = vec![0u8; self.send_buffer.available()];
            let n = self.send_buffer.read_bytes(&mut buf)?;
            self.stream.write_all(&buf[..n]).await?;
        }
        self.stream.flush().await?;
        Ok(())
    }

    /// Fill the receive buffer from the network
    async fn fill_recv_buffer(&mut self) -> MosResult<()> {
        let mut temp_buf = vec![0u8; 4096];
        let n = self.stream.read(&mut temp_buf).await?;

        if n == 0 {
            return Err(MosError::connection("connection closed"));
        }

        self.recv_buffer.write_bytes(&temp_buf[..n])?;
        Ok(())
    }

    /// Close the connection
    pub async fn close(mut self) -> MosResult<()> {
        self.flush().await?;
        self.stream.shutdown().await?;
        Ok(())
    }

    /// Get buffer statistics
    pub fn buffer_stats(&self) -> BufferStats {
        BufferStats {
            recv_available: self.recv_buffer.available(),
            recv_remaining: self.recv_buffer.remaining(),
            send_available: self.send_buffer.available(),
            send_remaining: self.send_buffer.remaining(),
        }
    }
}

/// Buffer statistics
#[derive(Debug, Clone, Copy)]
pub struct BufferStats {
    pub recv_available: usize,
    pub recv_remaining: usize,
    pub send_available: usize,
    pub send_remaining: usize,
}

#[cfg(test)]
mod tests {
    use super::*;

    // Note: Most tests require an actual TCP connection
    // These are unit tests for the structure

    #[test]
    fn test_buffer_stats() {
        // We can't easily test without a real connection
        // but we can test the structure
        let stats = BufferStats {
            recv_available: 100,
            recv_remaining: 900,
            send_available: 50,
            send_remaining: 950,
        };

        assert_eq!(stats.recv_available, 100);
        assert_eq!(stats.send_available, 50);
    }
}

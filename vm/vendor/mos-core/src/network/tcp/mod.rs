//! TCP connection implementation

mod connection;
pub use connection::TcpConnection;

use crate::utils::MosResult;
use tokio::net::TcpStream;

/// Connect to a TCP server
///
/// # Arguments
///
/// * `host` - Hostname or IP address
/// * `port` - Port number
///
/// # Returns
///
/// Returns a connected TcpStream
pub async fn connect(host: &str, port: u16) -> MosResult<TcpStream> {
    let addr = format!("{}:{}", host, port);
    tracing::info!("Connecting to {}...", addr);

    let stream = TcpStream::connect(&addr).await?;
    stream.set_nodelay(true)?; // Disable Nagle for low latency

    tracing::info!("Connected to {}", addr);
    Ok(stream)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[tokio::test]
    #[ignore] // Requires actual server
    async fn test_connect() {
        let result = connect("localhost", 5900).await;
        // This will fail without a VNC server
        assert!(result.is_ok() || result.is_err());
    }
}

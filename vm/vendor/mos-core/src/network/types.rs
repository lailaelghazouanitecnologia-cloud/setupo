//! Network types and constants

use std::time::Duration;

/// Default buffer sizes
pub const DEFAULT_SEND_BUFFER_SIZE: usize = 8192;
pub const DEFAULT_RECV_BUFFER_SIZE: usize = 16384;

/// Network timeouts
pub const DEFAULT_CONNECT_TIMEOUT: Duration = Duration::from_secs(10);
pub const DEFAULT_READ_TIMEOUT: Duration = Duration::from_secs(30);
pub const DEFAULT_WRITE_TIMEOUT: Duration = Duration::from_secs(10);

/// Connection configuration
#[derive(Debug, Clone)]
pub struct NetworkConfig {
    pub connect_timeout: Duration,
    pub read_timeout: Duration,
    pub write_timeout: Duration,
    pub send_buffer_size: usize,
    pub recv_buffer_size: usize,
    pub tcp_nodelay: bool,
}

impl Default for NetworkConfig {
    fn default() -> Self {
        Self {
            connect_timeout: DEFAULT_CONNECT_TIMEOUT,
            read_timeout: DEFAULT_READ_TIMEOUT,
            write_timeout: DEFAULT_WRITE_TIMEOUT,
            send_buffer_size: DEFAULT_SEND_BUFFER_SIZE,
            recv_buffer_size: DEFAULT_RECV_BUFFER_SIZE,
            tcp_nodelay: true, // Disable Nagle's algorithm for low latency
        }
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_default_config() {
        let config = NetworkConfig::default();
        assert_eq!(config.tcp_nodelay, true);
        assert_eq!(config.send_buffer_size, DEFAULT_SEND_BUFFER_SIZE);
    }
}

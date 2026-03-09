//! Time and timestamp utilities

use std::time::{Duration, Instant, SystemTime, UNIX_EPOCH};

/// Timestamp wrapper for performance measurements
#[derive(Debug, Clone, Copy)]
pub struct Timestamp(Instant);

impl Timestamp {
    /// Create a new timestamp for now
    pub fn now() -> Self {
        Self(Instant::now())
    }

    /// Get elapsed time since this timestamp
    pub fn elapsed(&self) -> Duration {
        self.0.elapsed()
    }

    /// Get elapsed time in milliseconds
    pub fn elapsed_ms(&self) -> u64 {
        self.elapsed().as_millis() as u64
    }

    /// Get elapsed time in microseconds
    pub fn elapsed_micros(&self) -> u64 {
        self.elapsed().as_micros() as u64
    }
}

/// Get current Unix timestamp in milliseconds
pub fn unix_timestamp_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

/// Get current Unix timestamp in seconds
pub fn unix_timestamp() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_secs()
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::thread;

    #[test]
    fn test_timestamp() {
        let ts = Timestamp::now();
        thread::sleep(Duration::from_millis(10));
        let elapsed = ts.elapsed_ms();
        assert!(elapsed >= 10);
    }

    #[test]
    fn test_unix_timestamp() {
        let ts = unix_timestamp();
        assert!(ts > 1_600_000_000); // After 2020

        let ts_ms = unix_timestamp_ms();
        assert!(ts_ms > 1_600_000_000_000); // After 2020
    }
}

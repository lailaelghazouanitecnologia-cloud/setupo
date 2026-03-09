//! Integration tests for Mos VNC client
//!
//! Tests the full stack integration of all components.

use mos_core::core::{ClientState, ConnectionConfig, RfbClient};
use mos_core::encodings::{Decoder, EncodingType, RawDecoder};
use mos_core::utils::{ByteOps, MosError};
use mos_core::network::Buffer;

#[test]
fn test_client_creation() {
    let config = ConnectionConfig::new("localhost", 5900);
    let client = RfbClient::new(config);

    assert_eq!(client.state(), ClientState::Disconnected);
    assert_eq!(client.framebuffer_size(), (0, 0));
    assert!(client.server_info().is_none());
}

#[test]
fn test_client_with_password() {
    let config = ConnectionConfig::new("localhost", 5900)
        .with_password("test123")
        .with_shared(true);

    let client = RfbClient::new(config);
    assert_eq!(client.state(), ClientState::Disconnected);
}

#[test]
fn test_raw_decoder_integration() {
    use mos_core::core::PixelFormat;

    let mut decoder = RawDecoder::new();
    assert_eq!(decoder.encoding_type(), EncodingType::Raw);

    let pixel_format = PixelFormat {
        bits_per_pixel: 32,
        depth: 24,
        big_endian: false,
        true_color: true,
        red_max: 255,
        green_max: 255,
        blue_max: 255,
        red_shift: 0,
        green_shift: 8,
        blue_shift: 16,
    };

    // Test decoding a single pixel
    let data = vec![255, 0, 0, 255]; // Red pixel
    let mut framebuffer = vec![0u8; 4 * 4 * 4]; // 4x4 framebuffer

    let bytes_read = decoder
        .decode(&data, 0, 0, 1, 1, &mut framebuffer, 4, &pixel_format)
        .unwrap();

    assert_eq!(bytes_read, 4);
    assert_eq!(framebuffer[0], 255); // Red
    assert_eq!(framebuffer[1], 0);   // Green
    assert_eq!(framebuffer[2], 0);   // Blue
}

#[test]
fn test_byte_ops() {
    let data = vec![0x12, 0x34, 0x56, 0x78, 0x9A, 0xBC, 0xDE, 0xF0];

    assert_eq!(data.read_u8(0).unwrap(), 0x12);
    assert_eq!(data.read_u16_be(0).unwrap(), 0x1234);
    assert_eq!(data.read_u32_be(0).unwrap(), 0x12345678);
    assert_eq!(data.read_u16_be(2).unwrap(), 0x5678);
}

#[test]
fn test_error_types() {
    let err = MosError::connection("Test error");
    assert!(err.is_connection());

    let err = MosError::auth("Auth failed");
    assert!(err.is_auth());

    let err = MosError::protocol("Protocol error");
    assert!(!err.is_connection());
}

#[test]
fn test_encoding_type_conversion() {
    use mos_core::encodings::EncodingType;

    assert_eq!(EncodingType::from_i32(0), Some(EncodingType::Raw));
    assert_eq!(EncodingType::Raw.to_i32(), 0);
    assert_eq!(EncodingType::Raw.name(), "Raw");

    assert_eq!(EncodingType::from_i32(7), Some(EncodingType::Tight));
    assert_eq!(EncodingType::Tight.to_i32(), 7);

    assert_eq!(EncodingType::from_i32(999), None);
}

#[test]
fn test_connection_config_builder() {
    let config = ConnectionConfig::new("192.168.1.100", 5901)
        .with_password("secret")
        .with_shared(false)
        .with_quality(8)
        .with_compression(6)
        .with_view_only(true);

    // Just verify it builds successfully
    let client = RfbClient::new(config);
    assert_eq!(client.state(), ClientState::Disconnected);
}

#[tokio::test]
async fn test_network_buffer() {
    use mos_core::network::RingBuffer;

    let mut buffer = RingBuffer::new(1024);
    assert_eq!(buffer.available(), 0);
    assert_eq!(buffer.capacity(), 1024);

    // Write some data
    let data = b"Hello, World!";
    let written = buffer.write_bytes(data).unwrap();
    assert_eq!(written, data.len());
    assert_eq!(buffer.available(), data.len());

    // Read it back
    let mut read_buf = vec![0u8; 20];
    let read = buffer.read_bytes(&mut read_buf).unwrap();
    assert_eq!(read, data.len());
    assert_eq!(&read_buf[..read], data);
    assert_eq!(buffer.available(), 0);
}

#[test]
fn test_pixel_format() {
    use mos_core::core::PixelFormat;

    let pf = PixelFormat::rgb888();
    assert_eq!(pf.bits_per_pixel, 32);
    assert_eq!(pf.depth, 24);
    assert_eq!(pf.bytes_per_pixel(), 4);
    assert!(pf.true_color);

    let pf_be = PixelFormat::rgb888_be();
    assert!(pf_be.big_endian);
}

/// Test that demonstrates the full client lifecycle (without actual network)
#[test]
fn test_client_lifecycle_states() {
    let config = ConnectionConfig::new("test.server", 5900)
        .with_password("testpass")
        .with_shared(true);

    let client = RfbClient::new(config);

    // Initial state should be disconnected
    assert_eq!(client.state(), ClientState::Disconnected);

    // Verify framebuffer is empty initially
    assert_eq!(client.framebuffer().len(), 0);
    assert_eq!(client.framebuffer_size(), (0, 0));

    // Verify no server info initially
    assert!(client.server_info().is_none());
}

#[test]
fn test_module_exports() {
    // Verify all main types are accessible
    let _config: mos_core::ConnectionConfig;
    let _client_state: mos_core::ClientState;
    let _encoding: mos_core::EncodingType;
    let _error: mos_core::MosError;

    // Test version constant
    assert!(!mos_core::VERSION.is_empty());
}

/// Performance test: Decoder throughput
#[test]
fn test_raw_decoder_performance() {
    use mos_core::core::PixelFormat;
    use std::time::Instant;

    let mut decoder = RawDecoder::new();
    let pixel_format = PixelFormat::rgb888();

    // Create 1920x1080 frame (Full HD)
    let width = 1920u16;
    let height = 1080u16;
    let bytes_per_pixel = 4;
    let frame_size = (width as usize) * (height as usize) * bytes_per_pixel;

    let data = vec![128u8; frame_size];
    let mut framebuffer = vec![0u8; frame_size];

    let start = Instant::now();
    decoder
        .decode(&data, 0, 0, width, height, &mut framebuffer, width, &pixel_format)
        .unwrap();
    let duration = start.elapsed();

    // Should decode Full HD frame in less than 10ms (very conservative)
    assert!(duration.as_millis() < 10);

    // Calculate throughput
    let mb_per_sec = (frame_size as f64) / (1024.0 * 1024.0) / duration.as_secs_f64();
    println!("Raw decoder throughput: {:.2} MB/s", mb_per_sec);
}

/// Test buffer compaction
#[test]
fn test_ring_buffer_compaction() {
    use mos_core::network::RingBuffer;

    let mut buffer = RingBuffer::new(100);

    // Write and read multiple times to fragment the buffer
    for _ in 0..5 {
        buffer.write_bytes(b"test data").unwrap();
        let mut read_buf = [0u8; 9];
        buffer.read_bytes(&mut read_buf).unwrap();
    }

    // Write more data
    buffer.write_bytes(b"hello world").unwrap();

    // Compact
    buffer.compact();

    // Should still be able to read the data
    let mut read_buf = vec![0u8; 20];
    let n = buffer.read_bytes(&mut read_buf).unwrap();
    assert_eq!(&read_buf[..n], b"hello world");
}

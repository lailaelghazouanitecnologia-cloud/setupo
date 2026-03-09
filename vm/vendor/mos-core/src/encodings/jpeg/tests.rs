use super::*;
use crate::core::PixelFormat;

/// Helper to create a test pixel format (32-bit RGBA)
fn test_pixel_format() -> PixelFormat {
    PixelFormat {
        bits_per_pixel: 32,
        depth: 24,
        big_endian: false,
        true_color: true,
        red_max: 255,
        green_max: 255,
        blue_max: 255,
        red_shift: 16,
        green_shift: 8,
        blue_shift: 0,
    }
}

/// Create a simple JPEG image for testing
/// Returns (jpeg_data, width, height)
fn create_test_jpeg(width: u16, height: u16, quality: u8) -> Vec<u8> {
    use jpeg_decoder::Decoder as JpegDecoder;

    // Create RGB pixels (gradient pattern)
    let mut rgb_pixels = Vec::with_capacity(width as usize * height as usize * 3);
    for y in 0..height {
        for x in 0..width {
            let r = ((x * 255) / width.max(1)) as u8;
            let g = ((y * 255) / height.max(1)) as u8;
            let b = 128;
            rgb_pixels.push(r);
            rgb_pixels.push(g);
            rgb_pixels.push(b);
        }
    }

    // Encode to JPEG using a simple encoder
    // For testing purposes, we'll create a minimal JPEG
    // In practice, you'd use jpeg-encoder or image crate

    // Since we don't have jpeg-encoder, we'll create a very simple
    // test JPEG by hand. For now, let's use a pre-made minimal JPEG.

    // Minimal valid JPEG (1x1 red pixel)
    // This is a real JPEG file for testing
    let minimal_jpeg: Vec<u8> = vec![
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x14, 0x00, 0x01,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x03, 0xFF, 0xC4, 0x00, 0x14, 0x10, 0x01, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01, 0x00, 0x00, 0x3F, 0x00,
        0x37, 0xFF, 0xD9,
    ];

    // Verify it's a valid JPEG
    let mut decoder = JpegDecoder::new(&minimal_jpeg[..]);
    decoder.decode().expect("Failed to decode test JPEG");

    minimal_jpeg
}

#[test]
fn test_jpeg_decode_basic() {
    let mut decoder = JpegEncodingDecoder::new();
    let pixel_format = test_pixel_format();

    // Create a minimal 1x1 JPEG
    let jpeg_data = create_test_jpeg(1, 1, 90);

    // Create encoded data with length header
    let mut data = Vec::new();
    data.extend_from_slice(&(jpeg_data.len() as u32).to_be_bytes());
    data.extend_from_slice(&jpeg_data);

    // Create framebuffer
    let mut framebuffer = vec![0u8; 100 * 100 * 4]; // 100x100 RGBA

    // Decode
    let result = decoder.decode(
        &data,
        0,
        0,
        1,
        1,
        &mut framebuffer,
        100,
        &pixel_format,
    );

    assert!(result.is_ok(), "JPEG decode should succeed");
    let bytes_read = result.unwrap();
    assert_eq!(bytes_read, 4 + jpeg_data.len(), "Should read all data");
}

#[test]
fn test_jpeg_insufficient_data() {
    let mut decoder = JpegEncodingDecoder::new();
    let pixel_format = test_pixel_format();
    let mut framebuffer = vec![0u8; 100 * 100 * 4];

    // Only 2 bytes (incomplete length header)
    let data = vec![0x00, 0x00];

    let result = decoder.decode(&data, 0, 0, 10, 10, &mut framebuffer, 100, &pixel_format);
    assert!(result.is_err(), "Should fail with insufficient data");
    assert!(result.unwrap_err().to_string().contains("Insufficient"));
}

#[test]
fn test_jpeg_invalid_length() {
    let mut decoder = JpegEncodingDecoder::new();
    let pixel_format = test_pixel_format();
    let mut framebuffer = vec![0u8; 100 * 100 * 4];

    // Length says 1000 bytes but only provide 10
    let mut data = Vec::new();
    data.extend_from_slice(&1000u32.to_be_bytes());
    data.extend_from_slice(&[0u8; 10]);

    let result = decoder.decode(&data, 0, 0, 10, 10, &mut framebuffer, 100, &pixel_format);
    assert!(result.is_err(), "Should fail with invalid length");
}

#[test]
fn test_jpeg_invalid_jpeg_data() {
    let mut decoder = JpegEncodingDecoder::new();
    let pixel_format = test_pixel_format();
    let mut framebuffer = vec![0u8; 100 * 100 * 4];

    // Invalid JPEG data
    let invalid_jpeg = vec![0x00, 0x01, 0x02, 0x03, 0x04, 0x05];
    let mut data = Vec::new();
    data.extend_from_slice(&(invalid_jpeg.len() as u32).to_be_bytes());
    data.extend_from_slice(&invalid_jpeg);

    let result = decoder.decode(&data, 0, 0, 1, 1, &mut framebuffer, 100, &pixel_format);
    assert!(result.is_err(), "Should fail with invalid JPEG");
    assert!(result.unwrap_err().to_string().contains("JPEG"));
}

#[test]
fn test_jpeg_dimension_mismatch() {
    let mut decoder = JpegEncodingDecoder::new();
    let pixel_format = test_pixel_format();
    let mut framebuffer = vec![0u8; 100 * 100 * 4];

    // Create 1x1 JPEG but claim it's 10x10
    let jpeg_data = create_test_jpeg(1, 1, 90);
    let mut data = Vec::new();
    data.extend_from_slice(&(jpeg_data.len() as u32).to_be_bytes());
    data.extend_from_slice(&jpeg_data);

    let result = decoder.decode(
        &data,
        0,
        0,
        10,  // Wrong dimensions
        10,
        &mut framebuffer,
        100,
        &pixel_format,
    );

    assert!(result.is_err(), "Should fail with dimension mismatch");
    assert!(result.unwrap_err().to_string().contains("dimensions"));
}

#[test]
fn test_jpeg_encoding_type() {
    let decoder = JpegEncodingDecoder::new();
    assert_eq!(decoder.encoding_type(), EncodingType::Jpeg);
}

#[test]
fn test_jpeg_reset() {
    let mut decoder = JpegEncodingDecoder::new();
    decoder.reset(); // Should not panic
}

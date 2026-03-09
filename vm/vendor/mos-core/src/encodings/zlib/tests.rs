//! Zlib decoder tests

use super::*;
use crate::core::PixelFormat;
use flate2::write::ZlibEncoder;
use flate2::Compression;
use std::io::Write;

fn create_test_pixel_format() -> PixelFormat {
    PixelFormat {
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
    }
}

fn compress_zlib(data: &[u8]) -> Vec<u8> {
    let mut encoder = ZlibEncoder::new(Vec::new(), Compression::default());
    encoder.write_all(data).unwrap();
    encoder.finish().unwrap()
}

fn write_u32_be(value: u32) -> Vec<u8> {
    vec![
        ((value >> 24) & 0xFF) as u8,
        ((value >> 16) & 0xFF) as u8,
        ((value >> 8) & 0xFF) as u8,
        (value & 0xFF) as u8,
    ]
}

#[test]
fn test_zlib_solid_color() {
    let mut decoder = ZlibDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 16 * 16 * 4];

    // Create raw pixel data (16x16 red pixels)
    let mut raw_data = Vec::new();
    for _ in 0..16 * 16 {
        raw_data.extend_from_slice(&[255, 0, 0, 0]); // Red RGBA
    }

    // Compress it
    let compressed = compress_zlib(&raw_data);
    let compressed_len = compressed.len() as u32;

    // Build Zlib data: length + compressed data
    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 16, 16, &mut fb, 16, &pixel_format)
        .unwrap();

    // Verify all pixels are red
    for i in 0..16 * 16 {
        let offset = i * 4;
        assert_eq!(fb[offset], 255, "Red component at pixel {}", i);
        assert_eq!(fb[offset + 1], 0, "Green component at pixel {}", i);
        assert_eq!(fb[offset + 2], 0, "Blue component at pixel {}", i);
    }
}

#[test]
fn test_zlib_gradient() {
    let mut decoder = ZlibDecoder::new();
    let pixel_format = create_test_pixel_format();

    let width = 8;
    let height = 8;
    let mut fb = vec![0u8; width * height * 4];

    // Create gradient pattern
    let mut raw_data = Vec::new();
    for y in 0..height {
        for x in 0..width {
            let r = (x * 255 / (width - 1)) as u8;
            let g = (y * 255 / (height - 1)) as u8;
            let b = 128;
            raw_data.extend_from_slice(&[r, g, b, 255]);
        }
    }

    let compressed = compress_zlib(&raw_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, width as u16, height as u16, &mut fb, width as u16, &pixel_format)
        .unwrap();

    // Verify some sample pixels
    // Top-left (0, 0)
    assert_eq!(fb[0], 0);
    assert_eq!(fb[1], 0);
    assert_eq!(fb[2], 128);

    // Top-right (7, 0)
    let offset = 7 * 4;
    assert_eq!(fb[offset], 255);
    assert_eq!(fb[offset + 1], 0);
    assert_eq!(fb[offset + 2], 128);

    // Bottom-left (0, 7)
    let offset = (7 * 8) * 4;
    assert_eq!(fb[offset], 0);
    assert_eq!(fb[offset + 1], 255);
    assert_eq!(fb[offset + 2], 128);
}

#[test]
fn test_zlib_with_offset() {
    let mut decoder = ZlibDecoder::new();
    let pixel_format = create_test_pixel_format();

    // Create 16x16 framebuffer, but write to 4x4 area at (2, 2)
    let mut fb = vec![0u8; 16 * 16 * 4];

    // Create 4x4 blue square
    let mut raw_data = Vec::new();
    for _ in 0..4 * 4 {
        raw_data.extend_from_slice(&[0, 0, 255, 255]); // Blue
    }

    let compressed = compress_zlib(&raw_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 2, 2, 4, 4, &mut fb, 16, &pixel_format)
        .unwrap();

    // Verify the blue square at (2, 2)
    for row in 2..6 {
        for col in 2..6 {
            let offset = (row * 16 + col) * 4;
            assert_eq!(fb[offset], 0, "Pixel ({}, {}) red", row, col);
            assert_eq!(fb[offset + 1], 0, "Pixel ({}, {}) green", row, col);
            assert_eq!(fb[offset + 2], 255, "Pixel ({}, {}) blue", row, col);
        }
    }

    // Verify outside area is still black
    assert_eq!(fb[0], 0);
    assert_eq!(fb[1], 0);
    assert_eq!(fb[2], 0);
}

#[test]
fn test_zlib_insufficient_data() {
    let mut decoder = ZlibDecoder::new();
    let pixel_format = create_test_pixel_format();
    let mut fb = vec![0u8; 16 * 16 * 4];

    // Data too short (less than 4 bytes)
    let data = vec![0, 1, 2];
    let result = decoder.decode(&data, 0, 0, 16, 16, &mut fb, 16, &pixel_format);
    assert!(result.is_err());
}

#[test]
fn test_zlib_size_mismatch() {
    let mut decoder = ZlibDecoder::new();
    let pixel_format = create_test_pixel_format();
    let mut fb = vec![0u8; 16 * 16 * 4];

    // Create data for 8x8 but claim it's 16x16
    let mut raw_data = Vec::new();
    for _ in 0..8 * 8 {
        raw_data.extend_from_slice(&[255, 0, 0, 0]);
    }

    let compressed = compress_zlib(&raw_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    let result = decoder.decode(&data, 0, 0, 16, 16, &mut fb, 16, &pixel_format);
    assert!(result.is_err());
}

#[test]
fn test_zlib_encoding_type() {
    let decoder = ZlibDecoder::new();
    assert_eq!(decoder.encoding_type(), EncodingType::Zlib);
}

#[test]
fn test_zlib_large_rectangle() {
    let mut decoder = ZlibDecoder::new();
    let pixel_format = create_test_pixel_format();

    let width = 64;
    let height = 64;
    let mut fb = vec![0u8; width * height * 4];

    // Create checkerboard pattern
    let mut raw_data = Vec::new();
    for y in 0..height {
        for x in 0..width {
            let is_white = (x / 8 + y / 8) % 2 == 0;
            let color = if is_white { 255 } else { 0 };
            raw_data.extend_from_slice(&[color, color, color, 255]);
        }
    }

    let compressed = compress_zlib(&raw_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    let bytes_consumed = decoder
        .decode(&data, 0, 0, width as u16, height as u16, &mut fb, width as u16, &pixel_format)
        .unwrap();

    assert_eq!(bytes_consumed, 4 + compressed_len as usize);

    // Verify checkerboard pattern
    for y in 0..height {
        for x in 0..width {
            let offset = (y * width + x) * 4;
            let expected = if (x / 8 + y / 8) % 2 == 0 { 255 } else { 0 };
            assert_eq!(fb[offset], expected, "Pixel ({}, {})", x, y);
        }
    }
}

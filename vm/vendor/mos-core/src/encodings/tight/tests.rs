//! Tight decoder tests

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

fn encode_compact_length(len: usize) -> Vec<u8> {
    if len < 128 {
        vec![len as u8]
    } else if len < 16384 {
        vec![
            ((len & 0x7F) | 0x80) as u8,
            (len >> 7) as u8,
        ]
    } else {
        vec![
            ((len & 0x3F) | 0xC0) as u8,
            ((len >> 6) & 0xFF) as u8,
            (len >> 14) as u8,
        ]
    }
}

#[test]
fn test_tight_fill_compression() {
    let mut decoder = TightDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 16 * 16 * 4];

    // Fill compression: control byte (0x80 = fill) + pixel data
    let data = vec![
        0x80, // Fill compression (bit 7 set, bits 4-7 = 0x08)
        255, 0, 0, 255, // Red pixel (RGBA)
    ];

    decoder
        .decode(&data, 0, 0, 16, 16, &mut fb, 16, &pixel_format)
        .unwrap();

    // Check that all pixels are red
    for i in 0..16 * 16 {
        let offset = i * 4;
        assert_eq!(fb[offset], 255, "Red component at pixel {}", i);
        assert_eq!(fb[offset + 1], 0, "Green component at pixel {}", i);
        assert_eq!(fb[offset + 2], 0, "Blue component at pixel {}", i);
        assert_eq!(fb[offset + 3], 255, "Alpha component at pixel {}", i);
    }
}

#[test]
fn test_tight_copy_filter() {
    let mut decoder = TightDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 4 * 4 * 4];

    // Create raw pixel data (4x4 green pixels)
    let mut raw_data = Vec::new();
    for _ in 0..4 * 4 {
        raw_data.extend_from_slice(&[0, 255, 0, 255]); // Green
    }

    // Compress it
    let compressed = compress_zlib(&raw_data);
    let length_bytes = encode_compact_length(compressed.len());

    // Build Tight data: control + filter + length + compressed data
    let mut data = vec![
        0x00, // Basic compression (bits 4-7 = 0)
        0x00, // Copy filter
    ];
    data.extend_from_slice(&length_bytes);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 4, 4, &mut fb, 4, &pixel_format)
        .unwrap();

    // Check that all pixels are green
    for i in 0..4 * 4 {
        let offset = i * 4;
        assert_eq!(fb[offset], 0);
        assert_eq!(fb[offset + 1], 255);
        assert_eq!(fb[offset + 2], 0);
    }
}

#[test]
fn test_tight_palette_2_colors() {
    let mut decoder = TightDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 8 * 8 * 4];

    // Palette: 2 colors (black and white)
    let palette = vec![
        0, 0, 0, 255,       // Black
        255, 255, 255, 255, // White
    ];

    // Create a checkerboard pattern with 1 bit per pixel
    // 8x8 = 64 pixels = 64 bits = 8 bytes
    let mut indices = vec![0u8; 8];
    for i in 0..8 {
        // Alternating pattern: 0b10101010 or 0b01010101
        indices[i] = if i % 2 == 0 { 0xAA } else { 0x55 };
    }

    let compressed = compress_zlib(&indices);
    let length_bytes = encode_compact_length(compressed.len());

    // Build Tight data
    let mut data = vec![
        0x00, // Basic compression
        0x01, // Palette filter
        0x01, // Palette size - 1 (2 colors)
    ];
    data.extend_from_slice(&palette);
    data.extend_from_slice(&length_bytes);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 8, 8, &mut fb, 8, &pixel_format)
        .unwrap();

    // Verify checkerboard pattern
    for row in 0..8 {
        for col in 0..8 {
            let offset = (row * 8 + col) * 4;
            let expected_color = if (row + col) % 2 == 0 { 255 } else { 0 };
            assert_eq!(fb[offset], expected_color, "Pixel at ({}, {})", row, col);
        }
    }
}

#[test]
fn test_compact_length_encoding() {
    // Test 1 byte (0-127)
    let (len, bytes) = TightDecoder::read_compact_length(&[42], 0).unwrap();
    assert_eq!(len, 42);
    assert_eq!(bytes, 1);

    // Test 2 bytes (128-16383)
    // Value 255 = 127 + (1 << 7) = 0x7F | (0x01 << 7)
    // Byte 1: (255 & 0x7F) | 0x80 = 0x7F | 0x80 = 0xFF but bit 6 must be 0
    // Correct encoding: lower 7 bits in first byte, upper bits in second
    let data = vec![0x80 | 0x7F, 0x01]; // 0xFF = bits 6-7 both set, triggers 3-byte case
    // Let's use 130 instead: 130 = 2 + (1 << 7) = 0x82
    let data = vec![0x80 | 0x02, 0x01]; // (130 & 0x7F) | 0x80, 130 >> 7
    let (len, bytes) = TightDecoder::read_compact_length(&data, 0).unwrap();
    assert_eq!(len, 130);
    assert_eq!(bytes, 2);

    // Test 3 bytes (16384+)
    let data = vec![0xC0, 0x00, 0x01]; // 16384
    let (len, bytes) = TightDecoder::read_compact_length(&data, 0).unwrap();
    assert_eq!(len, 16384);
    assert_eq!(bytes, 3);
}

#[test]
fn test_tight_encoding_type() {
    let decoder = TightDecoder::new();
    assert_eq!(decoder.encoding_type(), EncodingType::Tight);
}

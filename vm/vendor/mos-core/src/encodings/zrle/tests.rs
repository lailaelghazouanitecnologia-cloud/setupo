//! ZRLE decoder tests

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
fn test_zrle_raw_subencoding() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 8 * 8 * 4];

    // Create raw tile data (8x8 red pixels with CPIXEL = 3 bytes)
    let mut tile_data = vec![0x00]; // Subencoding 0 = Raw
    for _ in 0..8 * 8 {
        tile_data.extend_from_slice(&[255, 0, 0]); // Red CPIXEL (RGB)
    }

    // Compress tile data
    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    // Build ZRLE data: length + compressed data
    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 8, 8, &mut fb, 8, &pixel_format)
        .unwrap();

    // Verify all pixels are red
    for i in 0..8 * 8 {
        let offset = i * 4;
        assert_eq!(fb[offset], 255, "Red component at pixel {}", i);
        assert_eq!(fb[offset + 1], 0, "Green component at pixel {}", i);
        assert_eq!(fb[offset + 2], 0, "Blue component at pixel {}", i);
    }
}

#[test]
fn test_zrle_solid_subencoding() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 16 * 16 * 4];

    // Create solid tile data (single blue pixel)
    let tile_data = vec![
        0x01, // Subencoding 1 = Solid
        0, 0, 255, // Blue CPIXEL (RGB)
    ];

    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 16, 16, &mut fb, 16, &pixel_format)
        .unwrap();

    // Verify all pixels are blue
    for i in 0..16 * 16 {
        let offset = i * 4;
        assert_eq!(fb[offset], 0, "Red component at pixel {}", i);
        assert_eq!(fb[offset + 1], 0, "Green component at pixel {}", i);
        assert_eq!(fb[offset + 2], 255, "Blue component at pixel {}", i);
    }
}

#[test]
fn test_zrle_plain_rle() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 8 * 8 * 4];

    // Create RLE tile: 32 red pixels, then 32 green pixels
    let mut tile_data = vec![0x80]; // Subencoding 128 = Plain RLE

    // First run: 32 red pixels (run_length - 1 = 31)
    tile_data.push(31); // Run length - 1
    tile_data.extend_from_slice(&[255, 0, 0]); // Red CPIXEL

    // Second run: 32 green pixels
    tile_data.push(31);
    tile_data.extend_from_slice(&[0, 255, 0]); // Green CPIXEL

    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 8, 8, &mut fb, 8, &pixel_format)
        .unwrap();

    // Verify first 32 pixels are red
    for i in 0..32 {
        let offset = i * 4;
        assert_eq!(fb[offset], 255, "Red pixel {} red component", i);
        assert_eq!(fb[offset + 1], 0, "Red pixel {} green component", i);
        assert_eq!(fb[offset + 2], 0, "Red pixel {} blue component", i);
    }

    // Verify last 32 pixels are green
    for i in 32..64 {
        let offset = i * 4;
        assert_eq!(fb[offset], 0, "Green pixel {} red component", i);
        assert_eq!(fb[offset + 1], 255, "Green pixel {} green component", i);
        assert_eq!(fb[offset + 2], 0, "Green pixel {} blue component", i);
    }
}

#[test]
fn test_zrle_multiple_tiles() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    // Create 128x64 framebuffer (2 tiles horizontally, 1 vertically)
    let mut fb = vec![0u8; 128 * 64 * 4];

    // Build tile data (2 tiles: red and blue)
    let mut tile_data = Vec::new();
    tile_data.extend_from_slice(&[0x01, 255, 0, 0]); // Tile 1: 64x64 solid red
    tile_data.extend_from_slice(&[0x01, 0, 0, 255]); // Tile 2: 64x64 solid blue

    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 128, 64, &mut fb, 128, &pixel_format)
        .unwrap();

    // Verify left tile (first 64 columns) is red
    for row in 0..64 {
        for col in 0..64 {
            let offset = (row * 128 + col) * 4;
            assert_eq!(fb[offset], 255, "Left tile pixel ({}, {}) red", row, col);
            assert_eq!(fb[offset + 2], 0, "Left tile pixel ({}, {}) blue", row, col);
        }
    }

    // Verify right tile (last 64 columns) is blue
    for row in 0..64 {
        for col in 64..128 {
            let offset = (row * 128 + col) * 4;
            assert_eq!(fb[offset], 0, "Right tile pixel ({}, {}) red", row, col);
            assert_eq!(fb[offset + 2], 255, "Right tile pixel ({}, {}) blue", row, col);
        }
    }
}

#[test]
fn test_zrle_cpixel_expansion() {
    // Test CPIXEL expansion from 3 bytes to 4 bytes
    let pixel_format = create_test_pixel_format();

    let cpixel = vec![128, 64, 32]; // 3-byte RGB
    let expanded = ZrleDecoder::expand_cpixel(&cpixel, &pixel_format);

    assert_eq!(expanded.len(), 4);
    assert_eq!(expanded[0], 128);
    assert_eq!(expanded[1], 64);
    assert_eq!(expanded[2], 32);
    assert_eq!(expanded[3], 0);
}

#[test]
fn test_zrle_encoding_type() {
    let decoder = ZrleDecoder::new();
    assert_eq!(decoder.encoding_type(), EncodingType::Zrle);
}

#[test]
fn test_zrle_partial_tile() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    // Create 100x100 framebuffer (requires 4 tiles: 64x64, 36x64, 64x36, 36x36)
    let mut fb = vec![0u8; 100 * 100 * 4];

    // Create solid yellow tile data
    let tile_data = vec![
        0x01, 255, 255, 0, // Tile 1: 64x64 yellow
        0x01, 255, 255, 0, // Tile 2: 36x64 yellow
        0x01, 255, 255, 0, // Tile 3: 64x36 yellow
        0x01, 255, 255, 0, // Tile 4: 36x36 yellow
    ];

    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 100, 100, &mut fb, 100, &pixel_format)
        .unwrap();

    // Verify a few sample pixels are yellow
    for row in [0, 50, 99] {
        for col in [0, 50, 99] {
            let offset = (row * 100 + col) * 4;
            assert_eq!(fb[offset], 255, "Pixel ({}, {}) red", row, col);
            assert_eq!(fb[offset + 1], 255, "Pixel ({}, {}) green", row, col);
            assert_eq!(fb[offset + 2], 0, "Pixel ({}, {}) blue", row, col);
        }
    }
}

#[test]
fn test_zrle_packed_palette_2_colors() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 8 * 8 * 4];

    // Create packed palette data with 2 colors (1 bit per pixel)
    let mut tile_data = vec![
        0x02, // Subencoding 2 = 2-color palette
        255, 0, 0,   // Color 0: Red
        0, 0, 255,   // Color 1: Blue
    ];

    // Create checkerboard pattern: 8x8 = 64 pixels = 64 bits = 8 bytes
    // Row 0: 0,1,0,1,0,1,0,1 = 0b01010101 = 0x55
    // Row 1: 1,0,1,0,1,0,1,0 = 0b10101010 = 0xAA
    // Alternating pattern (Red=0, Blue=1)
    for i in 0..8 {
        let pattern = if i % 2 == 0 { 0x55 } else { 0xAA }; // Rows alternate
        tile_data.push(pattern);
    }

    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 8, 8, &mut fb, 8, &pixel_format)
        .unwrap();

    // Verify checkerboard pattern
    for row in 0..8 {
        for col in 0..8 {
            let offset = (row * 8 + col) * 4;
            let expected_red = if (row + col) % 2 == 0 { 255 } else { 0 };
            let expected_blue = if (row + col) % 2 == 0 { 0 } else { 255 };
            assert_eq!(fb[offset], expected_red, "Pixel ({}, {}) red", row, col);
            assert_eq!(fb[offset + 2], expected_blue, "Pixel ({}, {}) blue", row, col);
        }
    }
}

#[test]
fn test_zrle_packed_palette_4_colors() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 4 * 4 * 4];

    // Create packed palette data with 4 colors (2 bits per pixel)
    let mut tile_data = vec![
        0x04, // Subencoding 4 = 4-color palette
        255, 0, 0,     // Color 0: Red
        0, 255, 0,     // Color 1: Green
        0, 0, 255,     // Color 2: Blue
        255, 255, 0,   // Color 3: Yellow
    ];

    // 4x4 = 16 pixels, 2 bits each = 32 bits = 4 bytes
    // Pattern: 0,1,2,3, 0,1,2,3, 0,1,2,3, 0,1,2,3
    tile_data.push(0b00_01_10_11); // Pixels 0-3
    tile_data.push(0b00_01_10_11); // Pixels 4-7
    tile_data.push(0b00_01_10_11); // Pixels 8-11
    tile_data.push(0b00_01_10_11); // Pixels 12-15

    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 4, 4, &mut fb, 4, &pixel_format)
        .unwrap();

    // Verify pattern
    let colors = vec![
        (255, 0, 0),     // Red
        (0, 255, 0),     // Green
        (0, 0, 255),     // Blue
        (255, 255, 0),   // Yellow
    ];

    for i in 0..16 {
        let offset = i * 4;
        let expected = &colors[i % 4];
        assert_eq!(fb[offset], expected.0, "Pixel {} red", i);
        assert_eq!(fb[offset + 1], expected.1, "Pixel {} green", i);
        assert_eq!(fb[offset + 2], expected.2, "Pixel {} blue", i);
    }
}

#[test]
fn test_zrle_palette_rle() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 8 * 8 * 4];

    // Create palette RLE data
    let mut tile_data = vec![
        0x81, // Subencoding 129 = Palette RLE
        0x02, // Palette size - 1 (3 colors)
        255, 0, 0,     // Color 0: Red
        0, 255, 0,     // Color 1: Green
        0, 0, 255,     // Color 2: Blue
    ];

    // RLE runs: 20 red, 20 green, 24 blue = 64 pixels
    tile_data.push(0x80 | 0); // Index 0 with run length follows
    tile_data.push(19);        // Run length - 1 (20 pixels)

    tile_data.push(0x80 | 1); // Index 1 with run length follows
    tile_data.push(19);        // Run length - 1 (20 pixels)

    tile_data.push(0x80 | 2); // Index 2 with run length follows
    tile_data.push(23);        // Run length - 1 (24 pixels)

    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 8, 8, &mut fb, 8, &pixel_format)
        .unwrap();

    // Verify: first 20 red, next 20 green, last 24 blue
    for i in 0..64 {
        let offset = i * 4;
        if i < 20 {
            assert_eq!(fb[offset], 255, "Pixel {} should be red", i);
            assert_eq!(fb[offset + 1], 0);
            assert_eq!(fb[offset + 2], 0);
        } else if i < 40 {
            assert_eq!(fb[offset], 0, "Pixel {} should be green", i);
            assert_eq!(fb[offset + 1], 255);
            assert_eq!(fb[offset + 2], 0);
        } else {
            assert_eq!(fb[offset], 0, "Pixel {} should be blue", i);
            assert_eq!(fb[offset + 1], 0);
            assert_eq!(fb[offset + 2], 255);
        }
    }
}

#[test]
fn test_zrle_palette_rle_single_pixels() {
    let mut decoder = ZrleDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 4 * 4 * 4];

    // Palette RLE with single pixels (no run length byte)
    let mut tile_data = vec![
        0x81, // Subencoding 129 = Palette RLE
        0x01, // Palette size - 1 (2 colors)
        255, 0, 0,     // Color 0: Red
        0, 0, 255,     // Color 1: Blue
    ];

    // 16 pixels alternating: red, blue, red, blue...
    for i in 0..16 {
        tile_data.push(i % 2); // Index 0 or 1, no run length (bit 7 not set)
    }

    let compressed = compress_zlib(&tile_data);
    let compressed_len = compressed.len() as u32;

    let mut data = write_u32_be(compressed_len);
    data.extend_from_slice(&compressed);

    decoder
        .decode(&data, 0, 0, 4, 4, &mut fb, 4, &pixel_format)
        .unwrap();

    // Verify alternating pattern
    for i in 0..16 {
        let offset = i * 4;
        if i % 2 == 0 {
            assert_eq!(fb[offset], 255, "Pixel {} red", i);
            assert_eq!(fb[offset + 2], 0, "Pixel {} blue", i);
        } else {
            assert_eq!(fb[offset], 0, "Pixel {} red", i);
            assert_eq!(fb[offset + 2], 255, "Pixel {} blue", i);
        }
    }
}

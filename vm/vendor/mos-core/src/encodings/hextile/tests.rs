//! Hextile decoder tests

use super::*;
use crate::core::PixelFormat;

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

#[test]
fn test_hextile_raw_tile() {
    let mut decoder = HextileDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 16 * 16 * 4];

    // Raw tile: subencoding = 0x01, then 16x16 pixels
    let mut data = vec![0x01]; // RAW flag
    // Fill with red pixels
    for _ in 0..(16 * 16) {
        data.extend_from_slice(&[255, 0, 0, 255]); // Red
    }

    decoder
        .decode(&data, 0, 0, 16, 16, &mut fb, 16, &pixel_format)
        .unwrap();

    // Check first pixel is red
    assert_eq!(fb[0], 255);
    assert_eq!(fb[1], 0);
    assert_eq!(fb[2], 0);
}

#[test]
fn test_hextile_background_only() {
    let mut decoder = HextileDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 16 * 16 * 4];

    // Background specified, no subrects
    let data = vec![
        0x02, // BACKGROUND_SPECIFIED
        0, 255, 0, 255, // Green background
    ];

    decoder
        .decode(&data, 0, 0, 16, 16, &mut fb, 16, &pixel_format)
        .unwrap();

    // Check all pixels are green
    for i in 0..16 * 16 {
        let offset = i * 4;
        assert_eq!(fb[offset], 0);
        assert_eq!(fb[offset + 1], 255);
        assert_eq!(fb[offset + 2], 0);
    }
}

#[test]
fn test_hextile_with_subrect() {
    let mut decoder = HextileDecoder::new();
    let pixel_format = create_test_pixel_format();

    let mut fb = vec![0u8; 16 * 16 * 4];

    // Background + foreground + one subrect
    let data = vec![
        0x0E, // BACKGROUND_SPECIFIED | FOREGROUND_SPECIFIED | ANY_SUBRECTS
        0, 0, 255, 255, // Blue background
        255, 0, 0, 255, // Red foreground
        1,    // 1 subrectangle
        0x00, // xy: x=0, y=0
        0x00, // wh: w=1, h=1 (encoded as 0,0)
    ];

    decoder
        .decode(&data, 0, 0, 16, 16, &mut fb, 16, &pixel_format)
        .unwrap();

    // Check (0,0) is red (subrect)
    assert_eq!(fb[0], 255);
    assert_eq!(fb[1], 0);
    assert_eq!(fb[2], 0);

    // Check (1,1) is blue (background)
    let offset = (1 * 16 + 1) * 4;
    assert_eq!(fb[offset], 0);
    assert_eq!(fb[offset + 1], 0);
    assert_eq!(fb[offset + 2], 255);
}

#[test]
fn test_hextile_encoding_type() {
    let decoder = HextileDecoder::new();
    assert_eq!(decoder.encoding_type(), EncodingType::Hextile);
}

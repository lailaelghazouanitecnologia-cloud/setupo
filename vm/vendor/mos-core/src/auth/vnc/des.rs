//! DES encryption for VNC authentication
//!
//! VNC uses DES encryption with a quirky bit order.

use crate::utils::{MosError, MosResult};

/// Encrypt a 16-byte challenge with password using DES
pub fn des_encrypt_challenge(challenge: &[u8; 16], password: &str) -> MosResult<[u8; 16]> {
    // VNC password is max 8 characters, padded with nulls
    let mut key = [0u8; 8];
    let password_bytes = password.as_bytes();
    let len = password_bytes.len().min(8);
    key[..len].copy_from_slice(&password_bytes[..len]);

    // VNC uses a quirky bit order - need to reverse bits in each byte
    let key = reverse_bits_in_bytes(&key);

    // Encrypt using DES
    let encrypted = des_encrypt_block(&challenge[0..8], &key)?;
    let mut result = [0u8; 16];
    result[0..8].copy_from_slice(&encrypted);

    let encrypted = des_encrypt_block(&challenge[8..16], &key)?;
    result[8..16].copy_from_slice(&encrypted);

    Ok(result)
}

/// Reverse bits in each byte of the array
fn reverse_bits_in_bytes(bytes: &[u8; 8]) -> [u8; 8] {
    let mut result = [0u8; 8];
    for (i, &byte) in bytes.iter().enumerate() {
        result[i] = reverse_bits(byte);
    }
    result
}

/// Reverse bits in a single byte
fn reverse_bits(byte: u8) -> u8 {
    let mut result = 0u8;
    for i in 0..8 {
        if byte & (1 << i) != 0 {
            result |= 1 << (7 - i);
        }
    }
    result
}

/// DES encrypt a single 8-byte block
fn des_encrypt_block(data: &[u8], key: &[u8; 8]) -> MosResult<[u8; 8]> {
    use des::cipher::{BlockEncrypt, KeyInit};
    use des::Des;

    let cipher = Des::new_from_slice(key)
        .map_err(|e| MosError::auth(format!("DES key error: {}", e)))?;

    let mut block = [0u8; 8];
    block.copy_from_slice(data);

    let block = des::cipher::generic_array::GenericArray::from(block);
    let mut encrypted_block = block;
    cipher.encrypt_block(&mut encrypted_block);

    Ok(encrypted_block.into())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_reverse_bits() {
        assert_eq!(reverse_bits(0b00000001), 0b10000000);
        assert_eq!(reverse_bits(0b10101010), 0b01010101);
        assert_eq!(reverse_bits(0b11110000), 0b00001111);
    }

    #[test]
    fn test_reverse_bits_in_bytes() {
        let input = [0b00000001, 0b00000010, 0, 0, 0, 0, 0, 0];
        let output = reverse_bits_in_bytes(&input);
        assert_eq!(output[0], 0b10000000);
        assert_eq!(output[1], 0b01000000);
    }

    #[test]
    fn test_des_encrypt_challenge() {
        let challenge = [0u8; 16];
        let password = "test";
        let result = des_encrypt_challenge(&challenge, password);
        assert!(result.is_ok());
    }

    #[test]
    fn test_long_password_truncated() {
        let challenge = [0u8; 16];
        let password = "verylongpassword";
        let result = des_encrypt_challenge(&challenge, password);
        assert!(result.is_ok());
    }
}

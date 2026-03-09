# mos-core

**Headless VNC/RFB client library for Rust**

A fast, async, platform-independent VNC client implementation with zero UI dependencies.

## Features

✅ **Headless & Platform-Independent**
- No Tauri, GTK, or WebKit dependencies
- Works on any platform that supports Rust
- Can be embedded in any application

✅ **Full RFB Protocol Support**
- RFB versions: 3.3, 3.7, 3.8
- Authentication: None, VNC (DES)
- Client-to-server messages: Key events, pointer events, framebuffer updates
- Server-to-client messages: Framebuffer updates

✅ **Multiple Encodings (7)**
- **Tight** - Most efficient (zlib + palette + fill compression)
- **ZRLE** - Zlib Run-Length Encoding (64x64 tiles)
- **Zlib** - Simple zlib compression (general purpose)
- **CopyRect** - Efficient rectangle copying (scrolling)
- **Hextile** - 16x16 tile-based encoding
- **RRE** - Rise-and-Run-length Encoding (solid colors)
- **Raw** - Uncompressed pixel data (fallback)

✅ **Async/Await**
- Built on Tokio for efficient async I/O
- Non-blocking operations throughout

✅ **Zero-Copy Buffers**
- Ring buffer implementation for efficient network I/O
- Minimal allocations

## Installation

Add to your `Cargo.toml`:

```toml
[dependencies]
mos-core = { path = "../mos-core" }
tokio = { version = "1.40", features = ["full"] }
```

## Quick Start

```rust
use mos_core::prelude::*;

#[tokio::main]
async fn main() -> MosResult<()> {
    // Create client configuration
    let config = ConnectionConfig::builder()
        .host("localhost")
        .port(5900)
        .password(Some("secret"))
        .build()?;

    // Create and connect client
    let mut client = RfbClient::new(config);
    client.connect().await?;

    // Get server information
    if let Some(server_info) = client.server_info() {
        println!("Connected to: {}", server_info.name);
        println!("Resolution: {}x{}", server_info.width, server_info.height);
    }

    // Request initial framebuffer update
    let (width, height) = client.framebuffer_size();
    client.request_update(false, 0, 0, width, height).await?;

    // Process server messages
    loop {
        if client.process_message().await? {
            // Framebuffer was updated
            let fb = client.framebuffer();
            // Do something with framebuffer data...
        }
    }

    Ok(())
}
```

## Examples

### Simple Connection

```rust
use mos_core::prelude::*;

#[tokio::main]
async fn main() -> MosResult<()> {
    let config = ConnectionConfig::builder()
        .host("192.168.1.100")
        .port(5900)
        .build()?;

    let mut client = RfbClient::new(config);
    client.connect().await?;

    println!("State: {:?}", client.state());
    Ok(())
}
```

### Send Input Events

```rust
// Send key press
client.send_key_event(true, 0x0041).await?;  // Press 'A'
client.send_key_event(false, 0x0041).await?; // Release 'A'

// Send mouse movement
client.send_pointer_event(0x00, 100, 200).await?; // Move to (100, 200)

// Send mouse click
client.send_pointer_event(0x01, 100, 200).await?; // Left button down
client.send_pointer_event(0x00, 100, 200).await?; // Release
```

### Configuration Options

```rust
use std::time::Duration;

let config = ConnectionConfig::builder()
    .host("vnc.example.com")
    .port(5901)
    .password(Some("password123"))
    .shared(true)  // Share desktop with other clients
    .network_config(
        NetworkConfig::builder()
            .connect_timeout(Duration::from_secs(10))
            .read_timeout(Duration::from_secs(30))
            .tcp_nodelay(true)
            .build()
    )
    .build()?;
```

## Architecture

```
mos-core/
├── utils/       - Error handling, byte operations, metrics
├── network/     - Async TCP, ring buffers
├── core/        - RFB protocol, client implementation
├── auth/        - Authentication handlers (None, VNC)
└── encodings/   - Decoder implementations (Raw, CopyRect, RRE, Hextile)
```

## Testing

```bash
# Run all tests
cargo test -p mos-core

# Run unit tests only
cargo test -p mos-core --lib

# Run integration tests
cargo test -p mos-core --test integration_test

# Run specific module tests
cargo test -p mos-core --lib encodings::hextile
```

## Performance

- **Zero-copy buffers** for efficient network I/O
- **Async I/O** with Tokio for minimal overhead
- **Native Rust** performance (vs JavaScript-based clients)
- **Efficient encodings** (CopyRect, Hextile, RRE)

Target: **4-5x faster than noVNC**

## API Documentation

### Core Types

- **`RfbClient`** - Main VNC client
- **`ConnectionConfig`** - Connection configuration with builder pattern
- **`ClientState`** - Connection state (Disconnected, Handshaking, etc.)
- **`PixelFormat`** - Pixel format specification
- **`EncodingType`** - Available encoding types

### Client Methods

```rust
impl RfbClient {
    pub fn new(config: ConnectionConfig) -> Self;
    pub async fn connect(&mut self) -> MosResult<()>;
    pub async fn disconnect(&mut self) -> MosResult<()>;
    pub async fn process_message(&mut self) -> MosResult<bool>;
    pub async fn request_update(&mut self, incremental: bool, x: u16, y: u16, width: u16, height: u16) -> MosResult<()>;
    pub async fn send_key_event(&mut self, down: bool, key: u32) -> MosResult<()>;
    pub async fn send_pointer_event(&mut self, button_mask: u8, x: u16, y: u16) -> MosResult<()>;
    pub fn state(&self) -> ClientState;
    pub fn framebuffer(&self) -> &[u8];
    pub fn framebuffer_size(&self) -> (u16, u16);
    pub fn server_info(&self) -> Option<&ServerInit>;
}
```

## Error Handling

All operations return `MosResult<T>` which is an alias for `Result<T, MosError>`.

```rust
use mos_core::prelude::*;

match client.connect().await {
    Ok(_) => println!("Connected!"),
    Err(MosError::Connection(msg)) => eprintln!("Connection error: {}", msg),
    Err(MosError::Protocol(msg)) => eprintln!("Protocol error: {}", msg),
    Err(MosError::Authentication(msg)) => eprintln!("Auth error: {}", msg),
    Err(e) => eprintln!("Other error: {}", e),
}
```

## Supported Platforms

- ✅ Linux
- ✅ macOS
- ✅ Windows
- ✅ Any platform with Rust and Tokio support

## Requirements

- Rust 1.75 or later
- Tokio runtime

## License

See LICENSE file in the repository root.

## Contributing

This is a headless library - no UI dependencies allowed!

When contributing:
- Keep files under 350 lines
- Add tests for new features
- Follow existing code style
- Run `cargo test -p mos-core` before submitting

## Roadmap

### Implemented ✅
- [x] RFB 3.3, 3.7, 3.8 protocol support
- [x] None and VNC authentication
- [x] Raw, CopyRect, RRE, Hextile encodings
- [x] Async I/O with Tokio
- [x] Zero-copy ring buffers

### Planned 🚀
- [ ] Tight encoding (high priority - best compression)
- [ ] ZRLE encoding
- [ ] Clipboard support
- [ ] Desktop resize events
- [ ] Additional auth methods (RA2, Tight, VeNCrypt)
- [ ] Connection pooling
- [ ] Reconnection support

## See Also

- **mos-tauri** - Desktop VNC client using mos-core
- [RFB Protocol Specification](https://datatracker.ietf.org/doc/html/rfc6143)

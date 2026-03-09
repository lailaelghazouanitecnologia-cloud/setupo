# mos-gateway

`mos-gateway` is the web-facing bridge between NSO and `mos-core`.

It exists so the platform can own remote desktop end-to-end without embedding
Rust inside the Python API and without depending on Tauri.

## Goal

Turn a VNC server into an NSO-managed web session:

- NSO backend stores node-level remote desktop settings
- agent or host launches `mos-gateway`
- `mos-gateway` uses `mos-core` to talk RFB/VNC over TCP
- dashboard connects to `mos-gateway` over HTTP/WebSocket

## Why this shape

`mos-core` is reusable. `mos-tauri` is not.

The gateway keeps boundaries clean:

- Python keeps auth, tenancy, audit, secrets, node ownership
- Rust keeps framebuffer decoding, input, session timing
- Web UI only needs standard browser APIs

## Planned API

- `GET /health`
- `POST /sessions`
- `GET /sessions/:id`
- `DELETE /sessions/:id`
- `GET /sessions/:id/framebuffer`
- `WS /sessions/:id/stream`
- `POST /sessions/:id/input`
- `POST /sessions/:id/clipboard`

## NSO integration plan

1. Add node-level remote desktop config in central API.
2. Add agent route to manage `mos-gateway` process and local bind port.
3. Reverse proxy `/agent/remote/...` through nginx.
4. Add a `Remote Desktop` card in the `System` panel.
5. Start with one live session per node, then add pooling later.

## Current state

This folder is an initial scaffold. It already defines:

- a minimal HTTP server
- in-memory session registry
- stable request/response models
- a placeholder point where `mos-core::RfbClient` will be wired in

Next implementation step:

- move the placeholder session connect path to a real `RfbClient::connect()`
- add a background loop that requests framebuffer updates
- stream rectangles or frame snapshots over WebSocket

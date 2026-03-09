## WebRTC Remote Desktop Plan

Current remote desktop works, but the transport is still too expensive:

- VNC server produces framebuffer updates
- `mos-core` decodes them
- `mos-gateway` emits raw RGBA frames
- `nso-agent` proxies them
- browser paints a full frame into canvas

That path is functional, not efficient.

### Target architecture

Use WebRTC for media and DataChannel for control:

1. VNC server or capture source on the node
2. `mos-gateway` owns the WebRTC peer connection
3. `mos-gateway` encodes screen video as `H.264`
4. Browser receives video through WebRTC
5. Keyboard and pointer go through WebRTC DataChannel
6. `nso-agent` remains auth and control plane, not the hot path for every frame

### Why this is the right next step

- lower latency than raw frame shipping
- less bandwidth than RGBA or base64
- better browser decode path
- cleaner split between control plane and media plane

### Recommended implementation order

1. Signaling scaffold

- `POST /agent/remote/sessions/:id/webrtc/offer`
- `POST /agent/remote/sessions/:id/webrtc/ice`
- mirror endpoints in `mos-gateway`

2. WebRTC peer connection in `mos-gateway`

- add `webrtc-rs`
- create peer connection per remote session
- create DataChannel for input/control

3. H.264 media path

- first practical approach: feed frames into an ffmpeg process and publish encoded output into WebRTC
- preferred codec for first version: `H.264`
- avoid AV1 first; it is not the best latency/complexity tradeoff for this product phase

4. Browser viewer

- `RTCPeerConnection`
- DataChannel for keyboard, mouse, clipboard
- `<video>` element for remote display
- keep canvas fallback during migration

5. Remove raw-frame hot path

- keep `/framebuffer` only as debug fallback
- demote `/stream` raw WS to troubleshooting

### First concrete milestone

The first milestone is not “perfect remote desktop”.
It is:

- signaling works
- browser can create offer
- gateway returns answer
- a muted low-resolution H.264 track renders in a `<video>`
- DataChannel sends pointer and key events

Once that works, quality and tuning become iterative.

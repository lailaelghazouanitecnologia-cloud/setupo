# Remote Desktop Current Setup

This document describes the remote desktop setup that is currently working on the NSO VPS.

It reflects the real path in production today, not the older experimental raw-frame viewer.

## Current Result

The working viewer is:

- browser -> `noVNC`
- `noVNC` -> WebSocket tunnel on `nso-agent`
- `nso-agent` -> local TCP to `TigerVNC`
- `TigerVNC` -> X11 session `:1`
- X11 session `:1` -> `XFCE`
- apps inside XFCE -> `Chromium`, `Thunar`, terminal, etc.

This is why render latency is now much better than the old custom pipeline.

## Why It Improved

The previous approach moved custom frame data through our own stack:

- custom capture
- custom frame conversion
- custom transport
- custom canvas paint

That added CPU cost, copies, and latency.

The current approach uses `noVNC`, which already speaks VNC efficiently:

- rect-based VNC updates
- mature browser-side decoder
- direct VNC protocol path over WebSocket

So the browser is no longer waiting on our raw RGBA viewer.

## Production Pieces

### 1. VNC server

The VPS runs `TigerVNC` on localhost only:

- host: `127.0.0.1`
- port: `5901`
- display: `:1`

It is started with no VNC password because it is only exposed locally and accessed through the authenticated agent tunnel.

### 2. Desktop session

The VNC display now starts `XFCE` instead of the old minimal `xterm` session.

Current startup file:

- `/root/.vnc/xstartup`

It runs:

- `dbus-launch --exit-with-session startxfce4`

### 3. Browser UI

The dashboard route is:

- `/remote`

File:

- `client/dashboard/src/app/remote/page.tsx`

The viewer component is:

- `client/dashboard/src/components/remote/novnc-viewer.tsx`

It uses `@novnc/novnc`.

### 4. Agent tunnel

The WebSocket VNC tunnel lives in:

- `vm/agent/remote.py`

Route:

- `GET/WS /agent/remote/vnc?token=...&host=127.0.0.1&port=5901`

This route:

- verifies the agent token
- opens TCP to the target VNC server
- proxies bytes both directions

### 5. Keyboard bridge

Render is handled by `noVNC`, but keyboard input on the canvas was unreliable in this environment.

So for the local demo session we added a bridge through the agent:

- `POST /agent/remote/local/type`
- `POST /agent/remote/local/key`
- `POST /agent/remote/local/browser`

These routes use:

- `xdotool`

against:

- `DISPLAY=:1`

This lets the browser tell the VPS to:

- type text
- send special keys
- open Chromium

## VPS Packages Installed

These were installed to move from the test terminal to a real desktop:

- `xfce4`
- `xfce4-goodies`
- `dbus-x11`
- `xfce4-terminal`
- `thunar`
- `xdotool`
- `chromium`

## How To Reproduce On A Fresh VPS

### 1. Install desktop packages

```bash
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y \
  tigervnc-standalone-server \
  xfce4 xfce4-goodies dbus-x11 xfce4-terminal thunar \
  xdotool chromium
```

### 2. Configure VNC startup

Write `/root/.vnc/xstartup`:

```sh
#!/bin/sh
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_SESSION_DESKTOP=xfce
export XDG_CURRENT_DESKTOP=XFCE
export XDG_SESSION_TYPE=x11
exec dbus-launch --exit-with-session startxfce4
```

Then:

```bash
chmod +x /root/.vnc/xstartup
```

### 3. Start the VNC desktop

```bash
vncserver :1 -localhost yes -SecurityTypes None -geometry 1280x800 -depth 24
```

### 4. Make sure the agent routes exist

Required routes in `vm/agent/remote.py`:

- `/remote/vnc`
- `/remote/local/type`
- `/remote/local/key`
- `/remote/local/browser`

### 5. Build and publish the dashboard

From `client/dashboard`:

```bash
bun install
bun run export
```

Publish the exported files to:

- `/opt/nso/client/dashboard`

## Current Limitations

### Keyboard

The image path is now good, but keyboard handling is still mixed:

- render path: `noVNC`
- keyboard fallback for the local demo: `xdotool`

This works, but it is still a workaround.

The clean end state would be:

- `noVNC` handles both render and input correctly

or:

- a future WebRTC/native input path replaces this entirely

### Resolution

The VNC desktop can resize down to the current browser container because the viewer enables resize behavior.

That is why the session may show sizes like:

- `906x520`

even if VNC was initially started at `1280x800`.

### Security

The local test VNC session is intentionally loose:

- no VNC password
- localhost-only exposure
- access through authenticated agent tunnel

This is acceptable for the current internal test setup, but not the final production model for arbitrary nodes.

## Files To Know

- `client/dashboard/src/app/remote/page.tsx`
- `client/dashboard/src/components/remote/novnc-viewer.tsx`
- `vm/agent/remote.py`
- `deploy/REMOTE_DESKTOP_CURRENT_SETUP.md`
- `deploy/WEBRTC_REMOTE_DESKTOP.md`
- `deploy/MOS_GATEWAY_INTEGRATION.md`

## Recommended Next Step

Keep this `noVNC + TigerVNC + XFCE` path as the stable baseline.

If we continue improving remote desktop, the safest order is:

1. stabilize keyboard and focus behavior
2. keep Chromium/desktop launch simple
3. add per-node remote desktop install flow
4. revisit WebRTC only after the stable baseline remains available

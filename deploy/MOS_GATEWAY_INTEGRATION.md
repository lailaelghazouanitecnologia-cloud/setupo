# MOS Gateway Integration

This document defines how `mos-core` should land inside NSO.

## Scope

The goal is remote desktop for nodes from the `System` area of the dashboard.

This is not file browsing, shell execution, or process introspection. Those
already exist through the agent. This is only framebuffer + input + clipboard.

## Component split

### Central API

Owns:

- project and node ownership
- auth and permissions
- remote desktop configuration per node
- audit trail for session open/close
- issuing short-lived session tokens

### Agent

Owns:

- local process management for `mos-gateway`
- local port binding
- verifying that the target VNC endpoint is reachable
- reverse-proxying or tunneling traffic to the gateway

### mos-gateway

Owns:

- live VNC session state
- `mos-core::RfbClient`
- framebuffer polling
- input forwarding
- clipboard synchronization
- frame stream protocol for the browser

### Dashboard

Owns:

- `Remote Desktop` card in `System`
- session create/open/close UX
- canvas rendering
- sending mouse and keyboard events

## Recommended first data model

Store this on the node metadata or a dedicated table later:

```json
{
  "remote_desktop": {
    "enabled": true,
    "provider": "vnc",
    "host": "127.0.0.1",
    "port": 5901,
    "password_secret": "RD_VNC_PASSWORD",
    "via_agent": true
  }
}
```

## Recommended first routes

### Central API

- `POST /api/projects/:project_id/nodes/:node_id/remote/session`
- `DELETE /api/projects/:project_id/nodes/:node_id/remote/session/:session_id`
- `GET /api/projects/:project_id/nodes/:node_id/remote/config`
- `PUT /api/projects/:project_id/nodes/:node_id/remote/config`

### Agent

- `POST /remote/sessions`
- `GET /remote/sessions/:id`
- `DELETE /remote/sessions/:id`
- `GET /remote/sessions/:id/framebuffer`
- `WS /remote/sessions/:id/stream`
- `POST /remote/sessions/:id/input`
- `POST /remote/sessions/:id/clipboard`

The agent can either proxy these to `mos-gateway` or run them directly if the
gateway is embedded later.

## Why not Tauri

`mos-tauri` is a desktop shell. NSO needs:

- multi-tenant auth
- browser access
- reverse proxy support
- node-to-session permissions
- agent-managed lifecycle

That means `mos-core` is the right reusable layer and `mos-tauri` is not.

## First milestone

1. Launch `mos-gateway` beside the agent.
2. Open one VNC session manually for one node.
3. Render full framebuffer snapshots in browser.
4. Send mouse clicks and key presses.
5. Add clipboard.

Only after that should frame diffing, pooling, and multi-session routing be
optimized.

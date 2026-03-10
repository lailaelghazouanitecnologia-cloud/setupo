use std::{
    collections::HashMap,
    net::SocketAddr,
    sync::Arc,
    time::{SystemTime, UNIX_EPOCH},
};

use anyhow::Result;
use axum::{
    extract::{ws::Message, Path, State, WebSocketUpgrade},
    http::StatusCode,
    response::IntoResponse,
    routing::{get, post},
    Json, Router,
};
use base64::{engine::general_purpose::STANDARD as BASE64, Engine as _};
use mos_core::{
    core::{constants, PixelFormat},
    ClientState, ConnectionConfig, RfbClient,
};
use serde::{Deserialize, Serialize};
use tokio::sync::{broadcast, Mutex, RwLock};
use tokio::time::{timeout, Duration};
use tracing::{error, info, warn};
use uuid::Uuid;
use interceptor::registry::Registry;
use webrtc::{
    api::{
        interceptor_registry::register_default_interceptors,
        media_engine::{MediaEngine, MIME_TYPE_H264},
        APIBuilder,
    },
    data_channel::{data_channel_message::DataChannelMessage, RTCDataChannel},
    ice_transport::ice_candidate::RTCIceCandidateInit,
    peer_connection::{
        configuration::RTCConfiguration,
        peer_connection_state::RTCPeerConnectionState,
        sdp::session_description::RTCSessionDescription,
        RTCPeerConnection,
    },
    rtp_transceiver::rtp_codec::RTCRtpCodecCapability,
    track::track_local::{
        track_local_static_rtp::TrackLocalStaticRTP, TrackLocal, TrackLocalWriter,
    },
    util::Unmarshal,
};

#[derive(Clone)]
struct AppState {
    sessions: Arc<RwLock<HashMap<Uuid, Arc<SessionHandle>>>>,
}

const SESSION_IDLE_TTL_MS: u64 = 5 * 60 * 1000;
const MAX_ACTIVE_SESSIONS: usize = 4;

struct SessionHandle {
    meta: RwLock<SessionRecord>,
    client: Mutex<Option<RfbClient>>,
    peer_connection: Mutex<Option<Arc<RTCPeerConnection>>>,
    video_process: Mutex<Option<tokio::process::Child>>,
    framebuffer: RwLock<FramebufferState>,
    stream_tx: broadcast::Sender<FrameEvent>,
}

#[derive(Clone, Serialize)]
struct SessionRecord {
    id: Uuid,
    host: String,
    port: u16,
    name: String,
    state: SessionState,
    created_at_ms: u64,
    updated_at_ms: u64,
    last_error: Option<String>,
}

#[derive(Clone, Copy, Serialize)]
#[serde(rename_all = "snake_case")]
enum SessionState {
    Connecting,
    Connected,
    Closed,
    Error,
}

#[derive(Clone, Default)]
struct FramebufferState {
    width: u16,
    height: u16,
    data: Vec<u8>,
    sequence: u64,
    updated_at_ms: u64,
}

#[derive(Clone)]
struct FrameEvent {
    session_id: Uuid,
    sequence: u64,
    width: u16,
    height: u16,
    updated_at_ms: u64,
    patches: Vec<FramePatch>,
}

#[derive(Clone)]
struct FramePatch {
    x: u16,
    y: u16,
    width: u16,
    height: u16,
    data: Vec<u8>,
}

#[derive(Deserialize)]
struct CreateSessionRequest {
    host: String,
    port: u16,
    password: Option<String>,
    name: Option<String>,
}

#[derive(Serialize)]
struct CreateSessionResponse {
    session: SessionRecord,
    stream_path: String,
    framebuffer_path: String,
}

#[derive(Serialize)]
struct HealthResponse {
    ok: bool,
    service: &'static str,
    sessions: usize,
}

#[derive(Serialize)]
struct FramebufferResponse {
    session_id: Uuid,
    sequence: u64,
    width: u16,
    height: u16,
    encoding: &'static str,
    updated_at_ms: u64,
    data: String,
}

#[derive(Deserialize)]
struct InputEventRequest {
    kind: String,
    x: Option<u16>,
    y: Option<u16>,
    buttons: Option<u8>,
    key: Option<u32>,
    down: Option<bool>,
}

#[derive(Deserialize)]
struct ClipboardRequest {
    text: String,
}

#[derive(Deserialize)]
#[serde(tag = "type", rename_all = "snake_case")]
enum WebRtcInputMessage {
    Input {
        kind: String,
        x: Option<u16>,
        y: Option<u16>,
        buttons: Option<u8>,
        key: Option<u32>,
        down: Option<bool>,
    },
    Clipboard {
        text: String,
    },
    Ping,
}

#[derive(Deserialize)]
struct WebRtcOfferRequest {
    sdp: String,
    #[serde(default)]
    codec: Option<String>,
}

#[derive(Serialize)]
struct WebRtcOfferResponse {
    ok: bool,
    mode: &'static str,
    session_id: Uuid,
    answer_sdp: String,
    codec: String,
    note: &'static str,
}

#[derive(Deserialize)]
struct WebRtcIceRequest {
    candidate: String,
    #[serde(default)]
    sdp_mid: Option<String>,
    #[serde(default)]
    sdp_mline_index: Option<u16>,
}

#[tokio::main]
async fn main() -> Result<()> {
    tracing_subscriber::fmt()
        .with_env_filter(
            std::env::var("MOS_GATEWAY_LOG")
                .unwrap_or_else(|_| "mos_gateway=info,axum=info".to_string()),
        )
        .init();

    let bind = std::env::var("MOS_GATEWAY_BIND").unwrap_or_else(|_| "127.0.0.1:8091".to_string());
    let addr: SocketAddr = bind.parse()?;
    let state = AppState {
        sessions: Arc::new(RwLock::new(HashMap::new())),
    };
    tokio::spawn(session_reaper(state.clone()));

    let app = Router::new()
        .route("/health", get(health))
        .route("/sessions", post(create_session))
        .route("/sessions/:id", get(get_session).delete(delete_session))
        .route("/sessions/:id/framebuffer", get(get_framebuffer))
        .route("/sessions/:id/stream", get(stream_session))
        .route("/sessions/:id/webrtc/offer", post(webrtc_offer))
        .route("/sessions/:id/webrtc/ice", post(webrtc_ice))
        .route("/sessions/:id/input", post(send_input))
        .route("/sessions/:id/clipboard", post(send_clipboard))
        .with_state(state);

    info!("mos-gateway listening on {addr}");
    let listener = tokio::net::TcpListener::bind(addr).await?;
    axum::serve(listener, app).await?;
    Ok(())
}

async fn health(State(state): State<AppState>) -> Json<HealthResponse> {
    Json(HealthResponse {
        ok: true,
        service: "mos-gateway",
        sessions: state.sessions.read().await.len(),
    })
}

async fn create_session(
    State(state): State<AppState>,
    Json(req): Json<CreateSessionRequest>,
) -> Result<Json<CreateSessionResponse>, (StatusCode, String)> {
    if req.host.trim().is_empty() {
        return Err((StatusCode::BAD_REQUEST, "host is required".to_string()));
    }

    let mut duplicates = Vec::new();
    let mut overflow = Vec::new();
    {
        let sessions = state.sessions.read().await;
        for handle in sessions.values() {
            let meta = handle.meta.read().await;
            if meta.host == req.host && meta.port == req.port {
                duplicates.push(meta.id);
            }
        }

        if sessions.len() >= MAX_ACTIVE_SESSIONS {
            let mut ordered = Vec::with_capacity(sessions.len());
            for handle in sessions.values() {
                let meta = handle.meta.read().await.clone();
                ordered.push((meta.updated_at_ms, meta.id));
            }
            ordered.sort_by_key(|(updated_at_ms, _)| *updated_at_ms);
            let remove_count = sessions.len().saturating_sub(MAX_ACTIVE_SESSIONS) + 1;
            overflow.extend(ordered.into_iter().take(remove_count).map(|(_, id)| id));
        }
    }

    for id in duplicates.into_iter().chain(overflow.into_iter()) {
        close_session(&state, id).await;
    }

    let created_at_ms = now_ms();
    let session = SessionRecord {
        id: Uuid::new_v4(),
        host: req.host.clone(),
        port: req.port,
        name: req.name.unwrap_or_else(|| format!("{}:{}", req.host, req.port)),
        state: SessionState::Connecting,
        created_at_ms,
        updated_at_ms: created_at_ms,
        last_error: None,
    };

    let (stream_tx, _) = broadcast::channel(24);
    let handle = Arc::new(SessionHandle {
        meta: RwLock::new(session.clone()),
        client: Mutex::new(None),
        peer_connection: Mutex::new(None),
        video_process: Mutex::new(None),
        framebuffer: RwLock::new(FramebufferState::default()),
        stream_tx,
    });

    state.sessions.write().await.insert(session.id, handle.clone());

    let mut config = ConnectionConfig::new(req.host.clone(), req.port);
    if let Some(password) = req.password {
        config = config.with_password(password);
    }
    config = config.with_shared(true);
    config.preferred_encodings = vec![
        constants::encoding::COPY_RECT,
        constants::encoding::HEXTILE,
        constants::encoding::RRE,
        constants::encoding::RAW,
        constants::pseudo_encoding::CURSOR,
        constants::pseudo_encoding::DESKTOP_SIZE,
    ];

    tokio::spawn(run_session(handle, config));

    Ok(Json(CreateSessionResponse {
        stream_path: format!("/sessions/{}/stream", session.id),
        framebuffer_path: format!("/sessions/{}/framebuffer", session.id),
        session,
    }))
}

async fn get_session(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<SessionRecord>, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
    let meta = handle.meta.read().await.clone();
    Ok(Json(meta))
}

async fn delete_session(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let removed = close_session(&state, id).await;
    if !removed {
        return Err((StatusCode::NOT_FOUND, "session not found".to_string()));
    }

    Ok(Json(serde_json::json!({ "ok": true, "session_id": id })))
}

async fn get_framebuffer(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<FramebufferResponse>, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
    touch_session(&handle).await;
    let fb = handle.framebuffer.read().await.clone();

    Ok(Json(FramebufferResponse {
        session_id: id,
        sequence: fb.sequence,
        width: fb.width,
        height: fb.height,
        encoding: "raw",
        updated_at_ms: fb.updated_at_ms,
        data: BASE64.encode(fb.data),
    }))
}

async fn stream_session(
    ws: WebSocketUpgrade,
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<impl IntoResponse, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
    touch_session(&handle).await;
    let initial_meta = handle.meta.read().await.clone();
    let initial_fb = handle.framebuffer.read().await.clone();
    let mut rx = handle.stream_tx.subscribe();

    Ok(ws.on_upgrade(move |mut socket| async move {
        let _ = socket
            .send(Message::Text(
                serde_json::json!({
                    "type": "session",
                    "session": initial_meta,
                })
                .to_string(),
            ))
            .await;

        if !initial_fb.data.is_empty() {
            let event = FrameEvent {
                session_id: id,
                sequence: initial_fb.sequence,
                width: initial_fb.width,
                height: initial_fb.height,
                updated_at_ms: initial_fb.updated_at_ms,
                patches: vec![FramePatch {
                    x: 0,
                    y: 0,
                    width: initial_fb.width,
                    height: initial_fb.height,
                    data: initial_fb.data,
                }],
            };
            let _ = socket.send(Message::Binary(encode_frame_packet(&event))).await;
        }

        loop {
            match rx.recv().await {
                Ok(event) => {
                    if socket
                        .send(Message::Binary(encode_frame_packet(&event)))
                        .await
                        .is_err()
                    {
                        break;
                    }
                }
                Err(tokio::sync::broadcast::error::RecvError::Lagged(skipped)) => {
                    warn!("stream lagged for session {id}: skipped {skipped} frames");
                }
                Err(tokio::sync::broadcast::error::RecvError::Closed) => break,
            }
        }
    }))
}

async fn send_input(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<InputEventRequest>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
    touch_session(&handle).await;
    apply_input_event(&handle, &req).await?;

    Ok(Json(serde_json::json!({ "ok": true, "session_id": id })))
}

async fn send_clipboard(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<ClipboardRequest>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
    touch_session(&handle).await;
    apply_clipboard(&handle, &req.text).await?;

    Ok(Json(serde_json::json!({
        "ok": true,
        "session_id": id,
        "bytes": req.text.len()
    })))
}

async fn webrtc_offer(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<WebRtcOfferRequest>,
) -> Result<Json<WebRtcOfferResponse>, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
    touch_session(&handle).await;
    let codec = req.codec.unwrap_or_else(|| "h264".to_string());
    if req.sdp.trim().is_empty() {
        return Err((StatusCode::BAD_REQUEST, "offer SDP is required".to_string()));
    }

    let pc = create_peer_connection(id).await.map_err(internal_error)?;
    attach_input_channel(&pc, handle.clone(), id);
    attach_video_track(&pc, handle.clone(), id)
        .await
        .map_err(internal_error)?;
    pc.set_remote_description(RTCSessionDescription::offer(req.sdp).map_err(internal_error)?)
        .await
        .map_err(internal_error)?;

    let answer = pc.create_answer(None).await.map_err(internal_error)?;
    pc.set_local_description(answer).await.map_err(internal_error)?;

    let mut gather_complete = pc.gathering_complete_promise().await;
    let _ = gather_complete.recv().await;
    let local = pc.local_description().await.ok_or((
        StatusCode::BAD_GATEWAY,
        "webrtc local description missing".to_string(),
    ))?;

    let note = "Peer connection created. Media track is not attached yet.";
    let mut slot = handle.peer_connection.lock().await;
    if let Some(old) = slot.replace(pc) {
        let _ = old.close().await;
    }

    Ok(Json(WebRtcOfferResponse {
        ok: true,
        mode: "webrtc",
        session_id: id,
        answer_sdp: local.sdp,
        codec,
        note,
    }))
}

async fn webrtc_ice(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<WebRtcIceRequest>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
    touch_session(&handle).await;
    let pc = handle
        .peer_connection
        .lock()
        .await
        .clone()
        .ok_or((StatusCode::CONFLICT, "webrtc peer connection not initialized".to_string()))?;

    let candidate = req.candidate;
    pc.add_ice_candidate(RTCIceCandidateInit {
        candidate: candidate.clone(),
        sdp_mid: req.sdp_mid,
        sdp_mline_index: req.sdp_mline_index,
        username_fragment: None,
    })
    .await
    .map_err(internal_error)?;

    Ok(Json(serde_json::json!({
        "ok": true,
        "mode": "webrtc",
        "session_id": id,
        "candidate_len": candidate.len()
    })))
}

async fn get_session_handle(state: &AppState, id: Uuid) -> Result<Arc<SessionHandle>, (StatusCode, String)> {
    let sessions = state.sessions.read().await;
    sessions
        .get(&id)
        .cloned()
        .ok_or((StatusCode::NOT_FOUND, "session not found".to_string()))
}

async fn run_session(handle: Arc<SessionHandle>, config: ConnectionConfig) {
    let id = handle.meta.read().await.id;
    info!("session {id} connecting");

    let mut client = RfbClient::new(config);
    if let Err(err) = client.connect().await {
        error!("session {id} connect failed: {err}");
        set_error(&handle, err.to_string()).await;
        return;
    }

    let (width, height) = client.framebuffer_size();
    {
        let mut meta = handle.meta.write().await;
        meta.state = match client.state() {
            ClientState::Connected => SessionState::Connected,
            ClientState::Error => SessionState::Error,
            _ => SessionState::Connecting,
        };
        meta.updated_at_ms = now_ms();
    }

    if let Err(err) = client.request_update(false, 0, 0, width, height).await {
        error!("session {id} initial framebuffer request failed: {err}");
        set_error(&handle, err.to_string()).await;
        return;
    }

    {
        let mut slot = handle.client.lock().await;
        *slot = Some(client);
    }

    loop {
        let frame_result = {
            let mut client_guard = handle.client.lock().await;
            let Some(client) = client_guard.as_mut() else {
                break;
            };

            match timeout(Duration::from_millis(100), client.process_message()).await {
                Err(_) => Ok(None),
                Ok(result) => match result {
                Ok(true) => {
                    let (w, h) = client.framebuffer_size();
                    let pixel_format = client
                        .server_info()
                        .map(|info| info.pixel_format)
                        .unwrap_or_default();
                    let data = convert_to_rgba(client.framebuffer(), w, h, pixel_format);
                    if let Err(err) = client.request_update(true, 0, 0, w, h).await {
                        Err(err.to_string())
                    } else {
                        Ok(Some((w, h, data)))
                    }
                }
                Ok(false) => Ok(None),
                Err(err) => Err(err.to_string()),
                },
            }
        };

        match frame_result {
            Ok(Some((width, height, data))) => {
                publish_frame(&handle, width, height, data).await;
            }
            Ok(None) => {}
            Err(err) => {
                warn!("session {id} loop ended: {err}");
                set_error(&handle, err).await;
                let mut client_guard = handle.client.lock().await;
                *client_guard = None;
                break;
            }
        }
    }
}

async fn publish_frame(handle: &Arc<SessionHandle>, width: u16, height: u16, data: Vec<u8>) {
    let (sequence, updated_at_ms, patches) = {
        let mut fb = handle.framebuffer.write().await;
        let patches = build_frame_patches(&fb, width, height, &data);
        fb.sequence += 1;
        fb.width = width;
        fb.height = height;
        fb.updated_at_ms = now_ms();
        fb.data = data.clone();
        (fb.sequence, fb.updated_at_ms, patches)
    };

    let session_id = handle.meta.read().await.id;
    let _ = handle.stream_tx.send(FrameEvent {
        session_id,
        sequence,
        width,
        height,
        updated_at_ms,
        patches,
    });
}

async fn touch_session(handle: &Arc<SessionHandle>) {
    let mut meta = handle.meta.write().await;
    meta.updated_at_ms = now_ms();
}

async fn close_session(state: &AppState, id: Uuid) -> bool {
    let handle = {
        let mut sessions = state.sessions.write().await;
        sessions.remove(&id)
    };

    let Some(handle) = handle else {
        return false;
    };

    {
        let mut meta = handle.meta.write().await;
        meta.state = SessionState::Closed;
        meta.updated_at_ms = now_ms();
    }

    if let Some(mut client) = handle.client.lock().await.take() {
        let _ = client.disconnect().await;
    }
    if let Some(pc) = handle.peer_connection.lock().await.take() {
        let _ = pc.close().await;
    }
    stop_video_process(&handle).await;
    true
}

async fn session_reaper(state: AppState) {
    let interval = Duration::from_secs(30);
    loop {
        tokio::time::sleep(interval).await;
        let now = now_ms();
        let mut stale = Vec::new();
        {
            let sessions = state.sessions.read().await;
            for handle in sessions.values() {
                let meta = handle.meta.read().await;
                if now.saturating_sub(meta.updated_at_ms) > SESSION_IDLE_TTL_MS {
                    stale.push(meta.id);
                }
            }
        }

        for id in stale {
            info!("reaping idle session {id}");
            close_session(&state, id).await;
        }
    }
}

async fn set_error(handle: &Arc<SessionHandle>, message: String) {
    let mut meta = handle.meta.write().await;
    meta.state = SessionState::Error;
    meta.updated_at_ms = now_ms();
    meta.last_error = Some(message);
}

fn internal_error(err: impl ToString) -> (StatusCode, String) {
    (StatusCode::BAD_GATEWAY, err.to_string())
}

fn now_ms() -> u64 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis() as u64
}

fn convert_to_rgba(input: &[u8], width: u16, height: u16, pixel_format: PixelFormat) -> Vec<u8> {
    let px_count = width as usize * height as usize;
    let bytes_per_pixel = pixel_format.bytes_per_pixel();
    if bytes_per_pixel == 4
        && !pixel_format.big_endian
        && pixel_format.red_shift == 0
        && pixel_format.green_shift == 8
        && pixel_format.blue_shift == 16
    {
        return input.to_vec();
    }

    let mut out = vec![0u8; px_count * 4];
    for i in 0..px_count {
        let src = i * bytes_per_pixel;
        let raw = match bytes_per_pixel {
            1 => input.get(src).copied().unwrap_or_default() as u32,
            2 => {
                let bytes = [input.get(src).copied().unwrap_or_default(), input.get(src + 1).copied().unwrap_or_default()];
                if pixel_format.big_endian {
                    u16::from_be_bytes(bytes) as u32
                } else {
                    u16::from_le_bytes(bytes) as u32
                }
            }
            4 => {
                let bytes = [
                    input.get(src).copied().unwrap_or_default(),
                    input.get(src + 1).copied().unwrap_or_default(),
                    input.get(src + 2).copied().unwrap_or_default(),
                    input.get(src + 3).copied().unwrap_or_default(),
                ];
                if pixel_format.big_endian {
                    u32::from_be_bytes(bytes)
                } else {
                    u32::from_le_bytes(bytes)
                }
            }
            _ => 0,
        };

        let red = scale_component((raw >> pixel_format.red_shift) & pixel_format.red_max as u32, pixel_format.red_max);
        let green = scale_component(
            (raw >> pixel_format.green_shift) & pixel_format.green_max as u32,
            pixel_format.green_max,
        );
        let blue = scale_component((raw >> pixel_format.blue_shift) & pixel_format.blue_max as u32, pixel_format.blue_max);

        let dst = i * 4;
        out[dst] = red;
        out[dst + 1] = green;
        out[dst + 2] = blue;
        out[dst + 3] = 255;
    }
    out
}

fn scale_component(value: u32, max: u16) -> u8 {
    if max == 0 {
        return 0;
    }
    ((value * 255) / max as u32) as u8
}

fn encode_frame_packet(event: &FrameEvent) -> Vec<u8> {
    let payload_len: usize = event
        .patches
        .iter()
        .map(|patch| 12 + patch.data.len())
        .sum();

    let mut packet = Vec::with_capacity(28 + payload_len);
    packet.extend_from_slice(b"MOS2");
    packet.extend_from_slice(&event.sequence.to_le_bytes());
    packet.extend_from_slice(&event.updated_at_ms.to_le_bytes());
    packet.extend_from_slice(&event.width.to_le_bytes());
    packet.extend_from_slice(&event.height.to_le_bytes());
    packet.extend_from_slice(&(event.patches.len() as u16).to_le_bytes());
    packet.extend_from_slice(&0u16.to_le_bytes());

    for patch in &event.patches {
        packet.extend_from_slice(&patch.x.to_le_bytes());
        packet.extend_from_slice(&patch.y.to_le_bytes());
        packet.extend_from_slice(&patch.width.to_le_bytes());
        packet.extend_from_slice(&patch.height.to_le_bytes());
        packet.extend_from_slice(&(patch.data.len() as u32).to_le_bytes());
        packet.extend_from_slice(&patch.data);
    }

    packet
}

fn build_frame_patches(
    previous: &FramebufferState,
    width: u16,
    height: u16,
    next: &[u8],
) -> Vec<FramePatch> {
    if previous.width != width
        || previous.height != height
        || previous.data.len() != next.len()
        || previous.data.is_empty()
    {
        return vec![FramePatch {
            x: 0,
            y: 0,
            width,
            height,
            data: next.to_vec(),
        }];
    }

    const TILE: usize = 64;
    let stride = width as usize * 4;
    let mut patches = Vec::new();

    for tile_y in (0..height as usize).step_by(TILE) {
        for tile_x in (0..width as usize).step_by(TILE) {
            let patch_w = (width as usize - tile_x).min(TILE);
            let patch_h = (height as usize - tile_y).min(TILE);
            if !tile_changed(&previous.data, next, stride, tile_x, tile_y, patch_w, patch_h) {
                continue;
            }

            let mut patch_data = Vec::with_capacity(patch_w * patch_h * 4);
            for row in 0..patch_h {
                let start = (tile_y + row) * stride + tile_x * 4;
                let end = start + patch_w * 4;
                patch_data.extend_from_slice(&next[start..end]);
            }

            patches.push(FramePatch {
                x: tile_x as u16,
                y: tile_y as u16,
                width: patch_w as u16,
                height: patch_h as u16,
                data: patch_data,
            });
        }
    }

    if patches.is_empty() {
        return Vec::new();
    }

    if patches.len() > 96 || patches.iter().map(|patch| patch.data.len()).sum::<usize>() > next.len() / 2 {
        return vec![FramePatch {
            x: 0,
            y: 0,
            width,
            height,
            data: next.to_vec(),
        }];
    }

    patches
}

fn tile_changed(
    previous: &[u8],
    next: &[u8],
    stride: usize,
    x: usize,
    y: usize,
    width: usize,
    height: usize,
) -> bool {
    for row in 0..height {
        let start = (y + row) * stride + x * 4;
        let end = start + width * 4;
        if previous[start..end] != next[start..end] {
            return true;
        }
    }
    false
}

async fn apply_input_event(
    handle: &Arc<SessionHandle>,
    req: &InputEventRequest,
) -> Result<(), (StatusCode, String)> {
    let mut client_guard = handle.client.lock().await;
    let client = client_guard
        .as_mut()
        .ok_or((StatusCode::CONFLICT, "session is not connected".to_string()))?;

    match req.kind.as_str() {
        "pointer" | "mouse" => {
            let x = req.x.ok_or((StatusCode::BAD_REQUEST, "x is required".to_string()))?;
            let y = req.y.ok_or((StatusCode::BAD_REQUEST, "y is required".to_string()))?;
            let buttons = req.buttons.unwrap_or(0);
            client
                .send_pointer_event(buttons, x, y)
                .await
                .map_err(internal_error)?;
        }
        "key" | "keyboard" => {
            let key = req.key.ok_or((StatusCode::BAD_REQUEST, "key is required".to_string()))?;
            let down = req.down.unwrap_or(true);
            client
                .send_key_event(down, key)
                .await
                .map_err(internal_error)?;
        }
        other => {
            return Err((StatusCode::BAD_REQUEST, format!("unsupported input kind: {other}")));
        }
    }

    Ok(())
}

async fn apply_clipboard(
    handle: &Arc<SessionHandle>,
    text: &str,
) -> Result<(), (StatusCode, String)> {
    let mut client_guard = handle.client.lock().await;
    let client = client_guard
        .as_mut()
        .ok_or((StatusCode::CONFLICT, "session is not connected".to_string()))?;

    client
        .send_clipboard_text(text)
        .await
        .map_err(internal_error)?;

    Ok(())
}

fn attach_input_channel(pc: &Arc<RTCPeerConnection>, handle: Arc<SessionHandle>, session_id: Uuid) {
    pc.on_data_channel(Box::new(move |dc: Arc<RTCDataChannel>| {
        let handle = handle.clone();
        Box::pin(async move {
            let label = dc.label().to_string();
            info!("session {session_id} data channel opened: {label}");
            if label != "input" {
                return;
            }

            dc.on_open(Box::new(move || {
                Box::pin(async move {
                    info!("session {session_id} input data channel ready");
                })
            }));

            dc.on_message(Box::new(move |msg: DataChannelMessage| {
                let handle = handle.clone();
                Box::pin(async move {
                    match parse_webrtc_input_message(&msg) {
                        Ok(WebRtcInputMessage::Input {
                            kind,
                            x,
                            y,
                            buttons,
                            key,
                            down,
                        }) => {
                            let req = InputEventRequest {
                                kind,
                                x,
                                y,
                                buttons,
                                key,
                                down,
                            };
                            if let Err(err) = apply_input_event(&handle, &req).await {
                                warn!("session {session_id} data channel input failed: {}", err.1);
                            }
                        }
                        Ok(WebRtcInputMessage::Clipboard { text }) => {
                            if let Err(err) = apply_clipboard(&handle, &text).await {
                                warn!("session {session_id} data channel clipboard failed: {}", err.1);
                            }
                        }
                        Ok(WebRtcInputMessage::Ping) => {}
                        Err(err) => {
                            warn!("session {session_id} data channel message ignored: {err}");
                        }
                    }
                })
            }));
        })
    }));
}

fn parse_webrtc_input_message(msg: &DataChannelMessage) -> Result<WebRtcInputMessage> {
    if msg.data.is_empty() {
        return Ok(WebRtcInputMessage::Ping);
    }

    if msg.is_string {
        return Ok(serde_json::from_slice::<WebRtcInputMessage>(&msg.data)?);
    }

    Err(anyhow::anyhow!("binary data channel messages are not supported yet"))
}

async fn attach_video_track(
    pc: &Arc<RTCPeerConnection>,
    handle: Arc<SessionHandle>,
    session_id: Uuid,
) -> Result<()> {
    let track = Arc::new(TrackLocalStaticRTP::new(
        RTCRtpCodecCapability {
            mime_type: MIME_TYPE_H264.to_owned(),
            clock_rate: 90_000,
            channels: 0,
            sdp_fmtp_line: "level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f"
                .to_owned(),
            rtcp_feedback: vec![],
        },
        format!("video-{session_id}"),
        "desktop".to_owned(),
    ));

    let sender = pc
        .add_track(track.clone() as Arc<dyn TrackLocal + Send + Sync>)
        .await?;

    tokio::spawn(async move {
        let mut rtcp = vec![0u8; 1500];
        while sender.read(&mut rtcp).await.is_ok() {}
    });

    restart_video_process(&handle, track, session_id).await?;
    Ok(())
}

async fn restart_video_process(
    handle: &Arc<SessionHandle>,
    track: Arc<TrackLocalStaticRTP>,
    session_id: Uuid,
) -> Result<()> {
    stop_video_process(handle).await;

    let socket = tokio::net::UdpSocket::bind("127.0.0.1:0").await?;
    let port = socket.local_addr()?.port();
    let size = capture_size(handle).await;
    let ffmpeg = spawn_ffmpeg_capture(port, &size)?;

    {
        let mut slot = handle.video_process.lock().await;
        *slot = Some(ffmpeg);
    }

    tokio::spawn(async move {
        let mut buf = vec![0u8; 2048];
        loop {
            let n = match socket.recv(&mut buf).await {
                Ok(n) => n,
                Err(err) => {
                    warn!("session {session_id} video recv failed: {err}");
                    break;
                }
            };

            let mut packet_buf = &buf[..n];
            let packet = match webrtc::rtp::packet::Packet::unmarshal(&mut packet_buf) {
                Ok(packet) => packet,
                Err(err) => {
                    warn!("session {session_id} video RTP parse failed: {err}");
                    continue;
                }
            };

            if let Err(err) = track.write_rtp(&packet).await {
                warn!("session {session_id} video RTP write failed: {err}");
                break;
            }
        }
    });

    info!("session {session_id} video relay started on udp {port} with size {size}");
    Ok(())
}

async fn stop_video_process(handle: &Arc<SessionHandle>) {
    let mut slot = handle.video_process.lock().await;
    if let Some(mut child) = slot.take() {
        let _ = child.kill().await;
        let _ = child.wait().await;
    }
}

async fn capture_size(handle: &Arc<SessionHandle>) -> String {
    if let Ok(size) = std::env::var("MOS_WEBRTC_VIDEO_SIZE") {
        let trimmed = size.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }

    let fb = handle.framebuffer.read().await;
    if fb.width > 0 && fb.height > 0 {
        let width = fb.width as u32;
        let height = fb.height as u32;
        let max_width = 960u32;
        if width <= max_width {
            return format!("{}x{}", width, height);
        }
        let scaled_height = ((height * max_width) / width).max(2);
        let even_height = scaled_height - (scaled_height % 2);
        return format!("{}x{}", max_width, even_height.max(2));
    }

    "960x540".to_string()
}

fn spawn_ffmpeg_capture(port: u16, size: &str) -> Result<tokio::process::Child> {
    let bin = std::env::var("MOS_WEBRTC_FFMPEG_BIN").unwrap_or_else(|_| "ffmpeg".to_string());
    let display = std::env::var("MOS_WEBRTC_DISPLAY").unwrap_or_else(|_| ":1".to_string());
    let framerate = std::env::var("MOS_WEBRTC_FRAMERATE").unwrap_or_else(|_| "10".to_string());

    let mut command = tokio::process::Command::new(bin);
    command
        .arg("-loglevel")
        .arg("error")
        .arg("-nostdin")
        .arg("-f")
        .arg("x11grab")
        .arg("-video_size")
        .arg(size)
        .arg("-framerate")
        .arg(framerate)
        .arg("-i")
        .arg(display)
        .arg("-an")
        .arg("-c:v")
        .arg("libx264")
        .arg("-preset")
        .arg("ultrafast")
        .arg("-tune")
        .arg("zerolatency")
        .arg("-profile:v")
        .arg("baseline")
        .arg("-pix_fmt")
        .arg("yuv420p")
        .arg("-g")
        .arg("24")
        .arg("-keyint_min")
        .arg("24")
        .arg("-bf")
        .arg("0")
        .arg("-f")
        .arg("rtp")
        .arg("-payload_type")
        .arg("125")
        .arg(format!("rtp://127.0.0.1:{port}?pkt_size=1200"))
        .stdout(std::process::Stdio::null())
        .stderr(std::process::Stdio::null());

    Ok(command.spawn()?)
}

async fn create_peer_connection(session_id: Uuid) -> Result<Arc<RTCPeerConnection>> {
    let mut media_engine = MediaEngine::default();
    media_engine.register_default_codecs()?;

    let mut registry = Registry::new();
    registry = register_default_interceptors(registry, &mut media_engine)?;

    let api = APIBuilder::new()
        .with_media_engine(media_engine)
        .with_interceptor_registry(registry)
        .build();

    let pc = Arc::new(api.new_peer_connection(RTCConfiguration::default()).await?);
    pc.on_peer_connection_state_change(Box::new(move |state: RTCPeerConnectionState| {
        Box::pin(async move {
            info!("session {session_id} webrtc state: {state}");
        })
    }));

    Ok(pc)
}

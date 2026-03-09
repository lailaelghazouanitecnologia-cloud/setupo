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
use tracing::{error, info, warn};
use uuid::Uuid;

#[derive(Clone)]
struct AppState {
    sessions: Arc<RwLock<HashMap<Uuid, Arc<SessionHandle>>>>,
}

struct SessionHandle {
    meta: RwLock<SessionRecord>,
    client: Mutex<Option<RfbClient>>,
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

#[derive(Clone, Serialize)]
struct FrameEvent {
    #[serde(rename = "type")]
    event_type: &'static str,
    session_id: Uuid,
    sequence: u64,
    width: u16,
    height: u16,
    encoding: &'static str,
    data: String,
    updated_at_ms: u64,
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

    let app = Router::new()
        .route("/health", get(health))
        .route("/sessions", post(create_session))
        .route("/sessions/:id", get(get_session).delete(delete_session))
        .route("/sessions/:id/framebuffer", get(get_framebuffer))
        .route("/sessions/:id/stream", get(stream_session))
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
    let handle = {
        let mut sessions = state.sessions.write().await;
        sessions
            .remove(&id)
            .ok_or((StatusCode::NOT_FOUND, "session not found".to_string()))?
    };

    {
        let mut meta = handle.meta.write().await;
        meta.state = SessionState::Closed;
        meta.updated_at_ms = now_ms();
    }

    if let Some(mut client) = handle.client.lock().await.take() {
        let _ = client.disconnect().await;
    }

    Ok(Json(serde_json::json!({ "ok": true, "session_id": id })))
}

async fn get_framebuffer(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
) -> Result<Json<FramebufferResponse>, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
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
                event_type: "framebuffer",
                session_id: id,
                sequence: initial_fb.sequence,
                width: initial_fb.width,
                height: initial_fb.height,
                encoding: "raw",
                data: BASE64.encode(initial_fb.data),
                updated_at_ms: initial_fb.updated_at_ms,
            };
            let _ = socket.send(Message::Text(serde_json::to_string(&event).unwrap())).await;
        }

        loop {
            match rx.recv().await {
                Ok(event) => {
                    if socket
                        .send(Message::Text(serde_json::to_string(&event).unwrap()))
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

    Ok(Json(serde_json::json!({ "ok": true, "session_id": id })))
}

async fn send_clipboard(
    State(state): State<AppState>,
    Path(id): Path<Uuid>,
    Json(req): Json<ClipboardRequest>,
) -> Result<Json<serde_json::Value>, (StatusCode, String)> {
    let handle = get_session_handle(&state, id).await?;
    let mut client_guard = handle.client.lock().await;
    let client = client_guard
        .as_mut()
        .ok_or((StatusCode::CONFLICT, "session is not connected".to_string()))?;

    client
        .send_clipboard_text(&req.text)
        .await
        .map_err(internal_error)?;

    Ok(Json(serde_json::json!({
        "ok": true,
        "session_id": id,
        "bytes": req.text.len()
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

            match client.process_message().await {
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
    let (sequence, updated_at_ms) = {
        let mut fb = handle.framebuffer.write().await;
        fb.sequence += 1;
        fb.width = width;
        fb.height = height;
        fb.updated_at_ms = now_ms();
        fb.data = data.clone();
        (fb.sequence, fb.updated_at_ms)
    };

    let session_id = handle.meta.read().await.id;
    let _ = handle.stream_tx.send(FrameEvent {
        event_type: "framebuffer",
        session_id,
        sequence,
        width,
        height,
        encoding: "raw",
        data: BASE64.encode(data),
        updated_at_ms,
    });
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

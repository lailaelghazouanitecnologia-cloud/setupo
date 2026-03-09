//! Client connection and handshake logic

use super::types::ClientState;
use super::RfbClient;
use crate::auth::AuthHandler;
use crate::core::protocol::Handshake;
use crate::core::types::{ProtocolVersion, SecurityType};
use crate::network::TcpConnection;
use crate::utils::{MosError, MosResult};

impl RfbClient {
    /// Connect to VNC server
    pub async fn connect(&mut self) -> MosResult<()> {
        tracing::info!("Connecting to {}:{}", self.config.host, self.config.port);
        self.state = ClientState::Handshaking;

        // Establish TCP connection
        let mut conn = TcpConnection::connect(
            &self.config.host,
            self.config.port,
            self.config.network.clone(),
        )
        .await?;

        // Protocol handshake
        let server_version = Handshake::read_version(&mut conn).await?;
        tracing::info!("Server version: {:?}", server_version);

        // Send our version (match server or use 3.8 if supported)
        let client_version = match server_version {
            ProtocolVersion::Rfb38 => ProtocolVersion::Rfb38,
            ProtocolVersion::Rfb37 => ProtocolVersion::Rfb37,
            ProtocolVersion::Rfb33 => ProtocolVersion::Rfb33,
        };
        Handshake::send_version(&mut conn, client_version).await?;

        // Security negotiation
        self.state = ClientState::Authenticating;
        let security_types = Handshake::read_security_types(&mut conn).await?;
        tracing::info!("Available security types: {:?}", security_types);

        // Select security type
        let selected_security = self.select_security_type(&security_types)?;
        Handshake::send_security_type(&mut conn, selected_security).await?;

        // Authenticate
        AuthHandler::authenticate(selected_security, &mut conn, self.config.password.as_deref())
            .await?;

        // Read security result (for RFB 3.7+)
        if client_version != ProtocolVersion::Rfb33 {
            Handshake::read_security_result(&mut conn).await?;
        }

        // Client initialization
        self.state = ClientState::Initializing;
        Handshake::send_client_init(&mut conn, self.config.shared).await?;

        // Server initialization
        let server_init = Handshake::read_server_init(&mut conn).await?;
        tracing::info!("Server: {}x{} - {}",
            server_init.width,
            server_init.height,
            server_init.name
        );

        // Initialize framebuffer
        self.fb_width = server_init.width;
        self.fb_height = server_init.height;
        self.pixel_format = server_init.pixel_format.clone();

        let fb_size = (self.fb_width as usize)
            * (self.fb_height as usize)
            * self.pixel_format.bytes_per_pixel();
        self.framebuffer = vec![0u8; fb_size];

        self.server_init = Some(server_init);

        self.send_set_encodings(&mut conn, &self.config.preferred_encodings)
            .await?;

        // Set pixel format (use server's default for now)
        self.send_set_pixel_format(&mut conn, &self.pixel_format).await?;

        self.conn = Some(conn);
        self.state = ClientState::Connected;

        tracing::info!("Connected successfully");
        Ok(())
    }

    /// Select security type from available options
    pub(super) fn select_security_type(&self, types: &[SecurityType]) -> MosResult<SecurityType> {
        // Prefer VNC auth if password is provided
        if self.config.password.is_some() && types.contains(&SecurityType::VncAuth) {
            return Ok(SecurityType::VncAuth);
        }

        // Fall back to None auth
        if types.contains(&SecurityType::None) {
            return Ok(SecurityType::None);
        }

        Err(MosError::protocol(format!(
            "No supported security type found. Available: {:?}",
            types
        )))
    }

    /// Disconnect from server
    pub async fn disconnect(&mut self) -> MosResult<()> {
        if let Some(conn) = self.conn.take() {
            tracing::info!("Disconnecting");
            // TcpConnection will close on drop
            drop(conn);
        }
        self.state = ClientState::Disconnected;
        Ok(())
    }
}

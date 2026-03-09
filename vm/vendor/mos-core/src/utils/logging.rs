//! Logging configuration and utilities

use tracing::Level;
use tracing_subscriber::{fmt, layer::SubscriberExt, util::SubscriberInitExt, EnvFilter};

pub fn init() {
    init_with_level(None);
}

pub fn init_with_level(level: Option<Level>) {
    let filter = if let Some(level) = level {
        EnvFilter::from_default_env().add_directive(level.into())
    } else {
        EnvFilter::try_from_default_env()
            .unwrap_or_else(|_| EnvFilter::new("mos=info"))
    };

    tracing_subscriber::registry()
        .with(filter)
        .with(fmt::layer().with_target(true).with_thread_ids(true).with_line_number(true))
        .init();
}

pub fn init_test() {
    let _ = tracing_subscriber::fmt()
        .with_test_writer()
        .with_max_level(Level::DEBUG)
        .try_init();
}

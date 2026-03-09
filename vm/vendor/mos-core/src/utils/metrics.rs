//! Performance metrics collection

use parking_lot::RwLock;
use std::collections::HashMap;
use std::sync::Arc;

#[derive(Debug, Clone)]
pub struct Metrics {
    counters: Arc<RwLock<HashMap<String, u64>>>,
    gauges: Arc<RwLock<HashMap<String, f64>>>,
}

impl Default for Metrics {
    fn default() -> Self {
        Self::new()
    }
}

impl Metrics {
    pub fn new() -> Self {
        Self {
            counters: Arc::new(RwLock::new(HashMap::new())),
            gauges: Arc::new(RwLock::new(HashMap::new())),
        }
    }

    pub fn inc_counter(&self, name: &str) {
        self.add_counter(name, 1);
    }

    pub fn add_counter(&self, name: &str, value: u64) {
        let mut counters = self.counters.write();
        *counters.entry(name.to_string()).or_insert(0) += value;
    }

    pub fn get_counter(&self, name: &str) -> u64 {
        self.counters.read().get(name).copied().unwrap_or(0)
    }

    pub fn set_gauge(&self, name: &str, value: f64) {
        let mut gauges = self.gauges.write();
        gauges.insert(name.to_string(), value);
    }

    pub fn get_gauge(&self, name: &str) -> Option<f64> {
        self.gauges.read().get(name).copied()
    }

    pub fn reset(&self) {
        self.counters.write().clear();
        self.gauges.write().clear();
    }
}

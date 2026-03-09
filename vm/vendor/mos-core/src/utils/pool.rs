//! Object pooling for reducing allocations

use parking_lot::Mutex;
use std::sync::Arc;

pub struct Pool<T> {
    objects: Arc<Mutex<Vec<T>>>,
    factory: Arc<dyn Fn() -> T + Send + Sync>,
}

impl<T> Pool<T> {
    pub fn new<F>(factory: F) -> Self
    where
        F: Fn() -> T + Send + Sync + 'static,
    {
        Self {
            objects: Arc::new(Mutex::new(Vec::new())),
            factory: Arc::new(factory),
        }
    }

    pub fn get(&self) -> PooledObject<T> {
        let obj = self.objects.lock().pop().unwrap_or_else(|| (self.factory)());
        PooledObject {
            object: Some(obj),
            pool: self.objects.clone(),
        }
    }

    pub fn size(&self) -> usize {
        self.objects.lock().len()
    }
}

pub struct PooledObject<T> {
    object: Option<T>,
    pool: Arc<Mutex<Vec<T>>>,
}

impl<T> std::ops::Deref for PooledObject<T> {
    type Target = T;
    fn deref(&self) -> &Self::Target {
        self.object.as_ref().unwrap()
    }
}

impl<T> std::ops::DerefMut for PooledObject<T> {
    fn deref_mut(&mut self) -> &mut Self::Target {
        self.object.as_mut().unwrap()
    }
}

impl<T> Drop for PooledObject<T> {
    fn drop(&mut self) {
        if let Some(obj) = self.object.take() {
            self.pool.lock().push(obj);
        }
    }
}

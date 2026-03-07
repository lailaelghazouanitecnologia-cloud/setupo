"use client";

import { useState, useCallback, useEffect, useRef } from "react";

interface UseResourceManagerOptions<T> {
  fetcher: () => Promise<T[]>;
  autoFetch?: boolean;
  deps?: unknown[];
  getKey?: (item: T) => string;
}

interface ResourceManager<T> {
  items: T[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
  addOptimistic: (item: T) => void;
  removeOptimistic: (key: string) => void;
  updateOptimistic: (key: string, updater: (item: T) => T) => void;
  setItems: (items: T[]) => void;
  empty: boolean;
}

export function useResourceManager<T extends Record<string, any>>(options: UseResourceManagerOptions<T>): ResourceManager<T> {
  const { fetcher, autoFetch = true, deps = [], getKey = (item) => item.id } = options;

  const [items, setItems] = useState<T[]>([]);
  const [loading, setLoading] = useState(autoFetch);
  const [error, setError] = useState<string | null>(null);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => { mountedRef.current = false; };
  }, []);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const result = await fetcher();
      if (mountedRef.current) setItems(result);
    } catch (err: any) {
      if (mountedRef.current) setError(err.message || "Failed to load data");
    }
    if (mountedRef.current) setLoading(false);
  }, [fetcher]);

  useEffect(() => {
    if (autoFetch) refresh();
  }, [autoFetch, ...deps]);

  const addOptimistic = useCallback((item: T) => {
    setItems((prev) => [...prev, item]);
  }, []);

  const removeOptimistic = useCallback((key: string) => {
    setItems((prev) => prev.filter((item) => getKey(item) !== key));
  }, [getKey]);

  const updateOptimistic = useCallback((key: string, updater: (item: T) => T) => {
    setItems((prev) => prev.map((item) => getKey(item) === key ? updater(item) : item));
  }, [getKey]);

  return {
    items, loading, error, refresh,
    addOptimistic, removeOptimistic, updateOptimistic,
    setItems, empty: !loading && items.length === 0,
  };
}

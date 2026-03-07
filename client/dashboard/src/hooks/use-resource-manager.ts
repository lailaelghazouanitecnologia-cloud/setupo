"use client";

import { useState, useCallback, useEffect, useRef } from "react";

// ══════════════════════════════════════════════════════════════
//  useResourceManager — Generic CRUD resource management
// ══════════════════════════════════════════════════════════════
//
//  Replaces the repeated pattern in every panel:
//    const [items, setItems] = useState([]);
//    const [loading, setLoading] = useState(false);
//    const [error, setError] = useState("");
//    useEffect(() => { fetch... }, []);
//

interface UseResourceManagerOptions<T> {
  /** Fetch function that returns the resource list */
  fetcher: () => Promise<T[]>;
  /** Auto-fetch on mount? Default: true */
  autoFetch?: boolean;
  /** Dependencies that trigger a refetch (like projectId) */
  deps?: unknown[];
  /** Key extractor for deduplication. Default: (item) => item.id */
  getKey?: (item: T) => string;
}

interface ResourceManager<T> {
  items: T[];
  loading: boolean;
  error: string | null;
  /** Fetch/refresh the resource list */
  refresh: () => Promise<void>;
  /** Optimistically add an item to the list */
  addOptimistic: (item: T) => void;
  /** Optimistically remove an item from the list */
  removeOptimistic: (key: string) => void;
  /** Optimistically update an item in the list */
  updateOptimistic: (key: string, updater: (item: T) => T) => void;
  /** Set items directly */
  setItems: (items: T[]) => void;
  /** Is empty (not loading and no items) */
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
      if (mountedRef.current) {
        setItems(result);
      }
    } catch (err: any) {
      if (mountedRef.current) {
        setError(err.message || "Failed to load data");
      }
    }
    if (mountedRef.current) setLoading(false);
  }, [fetcher]);

  // Auto-fetch on mount and when deps change
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
    items,
    loading,
    error,
    refresh,
    addOptimistic,
    removeOptimistic,
    updateOptimistic,
    setItems,
    empty: !loading && items.length === 0,
  };
}

"use client";

import { useState, useCallback } from "react";

// ══════════════════════════════════════════════════════════════
//  useAsyncAction — Wraps any async operation with loading/error state
// ══════════════════════════════════════════════════════════════
//
//  Replaces the repeated pattern:
//    const [loading, setLoading] = useState(false);
//    const [error, setError] = useState("");
//    const doThing = async () => {
//      setLoading(true); setError("");
//      try { await ... } catch { setError(...) }
//      setLoading(false);
//    };
//

interface AsyncAction<TArgs extends unknown[], TResult> {
  execute: (...args: TArgs) => Promise<TResult | undefined>;
  loading: boolean;
  error: string | null;
  reset: () => void;
}

export function useAsyncAction<TArgs extends unknown[], TResult = void>(
  action: (...args: TArgs) => Promise<TResult>,
): AsyncAction<TArgs, TResult> {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const execute = useCallback(async (...args: TArgs): Promise<TResult | undefined> => {
    setLoading(true);
    setError(null);
    try {
      const result = await action(...args);
      setLoading(false);
      return result;
    } catch (err: any) {
      setError(err.message || "An error occurred");
      setLoading(false);
      return undefined;
    }
  }, [action]);

  const reset = useCallback(() => {
    setLoading(false);
    setError(null);
  }, []);

  return { execute, loading, error, reset };
}

import { useCallback, useEffect, useRef, useState } from "react";
import { api, ApiError } from "../api/client";
import type { Study } from "../api/types";

const POLL_MS = 1500;

/** Load a study, and poll it while an analysis is running. */
export function useStudy(id: string) {
  const [study, setStudy] = useState<Study | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const timer = useRef<number | undefined>(undefined);

  const refresh = useCallback(async () => {
    try {
      const s = await api.study(id);
      setStudy(s);
      setError(null);
      return s;
    } catch (e) {
      setError(e instanceof ApiError ? e : new ApiError(0, "error", String(e)));
      return null;
    }
  }, [id]);

  useEffect(() => {
    setStudy(null);
    void refresh();
  }, [refresh]);

  useEffect(() => {
    window.clearTimeout(timer.current);
    if (study?.status === "analyzing") {
      timer.current = window.setTimeout(() => void refresh(), POLL_MS);
    }
    return () => window.clearTimeout(timer.current);
  }, [study, refresh]);

  return { study, setStudy, error, refresh };
}

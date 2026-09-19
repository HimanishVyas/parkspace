import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "./api";

interface AsyncState<T> {
  data: T | null;
  error: ApiError | null;
  loading: boolean;
  reload: () => void;
  setData: (value: T | null) => void;
}

/**
 * Runs an async loader on mount and whenever `deps` change, cancelling the
 * in-flight request when they do so a slow response can't overwrite a fast one.
 */

/**
 * Turn any thrown value into an ApiError for display.
 *
 * Everything that was not an ApiError used to be reported as "Network error",
 * which disguised genuine client-side faults as connectivity problems — a
 * SubtleCrypto failure on a non-secure origin looked exactly like a dropped
 * connection. A real network failure surfaces as a TypeError from fetch, so
 * only that is called one.
 */
function toDisplayError(err: unknown): ApiError {
  if (err instanceof ApiError) return err;
  const message = err instanceof Error ? err.message : String(err);
  const looksLikeFetchFailure =
    err instanceof TypeError && /fetch|network|load failed/i.test(message);
  if (looksLikeFetchFailure) {
    return new ApiError(0, "NETWORK", "Could not reach the server. Check your connection.");
  }
  console.error("Unexpected client error", err);
  return new ApiError(0, "CLIENT", message || "Something went wrong on this device.");
}

export function useAsync<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  deps: unknown[] = [],
): AsyncState<T> {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [loading, setLoading] = useState(true);
  const [nonce, setNonce] = useState(0);
  const loaderRef = useRef(loader);
  loaderRef.current = loader;

  useEffect(() => {
    const controller = new AbortController();
    let active = true;
    setLoading(true);
    setError(null);
    loaderRef
      .current(controller.signal)
      .then((result) => {
        if (active) setData(result);
      })
      .catch((err: unknown) => {
        if (!active || controller.signal.aborted) return;
        setError(toDisplayError(err));
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
      controller.abort();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [...deps, nonce]);

  const reload = useCallback(() => setNonce((value) => value + 1), []);
  return { data, error, loading, reload, setData };
}

/** Wraps a submit handler with pending/error state so forms stay tidy. */
export function useSubmit<Args extends unknown[], Result>(
  action: (...args: Args) => Promise<Result>,
) {
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);

  const run = useCallback(
    async (...args: Args): Promise<Result | undefined> => {
      setPending(true);
      setError(null);
      try {
        return await action(...args);
      } catch (err) {
        setError(toDisplayError(err));
        return undefined;
      } finally {
        setPending(false);
      }
    },
    [action],
  );

  return { run, pending, error, setError };
}

/** Debounces a value — used for the search box so we don't query per keystroke. */
export function useDebounced<T>(value: T, delay = 400): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

/** The browser's location, requested only when the user asks for it. */
export function useGeolocation() {
  const [position, setPosition] = useState<{ latitude: number; longitude: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const locate = useCallback(() => {
    if (!navigator.geolocation) {
      setError("Location is not available in this browser");
      return;
    }
    setPending(true);
    setError(null);
    navigator.geolocation.getCurrentPosition(
      (result) => {
        setPosition({ latitude: result.coords.latitude, longitude: result.coords.longitude });
        setPending(false);
      },
      () => {
        setError("We could not get your location. Search by area instead.");
        setPending(false);
      },
      { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 },
    );
  }, []);

  return { position, error, pending, locate, setPosition };
}

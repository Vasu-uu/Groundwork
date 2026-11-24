import { useCallback, useEffect, useState } from "react";

/** Routes: "#/" (home) and "#/study/<id>/<step>" with step 1..4. */
export type Route = { page: "home" } | { page: "study"; id: string; step: number };

export function parseHash(hash: string): Route {
  const m = /^#\/study\/([\w-]+)(?:\/(\d))?/.exec(hash);
  if (!m) return { page: "home" };
  const step = Math.min(4, Math.max(1, Number(m[2] ?? 1)));
  return { page: "study", id: m[1]!, step };
}

export function useHashRoute() {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));

  useEffect(() => {
    const onChange = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", onChange);
    return () => window.removeEventListener("hashchange", onChange);
  }, []);

  const go = useCallback((r: Route) => {
    window.location.hash = r.page === "home" ? "#/" : `#/study/${r.id}/${r.step}`;
  }, []);

  return { route, go };
}

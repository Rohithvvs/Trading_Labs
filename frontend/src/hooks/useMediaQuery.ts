import { useEffect, useState } from "react";

/**
 * Subscribe to a CSS media query. Defaults to `false` (desktop) when
 * `window.matchMedia` is unavailable so tests and SSR render the table.
 */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return false;
    return window.matchMedia(query).matches;
  });

  useEffect(() => {
    if (typeof window === "undefined" || typeof window.matchMedia !== "function") return;
    const mq = window.matchMedia(query);
    const onChange = (event: MediaQueryListEvent) => setMatches(event.matches);
    setMatches(mq.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

export function useIsCompactViewport(): boolean {
  return useMediaQuery("(max-width: 768px)");
}

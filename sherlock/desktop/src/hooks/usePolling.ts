import { useEffect, type DependencyList } from "react";

export function usePolling(
  intervalMs: number,
  pollFn: () => void,
  deps: DependencyList,
) {
  useEffect(() => {
    const timer = setInterval(() => {
      void pollFn();
    }, intervalMs);
    return () => clearInterval(timer);
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}

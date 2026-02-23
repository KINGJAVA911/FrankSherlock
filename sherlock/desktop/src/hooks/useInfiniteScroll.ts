import { useEffect, type RefObject, type DependencyList } from "react";

export function useInfiniteScroll(
  sentinelRef: RefObject<HTMLDivElement | null>,
  onLoadMore: () => void,
  deps: DependencyList,
) {
  useEffect(() => {
    const el = sentinelRef.current;
    if (!el) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          void onLoadMore();
        }
      },
      { rootMargin: "200px" },
    );
    observer.observe(el);
    return () => observer.disconnect();
  }, deps); // eslint-disable-line react-hooks/exhaustive-deps
}

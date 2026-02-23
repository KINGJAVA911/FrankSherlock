import { useEffect, useRef, type RefObject } from "react";

export function useGridColumns(gridRef: RefObject<HTMLDivElement | null>) {
  const columnsRef = useRef(1);

  useEffect(() => {
    const el = gridRef.current;
    if (!el) return;
    const gap = 6;
    const minItemWidth = 220;
    const observer = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const w = entry.contentRect.width;
        columnsRef.current = Math.max(1, Math.floor((w + gap) / (minItemWidth + gap)));
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return columnsRef;
}

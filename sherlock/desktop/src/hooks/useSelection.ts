import { useState, useCallback } from "react";

export function useSelection() {
  const [selectedIndices, setSelectedIndices] = useState<Set<number>>(new Set());
  const [focusIndex, setFocusIndex] = useState<number | null>(null);
  const [anchorIndex, setAnchorIndex] = useState<number | null>(null);

  const selectOnly = useCallback((idx: number) => {
    setSelectedIndices(new Set([idx]));
    setFocusIndex(idx);
    setAnchorIndex(idx);
  }, []);

  const toggleSelect = useCallback((idx: number) => {
    setSelectedIndices(prev => {
      const next = new Set(prev);
      if (next.has(idx)) next.delete(idx); else next.add(idx);
      return next;
    });
    setFocusIndex(idx);
    setAnchorIndex(idx);
  }, []);

  const rangeSelect = useCallback((from: number, to: number) => {
    const lo = Math.min(from, to), hi = Math.max(from, to);
    setSelectedIndices(prev => {
      const next = new Set(prev);
      for (let i = lo; i <= hi; i++) next.add(i);
      return next;
    });
    setFocusIndex(to);
  }, []);

  const selectAll = useCallback((count: number) => {
    setSelectedIndices(new Set(Array.from({ length: count }, (_, i) => i)));
  }, []);

  const clearSelection = useCallback(() => {
    setSelectedIndices(new Set());
    setFocusIndex(null);
    setAnchorIndex(null);
  }, []);

  const replaceSelection = useCallback(
    (indices: Set<number>, focus: number | null, anchor: number | null) => {
      setSelectedIndices(indices);
      setFocusIndex(focus);
      setAnchorIndex(anchor);
    },
    [],
  );

  return {
    selectedIndices,
    focusIndex,
    anchorIndex,
    selectOnly,
    toggleSelect,
    rangeSelect,
    selectAll,
    clearSelection,
    replaceSelection,
  };
}

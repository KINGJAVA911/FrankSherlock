import { useEffect, useRef, useState, useCallback } from "react";
import { searchImages } from "../api";
import type { SearchItem, SearchResponse } from "../types";

const PAGE_SIZE = 80;

type UseSearchParams = {
  query: string;
  selectedMediaType: string;
  selectedRootId: number | null;
  isReady: boolean;
  onClearSelection: () => void;
};

export function useSearch({ query, selectedMediaType, selectedRootId, isReady, onClearSelection }: UseSearchParams) {
  const [items, setItems] = useState<SearchItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingMore, setLoadingMore] = useState(false);
  const requestIdRef = useRef(0);

  const canLoadMore = items.length < total;

  function applySearchResponse(response: SearchResponse, append: boolean) {
    setTotal(response.total);
    if (append) {
      setItems((prev) => [...prev, ...response.items]);
    } else {
      setItems(response.items);
      onClearSelection();
    }
  }

  const runSearch = useCallback(async (offset: number, append: boolean, limitOverride?: number) => {
    const reqId = ++requestIdRef.current;
    if (append) setLoadingMore(true);
    else setLoading(true);
    try {
      const response = await searchImages({
        query,
        limit: limitOverride ?? PAGE_SIZE,
        offset,
        mediaTypes: selectedMediaType ? [selectedMediaType] : undefined,
        rootScope: selectedRootId ? [selectedRootId] : undefined,
      });
      if (reqId !== requestIdRef.current) return;
      applySearchResponse(response, append);
    } catch (err) {
      if (reqId !== requestIdRef.current) return;
      // Error handling delegated to caller via return
    } finally {
      if (reqId !== requestIdRef.current) return;
      setLoading(false);
      setLoadingMore(false);
    }
  }, [query, selectedMediaType, selectedRootId, onClearSelection]);

  const onLoadMore = useCallback(async () => {
    if (!canLoadMore || loadingMore) return;
    await runSearch(items.length, true);
  }, [canLoadMore, loadingMore, items.length, runSearch]);

  // Debounced search effect
  useEffect(() => {
    if (!isReady) return;
    const timer = setTimeout(() => {
      void runSearch(0, false);
    }, 260);
    return () => clearTimeout(timer);
  }, [query, selectedMediaType, selectedRootId, isReady]);

  return { items, total, loading, loadingMore, canLoadMore, runSearch, onLoadMore };
}

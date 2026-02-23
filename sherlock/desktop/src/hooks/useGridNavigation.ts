import { useEffect, type RefObject, type MutableRefObject } from "react";
import { copyFilesToClipboard } from "../api";
import type { SearchItem, SetupStatus, RootInfo } from "../types";

type GridNavParams = {
  items: SearchItem[];
  selectedIndices: Set<number>;
  focusIndex: number | null;
  anchorIndex: number | null;
  columnsRef: MutableRefObject<number>;
  gridRef: RefObject<HTMLDivElement | null>;
  previewOpen: boolean;
  showSummary: boolean;
  showResumeModal: boolean;
  confirmDeleteRoot: RootInfo | null;
  setup: SetupStatus | null;
  canLoadMore: boolean;
  selectOnly: (idx: number) => void;
  rangeSelect: (from: number, to: number) => void;
  selectAll: (count: number) => void;
  clearSelection: () => void;
  setPreviewOpen: (open: boolean) => void;
  setCompletedJobs: (jobs: []) => void;
  setShowResumeModal: (show: boolean) => void;
  setConfirmDeleteRoot: (root: null) => void;
  setNotice: (msg: string) => void;
  onLoadMore: () => void;
};

export function useGridNavigation(p: GridNavParams) {
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "SELECT" || tag === "TEXTAREA") return;

      if (e.key === "Escape") {
        if (p.showSummary) {
          p.setCompletedJobs([]);
        } else if (p.showResumeModal) {
          p.setShowResumeModal(false);
        } else if (p.confirmDeleteRoot) {
          p.setConfirmDeleteRoot(null);
        } else if (p.previewOpen) {
          p.setPreviewOpen(false);
        } else if (p.selectedIndices.size > 0) {
          p.clearSelection();
        }
        return;
      }

      if (p.showResumeModal || p.confirmDeleteRoot || (p.setup && !p.setup.isReady)) return;

      if ((e.ctrlKey || e.metaKey) && e.key === "c") {
        e.preventDefault();
        const paths = [...p.selectedIndices].sort((a, b) => a - b)
          .filter(i => i < p.items.length)
          .map(i => p.items[i].absPath);
        if (paths.length > 0) {
          copyFilesToClipboard(paths).catch(() => {});
          p.setNotice(`Copied ${paths.length} file path(s)`);
        }
        return;
      }

      if ((e.ctrlKey || e.metaKey) && e.key === "a") {
        e.preventDefault();
        p.selectAll(p.items.length);
        return;
      }

      const cols = p.columnsRef.current;
      const isShift = e.shiftKey;

      if (e.key === "ArrowRight") {
        e.preventDefault();
        const next = p.focusIndex == null ? 0 : Math.min(p.focusIndex + 1, p.items.length - 1);
        if (isShift && p.anchorIndex != null) p.rangeSelect(p.anchorIndex, next);
        else p.selectOnly(next);
        scrollTileIntoView(next);
        autoLoadIfNeeded(next);
      } else if (e.key === "ArrowLeft") {
        e.preventDefault();
        const next = p.focusIndex == null ? 0 : Math.max(p.focusIndex - 1, 0);
        if (isShift && p.anchorIndex != null) p.rangeSelect(p.anchorIndex, next);
        else p.selectOnly(next);
        scrollTileIntoView(next);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        const next = p.focusIndex == null ? 0 : Math.min(p.focusIndex + cols, p.items.length - 1);
        if (isShift && p.anchorIndex != null) p.rangeSelect(p.anchorIndex, next);
        else p.selectOnly(next);
        scrollTileIntoView(next);
        autoLoadIfNeeded(next);
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        const next = p.focusIndex == null ? 0 : Math.max(p.focusIndex - cols, 0);
        if (isShift && p.anchorIndex != null) p.rangeSelect(p.anchorIndex, next);
        else p.selectOnly(next);
        scrollTileIntoView(next);
      } else if (e.key === " ") {
        e.preventDefault();
        if (p.selectedIndices.size > 0) {
          p.setPreviewOpen(!p.previewOpen);
        }
      }
    }

    function scrollTileIntoView(index: number) {
      const grid = p.gridRef.current;
      if (!grid) return;
      const tile = grid.children[index] as HTMLElement | undefined;
      tile?.scrollIntoView({ block: "nearest", behavior: "smooth" });
    }

    function autoLoadIfNeeded(index: number) {
      const cols = p.columnsRef.current;
      if (index >= p.items.length - cols * 2 && p.canLoadMore) {
        void p.onLoadMore();
      }
    }

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [
    p.focusIndex, p.anchorIndex, p.selectedIndices, p.previewOpen,
    p.items.length, p.showSummary, p.showResumeModal, p.confirmDeleteRoot,
    p.setup?.isReady, p.canLoadMore,
  ]);
}

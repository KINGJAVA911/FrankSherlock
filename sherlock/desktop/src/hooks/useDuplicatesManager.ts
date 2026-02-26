import { useState } from "react";
import { findDuplicates } from "../api";
import type { DuplicateGroup, DuplicatesResponse, SearchItem } from "../types";
import { errorMessage } from "../utils";

type DuplicatesManagerCallbacks = {
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
};

export function useDuplicatesManager({ onError }: DuplicatesManagerCallbacks) {
  const [duplicatesMode, setDuplicatesMode] = useState(false);
  const [duplicatesData, setDuplicatesData] = useState<DuplicatesResponse | null>(null);
  const [duplicatesLoading, setDuplicatesLoading] = useState(false);
  const [duplicatesSelected, setDuplicatesSelected] = useState<Set<number>>(new Set());
  const [nearEnabled, setNearEnabled] = useState(false);
  const [nearThreshold, setNearThreshold] = useState(0.85);
  const [dupPreviewItems, setDupPreviewItems] = useState<SearchItem[]>([]);

  async function onFindDuplicates(threshold?: number | null) {
    setDuplicatesMode(true);
    setDuplicatesLoading(true);
    setDuplicatesSelected(new Set());
    setDuplicatesData(null);
    try {
      // Guard: when called as an onClick handler, the first arg is a MouseEvent
      const safeThreshold = typeof threshold === "number" ? threshold : null;
      const effectiveThreshold = safeThreshold ?? (nearEnabled ? nearThreshold : null);
      const resp = await findDuplicates([], effectiveThreshold);
      setDuplicatesData(resp);
    } catch (err) {
      onError(errorMessage(err));
      setDuplicatesMode(false);
    } finally {
      setDuplicatesLoading(false);
    }
  }

  function onNearEnabledChange(enabled: boolean) {
    setNearEnabled(enabled);
    onFindDuplicates(enabled ? nearThreshold : null);
  }

  function onNearThresholdChange(value: number) {
    setNearThreshold(value);
    onFindDuplicates(value);
  }

  function onToggleFile(fileId: number) {
    setDuplicatesSelected((prev) => {
      const next = new Set(prev);
      if (next.has(fileId)) next.delete(fileId);
      else next.add(fileId);
      return next;
    });
  }

  function onSelectAllDuplicates() {
    if (!duplicatesData) return;
    const ids = new Set<number>();
    for (const group of duplicatesData.groups) {
      for (const file of group.files) {
        if (!file.isKeeper) ids.add(file.id);
      }
    }
    setDuplicatesSelected(ids);
  }

  function onDeselectAll() {
    setDuplicatesSelected(new Set());
  }

  function onSelectGroupDuplicates(group: DuplicateGroup) {
    setDuplicatesSelected((prev) => {
      const next = new Set(prev);
      for (const file of group.files) {
        if (!file.isKeeper) next.add(file.id);
      }
      return next;
    });
  }

  function onPreviewGroup(group: DuplicateGroup) {
    const items: SearchItem[] = group.files.slice(0, 10).map((file) => ({
      id: file.id,
      rootId: file.rootId,
      relPath: file.relPath,
      absPath: file.absPath,
      mediaType: file.mediaType,
      description: file.description,
      confidence: file.confidence,
      mtimeNs: file.mtimeNs,
      sizeBytes: file.sizeBytes,
      thumbnailPath: file.thumbnailPath,
    }));
    setDupPreviewItems(items);
  }

  function getDeleteFileIds(): number[] {
    if (!duplicatesData || duplicatesSelected.size === 0) return [];
    const ids: number[] = [];
    for (const group of duplicatesData.groups) {
      for (const file of group.files) {
        if (duplicatesSelected.has(file.id)) ids.push(file.id);
      }
    }
    return ids;
  }

  function getDeleteSearchItems(): SearchItem[] {
    if (!duplicatesData || duplicatesSelected.size === 0) return [];
    const items: SearchItem[] = [];
    for (const group of duplicatesData.groups) {
      for (const file of group.files) {
        if (duplicatesSelected.has(file.id)) {
          items.push({
            id: file.id,
            rootId: file.rootId,
            relPath: file.relPath,
            absPath: file.absPath,
            mediaType: file.mediaType,
            description: file.description,
            confidence: file.confidence,
            mtimeNs: file.mtimeNs,
            sizeBytes: file.sizeBytes,
            thumbnailPath: file.thumbnailPath,
          });
        }
      }
    }
    return items;
  }

  function onBack() {
    setDuplicatesMode(false);
    setDuplicatesData(null);
    setDuplicatesSelected(new Set());
  }

  async function refreshAfterDelete() {
    setDuplicatesSelected(new Set());
    try {
      const resp = await findDuplicates([], nearEnabled ? nearThreshold : null);
      setDuplicatesData(resp);
    } catch { /* ignore */ }
  }

  return {
    duplicatesMode,
    setDuplicatesMode,
    duplicatesData,
    duplicatesLoading,
    duplicatesSelected,
    nearEnabled,
    nearThreshold,
    dupPreviewItems,
    setDupPreviewItems,
    onFindDuplicates,
    onNearEnabledChange,
    onNearThresholdChange,
    onToggleFile,
    onSelectAllDuplicates,
    onDeselectAll,
    onSelectGroupDuplicates,
    onPreviewGroup,
    getDeleteFileIds,
    getDeleteSearchItems,
    onBack,
    refreshAfterDelete,
  };
}

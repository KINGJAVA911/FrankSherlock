import { useState, useCallback } from "react";
import {
  createSmartFolder,
  deleteSmartFolder,
  listSmartFolders,
  reorderSmartFolders,
} from "../api";
import type { SmartFolder } from "../types";
import { errorMessage } from "../utils";

type SmartFolderManagerCallbacks = {
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
};

export function useSmartFolderManager({ onNotice, onError }: SmartFolderManagerCallbacks) {
  const [smartFolders, setSmartFolders] = useState<SmartFolder[]>([]);
  const [showCreateSmartFolder, setShowCreateSmartFolder] = useState(false);
  const [activeSmartFolderId, setActiveSmartFolderId] = useState<number | null>(null);

  const refreshSmartFolders = useCallback(async () => {
    try { setSmartFolders(await listSmartFolders()); } catch { /* ignore */ }
  }, []);

  function onSelectSmartFolder(folder: SmartFolder): { query: string } {
    setActiveSmartFolderId(folder.id);
    return { query: folder.query };
  }

  async function onDeleteSmartFolder(folder: SmartFolder) {
    try {
      await deleteSmartFolder(folder.id);
      await refreshSmartFolders();
      if (activeSmartFolderId === folder.id) setActiveSmartFolderId(null);
      onNotice(`Deleted smart folder "${folder.name}"`);
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  async function onCreateSmartFolderConfirm(name: string, query: string) {
    setShowCreateSmartFolder(false);
    try {
      const folder = await createSmartFolder(name, query);
      await refreshSmartFolders();
      setActiveSmartFolderId(folder.id);
      onNotice(`Saved smart folder "${name}"`);
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  async function onReorderSmartFolders(ids: number[]) {
    try {
      await reorderSmartFolders(ids);
      await refreshSmartFolders();
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  function openCreateModal() {
    setShowCreateSmartFolder(true);
  }

  function closeCreateModal() {
    setShowCreateSmartFolder(false);
  }

  return {
    smartFolders,
    showCreateSmartFolder,
    activeSmartFolderId,
    setActiveSmartFolderId,
    refreshSmartFolders,
    onSelectSmartFolder,
    onDeleteSmartFolder,
    onCreateSmartFolderConfirm,
    onReorderSmartFolders,
    openCreateModal,
    closeCreateModal,
  };
}

import { useState, useCallback } from "react";
import {
  addFilesToAlbum,
  createAlbum,
  deleteAlbum,
  listAlbums,
  reorderAlbums,
} from "../api";
import type { Album } from "../types";
import { errorMessage } from "../utils";

type AlbumManagerCallbacks = {
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
};

export function useAlbumManager({ onNotice, onError }: AlbumManagerCallbacks) {
  const [albums, setAlbums] = useState<Album[]>([]);
  const [showCreateAlbum, setShowCreateAlbum] = useState(false);
  const [pendingAlbumFileIds, setPendingAlbumFileIds] = useState<number[]>([]);

  const refreshAlbums = useCallback(async () => {
    try { setAlbums(await listAlbums()); } catch { /* ignore */ }
  }, []);

  function onSelectAlbum(album: Album): { query: string } {
    const q = album.name.includes(" ") ? `album:"${album.name}"` : `album:${album.name}`;
    return { query: q };
  }

  async function onDeleteAlbum(album: Album) {
    try {
      await deleteAlbum(album.id);
      await refreshAlbums();
      onNotice(`Deleted album "${album.name}"`);
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  async function onAddToAlbum(albumId: number, fileIds: number[]) {
    if (fileIds.length === 0) return;
    try {
      const added = await addFilesToAlbum(albumId, fileIds);
      await refreshAlbums();
      onNotice(`Added ${added} file(s) to album`);
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  function onCreateAlbumFromSelection(fileIds: number[]) {
    setPendingAlbumFileIds(fileIds);
    setShowCreateAlbum(true);
  }

  async function onCreateAlbumConfirm(name: string) {
    setShowCreateAlbum(false);
    try {
      const album = await createAlbum(name);
      if (pendingAlbumFileIds.length > 0) {
        await addFilesToAlbum(album.id, pendingAlbumFileIds);
      }
      const hadFiles = pendingAlbumFileIds.length;
      setPendingAlbumFileIds([]);
      await refreshAlbums();
      onNotice(`Created album "${name}"${hadFiles > 0 ? ` with ${hadFiles} file(s)` : ""}`);
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  async function onReorderAlbums(ids: number[]) {
    try {
      await reorderAlbums(ids);
      await refreshAlbums();
    } catch (err) {
      onError(errorMessage(err));
    }
  }

  function closeCreateModal() {
    setShowCreateAlbum(false);
    setPendingAlbumFileIds([]);
  }

  return {
    albums,
    showCreateAlbum,
    pendingAlbumFileIds,
    refreshAlbums,
    onSelectAlbum,
    onDeleteAlbum,
    onAddToAlbum,
    onCreateAlbumFromSelection,
    onCreateAlbumConfirm,
    onReorderAlbums,
    closeCreateModal,
  };
}

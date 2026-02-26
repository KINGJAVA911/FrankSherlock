import { useCallback, useEffect, useRef, useState } from "react";
import type { UpdateInfo } from "../types";

type AutoUpdateCallbacks = {
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
};

export function useAutoUpdate({ onNotice, onError }: AutoUpdateCallbacks) {
  const [updateInfo, setUpdateInfo] = useState<UpdateInfo | null>(null);
  const [updateChecking, setUpdateChecking] = useState(false);
  const [updateDownloading, setUpdateDownloading] = useState(false);
  const [updateProgress, setUpdateProgress] = useState<{ downloaded: number; total: number | null } | null>(null);
  const updateRef = useRef<Awaited<ReturnType<typeof import("@tauri-apps/plugin-updater").check>> | null>(null);

  const checkForUpdates = useCallback(async (silent: boolean) => {
    if (updateChecking || updateDownloading) return;
    setUpdateChecking(true);
    try {
      const { check } = await import("@tauri-apps/plugin-updater");
      const update = await check();
      if (update) {
        setUpdateInfo({ version: update.version, body: update.body ?? null });
        updateRef.current = update;
      } else if (!silent) {
        onNotice("You're running the latest version");
      }
    } catch {
      if (!silent) onError("Could not check for updates");
    } finally {
      setUpdateChecking(false);
    }
  }, [updateChecking, updateDownloading, onNotice, onError]);

  const installUpdate = useCallback(async () => {
    const update = updateRef.current;
    if (!update || updateDownloading) return;
    setUpdateDownloading(true);
    setUpdateProgress(null);
    try {
      await update.downloadAndInstall((event) => {
        if (event.event === "Started") {
          setUpdateProgress({ downloaded: 0, total: event.data.contentLength ?? null });
        } else if (event.event === "Progress") {
          setUpdateProgress((prev) => ({
            downloaded: (prev?.downloaded ?? 0) + event.data.chunkLength,
            total: prev?.total ?? null,
          }));
        } else if (event.event === "Finished") {
          setUpdateProgress(null);
        }
      });
      const { relaunch } = await import("@tauri-apps/plugin-process");
      await relaunch();
    } catch (err) {
      onError(err instanceof Error ? err.message : String(err));
      setUpdateDownloading(false);
      setUpdateProgress(null);
    }
  }, [updateDownloading, onError]);

  // Check for updates silently on startup
  useEffect(() => {
    checkForUpdates(true);
  }, []); // eslint-disable-line react-hooks/exhaustive-deps

  return {
    updateInfo,
    updateChecking,
    updateDownloading,
    updateProgress,
    checkForUpdates,
    installUpdate,
  };
}

import { useState, useRef, useCallback } from "react";
import { open } from "@tauri-apps/plugin-dialog";
import {
  appHealth,
  cancelScan,
  cleanupOllamaModels,
  ensureDatabase,
  getRuntimeStatus,
  getScanJob,
  getSetupStatus,
  listActiveScans,
  listRoots,
  startScan,
  startSetupDownload,
} from "../api";
import type {
  DbStats,
  RootInfo,
  RuntimeStatus,
  ScanJobStatus,
  SetupStatus,
} from "../types";

const PAGE_SIZE = 80;
const MAX_ITEMS = 400;

type ScanManagerCallbacks = {
  setSetup: (s: SetupStatus) => void;
  setRuntime: (r: RuntimeStatus) => void;
  setDbStats: (d: DbStats) => void;
  setRoots: (r: RootInfo[]) => void;
  setReadOnly: (ro: boolean) => void;
  setShowResumeModal: (show: boolean) => void;
  setNotice: (msg: string) => void;
  setError: (msg: string) => void;
  runSearch: (offset: number, append: boolean, limitOverride?: number) => Promise<void>;
  itemsLength: () => number;
};

export function useScanManager(cb: ScanManagerCallbacks) {
  const [activeScans, setActiveScans] = useState<ScanJobStatus[]>([]);
  const [trackedJobIds, setTrackedJobIds] = useState<number[]>([]);
  const [completedJobs, setCompletedJobs] = useState<ScanJobStatus[]>([]);
  const lastProcessedRef = useRef(0);

  const refreshRoots = useCallback(async () => {
    try {
      const r = await listRoots();
      cb.setRoots(r);
    } catch {
      // Silently ignore
    }
  }, [cb.setRoots]);

  const pollRuntimeAndScans = useCallback(async () => {
    try {
      const ids = trackedJobIds;
      const [setupStatus, runtimeStatus, scans, ...trackedResults] = await Promise.all([
        getSetupStatus(),
        getRuntimeStatus(),
        listActiveScans(),
        ...ids.map((id) => getScanJob(id).catch(() => null)),
      ]);
      cb.setSetup(setupStatus);
      cb.setRuntime(runtimeStatus);
      setActiveScans(scans);

      if (ids.length === 0) return;

      const trackedJobs = trackedResults.filter((j): j is ScanJobStatus => j !== null);
      const stillTracked: number[] = [];
      const justCompleted: ScanJobStatus[] = [];
      let maxProcessed = 0;
      let anyRunning = false;

      for (const job of trackedJobs) {
        if (job.status === "running" || job.status === "pending" || job.status === "interrupted") {
          stillTracked.push(job.id);
          if (job.status === "running") {
            anyRunning = true;
            if (job.processedFiles > maxProcessed) maxProcessed = job.processedFiles;
          }
        } else if (job.status === "completed") {
          justCompleted.push(job);
        } else if (job.status === "failed") {
          cb.setError(job.errorText || `Scan failed for ${job.rootPath.split("/").pop()}`);
        }
      }

      if (anyRunning && maxProcessed > lastProcessedRef.current) {
        lastProcessedRef.current = maxProcessed;
        const liveLimit = Math.max(PAGE_SIZE, Math.min(cb.itemsLength(), MAX_ITEMS));
        void cb.runSearch(0, false, liveLimit);
        void refreshRoots();
      }

      if (justCompleted.length > 0) {
        lastProcessedRef.current = 0;
        setCompletedJobs((prev) => [...prev, ...justCompleted]);
        const stats = await ensureDatabase();
        cb.setDbStats(stats);
        await refreshRoots();
        await cb.runSearch(0, false);
      }

      setTrackedJobIds(stillTracked);
    } catch (err) {
      cb.setError(err instanceof Error ? err.message : String(err));
    }
  }, [trackedJobIds, cb, refreshRoots]);

  async function initApp() {
    try {
      const [db, setupStatus, runtimeStatus, scans, rootList, health] = await Promise.all([
        ensureDatabase(),
        getSetupStatus(),
        getRuntimeStatus(),
        listActiveScans(),
        listRoots(),
        appHealth(),
      ]);
      cb.setDbStats(db);
      cb.setSetup(setupStatus);
      cb.setRuntime(runtimeStatus);
      setActiveScans(scans);
      cb.setRoots(rootList);
      cb.setReadOnly(health.readOnly);
      const runningIds = scans.filter((s) => s.status === "running").map((s) => s.id);
      if (runningIds.length > 0) {
        setTrackedJobIds(runningIds);
      }
      const interrupted = scans.filter((s) => s.status === "interrupted");
      if (interrupted.length > 0) {
        cb.setShowResumeModal(true);
      }
    } catch (err) {
      cb.setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onPickAndScan(setup: SetupStatus | null, readOnly: boolean) {
    if (readOnly) return;
    if (setup && !setup.isReady) {
      cb.setError("Setup is incomplete. Finish Ollama setup before starting scans.");
      return;
    }
    try {
      const selected = await open({ directory: true, multiple: false, title: "Select folder to scan" });
      if (!selected) return;
      setCompletedJobs([]);
      const job = await startScan(selected as string);
      setTrackedJobIds((prev) => [...prev, job.id]);
      lastProcessedRef.current = 0;
      cb.setNotice(`Scan started for ${job.rootPath.split("/").pop()}`);
      await refreshRoots();
      await pollRuntimeAndScans();
    } catch (err) {
      cb.setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onCancelScan(scan: ScanJobStatus, readOnly: boolean) {
    if (readOnly) return;
    try {
      await cancelScan(scan.id);
      cb.setNotice(`Cancelling scan for ${scan.rootPath.split("/").pop()}...`);
    } catch (err) {
      cb.setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onResumeScan(scan: ScanJobStatus, readOnly: boolean) {
    if (readOnly) return;
    try {
      const job = await startScan(scan.rootPath);
      setTrackedJobIds((prev) => [...prev, job.id]);
      setCompletedJobs([]);
      lastProcessedRef.current = 0;
      cb.setNotice(`Resuming scan for ${job.rootPath.split("/").pop()}`);
      await pollRuntimeAndScans();
    } catch (err) {
      cb.setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onResumeAllInterrupted() {
    cb.setShowResumeModal(false);
    const newIds: number[] = [];
    for (const scan of activeScans.filter((s) => s.status === "interrupted")) {
      try {
        const job = await startScan(scan.rootPath);
        newIds.push(job.id);
        lastProcessedRef.current = 0;
      } catch (err) {
        cb.setError(err instanceof Error ? err.message : String(err));
      }
    }
    if (newIds.length > 0) {
      setTrackedJobIds((prev) => [...prev, ...newIds]);
      setCompletedJobs([]);
    }
    await pollRuntimeAndScans();
  }

  async function onCleanupOllama() {
    try {
      const result = await cleanupOllamaModels();
      cb.setNotice(`Unloaded ${result.stoppedModels}/${result.runningModels} model(s).`);
      await pollRuntimeAndScans();
    } catch (err) {
      cb.setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onSetupDownload() {
    try {
      await startSetupDownload();
      await pollRuntimeAndScans();
    } catch (err) {
      cb.setError(err instanceof Error ? err.message : String(err));
    }
  }

  async function onRecheckSetup() {
    await pollRuntimeAndScans();
  }

  return {
    activeScans,
    trackedJobIds,
    completedJobs,
    setCompletedJobs,
    pollRuntimeAndScans,
    initApp,
    onPickAndScan,
    onCancelScan,
    onResumeScan,
    onResumeAllInterrupted,
    onCleanupOllama,
    onSetupDownload,
    onRecheckSetup,
    refreshRoots,
  };
}

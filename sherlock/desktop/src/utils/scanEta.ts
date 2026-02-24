import type { ScanJobStatus } from "../types";

export function formatEta(seconds: number): string {
  if (seconds < 60) return `~${Math.ceil(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.ceil(seconds % 60);
  if (mins < 60) return `~${mins}m ${secs}s`;
  const hrs = Math.floor(mins / 60);
  const remainMins = mins % 60;
  return `~${hrs}h ${remainMins}m`;
}

export function computeEta(scan: ScanJobStatus): string | null {
  if (scan.phase === "discovering") return null;
  if (scan.processedFiles <= 0 || scan.totalFiles <= 0) return null;
  const remaining = scan.totalFiles - scan.processedFiles;
  if (remaining <= 0) return null;
  const now = Date.now() / 1000;
  const elapsed = now - scan.startedAt;
  if (elapsed <= 0) return null;
  const avgPerFile = elapsed / scan.processedFiles;
  const etaSeconds = avgPerFile * remaining;
  return formatEta(etaSeconds);
}

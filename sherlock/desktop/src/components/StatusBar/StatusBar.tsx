import type { RuntimeStatus, DbStats } from "../../types";
import "./StatusBar.css";

type Props = {
  runtime: RuntimeStatus | null;
  dbStats: DbStats | null;
  isScanning: boolean;
  runningScansCount: number;
  selectedCount: number;
  onShowModelInfo?: () => void;
};

export default function StatusBar({ runtime, dbStats, isScanning, runningScansCount, selectedCount, onShowModelInfo }: Props) {
  return (
    <div className="statusbar">
      <span
        className={onShowModelInfo ? "statusbar-clickable" : undefined}
        onClick={onShowModelInfo}
        title="Click for model & hardware details"
        role={onShowModelInfo ? "button" : undefined}
        tabIndex={onShowModelInfo ? 0 : undefined}
        onKeyDown={onShowModelInfo ? (e) => { if (e.key === "Enter" || e.key === " ") onShowModelInfo(); } : undefined}
      >
        VRAM:{" "}
        {runtime?.vramUsedMib != null && runtime?.vramTotalMib != null
          ? `${runtime.vramUsedMib}/${runtime.vramTotalMib} MiB`
          : "n/a"}
      </span>
      <span>Files: {dbStats?.files ?? "..."}</span>
      {isScanning && (
        <span>Scanning: {runningScansCount} active job(s)</span>
      )}
      {selectedCount > 0 && (
        <span>{selectedCount} selected</span>
      )}
      <span className="spacer" />
      <span>Model: {runtime?.currentModel || "none"}</span>
    </div>
  );
}

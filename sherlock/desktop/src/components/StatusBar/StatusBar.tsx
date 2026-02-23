import type { RuntimeStatus } from "../../types";
import "./StatusBar.css";

declare const __APP_VERSION__: string;

type Props = {
  runtime: RuntimeStatus | null;
  isScanning: boolean;
  runningScansCount: number;
  selectedCount: number;
  onShowModelInfo?: () => void;
};

export default function StatusBar({ runtime, isScanning, runningScansCount, selectedCount, onShowModelInfo }: Props) {
  return (
    <div className="statusbar">
      <span>Model: {runtime?.currentModel || "none"}</span>
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
      {isScanning && (
        <span>Scanning: {runningScansCount} active job(s)</span>
      )}
      {selectedCount > 0 && (
        <span>{selectedCount} selected</span>
      )}
      <span className="spacer" />
      <span className="statusbar-version">{__APP_VERSION__}</span>
    </div>
  );
}

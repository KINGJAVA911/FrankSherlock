import type { DbStats, RootInfo, RuntimeStatus, ScanJobStatus } from "../../types";
import RootCard from "./RootCard";
import ScanProgress from "./ScanProgress";
import "./Sidebar.css";

type SidebarProps = {
  roots: RootInfo[];
  selectedRootId: number | null;
  activeScans: ScanJobStatus[];
  runtime: RuntimeStatus | null;
  dbStats: DbStats | null;
  readOnly: boolean;
  setupReady: boolean;
  isScanning: boolean;
  onSelectRoot: (rootId: number | null) => void;
  onDeleteRoot: (root: RootInfo) => void;
  onPickAndScan: () => void;
  onCancelScan: (scan: ScanJobStatus) => void;
  onResumeScan: (scan: ScanJobStatus) => void;
  onCleanupOllama: () => void;
};

export default function Sidebar({
  roots, selectedRootId, activeScans, runtime, dbStats, readOnly,
  setupReady, isScanning, onSelectRoot, onDeleteRoot, onPickAndScan,
  onCancelScan, onResumeScan, onCleanupOllama,
}: SidebarProps) {
  const runningScans = activeScans.filter((s) => s.status === "running");
  const interruptedScans = activeScans.filter((s) => s.status === "interrupted");

  function scanForRoot(rootId: number): ScanJobStatus | undefined {
    return activeScans.find((s) => s.rootId === rootId && s.status === "running");
  }

  return (
    <aside className="sidebar">
      <div className="sidebar-section">
        <span>Folders</span>
        {!readOnly && (
          <button
            type="button"
            className="sidebar-add-btn"
            onClick={onPickAndScan}
            disabled={!setupReady}
            title="Add folder to scan"
          >+</button>
        )}
      </div>

      {roots.length === 0 && (
        <div className="sidebar-empty">No folders scanned yet</div>
      )}

      <div className="root-list">
        {roots.map((root) => (
          <RootCard
            key={root.id}
            root={root}
            isSelected={selectedRootId === root.id}
            scan={scanForRoot(root.id)}
            readOnly={readOnly}
            onSelect={() => onSelectRoot(selectedRootId === root.id ? null : root.id)}
            onDelete={() => onDeleteRoot(root)}
          />
        ))}
      </div>

      {runningScans.map((scan) => (
        <ScanProgress
          key={scan.id}
          scan={scan}
          readOnly={readOnly}
          onCancel={() => onCancelScan(scan)}
        />
      ))}
      {interruptedScans.map((scan) => (
        <ScanProgress
          key={scan.id}
          scan={scan}
          readOnly={readOnly}
          onResume={() => onResumeScan(scan)}
        />
      ))}

      <div className="sidebar-spacer" />

      <div className="sidebar-section"><span>Info</span></div>
      <div className="sidebar-item">Files: <span>{dbStats?.files ?? "..."}</span></div>
      <div className="sidebar-item">Roots: <span>{dbStats?.roots ?? "..."}</span></div>

      <div className="sidebar-section"><span>Actions</span></div>
      <button
        type="button"
        className="sidebar-action-btn"
        onClick={onCleanupOllama}
        disabled={isScanning || (runtime?.loadedModels?.length ?? 0) === 0}
        title={isScanning ? "Cannot unload during scan" : (runtime?.loadedModels?.length ?? 0) === 0 ? "No models loaded" : "Unload all loaded models"}
      >Unload Models</button>
    </aside>
  );
}

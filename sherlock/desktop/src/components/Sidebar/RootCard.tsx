import type { RootInfo, ScanJobStatus } from "../../types";

type RootCardProps = {
  root: RootInfo;
  isSelected: boolean;
  scan: ScanJobStatus | undefined;
  readOnly: boolean;
  onSelect: () => void;
  onDelete: () => void;
};

export default function RootCard({ root, isSelected, scan, readOnly, onSelect, onDelete }: RootCardProps) {
  const progress = scan?.totalFiles
    ? Math.min(100, (scan.processedFiles / Math.max(1, scan.totalFiles)) * 100)
    : 0;

  return (
    <div
      className={`root-card${isSelected ? " selected" : ""}`}
      onClick={onSelect}
      role="button"
      tabIndex={0}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onSelect();
        }
      }}
    >
      <div className="root-card-header">
        <span className="root-card-icon">&#128193;</span>
        <span className="root-card-name" title={root.rootPath}>{root.rootName}</span>
        {!readOnly && (
          <button
            type="button"
            className="root-card-delete"
            onClick={(e) => { e.stopPropagation(); onDelete(); }}
            title="Remove folder"
            aria-label={`Remove ${root.rootName}`}
          >&times;</button>
        )}
      </div>
      <div className="root-card-meta">
        <span>{root.fileCount.toLocaleString()} files</span>
      </div>
      {scan && (
        <div className="root-card-scan">
          <progress value={progress} max={100} />
          <span>{scan.processedFiles}/{scan.totalFiles}</span>
        </div>
      )}
    </div>
  );
}

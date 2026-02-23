import { convertFileSrc } from "@tauri-apps/api/core";
import type { SearchItem } from "../../types";
import ModalOverlay from "./ModalOverlay";
import "./PreviewModal.css";

type Props = {
  previewItems: SearchItem[];
  selectedCount: number;
  singlePreviewIndex: number | null;
  totalItems: number;
  onClose: () => void;
  onNavigate: (index: number) => void;
};

export default function PreviewModal({
  previewItems,
  selectedCount,
  singlePreviewIndex,
  totalItems,
  onClose,
  onNavigate,
}: Props) {
  return (
    <ModalOverlay className="preview-overlay" onBackdropClick={onClose}>
      <div className="preview-modal" onClick={(e) => e.stopPropagation()}>
        <button className="preview-close" onClick={onClose} type="button" aria-label="Close preview">
          &times;
        </button>
        {/* Nav buttons only for single-select preview */}
        {previewItems.length === 1 && singlePreviewIndex != null && singlePreviewIndex > 0 && (
          <button
            className="preview-nav preview-nav-left"
            onClick={() => onNavigate(singlePreviewIndex - 1)}
            type="button"
            aria-label="Previous image"
          >&#8249;</button>
        )}
        {previewItems.length === 1 && singlePreviewIndex != null && singlePreviewIndex < totalItems - 1 && (
          <button
            className="preview-nav preview-nav-right"
            onClick={() => onNavigate(singlePreviewIndex + 1)}
            type="button"
            aria-label="Next image"
          >&#8250;</button>
        )}
        {/* Single image preview */}
        {previewItems.length === 1 && (
          <div className="preview-image-wrap">
            <img src={convertFileSrc(previewItems[0].absPath)} alt={previewItems[0].relPath} />
          </div>
        )}
        {/* Collage preview (2-4 images) */}
        {previewItems.length >= 2 && (
          <div className="preview-collage" data-count={previewItems.length}>
            {previewItems.map(item => (
              <div key={item.id} className="preview-collage-cell">
                <img src={convertFileSrc(item.absPath)} alt={item.relPath} />
              </div>
            ))}
          </div>
        )}
        <div className="preview-info">
          {previewItems.length === 1 ? (
            <>
              <h3 title={previewItems[0].relPath}>{previewItems[0].relPath}</h3>
              <p className="preview-desc">{previewItems[0].description || "No description"}</p>
              <div className="preview-meta">
                <span className="badge">{previewItems[0].mediaType}</span>
                <span>Confidence: {previewItems[0].confidence.toFixed(2)}</span>
                <span>{(previewItems[0].sizeBytes / 1024).toFixed(0)} KB</span>
              </div>
            </>
          ) : (
            <h3>{selectedCount} files selected</h3>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

import { useState, useEffect } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import { getVideoStreamUrl } from "../../api";
import type { SearchItem } from "../../types";
import { fileName } from "../../utils/format";
import { formatBytes } from "../../utils/format";
import PdfViewer from "../Content/PdfViewer";
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

function isPdf(item: SearchItem): boolean {
  return /\.pdf$/i.test(item.relPath);
}

const VIDEO_EXTS = /\.(mp4|mkv|avi|mov|wmv|flv|webm|m4v|ts|mpg|mpeg)$/i;

function isVideo(item: SearchItem): boolean {
  return VIDEO_EXTS.test(item.relPath);
}

type LayoutMode =
  | "single-image"
  | "single-pdf"
  | "single-video"
  | "image-collage"
  | "dual-pdf"
  | "pdf-plus-image";

function detectLayout(items: SearchItem[]): {
  mode: LayoutMode;
  pdfs: SearchItem[];
  images: SearchItem[];
} {
  const pdfs = items.filter(isPdf).slice(0, 2);
  const images = items.filter((i) => !isPdf(i) && !isVideo(i));

  if (items.length === 1) {
    if (isVideo(items[0])) {
      return { mode: "single-video", pdfs, images };
    }
    return isPdf(items[0])
      ? { mode: "single-pdf", pdfs, images }
      : { mode: "single-image", pdfs, images };
  }

  if (pdfs.length >= 2) {
    return { mode: "dual-pdf", pdfs: pdfs.slice(0, 2), images: [] };
  }

  if (pdfs.length === 1 && images.length >= 1) {
    return { mode: "pdf-plus-image", pdfs, images: images.slice(0, 1) };
  }

  return { mode: "image-collage", pdfs: [], images };
}

/** Resolve the best playback URL for a video file. */
function useVideoStreamUrl(absPath: string | undefined): string | null {
  const [url, setUrl] = useState<string | null>(null);

  useEffect(() => {
    if (!absPath) { setUrl(null); return; }
    let cancelled = false;
    getVideoStreamUrl(absPath)
      .then((u) => { if (!cancelled) setUrl(u); })
      .catch(() => {
        // Fallback to asset protocol (works on macOS/Windows)
        if (!cancelled) setUrl(convertFileSrc(absPath));
      });
    return () => { cancelled = true; };
  }, [absPath]);

  return url;
}

export default function PreviewModal({
  previewItems,
  selectedCount,
  singlePreviewIndex,
  totalItems,
  onClose,
  onNavigate,
}: Props) {
  const { mode, pdfs, images } = detectLayout(previewItems);
  const videoItem = mode === "single-video" ? previewItems[0] : undefined;
  const videoUrl = useVideoStreamUrl(videoItem?.absPath);
  const [videoError, setVideoError] = useState(false);

  // Reset error when navigating to a different item
  useEffect(() => { setVideoError(false); }, [videoItem?.absPath]);

  return (
    <ModalOverlay className="preview-overlay" onBackdropClick={onClose}>
      <div className="preview-modal" onClick={(e) => e.stopPropagation()}>
        <button
          className="preview-close"
          onClick={onClose}
          type="button"
          aria-label="Close preview"
        >
          &times;
        </button>
        {/* Nav buttons only for single-select preview (image or PDF) */}
        {previewItems.length === 1 &&
          singlePreviewIndex != null &&
          singlePreviewIndex > 0 && (
            <button
              className="preview-nav preview-nav-left"
              onClick={() => onNavigate(singlePreviewIndex - 1)}
              type="button"
              aria-label="Previous image"
            >
              &#8249;
            </button>
          )}
        {previewItems.length === 1 &&
          singlePreviewIndex != null &&
          singlePreviewIndex < totalItems - 1 && (
            <button
              className="preview-nav preview-nav-right"
              onClick={() => onNavigate(singlePreviewIndex + 1)}
              type="button"
              aria-label="Next image"
            >
              &#8250;
            </button>
          )}

        {/* Single image preview */}
        {mode === "single-image" && (
          <div className="preview-image-wrap">
            <img
              src={convertFileSrc(previewItems[0].absPath)}
              alt={previewItems[0].relPath}
            />
          </div>
        )}

        {/* Single video preview */}
        {mode === "single-video" && !videoError && videoUrl && (
          <div className="preview-video-wrap">
            <video
              key={videoUrl}
              src={videoUrl}
              controls
              autoPlay
              onError={() => setVideoError(true)}
              style={{ maxWidth: "100%", maxHeight: "80vh" }}
            />
          </div>
        )}

        {/* Video loading state */}
        {mode === "single-video" && !videoError && !videoUrl && (
          <div className="preview-video-wrap">
            <p style={{ color: "var(--text-secondary)" }}>Loading video...</p>
          </div>
        )}

        {/* Video error fallback: show thumbnail + message */}
        {mode === "single-video" && videoError && (
          <div className="preview-video-wrap preview-video-fallback">
            {previewItems[0].thumbnailPath && (
              <img
                src={convertFileSrc(previewItems[0].thumbnailPath)}
                alt={previewItems[0].relPath}
                style={{ maxHeight: "50vh", objectFit: "contain" }}
              />
            )}
            <p style={{ color: "var(--text-secondary)", marginTop: 12 }}>
              Video playback not available. Your system may need GStreamer plugins
              (gst-plugins-good, gst-plugins-bad, gst-libav) for codec support.
            </p>
          </div>
        )}

        {/* Single PDF preview */}
        {mode === "single-pdf" && (
          <div className="preview-pdf-wrap">
            <PdfViewer filePath={pdfs[0].absPath} fileId={pdfs[0].id} />
          </div>
        )}

        {/* Dual PDF side-by-side */}
        {mode === "dual-pdf" && (
          <div className="preview-split" data-testid="preview-split">
            <div className="preview-split-pane">
              <PdfViewer filePath={pdfs[0].absPath} fileId={pdfs[0].id} />
            </div>
            <div className="preview-split-pane">
              <PdfViewer filePath={pdfs[1].absPath} fileId={pdfs[1].id} />
            </div>
          </div>
        )}

        {/* PDF + image side-by-side */}
        {mode === "pdf-plus-image" && (
          <div className="preview-split" data-testid="preview-split">
            <div className="preview-split-pane">
              <PdfViewer filePath={pdfs[0].absPath} fileId={pdfs[0].id} />
            </div>
            <div className="preview-split-pane preview-image-wrap">
              <img
                src={convertFileSrc(images[0].absPath)}
                alt={images[0].relPath}
              />
            </div>
          </div>
        )}

        {/* Image collage (2-10 images, no PDFs) */}
        {mode === "image-collage" && (
          <div className="preview-collage" data-count={images.length}>
            {images.map((item, idx) => (
              <div key={item.id} className="preview-collage-cell">
                <img
                  src={convertFileSrc(item.absPath)}
                  alt={item.relPath}
                />
                {images.length > 1 && (
                  <span className="preview-collage-label">{idx + 1}</span>
                )}
              </div>
            ))}
          </div>
        )}

        <div className="preview-info">
          {previewItems.length === 1 ? (
            <>
              <h3 title={previewItems[0].relPath}>
                {previewItems[0].relPath}
              </h3>
              <p className="preview-desc">
                {previewItems[0].description || "No description"}
              </p>
              <div className="preview-meta">
                <span className="badge">{previewItems[0].mediaType}</span>
                <span>
                  Confidence: {previewItems[0].confidence.toFixed(2)}
                </span>
                <span>
                  {formatBytes(previewItems[0].sizeBytes)}
                </span>
              </div>
            </>
          ) : previewItems.length <= 10 && singlePreviewIndex === null ? (
            <div className="preview-compare-list">
              {previewItems.map((item, idx) => (
                <div key={item.id} className="preview-compare-row">
                  <span className="preview-compare-num">{idx + 1}</span>
                  <span className="preview-compare-name" title={item.absPath}>
                    {fileName(item.relPath)}
                  </span>
                  <span className="preview-compare-meta">{formatBytes(item.sizeBytes)}</span>
                  <span className="preview-compare-meta">{item.mediaType}</span>
                  <span className="preview-compare-meta">
                    {new Date(item.mtimeNs / 1_000_000).toLocaleDateString()}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <h3>{selectedCount} files selected</h3>
          )}
        </div>
      </div>
    </ModalOverlay>
  );
}

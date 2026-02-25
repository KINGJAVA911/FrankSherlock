import { useEffect, useState } from "react";
import { getFileProperties } from "../../api";
import type { FileProperties } from "../../types";
import { errorMessage } from "../../utils";
import ModalOverlay from "./ModalOverlay";
import "./shared-modal.css";
import "./PropertiesModal.css";

type Props = {
  fileId: number;
  onClose: () => void;
};

function formatBytes(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDate(mtimeNs: number): string {
  const ms = mtimeNs / 1_000_000;
  return new Date(ms).toLocaleString();
}

function formatDuration(secs: number): string {
  const total = Math.round(secs);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const s = total % 60;
  if (h > 0) return `${h}h ${String(m).padStart(2, "0")}m`;
  if (m > 0) return `${m}m ${String(s).padStart(2, "0")}s`;
  return `${s}s`;
}

function Row({ label, value }: { label: string; value: string | undefined | null; mono?: boolean }) {
  if (!value) return null;
  return (
    <div className="properties-row">
      <span className="properties-label">{label}</span>
      <span className="properties-value">{value}</span>
    </div>
  );
}

function MonoRow({ label, value }: { label: string; value: string | undefined | null }) {
  if (!value) return null;
  return (
    <div className="properties-row">
      <span className="properties-label">{label}</span>
      <span className="properties-value mono">{value}</span>
    </div>
  );
}

export default function PropertiesModal({ fileId, onClose }: Props) {
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [props, setProps] = useState<FileProperties | null>(null);

  useEffect(() => {
    let cancelled = false;
    getFileProperties(fileId)
      .then((data) => {
        if (cancelled) return;
        setProps(data);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setLoadError(errorMessage(err));
        setLoading(false);
      });
    return () => { cancelled = true; };
  }, [fileId]);

  function handleKeyDown(e: React.KeyboardEvent) {
    if (e.key === "Escape") {
      e.preventDefault();
      onClose();
    }
  }

  const hasExif = props && (
    props.cameraMake || props.cameraModel || props.lensModel ||
    props.focalLength || props.aperture || props.exposureTime || props.iso
  );

  const hasDimensions = props && (props.imageWidth || props.imageHeight);
  const hasLocation = props && (props.gpsLocation || props.locationText);
  const hasVideo = props && (props.durationSecs != null || props.videoCodec || props.audioCodec);

  return (
    <ModalOverlay onBackdropClick={onClose}>
      <div
        className="modal-base properties-modal"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={handleKeyDown}
        tabIndex={-1}
      >
        <h3>
          Properties
          {props && <span className="badge">{props.mediaType}</span>}
        </h3>

        {loading && <div className="properties-loading">Loading...</div>}
        {loadError && <p className="properties-error">{loadError}</p>}

        {props && !loading && !loadError && (
          <div className="properties-body">
            {/* General */}
            <div className="properties-section">
              <div className="properties-section-title">General</div>
              <Row label="Name" value={props.filename} />
              <Row label="Path" value={props.absPath} />
              <Row label="Relative Path" value={props.relPath} />
              <Row label="Root" value={props.rootPath} />
              <Row label="Size" value={`${formatBytes(props.sizeBytes)} (${props.sizeBytes.toLocaleString()} bytes)`} />
              <Row label="Modified" value={formatDate(props.mtimeNs)} />
              {props.dateTaken && <Row label="Date Taken" value={props.dateTaken} />}
            </div>

            {/* Image info */}
            {(hasDimensions || props.colorSpace) && (
              <div className="properties-section">
                <div className="properties-section-title">Image</div>
                {hasDimensions && (
                  <Row label="Dimensions" value={`${props.imageWidth} x ${props.imageHeight} px`} />
                )}
                <Row label="Color Space" value={props.colorSpace} />
              </div>
            )}

            {/* Video info */}
            {hasVideo && (
              <div className="properties-section">
                <div className="properties-section-title">Video</div>
                {props.durationSecs != null && (
                  <Row label="Duration" value={formatDuration(props.durationSecs)} />
                )}
                {props.videoWidth != null && props.videoHeight != null && (
                  <Row label="Resolution" value={`${props.videoWidth} x ${props.videoHeight}`} />
                )}
                <Row label="Video Codec" value={props.videoCodec} />
                <Row label="Audio Codec" value={props.audioCodec} />
              </div>
            )}

            {/* Camera / EXIF */}
            {hasExif && (
              <div className="properties-section">
                <div className="properties-section-title">Camera</div>
                <Row label="Make" value={props.cameraMake} />
                <Row label="Model" value={props.cameraModel} />
                <Row label="Lens" value={props.lensModel} />
                <Row label="Focal Length" value={props.focalLength} />
                <Row label="Aperture" value={props.aperture ? `f/${props.aperture}` : null} />
                <Row label="Exposure" value={props.exposureTime ? `${props.exposureTime} s` : null} />
                <Row label="ISO" value={props.iso} />
              </div>
            )}

            {/* Location */}
            {hasLocation && (
              <div className="properties-section">
                <div className="properties-section-title">Location</div>
                <Row label="Location" value={props.gpsLocation || props.locationText} />
                {props.latitude != null && props.longitude != null && (
                  <Row label="Coordinates" value={`${props.latitude.toFixed(6)}, ${props.longitude.toFixed(6)}`} />
                )}
              </div>
            )}

            {/* Classification */}
            <div className="properties-section">
              <div className="properties-section-title">Classification</div>
              <Row label="Type" value={props.mediaType} />
              <Row label="Confidence" value={`${(props.confidence * 100).toFixed(0)}%`} />
              <Row label="Description" value={props.description} />
              {props.canonicalMentions && <Row label="Mentions" value={props.canonicalMentions} />}
              {props.extractedText && <Row label="OCR Text" value={props.extractedText} />}
            </div>

            {/* Internal */}
            <div className="properties-section">
              <div className="properties-section-title">Internal</div>
              <MonoRow label="Fingerprint" value={props.fingerprint} />
            </div>

            <div className="modal-actions">
              <button type="button" onClick={onClose}>Close</button>
            </div>
          </div>
        )}
      </div>
    </ModalOverlay>
  );
}

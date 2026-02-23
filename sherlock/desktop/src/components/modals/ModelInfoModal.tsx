import type { RuntimeStatus, SetupStatus } from "../../types";
import { formatBytes } from "../../utils/format";
import ModalOverlay from "./ModalOverlay";
import "./shared-modal.css";
import "./ModelInfoModal.css";

type Props = {
  runtime: RuntimeStatus;
  setup: SetupStatus | null;
  onClose: () => void;
};

function vendorLabel(vendor: string): string {
  switch (vendor) {
    case "nvidia": return "NVIDIA";
    case "amd": return "AMD";
    case "apple": return "Apple Silicon";
    default: return "Unknown";
  }
}

export default function ModelInfoModal({ runtime, setup, onClose }: Props) {
  return (
    <ModalOverlay onBackdropClick={onClose}>
      <div className="modal-base model-info-modal" onClick={(e) => e.stopPropagation()}>
        <h3>Model & Hardware Info</h3>

        <div className="model-info-grid">
          <div className="model-info-section">
            <h4>Hardware</h4>
            <dl>
              <dt>GPU</dt>
              <dd>{vendorLabel(runtime.gpuVendor)}</dd>
              {runtime.vramTotalMib != null && (
                <>
                  <dt>VRAM</dt>
                  <dd>
                    {runtime.vramUsedMib != null
                      ? `${runtime.vramUsedMib} / ${runtime.vramTotalMib} MiB`
                      : `${runtime.vramTotalMib} MiB total`}
                  </dd>
                </>
              )}
              <dt>System RAM</dt>
              <dd>{formatBytes(runtime.systemRamMib * 1024 * 1024)}</dd>
              <dt>Memory type</dt>
              <dd>{runtime.unifiedMemory ? "Unified" : "Discrete"}</dd>
            </dl>
          </div>

          <div className="model-info-section">
            <h4>Model selection</h4>
            <dl>
              {setup && (
                <>
                  <dt>Recommended</dt>
                  <dd className="model-tag">{setup.recommendedModel}</dd>
                  <dt>Tier</dt>
                  <dd>{setup.modelTier}</dd>
                  <dt>Reason</dt>
                  <dd>{setup.modelSelectionReason}</dd>
                </>
              )}
              <dt>Ollama</dt>
              <dd>{runtime.ollamaAvailable ? "Running" : "Not detected"}</dd>
            </dl>
          </div>

          <div className="model-info-section">
            <h4>Loaded models</h4>
            {runtime.loadedModels.length > 0 ? (
              <ul className="model-list">
                {runtime.loadedModels.map((m) => (
                  <li key={m}>
                    <span className="model-tag">{m}</span>
                    {runtime.currentModel === m && <span className="model-active">active</span>}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="model-empty">No models currently loaded</p>
            )}
          </div>

          {setup && setup.missingModels.length > 0 && (
            <div className="model-info-section">
              <h4>Missing models</h4>
              <ul className="model-list">
                {setup.missingModels.map((m) => (
                  <li key={m}><span className="model-tag model-missing">{m}</span></li>
                ))}
              </ul>
            </div>
          )}
        </div>

        <div className="modal-actions">
          <button type="button" onClick={onClose}>Close</button>
        </div>
      </div>
    </ModalOverlay>
  );
}

import { useEffect, useState, useRef, useCallback } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import type { PersonInfo, FaceInfo, ReclusterProgress } from "../../types";
import {
  listPersons,
  renamePerson,
  reclusterFaces,
  getReclusterStatus,
  listFacesForPerson,
  unassignFaceFromPerson,
} from "../../api";
import "./FacesView.css";

type Props = {
  onBack: () => void;
  onSelectPerson: (personId: number, personName: string) => void;
  onNotice: (msg: string) => void;
  onError: (msg: string) => void;
};

export default function FacesView({ onBack, onSelectPerson, onNotice, onError }: Props) {
  const [persons, setPersons] = useState<PersonInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [editValue, setEditValue] = useState("");
  const [reclusterStatus, setReclusterStatus] = useState<ReclusterProgress | null>(null);
  const [selectedPerson, setSelectedPerson] = useState<PersonInfo | null>(null);
  const [faces, setFaces] = useState<FaceInfo[]>([]);
  const [facesLoading, setFacesLoading] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);

  const loadPersons = useCallback(() => {
    setLoading(true);
    listPersons([])
      .then(setPersons)
      .catch(() => {})
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadPersons();
  }, [loadPersons]);

  // Poll recluster progress while running
  useEffect(() => {
    if (!reclusterStatus) return;
    const id = setInterval(async () => {
      try {
        const status = await getReclusterStatus();
        if (status) {
          setReclusterStatus(status);
          if (status.phase === "done" && status.result) {
            onNotice(
              `Re-clustered: ${status.result.newPersons} people, ${status.result.assignedFaces} faces assigned`,
            );
            // Give the backend time to clear, then reload
            setTimeout(() => {
              setReclusterStatus(null);
              setSelectedPerson(null);
              loadPersons();
            }, 600);
          }
        } else {
          // Backend cleared progress — done
          setReclusterStatus(null);
          setSelectedPerson(null);
          loadPersons();
        }
      } catch {
        /* ignore */
      }
    }, 500);
    return () => clearInterval(id);
  }, [reclusterStatus, loadPersons, onNotice]);

  useEffect(() => {
    if (editingId !== null && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const totalFaces = persons.reduce((sum, p) => sum + p.faceCount, 0);
  const isReclustering = reclusterStatus !== null;

  function startRename(person: PersonInfo) {
    setEditingId(person.id);
    setEditValue(person.name);
  }

  async function handleRecluster() {
    try {
      setReclusterStatus({ phase: "crops", total: 0, processed: 0, result: null });
      await reclusterFaces();
    } catch (err) {
      onError(String(err));
      setReclusterStatus(null);
    }
  }

  async function commitRename(personId: number) {
    const trimmed = editValue.trim();
    setEditingId(null);
    if (!trimmed) return;
    const person = persons.find((p) => p.id === personId);
    if (person && trimmed === person.name) return;
    try {
      await renamePerson(personId, trimmed);
      onNotice(`Renamed to "${trimmed}"`);
      loadPersons();
      // Update selectedPerson name if this is the currently viewed person
      if (selectedPerson && selectedPerson.id === personId) {
        setSelectedPerson({ ...selectedPerson, name: trimmed });
      }
    } catch (err) {
      onError(String(err));
    }
  }

  function handleSelectPerson(person: PersonInfo) {
    setSelectedPerson(person);
    setFacesLoading(true);
    listFacesForPerson(person.id)
      .then(setFaces)
      .catch(() => setFaces([]))
      .finally(() => setFacesLoading(false));
  }

  async function handleUnassignFace(faceId: number) {
    try {
      await unassignFaceFromPerson(faceId);
      onNotice("Face removed from person");
      // Refresh face list
      const updated = faces.filter((f) => f.id !== faceId);
      setFaces(updated);
      // Refresh person list to get updated counts
      loadPersons();
      // If no faces left, go back to grid
      if (updated.length === 0) {
        setSelectedPerson(null);
      }
    } catch (err) {
      onError(String(err));
    }
  }

  function renderProgress() {
    if (!reclusterStatus) return null;
    const { phase, total, processed } = reclusterStatus;
    if (phase === "crops" && total > 0) {
      const pct = Math.round((processed / total) * 100);
      return (
        <div className="faces-progress">
          Regenerating face crops... {processed}/{total} ({pct}%)
        </div>
      );
    }
    if (phase === "crops") {
      return <div className="faces-progress">Preparing re-cluster...</div>;
    }
    if (phase === "clustering") {
      return <div className="faces-progress">Clustering faces...</div>;
    }
    if (phase === "done") {
      return <div className="faces-progress">Done! Reloading...</div>;
    }
    return null;
  }

  // ── Person detail view ────────────────────────────────────────────
  if (selectedPerson) {
    return (
      <div className="faces-view">
        <div className="faces-toolbar">
          <button type="button" onClick={() => setSelectedPerson(null)}>
            Back to People
          </button>
          <div className="faces-stats">
            <strong>{selectedPerson.name}</strong> &mdash; {faces.length} face
            {faces.length !== 1 ? "s" : ""}
          </div>
          <button
            type="button"
            onClick={() => onSelectPerson(selectedPerson.id, selectedPerson.name)}
          >
            View Photos
          </button>
        </div>

        <div className="faces-body">
          {facesLoading && <div className="faces-loading">Loading faces...</div>}
          {!facesLoading && faces.length === 0 && (
            <div className="faces-empty">No faces for this person.</div>
          )}
          {!facesLoading && faces.length > 0 && (
            <div className="faces-detail-grid">
              {faces.map((face) => (
                <div key={face.id} className="faces-detail-card">
                  <div className="faces-detail-crop">
                    {face.cropPath ? (
                      <img src={convertFileSrc(face.cropPath)} alt="" loading="lazy" />
                    ) : (
                      <div className="faces-card-placeholder" />
                    )}
                  </div>
                  <div className="faces-detail-info">
                    <span className="faces-detail-filename" title={face.relPath}>
                      {face.filename}
                    </span>
                    <span className="faces-detail-confidence">
                      {(face.confidence * 100).toFixed(0)}% confidence
                    </span>
                    <button
                      type="button"
                      className="faces-detail-remove"
                      onClick={() => handleUnassignFace(face.id)}
                    >
                      Remove
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>
    );
  }

  // ── Person grid view ──────────────────────────────────────────────
  return (
    <div className="faces-view">
      <div className="faces-toolbar">
        <div className="faces-stats">
          <strong>{persons.length}</strong> {persons.length !== 1 ? "people" : "person"},{" "}
          <strong>{totalFaces}</strong> face{totalFaces !== 1 ? "s" : ""} total
        </div>
        <button
          type="button"
          onClick={handleRecluster}
          disabled={isReclustering || persons.length === 0}
        >
          {isReclustering ? "Re-clustering..." : "Re-cluster"}
        </button>
        <button type="button" onClick={onBack}>
          Back
        </button>
      </div>

      {renderProgress()}

      <div className="faces-body">
        {loading && <div className="faces-loading">Loading...</div>}
        {!loading && persons.length === 0 && !isReclustering && (
          <div className="faces-empty">
            No faces clustered yet. Right-click a folder and select &quot;Detect Faces&quot; to
            scan for faces.
          </div>
        )}
        {!loading && persons.length > 0 && (
          <div className="faces-grid">
            {persons.map((person) => (
              <div
                key={person.id}
                className="faces-card"
                onClick={() => handleSelectPerson(person)}
                title={`${person.name} (${person.faceCount} face${person.faceCount !== 1 ? "s" : ""})`}
              >
                <div className="faces-card-crop">
                  {person.cropPath ? (
                    <img src={convertFileSrc(person.cropPath)} alt="" loading="lazy" />
                  ) : (
                    <div className="faces-card-placeholder" />
                  )}
                  <span className="faces-card-badge">{person.faceCount}</span>
                </div>
                <div className="faces-card-name">
                  {editingId === person.id ? (
                    <input
                      ref={inputRef}
                      className="faces-card-name-input"
                      value={editValue}
                      onChange={(e) => setEditValue(e.target.value)}
                      onBlur={() => commitRename(person.id)}
                      onKeyDown={(e) => {
                        if (e.key === "Enter") commitRename(person.id);
                        if (e.key === "Escape") setEditingId(null);
                      }}
                      onClick={(e) => e.stopPropagation()}
                    />
                  ) : (
                    <span
                      className="faces-card-name-label"
                      onClick={(e) => {
                        e.stopPropagation();
                        startRename(person);
                      }}
                      title="Click to rename"
                    >
                      {person.name}
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

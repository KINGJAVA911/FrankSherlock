import { useEffect, useState, useRef } from "react";
import { convertFileSrc } from "@tauri-apps/api/core";
import type { PersonInfo } from "../../types";
import { listPersons, renamePerson } from "../../api";
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
  const inputRef = useRef<HTMLInputElement>(null);

  function loadPersons() {
    setLoading(true);
    listPersons([])
      .then(setPersons)
      .catch(() => {})
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    loadPersons();
  }, []);

  useEffect(() => {
    if (editingId !== null && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [editingId]);

  const totalFaces = persons.reduce((sum, p) => sum + p.faceCount, 0);

  function startRename(person: PersonInfo) {
    setEditingId(person.id);
    setEditValue(person.name);
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
    } catch (err) {
      onError(String(err));
    }
  }

  return (
    <div className="faces-view">
      <div className="faces-toolbar">
        <div className="faces-stats">
          <strong>{persons.length}</strong> {persons.length !== 1 ? "people" : "person"},
          {" "}<strong>{totalFaces}</strong> face{totalFaces !== 1 ? "s" : ""} total
        </div>
        <button type="button" onClick={onBack}>Back</button>
      </div>

      <div className="faces-body">
        {loading && <div className="faces-loading">Loading...</div>}
        {!loading && persons.length === 0 && (
          <div className="faces-empty">
            No faces clustered yet. Right-click a folder and select &quot;Detect Faces&quot; to scan for faces.
          </div>
        )}
        {!loading && persons.length > 0 && (
          <div className="faces-grid">
            {persons.map((person) => (
              <div
                key={person.id}
                className="faces-card"
                onClick={() => onSelectPerson(person.id, person.name)}
                title={`${person.name} (${person.faceCount} face${person.faceCount !== 1 ? "s" : ""})`}
              >
                <div className="faces-card-crop">
                  {person.cropPath ? (
                    <img src={convertFileSrc(person.cropPath)} alt="" loading="lazy" />
                  ) : person.thumbnailPath ? (
                    <img src={convertFileSrc(person.thumbnailPath)} alt="" loading="lazy" />
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

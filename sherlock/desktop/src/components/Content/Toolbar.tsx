import { useEffect } from "react";
import type { SortField, SortOrder } from "../../types";

type Props = {
  query: string;
  onQueryChange: (value: string) => void;
  selectedMediaType: string;
  onMediaTypeChange: (value: string) => void;
  mediaTypeOptions: string[];
  sortBy: SortField;
  onSortByChange: (value: SortField) => void;
  sortOrder: SortOrder;
  onSortOrderChange: (value: SortOrder) => void;
  hasTextQuery: boolean;
};

export default function Toolbar({
  query, onQueryChange, selectedMediaType, onMediaTypeChange, mediaTypeOptions,
  sortBy, onSortByChange, sortOrder, onSortOrderChange, hasTextQuery,
}: Props) {
  // When the text query is cleared, switch away from relevance sort
  useEffect(() => {
    if (!hasTextQuery && sortBy === "relevance") {
      onSortByChange("dateModified");
    }
  }, [hasTextQuery, sortBy, onSortByChange]);

  return (
    <div className="toolbar">
      <input
        type="search"
        placeholder="Search images..."
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        aria-label="Search query"
      />
      <select
        value={selectedMediaType}
        onChange={(e) => onMediaTypeChange(e.target.value)}
        aria-label="Media type filter"
      >
        {mediaTypeOptions.map((opt) => (
          <option key={opt} value={opt}>
            {opt ? opt : "all types"}
          </option>
        ))}
      </select>
      <select
        className="toolbar-sort-select"
        value={sortBy}
        onChange={(e) => onSortByChange(e.target.value as SortField)}
        aria-label="Sort field"
      >
        {hasTextQuery && <option value="relevance">Relevance</option>}
        <option value="dateModified">Date modified</option>
        <option value="name">Name</option>
        <option value="type">Type</option>
      </select>
      {sortBy !== "relevance" && (
        <button
          className="toolbar-sort-dir"
          onClick={() => onSortOrderChange(sortOrder === "asc" ? "desc" : "asc")}
          aria-label="Sort direction"
          title={sortOrder === "asc" ? "Ascending" : "Descending"}
        >
          {sortOrder === "asc" ? "\u2191" : "\u2193"}
        </button>
      )}
    </div>
  );
}

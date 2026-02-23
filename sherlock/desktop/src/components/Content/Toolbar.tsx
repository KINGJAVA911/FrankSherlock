type Props = {
  query: string;
  onQueryChange: (value: string) => void;
  selectedMediaType: string;
  onMediaTypeChange: (value: string) => void;
  mediaTypeOptions: string[];
};

export default function Toolbar({ query, onQueryChange, selectedMediaType, onMediaTypeChange, mediaTypeOptions }: Props) {
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
    </div>
  );
}

type Props = {
  count: number;
  total: number;
  loading: boolean;
  isScanning: boolean;
  selectedRootName: string | null;
};

export default function ResultsMeta({ count, total, loading, isScanning, selectedRootName }: Props) {
  return (
    <div className="results-meta">
      <span>
        {count} of {total} results
        {selectedRootName && (
          <> in <strong>{selectedRootName}</strong></>
        )}
      </span>
      {loading && <span>Searching...</span>}
      {isScanning && <span className="scanning-indicator">Scanning...</span>}
    </div>
  );
}

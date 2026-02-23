import { useEffect, useState } from "react";

export function useToast() {
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!notice) return;
    const t = setTimeout(() => setNotice(null), 6000);
    return () => clearTimeout(t);
  }, [notice]);

  useEffect(() => {
    if (!error) return;
    const t = setTimeout(() => setError(null), 10000);
    return () => clearTimeout(t);
  }, [error]);

  return { notice, error, setNotice, setError };
}

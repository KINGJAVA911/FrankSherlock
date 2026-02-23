export function fileName(relPath: string): string {
  const i = relPath.lastIndexOf("/");
  return i >= 0 ? relPath.slice(i + 1) : relPath;
}

export function formatElapsed(startedAt: number, completedAt: number | null | undefined): string {
  if (!completedAt) return "n/a";
  const totalSecs = completedAt - startedAt;
  if (totalSecs < 60) return `${totalSecs}s`;
  const mins = Math.floor(totalSecs / 60);
  const secs = totalSecs % 60;
  if (mins < 60) return `${mins}m ${secs}s`;
  const hours = Math.floor(mins / 60);
  return `${hours}h ${mins % 60}m`;
}

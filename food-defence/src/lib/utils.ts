/** Risk colour scale: low (emerald) -> medium (amber) -> high (red) */
export function riskColor(value: number, max = 1): string {
  const ratio = Math.min(value / max, 1);
  if (ratio < 0.25) return "text-emerald-600";
  if (ratio < 0.5) return "text-amber-500";
  if (ratio < 0.75) return "text-orange-500";
  return "text-red-600";
}

export function riskBg(value: number, max = 1): string {
  const ratio = Math.min(value / max, 1);
  if (ratio < 0.25) return "bg-emerald-500";
  if (ratio < 0.5) return "bg-amber-500";
  if (ratio < 0.75) return "bg-orange-500";
  return "bg-red-500";
}

export function riskBgLight(value: number, max = 1): string {
  const ratio = Math.min(value / max, 1);
  if (ratio < 0.25) return "bg-emerald-50";
  if (ratio < 0.5) return "bg-amber-50";
  if (ratio < 0.75) return "bg-orange-50";
  return "bg-red-50";
}

export function riskHex(value: number, max = 1): string {
  const ratio = Math.min(value / max, 1);
  if (ratio < 0.25) return "#10b981";
  if (ratio < 0.5) return "#f59e0b";
  if (ratio < 0.75) return "#f97316";
  return "#ef4444";
}

/** Format a number for display */
export function fmt(n: number, decimals = 3): string {
  if (n == null || isNaN(n)) return "N/A";
  return n.toFixed(decimals);
}

export function fmtPct(n: number): string {
  if (n == null || isNaN(n)) return "N/A";
  return (n * 100).toFixed(1) + "%";
}

export function fmtInt(n: number): string {
  if (n == null || isNaN(n)) return "N/A";
  return n.toLocaleString();
}

/** Truncate string with ellipsis */
export function truncate(s: string, max = 30): string {
  if (!s) return "";
  return s.length > max ? s.slice(0, max) + "..." : s;
}

/** Get HS chapter (first 2 digits) from HS code */
export function hsChapter(hs: string): string {
  return hs.slice(0, 2);
}

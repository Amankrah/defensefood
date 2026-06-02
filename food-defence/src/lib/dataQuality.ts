/** Short labels for API ``sci_unavailable_reason`` codes (corridor table). */

export type SciUnavailableReason =
  | "no_trade_footprint"
  | "ds_prime_error"
  | "zero_destination_imports"
  | "hhi_unavailable"
  | "no_hazard_signal";

export type DataQualityTier = "full" | "hazard_only" | "partial" | "unavailable";

const SHORT: Record<SciUnavailableReason, string> = {
  no_trade_footprint: "No trade data",
  ds_prime_error: "Invalid balance sheet",
  zero_destination_imports: "No destination imports",
  hhi_unavailable: "HHI unavailable",
  no_hazard_signal: "No hazard signal",
};

export function sciReasonShort(
  reason: string | null | undefined
): string | null {
  if (!reason) return null;
  return SHORT[reason as SciUnavailableReason] ?? reason.replaceAll("_", " ");
}

export function structuralGapTitle(
  label: string | null | undefined,
  reason: string | null | undefined,
  cvsHazardOnly?: number | null
): string {
  const parts: string[] = [];
  if (label) parts.push(label);
  else if (reason) parts.push(sciReasonShort(reason) ?? reason);
  if (cvsHazardOnly != null) {
    parts.push(`Hazard-only priority fallback: ${cvsHazardOnly.toFixed(3)}`);
  }
  return parts.join(" · ") || "Structural score unavailable";
}

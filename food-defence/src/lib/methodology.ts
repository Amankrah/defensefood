"use client";

/**
 * Methodology catalogue client + React hook.
 *
 * Fetches /api/v1/research/methodology once, caches it in module scope, and
 * exposes typed lookups by metric key. The backend is the single source of
 * truth for: formula_latex, formula_plain, scale, when_matters, related,
 * inputs, definition.
 *
 * Frontend `METRIC` (in `labels.ts`) stays as the short label/abbr fallback
 * for synchronous renders where the catalogue hasn't loaded yet.
 */

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { MetricInterpretation, MethodologyEntry, MethodologyScaleBand } from "@/lib/types";

let _cache: Record<string, MethodologyEntry> | null = null;
let _pending: Promise<Record<string, MethodologyEntry>> | null = null;

async function fetchCatalogue(): Promise<Record<string, MethodologyEntry>> {
  if (_cache) return _cache;
  if (_pending) return _pending;
  _pending = api.research.methodology().then((r) => {
    const m: Record<string, MethodologyEntry> = {};
    for (const e of r.entries) m[e.key] = e;
    _cache = m;
    _pending = null;
    return m;
  });
  return _pending;
}

/** Synchronous lookup; returns null until first load completes. */
export function getMethodologyEntry(key: string): MethodologyEntry | null {
  return _cache?.[key] ?? null;
}

/** Hook returning the entry for a single key (null until catalogue loads). */
export function useMethodologyEntry(key: string | null): MethodologyEntry | null {
  const [entry, setEntry] = useState<MethodologyEntry | null>(
    key ? _cache?.[key] ?? null : null
  );
  useEffect(() => {
    if (!key) {
      setEntry(null);
      return;
    }
    let cancelled = false;
    fetchCatalogue().then((m) => {
      if (!cancelled) setEntry(m[key] ?? null);
    });
    return () => {
      cancelled = true;
    };
  }, [key]);
  return entry;
}

/** Hook returning the full catalogue (null until first load). */
export function useMethodologyCatalogue(): Record<string, MethodologyEntry> | null {
  const [cat, setCat] = useState<Record<string, MethodologyEntry> | null>(_cache);
  useEffect(() => {
    if (_cache) {
      setCat(_cache);
      return;
    }
    let cancelled = false;
    fetchCatalogue().then((m) => {
      if (!cancelled) setCat(m);
    });
    return () => {
      cancelled = true;
    };
  }, []);
  return cat;
}

/**
 * Find the scale band whose [min, max) contains `value`. Returns null when
 * the entry has no scale (e.g. DS' raw kg quantity) or value isn't finite.
 */
export function findScaleBand(
  entry: MethodologyEntry | null,
  value: number | null | undefined
): MethodologyScaleBand | null {
  if (!entry?.scale?.length) return null;
  if (value == null || Number.isNaN(value) || !Number.isFinite(value)) return null;
  for (const band of entry.scale) {
    if (value >= band.min && value < band.max) return band;
  }
  // Edge: value above last band's max (shouldn't happen but defend)
  return entry.scale[entry.scale.length - 1] ?? null;
}

/** Client-side fallback when the API didn't return an `interpretations` map. */
export function interpretValueLocal(
  entry: MethodologyEntry | null,
  value: number | null | undefined
): MetricInterpretation {
  const band = findScaleBand(entry, value);
  if (!band || value == null) {
    return {
      verdict: "Not available",
      band: "low",
      advice: null,
      label: entry?.name ?? null,
      ok: false,
    };
  }
  return {
    verdict: band.label,
    band: band.band,
    advice: band.advice,
    label: entry?.name ?? null,
    ok: true,
  };
}

/**
 * Map band tone to Tailwind classes — re-exports interpret.ts's `bandClasses`
 * shape so call sites can use either source uniformly.
 */
export { bandClasses } from "@/lib/interpret";

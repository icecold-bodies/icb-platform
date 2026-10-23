// RT10 — revisions visible. Michael's rule (22 Oct 2026): "the first save does not have a REV number ever … Call the
// 1st quote REV 0, then REV 1 etc." REV = the stored version − 1 (the version itself is never rewritten). The one
// client mapping for the SPA; the server's is backend/app/services/revisions.py (the API also sends `rev`).
//
// The chain (RT10_RULING_1 Q1) is the quote number. Latest = the highest version among the chain's LIVE rows (the
// server decides it: `is_latest`, `latest_rev`, `latest_id`). A costing is identified by its RECORD ID everywhere —
// never by its quote number, which every revision of a quote shares (RT10_RETURN_1 §4: keyed by quote number, the
// list left ghost rows and Accept reached the oldest revision).

export function revNumber(version?: number | null): number {
  const v = Number(version)
  return Math.max((Number.isFinite(v) && v > 0 ? v : 1) - 1, 0)
}

export function revLabel(version?: number | null): string {
  return `REV ${revNumber(version)}`
}

/** Staff screens: `N10022/10/2026 · REV 1` — REV 0 included, so a group reads clearly. */
export function staffLabel(quoteNumber: string | null | undefined, version?: number | null, rev?: number | null): string {
  const n = rev ?? revNumber(version)
  return `${quoteNumber ?? ''} · REV ${n}`
}

interface Keyed { calculation_id?: number; quote_number: string }

/** The one identity of a costing row: its record id (a mock row without one falls back to its quote number). */
export function rowKey(c: Keyed): string {
  return c.calculation_id != null ? `c${c.calculation_id}` : `q${c.quote_number}`
}

interface Groupable extends Keyed { version?: number | null; is_latest?: boolean | null; created_at?: string }

/** The list's order with each quote's revisions together, latest on top, the group where its latest (or, when the
 *  latest is not on the page, its first row) falls in the current order. Pure; the input order is the list's sort. */
export function groupRevisions<T extends Groupable>(rows: T[]): T[] {
  const groups = new Map<string, T[]>()
  for (const r of rows) {
    const k = r.quote_number || rowKey(r)
    const g = groups.get(k)
    if (g) g.push(r)
    else groups.set(k, [r])
  }
  const anchorOf = new Map<string, number>()
  rows.forEach((r, i) => {
    const k = r.quote_number || rowKey(r)
    if (r.is_latest && !anchorOf.has(k)) anchorOf.set(k, i)
  })
  rows.forEach((r, i) => {
    const k = r.quote_number || rowKey(r)
    if (!anchorOf.has(k)) anchorOf.set(k, i)
  })
  const order = [...groups.keys()].sort((a, b) => (anchorOf.get(a) ?? 0) - (anchorOf.get(b) ?? 0))
  const byVersion = (a: T, b: T) =>
    (Number(b.version ?? 1) - Number(a.version ?? 1)) ||
    String(b.created_at ?? '').localeCompare(String(a.created_at ?? '')) ||
    ((b.calculation_id ?? 0) - (a.calculation_id ?? 0))
  return order.flatMap((k) => [...(groups.get(k) as T[])].sort(byVersion))
}

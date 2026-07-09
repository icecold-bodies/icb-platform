// Standardized Plan job drawer (Michael, 3 Jul — "standardize on the second modal layout").
// ONE corporate right-drawer for every card on /plan: the planner grid (V/P slots), Panels ready,
// Pre-Assembly / Merge, Parking and QC all open THIS. Layout = the A06 job-modal design system
// (.mh kicker/number header, red-underline .tabs, .frow fact rows, table.bom) so it reads
// identically to the floor mockup Michael approved.
//
// Tabs:
//   Overview — the stage actions (for a scheduled V/P job this is the existing CockpitSlotDetail
//              node, passed in by the cockpit with all its handlers wired); otherwise job facts.
//   Bill of Materials — the REAL costing-sheet items (GET /api/plan/job-card/{job}), grouped per
//              category, COLLAPSED by default; no ratios/margins/discounts (Michael's rule).
//   Chassis — the full chassis-page header (same fields + resolved type picture) via the bundle.
//   Pre-Job — card state + PDF.
import { useEffect, useMemo, useState, type ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { Clock } from 'lucide-react'

import { apiGet } from '../../lib/api'
import { TONE_BAR, TONE_TEXT, pctClamped, progressTone } from '../Planning/cockpit/slotProgress'

export interface PlanBomItem {
  code: string | null
  material: string
  quantity: number
  unit: string
  unit_price: number | null
  line_total: number | null
}
export interface PlanBomCategory { category: string; count: number; total: number | null; items: PlanBomItem[] }
export interface PlanStageClock {
  stage: string            // thresholds stage_code ('panels_ready' | 'pre_assembly' | 'merge' | 'qc')
  label: string            // the threshold row's label (what the admin captured)
  stage_label: string      // the floor position ('Pre-Merge' vs the shared 'Merge' threshold)
  threshold_hours: number
  started_at: string | null    // engine transition stamp; null = entry predates v1.40.8 stamps
  elapsed_hours: number | null // SERVER-computed at fetch; the drawer ticks forward from fetch
}
export interface PlanJobBundle {
  job: { id: number; job_number: string; customer?: string | null; description?: string | null
         status?: string | null; calculation_id?: number | null }
  bom: { quote_number?: string | null; version: number; show_cost: boolean
         categories: PlanBomCategory[]; grand_total: number | null } | null
  chassis: Record<string, unknown> | null
  prejob: { id: number; status: string; sent_for_check_at?: string | null; pdf_url: string } | null
  stage_clock?: PlanStageClock | null   // v1.40.8 — floor-stage clock (Michael 9 Jul)
}

/** v1.40.8 — the drawer header's floor-stage clock: "Pre-Assembly clock · 12.3h of 40h (31%)".
 * Server computes elapsed at fetch; this ticks forward from the fetch moment (60s), so client
 * clock skew never enters the math (the V/P slotProgress model). Hidden when the floor entry
 * predates the engine's transition stamps (no invented start times). */
function FloorStageClock({ clock, fetchedAtMs }: { clock: PlanStageClock; fetchedAtMs: number }) {
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 60_000)
    return () => clearInterval(t)
  }, [])
  if (clock.elapsed_hours == null) return null
  const elapsed = clock.elapsed_hours + Math.max(0, nowMs - fetchedAtMs) / 3_600_000
  const tone = progressTone(elapsed, clock.threshold_hours)
  const fmt = (h: number) => `${(Math.round(h * 10) / 10).toFixed(1)}h`
  return (
    <div data-testid="floor-stage-clock" data-tone={tone}
         className="mt-2 flex items-center gap-2 rounded-md bg-white/70 px-2.5 py-2">
      <Clock size={15} className={TONE_TEXT[tone]} />
      <div className="min-w-0 flex-1">
        <div className="text-[10px] uppercase tracking-wide text-muted">
          {clock.stage_label} clock{clock.stage_label !== clock.label ? ` · ${clock.label} threshold` : ''}
        </div>
        <div className={`text-sm font-semibold tabular-nums ${TONE_TEXT[tone]}`}>
          {fmt(elapsed)} of {fmt(clock.threshold_hours)}
          {' '}({Math.round((elapsed / clock.threshold_hours) * 100)}%)
          {tone === 'red' ? ' — over threshold' : ''}
        </div>
      </div>
      <div className="h-1.5 w-20 shrink-0 overflow-hidden rounded-full bg-line/60">
        <div className={`h-full ${TONE_BAR[tone]}`}
             style={{ width: `${pctClamped(elapsed, clock.threshold_hours)}%` }} />
      </div>
    </div>
  )
}

const zar = (n: number) =>
  'R ' + n.toLocaleString('en-ZA', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const qty = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(2))

type TabKey = 'overview' | 'bom' | 'chassis' | 'prejob'

/** Slide-in shell (scrim + right aside) on the a06 .scrim/.modal classes — must render inside an
 * `.a06-flow`-scoped element. Same rAF open transition as the floor drawer. */
export function PlanJobDrawerShell({ onClose, label, children }: {
  onClose: () => void; label: string; children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setOpen(true))
    return () => cancelAnimationFrame(id)
  }, [])
  return (
    <>
      <div className={`scrim ${open ? 'show' : ''}`} onClick={onClose} />
      <aside className={`modal ${open ? 'open' : ''}`} role="dialog" aria-label={label}
             data-testid="plan-job-drawer">
        {children}
      </aside>
    </>
  )
}

export function PlanJobTabs({ kicker, jobNumber, subtitle, slotLabel, overview, chassisId, initialTab, onClose }: {
  kicker: string                       // SCHEDULED JOB · PANEL SET · ASSEMBLY · QUALITY CONTROL · CHASSIS
  jobNumber?: string | null
  subtitle?: string | null             // customer · body line under the number
  slotLabel?: string | null            // e.g. "V-1 · 2026-W27"
  overview?: ReactNode                 // stage actions (cockpit slot detail) — becomes the Overview tab
  chassisId?: number | null            // chassis-only cards (no job): fetch the chassis directly
  initialTab?: TabKey
  onClose: () => void
}) {
  const [bundle, setBundle] = useState<PlanJobBundle | null>(null)
  const [chassisOnly, setChassisOnly] = useState<Record<string, unknown> | null>(null)
  const [loading, setLoading] = useState(true)
  const [tab, setTab] = useState<TabKey>(initialTab ?? (overview ? 'overview' : 'bom'))
  const [openCats, setOpenCats] = useState<Set<string>>(new Set())
  const [fetchedAtMs, setFetchedAtMs] = useState(() => Date.now())   // v1.40.8 — stage-clock tick anchor

  useEffect(() => {
    let live = true
    setLoading(true)
    const done = () => { if (live) setLoading(false) }
    if (jobNumber) {
      apiGet<PlanJobBundle>(`/api/plan/job-card/${encodeURIComponent(jobNumber)}`)
        .then((b) => { if (live) { setBundle(b); setFetchedAtMs(Date.now()) } })
        .catch(() => { /* facts-only drawer */ }).finally(done)
    } else if (chassisId != null) {
      apiGet<Record<string, unknown>>(`/api/chassis-records/${chassisId}`)
        .then((c) => { if (live) setChassisOnly(c) }).catch(() => { /* header-only */ }).finally(done)
    } else { setLoading(false) }
    return () => { live = false }
  }, [jobNumber, chassisId])

  const chassis = (bundle?.chassis ?? chassisOnly) as Record<string, unknown> | null
  const bom = bundle?.bom ?? null
  const prejob = bundle?.prejob ?? null

  const tabs = useMemo(() => {
    const t: { key: TabKey; label: string }[] = []
    if (overview) t.push({ key: 'overview', label: 'Overview' })
    if (jobNumber) t.push({ key: 'bom', label: 'Bill of Materials' })
    t.push({ key: 'chassis', label: 'Chassis' })
    if (jobNumber) t.push({ key: 'prejob', label: 'Pre-Job' })
    return t
  }, [overview, jobNumber])

  const toggleCat = (c: string) =>
    setOpenCats((prev) => { const n = new Set(prev); if (n.has(c)) n.delete(c); else n.add(c); return n })

  const s = (k: string): string => {
    const v = chassis?.[k]
    return v == null || v === '' ? '—' : String(v)
  }

  return (
    <>
      <div className="mh">
        <div className="top">
          <div>
            <div className="kind">{kicker}</div>
            <div className="num">{jobNumber ? `#${jobNumber}` : s('vin')}</div>
            {subtitle && <div className="meta">{subtitle}</div>}
            {slotLabel && <div className="job">{slotLabel}</div>}
            {/* v1.40.8 — floor-stage clock, header-level so every tab shows it */}
            {bundle?.stage_clock && <FloorStageClock clock={bundle.stage_clock} fetchedAtMs={fetchedAtMs} />}
          </div>
          <button className="x" onClick={onClose} data-testid="plan-drawer-close">✕</button>
        </div>
        <div className="tabs" data-testid="plan-drawer-tabs">
          {tabs.map((t) => (
            <button key={t.key} className={`tab ${tab === t.key ? 'on' : ''}`}
                    data-testid={`plan-tab-${t.key}`} onClick={() => setTab(t.key)}>
              {t.label}
            </button>
          ))}
        </div>
      </div>
      <div className="mbody">
        {tab === 'overview' && overview}

        {tab === 'bom' && (
          loading ? <div className="draw">Loading the costing sheet…</div>
          : !bom || bom.categories.length === 0 ? (
            <div className="draw">No costing sheet linked to this job yet.</div>
          ) : (
            <div data-testid="plan-bom">
              <div className="frow"><span className="k">Costing</span>
                <span className="v">{bom.quote_number || '—'} · v{bom.version}</span></div>
              <div className="frow"><span className="k">Lines</span>
                <span className="v">{bom.categories.reduce((a, c) => a + c.count, 0)} items · {bom.categories.length} categories</span></div>
              {bom.categories.map((c) => {
                const on = openCats.has(c.category)
                return (
                  <div key={c.category}>
                    <button className={`bomcat ${on ? 'on' : ''}`} data-testid="plan-bom-cat"
                            data-cat={c.category} onClick={() => toggleCat(c.category)}>
                      <span className="chev">▸</span> {c.category}
                      <span className="n">{c.count} item{c.count === 1 ? '' : 's'}</span>
                      <span className="amt">{c.total != null ? zar(c.total) : ''}</span>
                    </button>
                    {on && (
                      <div className="bomwrap">
                        <table className="bom">
                          <thead><tr>
                            <th>Code</th><th>Description</th><th style={{ textAlign: 'right' }}>Qty</th>
                            {bom.show_cost && <th style={{ textAlign: 'right' }}>Unit price</th>}
                            {bom.show_cost && <th style={{ textAlign: 'right' }}>Line total</th>}
                          </tr></thead>
                          <tbody>
                            {c.items.map((it, i) => (
                              <tr key={i}>
                                <td className="code">{it.code || '—'}</td>
                                <td>{it.material}</td>
                                <td style={{ textAlign: 'right' }}>{qty(it.quantity)}{it.unit ? <span className="sup"> {it.unit}</span> : null}</td>
                                {bom.show_cost && <td style={{ textAlign: 'right' }}>{it.unit_price != null ? zar(it.unit_price) : '—'}</td>}
                                {bom.show_cost && <td style={{ textAlign: 'right' }}>{it.line_total != null ? zar(it.line_total) : '—'}</td>}
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                )
              })}
              {bom.show_cost && bom.grand_total != null && (
                <div className="bomtotal" data-testid="plan-bom-grand">
                  <span>Grand total (materials)</span><span>{zar(bom.grand_total)}</span>
                </div>
              )}
            </div>
          )
        )}

        {tab === 'chassis' && (
          loading ? <div className="draw">Loading the chassis record…</div>
          : !chassis ? <div className="draw">No chassis linked to this job yet.</div>
          : (
            <div data-testid="plan-chassis">
              {typeof chassis.type_image_url === 'string' && chassis.type_image_url && (
                <img src={chassis.type_image_url as string} alt="Chassis type"
                     style={{ display: 'block', width: '100%', maxHeight: 170, objectFit: 'contain',
                              border: '1px solid var(--hair)', borderRadius: 10, background: '#fff',
                              marginBottom: 12 }} />
              )}
              <div className="frow"><span className="k">VIN</span>
                <span className="v" style={{ fontFamily: 'ui-monospace,Consolas,monospace' }}>{s('vin')}</span></div>
              <div className="frow"><span className="k">Status</span>
                <span className="v" style={{ textTransform: 'capitalize' }}>{s('status').replace(/_/g, ' ')}</span></div>
              <div className="frow"><span className="k">Customer</span><span className="v">{s('customer_name')}</span></div>
              <div className="frow"><span className="k">Dealer</span><span className="v">{s('dealer_name')}</span></div>
              <div className="frow"><span className="k">Contact</span><span className="v">{s('contact_person')}</span></div>
              <div className="frow"><span className="k">Telephone</span><span className="v">{s('telephone')}</span></div>
              <div className="frow"><span className="k">Job number</span><span className="v">{s('job_number')}</span></div>
              <div className="frow"><span className="k">Make / model</span>
                <span className="v">{[chassis.make, chassis.model].filter(Boolean).join(' ') || '—'}</span></div>
              <div className="frow"><span className="k">Description</span><span className="v">{s('description')}</span></div>
              <div className="frow"><span className="k">Tail lift</span><span className="v">{s('tail_lift_code')}</span></div>
              <div className="frow"><span className="k">Body gap</span>
                <span className="v">{chassis.body_gap_mm != null ? `${chassis.body_gap_mm} mm` : '—'}</span></div>
              <div className="frow"><span className="k">Delivery ETA</span><span className="v">{s('chassis_eta')}</span></div>
              <div className="frow"><span className="k">Lifecycle</span>
                <span className="v">{Number(chassis.event_count ?? 0)} event{Number(chassis.event_count ?? 0) === 1 ? '' : 's'}</span></div>
              <div className="frow"><span className="k">Origin ref</span><span className="v">{s('created_source_ref')}</span></div>
              {typeof chassis.id === 'number' && (
                <div style={{ marginTop: 14 }}>
                  <Link to={`/chassis/${chassis.id}`} data-testid="plan-open-chassis"
                        style={{ fontSize: 12.5, fontWeight: 700, color: '#2563EB', textDecoration: 'none' }}>
                    Open chassis page →
                  </Link>
                </div>
              )}
            </div>
          )
        )}

        {tab === 'prejob' && (
          loading ? <div className="draw">Loading…</div>
          : !prejob ? <div className="draw">No Pre-Job Card for this job yet.</div>
          : (
            <div data-testid="plan-prejob">
              <div className="frow"><span className="k">Status</span>
                <span className="v" style={{ textTransform: 'capitalize' }}>{prejob.status.replace(/_/g, ' ')}</span></div>
              <div className="frow"><span className="k">Sent for check</span>
                <span className="v">{prejob.sent_for_check_at ? prejob.sent_for_check_at.slice(0, 16).replace('T', ' ') : '—'}</span></div>
              <div style={{ marginTop: 14 }}>
                <a href={prejob.pdf_url} target="_blank" rel="noreferrer"
                   style={{ fontSize: 12.5, fontWeight: 700, color: '#2563EB', textDecoration: 'none' }}>
                  Open Pre-Job Card PDF →
                </a>
              </div>
            </div>
          )
        )}
      </div>
    </>
  )
}

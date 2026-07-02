// WO A09 — Combined Cockpit (Rapid Prototype Phase).
// One integrated page (handover §2, top → bottom): the A06 Production Flow
// dashboard (header + 6 KPIs) → the LIVE MES Planning Cockpit (week × slot
// grid, Unscheduled rail, Inspector, filters, week nav, summary — the existing
// component, embedded, dock hidden) → Panels ready → Pre-Assembly → Merge →
// Parking. Single component tree, no iframe; the planner mounts into the A06
// shell via a React portal so the §2 stacking order lives in one column.
//
// Wiring (§3/§4): the Job is the spine. "Panels ready" is DERIVED from the
// same live PlanningContext board the cockpit mutates — scheduling a job onto
// a V-x/P-x slot books its cut on that machine; the panel-set surfaces here
// and vanishes on unschedule. Readiness: the MES has no Vacuum/Press
// cut-complete event yet, so per the companion Pre-Assembly handover's
// RATIFIED D2, `ready` uses the scheduled-readiness proxy with this mapping
// as the single hook for the future panels_cut signal (documented deviation
// from §4.4 until that event exists). §4.3 guards live in the engine: a
// started job's body is never yanked and its panel never resurrects.
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './productionFlow.css'
import { initProductionFlow } from './productionFlowEngine'
import { usePlanning } from '../../store/PlanningContext'
import { PlanningCockpit } from '../Planning/cockpit/PlanningCockpit'
import { apiGet } from '../../lib/api'
import { useRefetchOnFocus } from '../../lib/useRefetchOnFocus'
import type { PlanningBoardView } from '../../lib/types'
import type { ChassisRecord } from '../Chassis/types'

interface FlowApi {
  cleanup: () => void
  setPanels: (list: unknown[]) => void
  setParking: (list: unknown[]) => void
  getMergedJobs: () => string[]
  plannerSlot: HTMLElement | null
}

// Board → PanelSet contract (§4.1). Method/origin from the slot machine
// (V-x → Vacuum, P-x → Press); length parsed from the body-type text (the
// planning job carries no numeric length), fallback 5.4 m.
function boardToPanels(board: PlanningBoardView) {
  const seen = new Set<number>()
  const panels: unknown[] = []
  for (const s of board.slots) {
    const j = s.job
    if (!j || seen.has(j.id)) continue
    const bay = s.bay || ''
    const isV = bay.startsWith('V-'), isP = bay.startsWith('P-')
    if (!isV && !isP) continue
    seen.add(j.id)
    const bt = j.body_type || ''
    const m = bt.match(/(\d+(?:[.,]\d+)?)\s*m\b/i)
    const len = m ? parseFloat(m[1].replace(',', '.')) : 5.4
    // Fallback '' when the job carries no body_type (the card template appends "body" itself).
    const type = bt.replace(/(\d+(?:[.,]\d+)?)\s*m\b/i, '').trim().replace(/^[-·,\s]+/, '')
    panels.push({
      id: 'PS-' + j.job_number,
      job: j.job_number,
      cust: j.customer,
      len: Number.isFinite(len) && len > 0 ? len : 5.4,
      type,
      method: isV ? 'Vacuum' : 'Press',
      origin: bay,
      vin: j.vin,    // the job's linked chassis VIN — rides onto the started body's tag + merge hints
      ready: true,   // D2 readiness proxy (scheduled) — future: the real panels_cut signal
    })
  }
  return panels
}

// Chassis records → Parking cards (job-spine): the MES parking pool = chassis with
// status 'in_workshop' (booked in, awaiting their body — the bay model's own
// definition). The card's `job` links via the board (job.vin === chassis.vin), which
// is what the merge-matching rule and the drag guides key on. `kind` picks the
// side-view image only (trailer keywords → trailer, else truck).
function chassisToParking(rows: ChassisRecord[], board: PlanningBoardView) {
  const vinToJob = new Map<string, string>()
  for (const s of board.slots) if (s.job?.vin) vinToJob.set(String(s.job.vin), s.job.job_number)
  for (const j of board.pool) if (j.vin) vinToJob.set(String(j.vin), j.job_number)
  return rows
    .filter((r) => r.status === 'in_workshop' && r.vin)
    .map((r) => {
      const model = [r.make, r.model].filter(Boolean).join(' ') || '—'
      const kind = /trailer|tri[- ]?axle|drawbar|semi/i.test(model) ? 'trailer' : 'truck'
      return { id: r.vin, cust: r.customer_name || '—', model, job: vinToJob.get(String(r.vin)) ?? null, kind }
    })
}

export function PlanCombined() {
  const ref = useRef<HTMLDivElement>(null)
  const [api, setApi] = useState<FlowApi | null>(null)
  // Business rules (2 Jul): MERGED WITH CHASSIS = the permanent point of no
  // return. The engine pushes its merged set up; the embedded planner locks
  // those jobs against backward moves (unschedule / revert-to-unscheduled).
  const [mergedJobNos, setMergedJobNos] = useState<string[]>([])
  const { board, mode } = usePlanning()

  useEffect(() => {
    if (!ref.current) return
    const inst = initProductionFlow(ref.current, {
      onChange: (s: { mergedJobs: string[] }) => setMergedJobNos(s.mergedJobs),
    }) as FlowApi
    setApi(inst)
    return () => { inst.cleanup(); setApi(null) }
  }, [])

  // Merged job numbers → planner job ids (the planner keys on production_job.id).
  const lockedJobIds = useMemo(() => {
    if (!mergedJobNos.length) return undefined
    const set = new Set<number>()
    const want = new Set(mergedJobNos.map(String))
    for (const s of board.slots) if (s.job && want.has(String(s.job.job_number))) set.add(s.job.id)
    for (const j of board.pool) if (want.has(String(j.job_number))) set.add(j.id)
    return set.size ? set : undefined
  }, [mergedJobNos, board])

  // Live link: every board change (schedule / move / unschedule / window nav /
  // focus refetch) re-derives the Panels-ready set. In mock/offline mode the
  // floor keeps its seed and the cockpit shows its own offline notice.
  useEffect(() => {
    if (!api || mode !== 'live') return
    api.setPanels(boardToPanels(board))
  }, [api, board, mode])

  // Live Parking: the MES chassis records (in_workshop pool), refreshed on tab
  // focus like every other floor surface, re-pushed whenever the board changes
  // (the chassis→job link derives from the board's VINs).
  const [chassisRows, setChassisRows] = useState<ChassisRecord[]>([])
  const refetchChassis = useCallback(async () => {
    try { setChassisRows(await apiGet<ChassisRecord[]>('/api/chassis-records?limit=200')) } catch { /* keep last */ }
  }, [])
  useEffect(() => { void refetchChassis() }, [refetchChassis])
  useRefetchOnFocus(refetchChassis)
  useEffect(() => {
    if (!api || mode !== 'live') return
    api.setParking(chassisToParking(chassisRows, board))
  }, [api, board, chassisRows, mode])

  return (
    <>
      <div ref={ref} className="a06-flow" data-testid="plan-combined" />
      {api?.plannerSlot &&
        createPortal(
          <div className="zone" style={{ overflow: 'hidden' }} data-testid="plan-embedded-cockpit">
            <div style={{ height: '76vh' }}>
              <PlanningCockpit embedded lockedJobIds={lockedJobIds} />
            </div>
          </div>,
          api.plannerSlot,
        )}
    </>
  )
}

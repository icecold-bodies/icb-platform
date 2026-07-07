// WO A09 — Combined Cockpit (Rapid Prototype Phase).
// One integrated page (handover §2, top → bottom; the A06 header strip + KPI
// row were removed per Michael 6 Jul): the LIVE MES Planning Cockpit (week ×
// slot grid, Unscheduled rail, Inspector, filters, week nav, summary — the
// existing component, embedded, dock hidden) → Panels ready → Pre-Assembly →
// Merge → Parking. Single component tree, no iframe; the planner mounts into
// the A06 shell via a React portal so the §2 stacking order lives in one column.
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
import { PlanningCockpit, type RenderSlotDrawer } from '../Planning/cockpit/PlanningCockpit'
import { PlanJobDrawerShell, PlanJobTabs } from './PlanJobDrawer'
import { apiGet, apiPut } from '../../lib/api'
import { useRefetchOnFocus } from '../../lib/useRefetchOnFocus'
import type { PlanningBoardView } from '../../lib/types'
import type { ChassisRecord } from '../Chassis/types'

interface FlowApi {
  cleanup: () => void
  setPanels: (list: unknown[]) => void
  setParking: (list: unknown[]) => void
  getMergedJobs: () => string[]
  loadState: (json: string | null) => boolean
  getState: () => string
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
      jobId: j.id,   // the grid drag carries the production_job id (application/x-panel-job)
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
      // 0033 — the user-picked (or catalog-default) chassis-type picture rides the card through
      // Parking AND into the merge bay (the engine falls back to the mockup art when null).
      return { id: r.vin, cust: r.customer_name || '—', model, job: vinToJob.get(String(r.vin)) ?? null, kind,
               img: r.type_image_url ?? null }
    })
}

export function PlanCombined() {
  const ref = useRef<HTMLDivElement>(null)
  const [api, setApi] = useState<FlowApi | null>(null)
  // Business rules (2 Jul): MERGED WITH CHASSIS = the permanent point of no
  // return. The engine pushes its merged set up; the embedded planner locks
  // those jobs against backward moves (unschedule / revert-to-unscheduled).
  const [mergedJobNos, setMergedJobNos] = useState<string[]>([])
  // Single-location rule: jobs that left the V/P stage (Panels ready / floor / QC) — the
  // embedded grid hides their cards and the summary rows re-count without them.
  const [downstreamJobNos, setDownstreamJobNos] = useState<string[]>([])
  const { board, mode } = usePlanning()

  // 3 Jul — the standardized job drawer (every /plan card opens it; kicker names the stage).
  const [drawer, setDrawer] = useState<{
    kicker: string; jobNumber?: string; chassisId?: number
    subtitle?: string; initialTab?: 'chassis' | 'bom'
  } | null>(null)
  // The engine's onOpenCard callback is captured once at init — read live data through refs.
  const boardRef = useRef(board)
  useEffect(() => { boardRef.current = board }, [board])
  const chassisRowsRef = useRef<ChassisRecord[]>([])
  const apiRef = useRef<FlowApi | null>(null)

  // Phase 2 — persisted floor state: the engine hands us a snapshot on every floor
  // mutation (onPersist) -> PUT /api/plan/floor-state; on mount we load the saved
  // floor; a poll picks up other users' changes (stamp-based echo avoidance,
  // last-write-wins). The floor survives reloads and is shared between planners.
  const stampRef = useRef<string | null>(null)
  const loadedRef = useRef(false)
  // 3 Jul — resolve an engine card click to the standardized drawer. Returns false (engine modal
  // fallback) when the card can't be matched to live data (e.g. mock mode / the A06 seed).
  const openCardDrawer = useCallback((kind: string, id: string): boolean => {
    if (mode !== 'live') return false
    const b = boardRef.current
    const jobMeta = (jobNo: string) => {
      for (const s of b.slots) if (s.job && String(s.job.job_number) === jobNo) return s.job
      for (const j of b.pool) if (String(j.job_number) === jobNo) return j
      return null
    }
    const open = (kicker: string, jobNo: string | null, chassisId?: number, initialTab?: 'chassis' | 'bom') => {
      const j = jobNo ? jobMeta(jobNo) : null
      const ch = chassisId != null ? chassisRowsRef.current.find((r) => r.id === chassisId) : undefined
      setDrawer({
        kicker,
        jobNumber: jobNo ?? undefined,
        chassisId,
        subtitle: j ? [j.customer, j.body_type].filter(Boolean).join(' · ')
          : ch ? [ch.customer_name, [ch.make, ch.model].filter(Boolean).join(' ')].filter(Boolean).join(' · ')
          : undefined,
        initialTab,
      })
      return true
    }
    if (kind === 'panel' && id.startsWith('PS-')) return open('PANELS READY', id.slice(3))
    if (kind === 'chassis') {
      const row = chassisRowsRef.current.find((r) => String(r.vin) === id)
      if (!row) return false
      let jobNo: string | null = null
      for (const s of b.slots) if (s.job?.vin && String(s.job.vin) === id) jobNo = s.job.job_number
      if (!jobNo) for (const j of b.pool) if (j.vin && String(j.vin) === id) jobNo = j.job_number
      return open('CHASSIS', jobNo, row.id, 'chassis')
    }
    if (kind === 'body') {
      try {
        const st = JSON.parse(apiRef.current?.getState() ?? '{}')
        for (const bay of st.pre ?? []) {
          for (const x of bay.bodies ?? []) if (String(x.id) === id) return open('ASSEMBLY', String(x.job))
          if (bay.merge?.assembly && String(bay.merge.assembly.id) === id) return open('MERGE', String(bay.merge.assembly.job))
          if (bay.merge?.attached?.body && String(bay.merge.attached.body.id) === id) return open('MERGED UNIT', String(bay.merge.attached.body.job))
        }
        for (const u of st.qc ?? []) if (String(u.id) === id) return open('QUALITY CONTROL', String(u.job))
      } catch { /* fall through to the engine modal */ }
    }
    return false
  }, [mode])
  const openCardRef = useRef(openCardDrawer)
  useEffect(() => { openCardRef.current = openCardDrawer }, [openCardDrawer])

  useEffect(() => {
    if (!ref.current) return
    const inst = initProductionFlow(ref.current, {
      onChange: (s: { mergedJobs: string[]; downstreamJobs?: string[] }) => {
        setMergedJobNos(s.mergedJobs)
        setDownstreamJobNos(s.downstreamJobs ?? [])
      },
      onPersist: (json: string) => {
        void apiPut<{ updated_at: string }>('/api/plan/floor-state', { state: json })
          .then((r) => { stampRef.current = r.updated_at })
          .catch(() => { /* non-fatal — next mutation retries */ })
      },
      // 3 Jul — card clicks route to the standardized React drawer (stable ref: live data inside).
      onOpenCard: (kind: string, id: string) => openCardRef.current(kind, id),
    }) as FlowApi
    setApi(inst)
    apiRef.current = inst
    return () => { inst.cleanup(); setApi(null); apiRef.current = null }
  }, [])

  // Initial floor load + the change poll (floor 8s; board + chassis 30s).
  const { refresh } = usePlanning()
  useEffect(() => {
    if (!api || mode !== 'live') return
    let dead = false
    const pull = async (initial: boolean) => {
      try {
        const r = await apiGet<{ state: string | null; updated_at: string | null }>('/api/plan/floor-state')
        if (dead) return
        if (initial || (r.updated_at && r.updated_at !== stampRef.current)) {
          if (api.loadState(r.state)) stampRef.current = r.updated_at
        }
      } catch { /* offline — keep the current floor */ }
    }
    if (!loadedRef.current) { loadedRef.current = true; void pull(true) }
    const floorPoll = window.setInterval(() => { void pull(false) }, 8000)
    const dataPoll = window.setInterval(() => { void refresh(); void refetchChassis() }, 30000)
    return () => { dead = true; window.clearInterval(floorPoll); window.clearInterval(dataPoll) }
  }, [api, mode, refresh])

  // Merged job numbers → planner job ids (the planner keys on production_job.id).
  const lockedJobIds = useMemo(() => {
    if (!mergedJobNos.length) return undefined
    const set = new Set<number>()
    const want = new Set(mergedJobNos.map(String))
    for (const s of board.slots) if (s.job && want.has(String(s.job.job_number))) set.add(s.job.id)
    for (const j of board.pool) if (want.has(String(j.job_number))) set.add(j.id)
    return set.size ? set : undefined
  }, [mergedJobNos, board])

  const downstreamJobIds = useMemo(() => {
    if (!downstreamJobNos.length) return undefined
    const set = new Set<number>()
    const want = new Set(downstreamJobNos.map(String))
    for (const s of board.slots) if (s.job && want.has(String(s.job.job_number))) set.add(s.job.id)
    return set.size ? set : undefined
  }, [downstreamJobNos, board])

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
  useEffect(() => { chassisRowsRef.current = chassisRows }, [chassisRows])
  const refetchChassis = useCallback(async () => {
    try { setChassisRows(await apiGet<ChassisRecord[]>('/api/chassis-records?limit=200')) } catch { /* keep last */ }
  }, [])
  useEffect(() => { void refetchChassis() }, [refetchChassis])
  useRefetchOnFocus(refetchChassis)
  useEffect(() => {
    if (!api || mode !== 'live') return
    api.setParking(chassisToParking(chassisRows, board))
  }, [api, board, chassisRows, mode])

  // 3 Jul — the cockpit's slot drawer now renders the SAME standardized tabbed layout as every
  // other /plan card; the cockpit supplies its stage-actions node (CockpitSlotDetail) as Overview.
  const renderSlotDrawer: RenderSlotDrawer = useCallback(({ slot, overview, close }) => (
    <PlanJobDrawerShell label={`Job ${slot.job?.job_number ?? ''}`} onClose={close}>
      <PlanJobTabs
        kicker="SCHEDULED JOB"
        jobNumber={slot.job?.job_number}
        subtitle={[slot.job?.customer, slot.job?.body_type].filter(Boolean).join(' · ') || undefined}
        // A10 day-slots: the slot label names the exact day (legacy null renders as Monday)
        slotLabel={`${slot.bay} · ${slot.week_key} · ${['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'][slot.day_of_week ?? 0]}`}
        overview={overview}
        onClose={close}
      />
    </PlanJobDrawerShell>
  ), [])

  return (
    <>
      <div ref={ref} className="a06-flow" data-testid="plan-combined" />
      {api?.plannerSlot &&
        createPortal(
          <div className="zone" style={{ overflow: 'hidden' }} data-testid="plan-embedded-cockpit">
            <div style={{ height: '76vh' }}>
              <PlanningCockpit embedded lockedJobIds={lockedJobIds} downstreamJobIds={downstreamJobIds}
                               renderSlotDrawer={renderSlotDrawer} />
            </div>
          </div>,
          api.plannerSlot,
        )}
      {/* 3 Jul — the standardized drawer for floor-card clicks (panels / bodies / chassis / QC).
          Wrapped in its own .a06-flow scope so the shared modal tokens apply outside the engine root. */}
      {drawer && (
        <div className="a06-flow">
          <PlanJobDrawerShell label={drawer.jobNumber ? `Job ${drawer.jobNumber}` : 'Chassis'}
                              onClose={() => setDrawer(null)}>
            <PlanJobTabs
              kicker={drawer.kicker}
              jobNumber={drawer.jobNumber}
              chassisId={drawer.chassisId}
              subtitle={drawer.subtitle}
              initialTab={drawer.initialTab}
              onClose={() => setDrawer(null)}
            />
          </PlanJobDrawerShell>
        </div>
      )}
    </>
  )
}

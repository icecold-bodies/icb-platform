// PlanningCockpit.tsx — WO Cockpit (Concept 6). An ADDITIVE alternate Planning layout at
// /planning/cockpit: a 3-pane cockpit (collapsible Unscheduled rail · hero timeline · persistent
// inspector) with a collapsible bottom dock for the bay-model flow zones, plus native-fullscreen
// Focus Mode. It reuses the SAME live data + mutators as the board (usePlanning / useCostings) and
// the standalone BayModelLanes / JobCardSections / PlanningAckPanel components.
//
// The week-grid + Unscheduled pool logic below is DUPLICATED from PlanningBoard's LivePlanningBoard
// (those parts are module-private there). KEEP IN SYNC with PlanningBoard.tsx; never edit the original
// — the existing /planning board is frozen for the demo.
import { Fragment, useEffect, useMemo, useRef, useState, type ReactNode } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import {
  GripVertical, CalendarDays, Maximize, Layers, X,
  ChevronsLeft, ChevronsRight, ChevronUp, ChevronDown,
} from 'lucide-react'
import { data } from '../../../data/mockData'
import { zarShort, dmy, monthYear, nextMonths } from '../../../lib/format'
import { Card } from '../../../components/ui/primitives'
import { Spinner, Skeleton, EmptyState, LastUpdated } from '../../../components/ui/feedback'
import { ApiError } from '../../../lib/api'
import { useToast } from '../../../components/ui/toast'
import { useAppData } from '../../../store/AppDataContext'
import { useCostings } from '../../../store/CostingsContext'
import { usePlanning } from '../../../store/PlanningContext'
import { useRefetchOnFocus } from '../../../lib/useRefetchOnFocus'
import { getChassisState, type PlanningJob, type PlanningSlot, type PlanningWeekCol } from '../../../lib/types'
import type { Costing } from '../../../data/costingsData'
import { BayModelLanes } from '../BayModelLanes'
import { PlanningAckPanel } from '../PlanningAckPanel'
import { ChassisBadge, SourceBadge, FooterRow } from './badges'
import { CockpitSlotDetail } from './CockpitSlotDetail'
import { TONE_BAR, elapsedNowHours, pctClamped, progressTone } from './slotProgress'
import { useCockpitLayout } from './useCockpitLayout'

const SLOTS = ['V-1', 'V-2', 'V-3', 'V-4', 'V-5', 'P-1', 'P-2', 'P-3']

// ── A10 day-slots (Simeon-ratified v0.2) ─────────────────────────────────────
// Each bay-week is a 7-day sub-grid: 5 weekday slots + 2 weekend slots that are
// skinny (24px) until occupied, then flex to full width. 0=Mon .. 6=Sun.
const DAY_LABELS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'] as const
const WEEKDAYS = 5
const WKND_SKINNY = '24px'

function dayGridTemplate(satOcc: boolean, sunOcc: boolean): string {
  return `repeat(5, minmax(64px, 1fr)) ${satOcc ? 'minmax(64px, 1fr)' : WKND_SKINNY} ${
    sunOcc ? 'minmax(64px, 1fr)' : WKND_SKINNY}`
}

function dayIso(mondayIso: string, day: number): string {
  const d = new Date(`${mondayIso}T00:00:00Z`)
  d.setUTCDate(d.getUTCDate() + day)
  return d.toISOString().slice(0, 10)
}

// Health = the existing chassis-state machinery (v1.40.x), projected onto the slot's DAY:
// received → green (on schedule) · ETA on/before the slot day → amber (attention, chassis
// still inbound) · ETA after the slot day → red (delayed — the plan can't be met) ·
// no ETA at all → grey (waiting). Mockup tokens (A10/A06 STATUS palette).
type SlotHealth = 'green' | 'amber' | 'red' | 'grey'
const HEALTH_HEX: Record<SlotHealth, string> = {
  green: '#0F9D7A', amber: '#D97706', red: '#DC4A3D', grey: '#64748B',
}
function slotHealth(job: PlanningJob, slotDateIso: string): SlotHealth {
  const state = getChassisState(job)
  if (state === 'eta_committed') {
    return (job.chassis_eta ?? '').slice(0, 10) > slotDateIso ? 'red' : 'amber'
  }
  return state === 'received' ? 'green' : 'grey'
}

// Body-type pill — keyword classification of the free-text body_type (ratified taxonomy:
// Chiller / Freezer / Dry Freight / Insulated / Repair; anything else gets no pill).
const BODY_PILLS: Array<{ match: RegExp; label: string; hex: string }> = [
  { match: /chill/i, label: 'CHILLER', hex: '#0891B2' },
  { match: /freez/i, label: 'FREEZER', hex: '#1E40AF' },
  { match: /dry/i, label: 'DRY FRT', hex: '#64748B' },
  { match: /insul/i, label: 'INSUL', hex: '#059669' },
  { match: /repair/i, label: 'REPAIR', hex: '#7C3AED' },
]
function bodyPill(bodyType: string | null): { label: string; hex: string } | null {
  if (!bodyType) return null
  const hit = BODY_PILLS.find((p) => p.match.test(bodyType))
  return hit ? { label: hit.label, hex: hit.hex } : null
}
function bodyLength(bodyType: string | null): string | null {
  const m = (bodyType ?? '').match(/(\d+(?:[.,]\d+)?)\s*m\b/i)
  return m ? `${m[1].replace(',', '.')}m` : null
}

// Middle-mouse drag-to-pan for the grid panel (duplicated from PlanningBoard.tsx).
function useMiddleButtonPan<T extends HTMLElement>() {
  const ref = useRef<T>(null)
  useEffect(() => {
    const el = ref.current
    if (!el) return
    let panning = false
    let startX = 0, startY = 0, startLeft = 0, startTop = 0
    const onMove = (e: MouseEvent) => {
      if (!panning) return
      el.scrollLeft = startLeft - (e.clientX - startX)
      el.scrollTop = startTop - (e.clientY - startY)
    }
    const onUp = () => {
      if (!panning) return
      panning = false
      el.style.cursor = ''
      el.style.userSelect = ''
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
    const onDown = (e: MouseEvent) => {
      if (e.button !== 1) return
      panning = true
      startX = e.clientX; startY = e.clientY
      startLeft = el.scrollLeft; startTop = el.scrollTop
      el.style.cursor = 'grabbing'
      el.style.userSelect = 'none'
      e.preventDefault()
      window.addEventListener('mousemove', onMove)
      window.addEventListener('mouseup', onUp)
    }
    el.addEventListener('mousedown', onDown)
    return () => {
      el.removeEventListener('mousedown', onDown)
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup', onUp)
    }
  }, [])
  return ref
}

// WO A09 Combined Cockpit — `embedded` mounts the SAME live cockpit inside the Plan module's
// combined page (grid + Unscheduled rail + Inspector + filters + summary), hiding only the
// bottom Bay-model dock (the A06 Production Flow floor replaces those zones on that page).
// `lockedJobIds` (business rules 2 Jul): jobs whose body is MERGED WITH CHASSIS — the permanent
// point of no return. Backward planner moves (unschedule / revert-to-unscheduled) are rejected
// for them. Standalone /planning/cockpit behaviour is unchanged (both props default off).
// 3 Jul — standardized Plan drawer: the host (PlanCombined) may take over the embedded slot
// drawer's PRESENTATION (tabbed corporate layout) while this component keeps supplying the
// stage-action node (CockpitSlotDetail with all its handlers) as `overview`.
export type RenderSlotDrawer = (args: { slot: PlanningSlot; overview: ReactNode; close: () => void }) => ReactNode

export function PlanningCockpit({ embedded = false, lockedJobIds, downstreamJobIds, renderSlotDrawer }: {
  embedded?: boolean; lockedJobIds?: Set<number>; downstreamJobIds?: Set<number>
  renderSlotDrawer?: RenderSlotDrawer
} = {}) {
  const { mode } = usePlanning()
  if (mode === 'loading') return <CockpitSkeleton />
  if (mode !== 'live') return <CockpitMockNotice />
  return <LiveCockpit embedded={embedded} lockedJobIds={lockedJobIds} downstreamJobIds={downstreamJobIds}
                      renderSlotDrawer={renderSlotDrawer} />
}

function CockpitSkeleton() {
  return (
    <div className="flex h-full flex-col p-3">
      <div className="mb-3 flex shrink-0 items-center justify-between">
        <h1 className="text-xl font-bold text-body">Planning Cockpit</h1>
        <span className="text-xs text-muted">Loading…</span>
      </div>
      <div className="grid min-h-0 flex-1 grid-cols-[232px_1fr_340px] gap-2">
        <Card className="min-h-0 overflow-y-auto"><Skeleton rows={4} /></Card>
        <Card className="min-h-0 overflow-auto p-0"><Skeleton rows={8} /></Card>
        <Card className="min-h-0 overflow-y-auto"><Skeleton rows={5} /></Card>
      </div>
    </div>
  )
}

// Cockpit duplicates only the LIVE board; offline/mock demos keep using the original board.
// v1.43 (Michael 20 Jul) — the mode LATCHES on one failed bootstrap fetch (a service
// restart mid-session or an expired session both land here), so give the user a Retry
// that re-runs the board fetch in place instead of requiring a full page reload.
function CockpitMockNotice() {
  const { refresh } = usePlanning()
  const [retrying, setRetrying] = useState(false)
  const retry = async () => {
    setRetrying(true)
    try { await refresh() } finally { setRetrying(false) }
  }
  return (
    <div className="p-6">
      <div className="mb-1 text-[11px] text-muted">MES › Planning › Cockpit (beta)</div>
      <h1 className="mb-3 text-xl font-bold text-body">Planning Cockpit</h1>
      <Card className="max-w-xl">
        <div className="text-sm text-body">
          The Cockpit runs on live planning data and the last attempt to reach the API failed — this
          happens when the server restarted mid-session or the session expired. Retry below, or use
          the classic board (it renders the bundled demo data).
        </div>
        <div className="mt-3 flex gap-2">
          <button onClick={() => void retry()} disabled={retrying}
            className="inline-flex rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-white hover:bg-primary-dark disabled:opacity-50">
            {retrying ? 'Retrying…' : 'Retry live data'}
          </button>
          <Link to="/plan" className="inline-flex rounded-md border border-line px-3 py-1.5 text-sm font-semibold text-body hover:bg-surface-alt">
            Open the Plan page
          </Link>
        </div>
      </Card>
    </div>
  )
}

function LiveCockpit({ embedded = false, lockedJobIds, downstreamJobIds, renderSlotDrawer }: {
  embedded?: boolean; lockedJobIds?: Set<number>; downstreamJobIds?: Set<number>
  renderSlotDrawer?: RenderSlotDrawer
}) {
  const nav = useNavigate()
  const { board, schedule, move, unschedule, revertToUnscheduled, rejectJob, lastUpdated, refresh, jumpTo, today, nextWindow, prevWindow } = usePlanning()
  useRefetchOnFocus(refresh)
  const { profile, hasPermission } = useAppData()
  const { costings, ackPlanning, markChassisReceived } = useCostings()
  const toast = useToast()
  const layout = useCockpitLayout()
  const rootRef = useRef<HTMLDivElement>(null)
  const panRef = useMiddleButtonPan<HTMLDivElement>()

  const canSchedule = hasPermission('planning.schedule')
  const canUnschedule = hasPermission('planning.unschedule')
  const canTickChassis = hasPermission('production.chassis_received')
  const target = data.kpis.weekly_target_zar
  const byActor = profile.id === 'rep_burt' ? 'BURT' : profile.id

  const ackCandidates = useMemo(
    () => costings.filter((c) => c.status === 'Pre-Job Confirmed' && c.production_job_id != null),
    [costings],
  )

  // v1.40.6 thresholds WO — one grid-level 60s tick re-renders the stage-progress bars
  // between board polls (KanbanTV precedent; the 30s poll re-syncs server elapsed anyway).
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 60_000)
    return () => clearInterval(t)
  }, [])

  const [dragPoolJob, setDragPoolJob] = useState<PlanningJob | null>(null)
  const [dragSlot, setDragSlot] = useState<PlanningSlot | null>(null)
  const [spinnerKey, setSpinnerKey] = useState<string | null>(null)
  const [rejectKey, setRejectKey] = useState<string | null>(null)
  const [poolHot, setPoolHot] = useState(false)
  const [ackTarget, setAckTarget] = useState<Costing | null>(null)
  const [sourceFilter, setSourceFilter] = useState<'all' | 'quote' | 'workbook'>('all')
  const matchesSource = (j: PlanningJob) => sourceFilter === 'all' || j.source === sourceFilter

  // Inspector selection (replaces the SidePanel pop-up). Re-derive the LIVE slot by id each render so
  // the inspector follows mutations (the board replaces board.slots on every schedule/move/unschedule).
  const [selectedSlotId, setSelectedSlotId] = useState<number | null>(null)
  const [pinned, setPinned] = useState(false)
  const selectedLiveSlot = useMemo(
    () => (selectedSlotId == null ? null : board.slots.find((s) => s.id === selectedSlotId && s.job) ?? null),
    [board.slots, selectedSlotId],
  )

  // Same-page sync: bay mutations → refetch the grid (PR #39). Identical to the board.
  useEffect(() => {
    const onBoardChange = () => { void refresh() }
    document.addEventListener('icb:planning-refetch', onBoardChange)
    return () => document.removeEventListener('icb:planning-refetch', onBoardChange)
  }, [refresh])

  // When the planner starts dragging a scheduled job's panels (icb:panel-drag), auto-open the dock so
  // the bay drop targets (BayModelLanes) are mounted + visible to receive the drop.
  const setDockOpen = layout.setDockOpen
  useEffect(() => {
    const onPanelDrag = (e: Event) => {
      const active = (e as CustomEvent<{ active?: boolean }>).detail?.active
      if (active) setDockOpen(true)
    }
    document.addEventListener('icb:panel-drag', onPanelDrag)
    return () => document.removeEventListener('icb:panel-drag', onPanelDrag)
  }, [setDockOpen])

  async function markSlotChassisReceived(slot: PlanningSlot) {
    if (!slot.job) return
    const costing = costings.find((c) => c.production_job_id === slot.job!.id)
    if (!costing) {
      toast.push({ kind: 'warn', message: 'Could not match this slot to a costing.' })
      return
    }
    await markChassisReceived(costing.quote_number, todayIso(), byActor)
    await refresh()
  }

  const bays = useMemo(() => {
    const extra = board.bays.filter((b) => !SLOTS.includes(b))
    return [...SLOTS, ...extra]
  }, [board.bays])

  // A10 day-slots: the cell key is (week, bay, DAY). Legacy slots (day_of_week null) render
  // as Monday — the same day migration 0034 backfilled them to.
  const slotDay = (s: PlanningSlot): number => s.day_of_week ?? 0
  const cellFor = (weekKey: string, bay: string, day: number): PlanningSlot | undefined =>
    board.slots.find((s) => s.week_key === weekKey && s.bay === bay && slotDay(s) === day)
  // A card is VISIBLE unless its job moved downstream (embedded single-location rule) —
  // width flexing, utilization dots and the summary all key off visibility, not raw rows.
  const visibleCell = (weekKey: string, bay: string, day: number): PlanningSlot | undefined => {
    const c = cellFor(weekKey, bay, day)
    return c && c.job && !(embedded && downstreamJobIds && downstreamJobIds.has(c.job.id)) ? c : undefined
  }
  const capFor = (weekKey: string) => board.capacity.find((c) => c.week_key === weekKey)
  // A09 single-location rule (embedded): FILLED / EMPTY / VALUE / GAP derive from the cards
  // VISIBLE on the grid — a job that moved downstream (Panels ready / bays / merge / QC)
  // leaves the counts the moment its card moves, exactly like the A09 mockup's summary.
  const visibleWeekSlots = (weekKey: string) =>
    board.slots.filter((s) => s.week_key === weekKey && s.job && !(downstreamJobIds && downstreamJobIds.has(s.job.id)))
  const embFilled = (weekKey: string) => visibleWeekSlots(weekKey).length
  const embValue = (weekKey: string) => visibleWeekSlots(weekKey).reduce((a, s) => a + (s.job?.selling_zar ?? 0), 0)
  const laneForBay = (bay: string): string => (bay.startsWith('P') ? 'panelshop' : 'vacuum')
  // Bay-label utilization (first visible week): booked weekday count drives the dot —
  // green 5/5 · amber 2-4 · grey 0-1 (ratified §8.2.3); weekend bookings shown separately.
  const utilFor = (bay: string) => {
    const wk = board.weeks[0]
    if (!wk) return { n: 0, sat: false, sun: false }
    let n = 0
    for (let d = 0; d < WEEKDAYS; d++) if (visibleCell(wk.key, bay, d)) n++
    return { n, sat: !!visibleCell(wk.key, bay, 5), sun: !!visibleCell(wk.key, bay, 6) }
  }
  // Week-header day labels share the widest occupancy state across bays so the header
  // tracks the grid (per-bay rows still flex independently, as in the A10 mockup).
  const weekWknd = (weekKey: string) => {
    let sat = false, sun = false
    for (const b of bays) {
      sat = sat || !!visibleCell(weekKey, b, 5)
      sun = sun || !!visibleCell(weekKey, b, 6)
    }
    return { sat, sun }
  }
  const todayStr = todayIso()
  function flashReject(key: string) {
    setRejectKey(key)
    setTimeout(() => setRejectKey(null), 1800)
  }

  async function dropOnCell(week: PlanningWeekCol, bay: string, day: number) {
    const key = `${week.key}:${bay}:${day}`
    if (dragSlot) {
      const src = dragSlot
      setDragSlot(null)
      if (src.week_key === week.key && src.bay === bay && slotDay(src) === day) return
      try {
        setSpinnerKey(key)
        await move(src.id, { week: week.start, bay, lane: laneForBay(bay), day_of_week: day })
      } catch (e) {
        // 409 occupied / 422 chassis-ETA gate → red flash on the exact day-slot (A10 §3.5
        // visual reject cue); the 422 detail toast is already pushed by the context.
        if (e instanceof ApiError && (e.status === 409 || e.status === 422)) {
          flashReject(key)
          if (e.status === 409) toast.push({ kind: 'warn', message: 'That day-slot is already occupied.' })
        }
      } finally {
        setSpinnerKey(null)
      }
      return
    }
    if (dragPoolJob) {
      const job = dragPoolJob
      setDragPoolJob(null)
      if (getChassisState(job) === 'none') {
        toast.push({
          kind: 'warn',
          message:
            'No chassis ETA committed yet — rep should confirm an ETA with the customer/dealer before this job can be scheduled.',
        })
        return
      }
      try {
        setSpinnerKey(key)
        await schedule({ production_job_id: job.id, week: week.start, bay, lane: laneForBay(bay), day_of_week: day })
      } catch (e) {
        if (e instanceof ApiError && (e.status === 409 || e.status === 422)) {
          flashReject(key)
          if (e.status === 409) toast.push({ kind: 'warn', message: 'That day-slot is already occupied.' })
        }
      } finally {
        setSpinnerKey(null)
      }
    }
  }

  async function dropOnPool() {
    setPoolHot(false)
    if (!dragSlot) return
    const src = dragSlot
    setDragSlot(null)
    if (!canUnschedule) {
      toast.push({ kind: 'warn', message: "You don't have permission to unschedule jobs." })
      return
    }
    // Business rules 2 Jul — MERGED WITH CHASSIS is the point of no return: no backward moves.
    if (lockedJobIds && src.job && lockedJobIds.has(src.job.id)) {
      toast.push({ kind: 'warn', message: `Job ${src.job.job_number} is merged with its chassis — it can't move back to an earlier state.` })
      return
    }
    try {
      await unschedule(src.id)
    } catch {
      /* surfaced by the context */
    }
  }

  const poolJobs = board.pool.filter(matchesSource)
  const poolCount = poolJobs.length + ackCandidates.length
  const { leftCollapsed, rightCollapsed, dockOpen, isFullscreen } = layout
  const rightExpanded = !rightCollapsed || !!selectedLiveSlot || pinned
  // A09 embedded: the inspector column is replaced by a right-side slide-in drawer
  // (same presentation as the floor's job-detail modal), so the grid drops to two columns.
  const gridTemplateColumns = embedded
    ? `${leftCollapsed ? '40px' : '232px'} minmax(0,1fr)`
    : `${leftCollapsed ? '40px' : '232px'} minmax(0,1fr) ${rightExpanded ? '340px' : '40px'}`

  return (
    <div ref={rootRef} className="flex h-full flex-col gap-2 bg-surface-alt/30 p-3">
      {/* ── Toolbar ─────────────────────────────────────────────────────────── */}
      <div className="flex shrink-0 flex-wrap items-center justify-between gap-2">
        <div>
          <div className="mb-0.5 flex items-center gap-2 text-[11px] text-muted">
            MES › Planning › Cockpit
            <span className="rounded bg-primary/10 px-1.5 py-0.5 text-[9px] font-bold uppercase text-primary">beta</span>
          </div>
          <h1 className="text-xl font-bold text-body">Planning Cockpit</h1>
        </div>
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <div className="flex items-center gap-1" title="Filter board by job source">
            {(['all', 'quote', 'workbook'] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSourceFilter(s)}
                className={`rounded-md px-2.5 py-1.5 text-xs font-semibold transition ${
                  sourceFilter === s ? 'bg-primary text-white' : 'border border-line bg-white text-body hover:bg-surface-alt'
                }`}
              >
                {s === 'all' ? 'All' : s === 'quote' ? 'Quote-born' : 'Workbook'}
              </button>
            ))}
          </div>
          <div className="flex items-center gap-1">
            <button onClick={prevWindow} title="Earlier weeks" aria-label="Earlier weeks"
              className="rounded-md border border-line bg-white px-2 py-1.5 text-xs font-semibold hover:bg-surface-alt">‹</button>
            <select
              value=""
              onChange={(e) => { if (e.target.value) jumpTo(e.target.value) }}
              title="Jump to month"
              className="rounded-md border border-line bg-white px-2 py-1.5 text-xs outline-none"
            >
              <option value="">Jump to month…</option>
              {nextMonths(12).map((m) => <option key={m.iso} value={m.iso}>{m.label}</option>)}
            </select>
            <button onClick={nextWindow} title="Later weeks" aria-label="Later weeks"
              className="rounded-md border border-line bg-white px-2 py-1.5 text-xs font-semibold hover:bg-surface-alt">›</button>
            <button onClick={today}
              className="rounded-md border border-line bg-white px-2.5 py-1.5 text-xs font-semibold hover:bg-surface-alt">Today</button>
          </div>
          <span className="hidden rounded-md border border-line bg-white px-3 py-1.5 text-xs lg:inline">
            {board.weeks.length ? `${monthYear(board.weeks[0].start)} · ${board.weeks.length} wks` : `${board.weeks.length} weeks`}
          </span>
          {/* Layout controls */}
          <div className="flex items-center gap-1 border-l border-line pl-2">
            <button onClick={layout.toggleLeft} aria-pressed={leftCollapsed}
              title={leftCollapsed ? 'Show Unscheduled rail' : 'Collapse Unscheduled rail'}
              className="rounded-md border border-line bg-white p-1.5 text-muted hover:bg-surface-alt">
              {leftCollapsed ? <ChevronsRight size={15} /> : <ChevronsLeft size={15} />}
            </button>
            <button onClick={layout.maxHero}
              title="Maximise the timeline (collapse rails + dock)"
              className="rounded-md border border-line bg-white px-2 py-1.5 text-xs font-semibold text-muted hover:bg-surface-alt">
              Max hero
            </button>
            <button onClick={() => layout.toggleFullscreen(rootRef.current)} aria-pressed={isFullscreen}
              title={isFullscreen ? 'Exit full-screen (Esc)' : 'Focus mode — full-screen the cockpit'}
              className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition ${
                isFullscreen ? 'bg-primary text-white' : 'border border-line bg-white text-body hover:bg-surface-alt'
              }`}>
              <Maximize size={14} /> {isFullscreen ? 'Exit full-screen' : 'Focus'}
            </button>
          </div>
        </div>
      </div>

      {/* ── 3-pane body ─────────────────────────────────────────────────────── */}
      <div className="grid min-h-0 flex-1 gap-2" style={{ gridTemplateColumns }}>
        {/* LEFT RAIL — Unscheduled pool (collapsible) */}
        {leftCollapsed ? (
          <button onClick={layout.toggleLeft} title="Show Unscheduled rail"
            className="flex min-h-0 flex-col items-center gap-2 rounded-lg border border-line bg-white py-2 text-muted hover:border-primary/40">
            <ChevronsRight size={15} />
            <span style={{ writingMode: 'vertical-rl' }} className="text-[11px] font-semibold uppercase tracking-wide">
              Unscheduled ({poolCount})
            </span>
          </button>
        ) : (
          <Card className="min-h-0 overflow-y-auto">
            <div
              onDragOver={(e) => { if (dragSlot) { e.preventDefault(); setPoolHot(true) } }}
              onDragLeave={() => setPoolHot(false)}
              onDrop={() => dropOnPool()}
              className={`rounded-md transition ${poolHot ? 'ring-2 ring-status-amber' : ''}`}
            >
              <div className="mb-2 flex items-center justify-between">
                <span className="text-sm font-semibold uppercase tracking-wide text-muted">Unscheduled ({poolCount})</span>
                <button onClick={layout.toggleLeft} title="Collapse rail" className="rounded p-0.5 text-muted hover:bg-surface-alt"><ChevronsLeft size={14} /></button>
              </div>
              {ackCandidates.length > 0 && (
                <div className="mb-3 space-y-2">
                  {ackCandidates.map((c) => (
                    <button
                      key={c.quote_number}
                      onClick={() => setAckTarget(c)}
                      className="flex w-full items-start gap-2 rounded-md border-l-4 border-[#06B6D4] bg-[#06B6D4]/5 p-2 text-left hover:bg-[#06B6D4]/10 animate-pulseRing"
                    >
                      <CalendarDays size={14} className="mt-0.5 text-[#06B6D4]" />
                      <div className="flex-1">
                        <div className="font-mono text-sm font-semibold">#{c.job_number_assigned ?? c.quote_number}</div>
                        <div className="text-xs text-body">{c.customer_name}</div>
                        <div className="mt-1 text-[10px] font-medium text-[#0E7490]">Awaiting Planning ack · click to acknowledge</div>
                      </div>
                    </button>
                  ))}
                </div>
              )}
              <div className="space-y-2">
                {poolJobs.map((job) => (
                  <div
                    key={job.id}
                    draggable={canSchedule}
                    onDragStart={() => { if (canSchedule) setDragPoolJob(job) }}
                    onDragEnd={() => setDragPoolJob(null)}
                    className={`flex items-start gap-2 rounded-md border border-line bg-white p-2 ${
                      canSchedule ? 'cursor-grab active:cursor-grabbing' : ''
                    }`}
                  >
                    {canSchedule && <GripVertical size={14} className="mt-0.5 text-muted" />}
                    <div className="flex-1">
                      <div className="flex flex-wrap items-center justify-between gap-1">
                        <span className="font-mono text-sm font-semibold">#{job.job_number}</span>
                        <span className="flex items-center gap-1">
                          <SourceBadge source={job.source} />
                          <ChassisBadge state={getChassisState(job)} eta={job.chassis_eta} />
                        </span>
                      </div>
                      <div className="text-xs text-body">{job.customer}</div>
                      {job.body_type && <div className="text-[11px] text-muted">{job.body_type}</div>}
                    </div>
                  </div>
                ))}
                {poolJobs.length === 0 && <div className="text-sm text-muted">All scheduled.</div>}
              </div>
              <div className="mt-3 border-t border-line pt-3 text-[11px] text-muted">
                Drag a card onto a slot →{canUnschedule ? ' · drop a scheduled job here to unschedule' : ''}
              </div>
            </div>
          </Card>
        )}

        {/* CENTRE — hero timeline (week grid) */}
        <Card className="flex min-h-0 flex-col overflow-hidden p-0">
          <div ref={panRef} className="min-h-0 flex-1 overflow-auto" title="Tip: hold the middle mouse button and drag to pan">
            {board.weeks.length === 0 ? (
              <EmptyState
                title="No scheduled weeks yet"
                hint="Schedule a job from the unscheduled pool to populate the board."
              />
            ) : (
              <table className="w-full border-collapse text-sm">
                <thead>
                  <tr className="text-white">
                    <th className="sticky left-0 top-0 z-30 bg-primary px-2 py-2 text-left font-semibold">V/P Bay</th>
                    {board.weeks.map((w) => {
                      const wk = weekWknd(w.key)
                      return (
                        <th key={w.key} className="sticky top-0 z-20 bg-primary px-2 py-1.5 text-left font-semibold"
                            style={{ minWidth: 400 }}>
                          {w.key}
                          <span className="ml-1.5 text-[10px] font-normal opacity-80">{dmy(w.start)}</span>
                          {/* A10 — day sub-columns; weekend labels stay skinny until a bay books one */}
                          <div className="mt-1 grid gap-[3px]"
                               style={{ gridTemplateColumns: dayGridTemplate(wk.sat, wk.sun) }}>
                            {DAY_LABELS.map((label, day) => {
                              const weekend = day >= WEEKDAYS
                              const isToday = dayIso(w.start, day) === todayStr
                              return (
                                <span key={label}
                                  className={`overflow-hidden text-center text-[8px] font-bold uppercase tracking-wide ${
                                    isToday ? 'text-[#FCA5A5]' : weekend ? 'opacity-60' : 'opacity-80'}`}>
                                  {label}
                                </span>
                              )
                            })}
                          </div>
                        </th>
                      )
                    })}
                  </tr>
                </thead>
                <tbody>
                  {bays.map((bay, bayIdx) => {
                    const lane = laneForBay(bay)
                    const showLane = bayIdx === 0 || laneForBay(bays[bayIdx - 1]) !== lane
                    return (
                    <Fragment key={bay}>
                      {showLane && (
                        <tr className="border-b border-line">
                          <td colSpan={board.weeks.length + 1} className="sticky left-0 bg-surface-alt px-2 py-1 text-[10px] font-semibold uppercase tracking-wide text-muted">
                            {lane === 'panelshop' ? 'Press' : 'Vacuum'}
                          </td>
                        </tr>
                      )}
                    <tr className="border-b border-line">
                      <td className="sticky left-0 z-10 bg-surface-alt px-2 py-1.5 align-top shadow-[inset_-1px_0_0_#E5E7EB]">
                        {(() => {
                          const u = utilFor(bay)
                          const dotHex = u.n === WEEKDAYS ? HEALTH_HEX.green : u.n >= 2 ? HEALTH_HEX.amber : HEALTH_HEX.grey
                          const wknd = [u.sat && 'Sat', u.sun && 'Sun'].filter(Boolean).join('/')
                          return (
                            <div className="flex min-w-[86px] flex-col gap-0.5">
                              <span className="font-mono text-xs font-bold text-body">{bay}</span>
                              <span className="text-[9px] font-semibold uppercase tracking-wide text-muted">
                                {lane === 'panelshop' ? 'Press' : 'Vacuum'}
                              </span>
                              <span className="flex items-center gap-1 whitespace-nowrap text-[10px] text-body/80"
                                    title="Weekday day-slots booked in the first visible week">
                                <span className="inline-block h-1.5 w-1.5 rounded-full" style={{ backgroundColor: dotHex }} />
                                {u.n} / {WEEKDAYS}{wknd ? ` + ${wknd}` : ''}
                              </span>
                            </div>
                          )
                        })()}
                      </td>
                      {board.weeks.map((w) => {
                        const satOcc = !!visibleCell(w.key, bay, 5)
                        const sunOcc = !!visibleCell(w.key, bay, 6)
                        return (
                          <td key={w.key} className="border-l border-line px-1 py-1 align-top" style={{ minWidth: 400 }}>
                            <div className="grid gap-[3px]" style={{ gridTemplateColumns: dayGridTemplate(satOcc, sunOcc) }}>
                              {DAY_LABELS.map((_, day) => {
                                const cell = visibleCell(w.key, bay, day)
                                const key = `${w.key}:${bay}:${day}`
                                const rejected = rejectKey === key
                                const busy = spinnerKey === key
                                const weekend = day >= WEEKDAYS
                                const skinny = weekend && !cell
                                const slotDate = dayIso(w.start, day)
                                const isToday = slotDate === todayStr
                                const selected = !!cell?.job && cell.id === selectedSlotId
                                const health = cell?.job ? slotHealth(cell.job, slotDate) : null
                                const pill = cell?.job ? bodyPill(cell.job.body_type) : null
                                const len = cell?.job ? bodyLength(cell.job.body_type) : null
                                return (
                                  <div
                                    key={day}
                                    onDragOver={(e) => e.preventDefault()}
                                    onDrop={() => dropOnCell(w, bay, day)}
                                    className={`relative rounded-md transition ${
                                      rejected ? 'bg-status-red/30 ring-2 ring-status-red' : ''}`}
                                  >
                                    {busy && (
                                      <div className="absolute inset-0 z-10 flex items-center justify-center rounded-md bg-white/60">
                                        <Spinner size={14} className="text-primary" />
                                      </div>
                                    )}
                                    {cell && cell.job && health ? (
                                      <button
                                        onClick={() => setSelectedSlotId(cell.id)}
                                        data-testid="cockpit-slot-cell"
                                        data-job-id={cell.job.id}
                                        data-day={day}
                                        draggable={canSchedule}
                                        onDragStart={(e) => {
                                          if (!canSchedule) { e.preventDefault(); return }
                                          setDragSlot(cell)
                                          if (cell.job) {
                                            e.dataTransfer.setData('application/x-panel-job', String(cell.job.id))
                                            e.dataTransfer.effectAllowed = 'copyMove'
                                            document.dispatchEvent(new CustomEvent('icb:panel-drag', { detail: { active: true } }))
                                          }
                                        }}
                                        onDragEnd={() => {
                                          setDragSlot(null)
                                          document.dispatchEvent(new CustomEvent('icb:panel-drag', { detail: { active: false } }))
                                        }}
                                        title={`${cell.job.customer}${cell.job.vin ? ` · ${cell.job.vin}` : ''} · ${DAY_LABELS[day]} ${slotDate}`}
                                        className={`relative flex h-[82px] w-full flex-col justify-between overflow-hidden rounded-md border border-line bg-white px-1.5 pb-1 pt-1.5 text-left shadow-sm hover:shadow ${
                                          selected ? 'ring-1 ring-primary' : ''
                                        } ${canSchedule ? 'cursor-grab active:cursor-grabbing' : ''} ${matchesSource(cell.job) ? '' : 'opacity-30'}`}
                                        style={{ borderLeftWidth: 3, borderLeftColor: HEALTH_HEX[health] }}
                                      >
                                        {weekend && (
                                          <span className="absolute right-3 top-0 rounded-b bg-status-amber px-1 pb-px text-[7px] font-extrabold uppercase tracking-wide text-white">
                                            WKND
                                          </span>
                                        )}
                                        <span className="absolute right-1 top-1 h-1.5 w-1.5 rounded-full"
                                              style={{ backgroundColor: HEALTH_HEX[health] }} />
                                        <span className="min-w-0">
                                          <span className="block font-mono text-[11px] font-bold leading-tight tabular-nums text-body">
                                            {cell.job.job_number}
                                          </span>
                                          <span className="mt-0.5 block truncate text-[9px] font-semibold text-body/70">
                                            {cell.job.customer}
                                          </span>
                                        </span>
                                        <span className="flex items-center justify-between gap-1">
                                          {pill ? (
                                            <span className="rounded px-1 py-px text-[7px] font-bold uppercase leading-3 tracking-wide text-white"
                                                  style={{ backgroundColor: pill.hex }}>
                                              {pill.label}
                                            </span>
                                          ) : <span />}
                                          <span className="text-[9px] font-semibold text-body/70">{len ?? '—'}</span>
                                        </span>
                                        {/* v1.40.6 — stage clock vs admin threshold (bottom strip; empty track = pending) */}
                                        {cell.progress && (() => {
                                          const el = elapsedNowHours(cell.progress, lastUpdated, nowMs)
                                          const tone = progressTone(el, cell.progress.threshold_hours)
                                          return (
                                            <span data-testid="slot-progress" data-tone={tone}
                                                  title={`${cell.progress.label}: ${el < 0 ? 'not started' : `${el.toFixed(1)}h of ${cell.progress.threshold_hours}h`}`}
                                                  className="absolute inset-x-0 bottom-0 h-[3px] bg-line/60">
                                              <span className={`block h-full ${TONE_BAR[tone]}`}
                                                    style={{ width: `${pctClamped(el, cell.progress.threshold_hours)}%` }} />
                                            </span>
                                          )
                                        })()}
                                      </button>
                                    ) : (
                                      // Empty day-slot: weekday = dashed drop target; weekend = skinny
                                      // amber strip (A10 v0.2 — visible but unobtrusive overtime space).
                                      <div
                                        className={`flex h-[82px] w-full items-center justify-center rounded-md border border-dashed transition ${
                                          skinny
                                            ? 'border-[#FDE0C7] bg-[#FEF3EC] text-[#B45309] hover:border-status-amber'
                                            : `border-line text-muted hover:border-primary/50 hover:bg-primary/5 ${
                                                isToday ? 'bg-[#FEF2F2]' : 'bg-surface-alt/40'}`}`}
                                        title={`${DAY_LABELS[day]} ${slotDate}${weekend ? ' (weekend overtime)' : ''}`}
                                      >
                                        <span className={skinny ? 'text-[10px] opacity-60' : 'text-sm opacity-50'}>+</span>
                                      </div>
                                    )}
                                  </div>
                                )
                              })}
                            </div>
                          </td>
                        )
                      })}
                    </tr>
                    </Fragment>
                    )
                  })}
                  <FooterRow
                    label="Filled"
                    cells={board.weeks.map((w) => `${embedded ? embFilled(w.key) : capFor(w.key)?.filled ?? 0}`)}
                    tooltipKey="planning_board.weekly_capacity_footer"
                  />
                  {/* A10 day-slots: weekly capacity = 5 weekday slots per bay (weekends are overtime, not capacity) */}
                  <FooterRow label="Empty" cells={board.weeks.map((w) => `${embedded ? SLOTS.length * WEEKDAYS - embFilled(w.key) : capFor(w.key)?.empty ?? 0}`)} />
                  <FooterRow label="Value" cells={board.weeks.map((w) => zarShort(embedded ? embValue(w.key) : capFor(w.key)?.value_zar ?? 0))} strong />
                  <FooterRow
                    label="Gap vs target"
                    cells={board.weeks.map((w) => zarShort((embedded ? embValue(w.key) : capFor(w.key)?.value_zar ?? 0) - target))}
                    tone={board.weeks.map((w) => ((embedded ? embValue(w.key) : capFor(w.key)?.value_zar ?? 0) >= target ? 'green' : 'red'))}
                  />
                </tbody>
              </table>
            )}
          </div>
        </Card>

        {/* RIGHT — persistent inspector (standalone only; embedded uses the slide-in drawer below) */}
        {!embedded && (rightExpanded ? (
          <Card className="flex min-h-0 flex-col overflow-hidden p-0">
            <div className="flex shrink-0 items-center justify-between border-b border-line px-3 py-2">
              <span className="text-sm font-semibold text-body">
                {selectedLiveSlot?.job ? `Job #${selectedLiveSlot.job.job_number}` : 'Inspector'}
              </span>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setPinned((p) => !p)}
                  aria-pressed={pinned}
                  title={pinned ? 'Unpin — let the panel collapse when nothing is selected' : 'Pin the inspector open'}
                  className={`rounded px-1.5 py-0.5 text-[11px] font-semibold ${pinned ? 'bg-primary/10 text-primary' : 'text-muted hover:bg-surface-alt'}`}
                >
                  {pinned ? 'Pinned' : 'Pin'}
                </button>
                <button onClick={() => setSelectedSlotId(null)}
                  title="Clear selection" className="rounded p-1 text-muted hover:bg-surface-alt"><X size={14} /></button>
              </div>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3">
              {selectedLiveSlot?.job ? (
                <CockpitSlotDetail
                  slot={selectedLiveSlot}
                  clockLastUpdated={lastUpdated}
                  canTick={canTickChassis}
                  canRevert={canUnschedule && selectedLiveSlot.job?.status === 'planning'
                    && !(lockedJobIds && selectedLiveSlot.job && lockedJobIds.has(selectedLiveSlot.job.id))}
                  onMarkReceived={() => markSlotChassisReceived(selectedLiveSlot)}
                  onRevert={async (reason) => {
                    const jid = selectedLiveSlot.job?.id
                    if (jid == null) return
                    // Business rules 2 Jul — merged jobs never move backwards.
                    if (lockedJobIds && lockedJobIds.has(jid)) {
                      toast.push({ kind: 'warn', message: `Job ${selectedLiveSlot.job?.job_number} is merged with its chassis — it can't move back to an earlier state.` })
                      return
                    }
                    try {
                      await revertToUnscheduled(jid, reason)
                      setSelectedSlotId(null)
                    } catch { /* surfaced by the context toast */ }
                  }}
                  // v1.49 — reject: the job leaves the board entirely and its costing
                  // reads as Rejected. Same permission and the same merge lock as revert.
                  onReject={async (reason) => {
                    const jid = selectedLiveSlot.job?.id
                    if (jid == null) return
                    if (lockedJobIds && lockedJobIds.has(jid)) {
                      toast.push({ kind: 'warn', message: `Job ${selectedLiveSlot.job?.job_number} is merged with its chassis — it can't be rejected.` })
                      return
                    }
                    try {
                      await rejectJob(jid, reason)
                      setSelectedSlotId(null)
                    } catch { /* surfaced by the context toast */ }
                  }}
                  onViewProduction={() => {
                    const jn = selectedLiveSlot.job?.job_number
                    nav(jn ? `/production?jobId=${encodeURIComponent(jn)}` : '/production')
                  }}
                />
              ) : (
                <EmptyState title="No job selected" hint="Click a job on the timeline to inspect it here — no pop-up." />
              )}
            </div>
          </Card>
        ) : (
          <button onClick={layout.toggleRight} title="Show inspector"
            className="flex min-h-0 flex-col items-center gap-2 rounded-lg border border-line bg-white py-2 text-muted hover:border-primary/40">
            <ChevronsLeft size={15} />
            <span style={{ writingMode: 'vertical-rl' }} className="text-[11px] font-semibold uppercase tracking-wide">Inspector</span>
          </button>
        ))}
      </div>

      {/* A09 embedded — slot detail as a right-side slide-in (same presentation + tokens as the
          floor's job-detail drawer; the a06 .modal/.scrim classes apply because the embedded
          cockpit renders inside the .a06-flow scope). */}
      {embedded && selectedLiveSlot?.job && (() => {
        const close = () => setSelectedSlotId(null)
        const overview = (
          <CockpitSlotDetail
            slot={selectedLiveSlot}
            clockLastUpdated={lastUpdated}
            // 3 Jul (Michael) — inside the standardized drawer the planning-BOM section is
            // redundant: the drawer's Bill of Materials tab shows the live costing sheet.
            hideSections={renderSlotDrawer ? ['bom'] : undefined}
            canTick={canTickChassis}
            canRevert={canUnschedule && selectedLiveSlot.job?.status === 'planning'
              && !(lockedJobIds && selectedLiveSlot.job && lockedJobIds.has(selectedLiveSlot.job.id))}
            onMarkReceived={() => markSlotChassisReceived(selectedLiveSlot)}
            onRevert={async (reason) => {
              const jid = selectedLiveSlot.job?.id
              if (jid == null) return
              if (lockedJobIds && lockedJobIds.has(jid)) {
                toast.push({ kind: 'warn', message: `Job ${selectedLiveSlot.job?.job_number} is merged with its chassis — it can't move back to an earlier state.` })
                return
              }
              try {
                await revertToUnscheduled(jid, reason)
                setSelectedSlotId(null)
              } catch { /* surfaced by the context toast */ }
            }}
            // v1.49 — reject: the job leaves the board entirely and its costing
            // reads as Rejected. Same permission and the same merge lock as revert.
            onReject={async (reason) => {
              const jid = selectedLiveSlot.job?.id
              if (jid == null) return
              if (lockedJobIds && lockedJobIds.has(jid)) {
                toast.push({ kind: 'warn', message: `Job ${selectedLiveSlot.job?.job_number} is merged with its chassis — it can't be rejected.` })
                return
              }
              try {
                await rejectJob(jid, reason)
                setSelectedSlotId(null)
              } catch { /* surfaced by the context toast */ }
            }}
            onViewProduction={() => {
              const jn = selectedLiveSlot.job?.job_number
              nav(jn ? `/production?jobId=${encodeURIComponent(jn)}` : '/production')
            }}
          />
        )
        // 3 Jul — the host may render the standardized tabbed drawer around the same actions node.
        if (renderSlotDrawer) {
          return <Fragment key={selectedLiveSlot.id}>{renderSlotDrawer({ slot: selectedLiveSlot, overview, close })}</Fragment>
        }
        return (
          <EmbeddedSlotDrawer
            key={selectedLiveSlot.id}
            jobNumber={selectedLiveSlot.job.job_number}
            customer={selectedLiveSlot.job.customer}
            slotLabel={`${selectedLiveSlot.bay} · ${selectedLiveSlot.week_key}`}
            onClose={close}
          >
            {overview}
          </EmbeddedSlotDrawer>
        )
      })()}

      {/* ── Bottom dock — bay-model flow zones (collapsed by default). Hidden when embedded in
          the Combined Cockpit: the A06 Production Flow floor below replaces these zones. ─────── */}
      {!embedded && (
      <div className="shrink-0 overflow-hidden rounded-lg border border-line bg-white">
        <button onClick={layout.toggleDock}
          aria-expanded={dockOpen}
          className="flex w-full items-center justify-between px-3 py-2 text-left hover:bg-surface-alt">
          <span className="flex items-center gap-2 text-sm font-semibold text-body">
            <Layers size={15} className="text-primary" />
            Bay model
            <span className="text-xs font-normal text-muted">Parking · Pre-Assembly · Merge · Awaiting QA</span>
          </span>
          {dockOpen ? <ChevronDown size={16} className="text-muted" /> : <ChevronUp size={16} className="text-muted" />}
        </button>
        {dockOpen && (
          <div className="max-h-[44vh] overflow-auto border-t border-line p-3">
            <BayModelLanes />
          </div>
        )}
      </div>
      )}

      {/* ── Footer ───────────────────────────────────────────────────────────── */}
      <div className="flex shrink-0 items-center justify-between">
        <LastUpdated at={lastUpdated} onRefresh={refresh} />
        {!canSchedule && (
          <span className="text-[11px] text-muted">Read-only — your role can’t schedule on the board.</span>
        )}
      </div>

      {/* Ack flow stays a modal (reused as-is). */}
      <PlanningAckPanel
        costing={ackTarget}
        onClose={() => setAckTarget(null)}
        onAcknowledge={async (c, payload) => {
          await ackPlanning(c.quote_number, byActor, payload)
          await refresh()
          setAckTarget(null)
        }}
      />
    </div>
  )
}

// A09 — slot detail presented like the floor's job-detail drawer (slide-in from the right).
// Styled by the a06 .scrim/.modal/.mh classes (the embedded cockpit lives inside .a06-flow).
function EmbeddedSlotDrawer({ jobNumber, customer, slotLabel, onClose, children }: {
  jobNumber: string; customer: string; slotLabel: string; onClose: () => void; children: ReactNode
}) {
  const [open, setOpen] = useState(false)
  useEffect(() => {
    const id = requestAnimationFrame(() => setOpen(true))
    return () => cancelAnimationFrame(id)
  }, [])
  return (
    <>
      <div className={`scrim ${open ? 'show' : ''}`} onClick={onClose} />
      <aside className={`modal ${open ? 'open' : ''}`} role="dialog" aria-label={`Job ${jobNumber}`}>
        <div className="mh">
          <div className="top">
            <div>
              <div className="kind">Scheduled job</div>
              <div className="num">#{jobNumber}</div>
              <div className="meta">{customer}</div>
              <div className="job">{slotLabel}</div>
            </div>
            <button className="x" onClick={onClose}>✕</button>
          </div>
        </div>
        <div className="mbody">{children}</div>
      </aside>
    </>
  )
}

function todayIso(): string {
  const d = new Date()
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

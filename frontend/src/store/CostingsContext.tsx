import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from 'react'
import {
  costingsMock,
  liveToCosting,
  ALL_STATUSES,
  type Costing,
  type LiveCalculation,
  type PrejobCardSummary,
  type RepairPhaseInsertion,
  type StatusName,
} from '../data/costingsData'
import { apiGet, apiPost, ApiError, handleApiError } from '../lib/api'
import { useToast } from '../components/ui/toast'
import { rowKey, staffLabel } from '../lib/revisions'
import { useAppData } from './AppDataContext'

// WO v4.19 (Phase 2C-3): CostingsContext now rides the v4.17/v4.18 primitives.
// It reads the calculations spine + the production-jobs lifecycle and merges them
// (join by calculation_record_id), and its lifecycle mutators POST to
// /api/production-jobs/* via lib/api — which sends the X-CSRF-Token that the raw
// fetch used to omit (the legacy mutations were silently 403ing). Chassis-detail
// capture + repair scheduling have no production-jobs endpoint, so they stay on
// /api/calculations/* but now go through lib/api (CSRF-safe). Mock mode unchanged.

type Mode = 'live' | 'mock' | 'loading'
export type AcceptStage = 'idle' | 'accepting' | 'creating_job' | 'partial' | 'done'

interface CostingsValue {
  mode: Mode
  costings: Costing[]
  statusCounts: Record<StatusName | 'Total', number>
  refresh: () => Promise<void>
  // Per-ROW accept progress (WO v4.19 — drives the Accept/Retry button spinner), keyed by rowKey (the record id).
  acceptStage: Record<string, AcceptStage>
  // Mutations — POST to FastAPI in Live mode; update local state in Mock mode.
  // RT10 — every one takes the costing ROW and acts on ITS record id (calculation_id / production_job_id). They took
  // the quote number until RT10; every revision of a quote shares it, and the quote → id map resolved it to the
  // OLDEST row: Accept on REV 2 accepted REV 0 (RT10_RETURN_1 §4.2).
  firePreJobCard: (c: Costing) => Promise<void>
  confirmPreJobCard: (c: Costing) => Promise<void>
  scheduleRepairPhases: (c: Costing, phases: RepairPhaseInsertion[]) => Promise<void>
  // Work Order v4 mutators.
  acceptCosting: (c: Costing) => Promise<void>
  // Legacy-dashboard parity (Michael, 3 Jul): decline a Pending costing with a required reason.
  declineCosting: (c: Costing, reason: string) => Promise<void>
  signoffPreJob: (c: Costing, role: 'sales' | 'production', attestation: string, by: string) => Promise<void>
  ackPlanning: (c: Costing, by: string, payload?: ChassisEtaPayload | null, notes?: string | null) => Promise<void>
  // Work Order v4.2 — chassis ETA capture.
  captureChassisEta: (c: Costing, payload: ChassisEtaPayload, by: string) => Promise<void>
  loadChassisCatalogue: () => Promise<ChassisCatalogue | null>
  // Work Order v4.3 — chassis arrival confirmation (tick box on job card).
  markChassisReceived: (c: Costing, receivedAt: string | null, by: string) => Promise<void>
}

export interface ChassisEtaPayload {
  chassis_eta: string                        // ISO date
  chassis_vin?: string
  chassis_model?: string
  customer_dealer?: string                   // WO v4.34.1 §0.2 — legacy free-text, superseded by dealer_id
  dealer_id?: number | null                  // WO v4.34.1 §0.3 — structured chassis supplier (customers.is_dealer)
  dealer_name?: string                       // display label for the picked dealer (not persisted server-side)
  tail_lift_code?: string
  chassis_inhouse_bom?: { category: string; description: string; item_code: string }[]
  job_number?: string                        // WO v4.34 §0.8 — Planning-ack override (SAP-assigned)
  // WO v4.36b — chassis-field unification: the ack persists these onto chassis_records (single source of
  // truth). chassis_notes is the CHASSIS note, distinct from the ack `notes` audit comment.
  customer_name?: string
  contact_person?: string
  telephone?: string
  description?: string
  chassis_notes?: string
}

export interface ChassisCatalogue {
  constants: { id: number; category: string; name: string; unit_price: number }[]
  options:   { id: number; kind: string; label: string; axle_count?: number | null; tyre_style?: string | null; price?: number }[]
}

// v4.14 production-jobs list item — the subset we join on (by calculation_record_id).
interface ApiProductionJob {
  id: number
  calculation_record_id: number
  job_number: string | null
  status: string
  mes_status: string
  // WO v4.29 — per-role sign-off timestamps (live on the production_job) so each box ticks + shows
  // "signed by … at …" the moment that role signs.
  pre_job_signoff_sales_at?: string | null
  pre_job_signoff_sales_by?: string | null
  pre_job_signoff_production_at?: string | null
  pre_job_signoff_production_by?: string | null
  pre_job_confirmed_at?: string | null
  // WO v4.34 §0.7/§0.9 — the canonical numeric job_number's provenance + lock + site flag.
  job_number_source?: string | null
  job_number_locked?: boolean
  sap_retired?: boolean
}

const CostingsContext = createContext<CostingsValue | null>(null)

function deriveStatusCounts(rows: Costing[]): Record<StatusName | 'Total', number> {
  const counts = { Total: 0 } as Record<StatusName | 'Total', number>
  for (const s of ALL_STATUSES) counts[s] = 0
  for (const r of rows) {
    counts.Total++
    if ((ALL_STATUSES as string[]).includes(r.status)) counts[r.status]++
  }
  return counts
}

// §0.1 enrichment: an accepted+ calc's lifecycle status/job-number come from its
// production_job; pre-accept calcs (no pj) keep their own status. `production_job_id`
// null on an Accepted row = the "partial" state (accepted calc, job not created yet).
function mergeProductionJob(c: Costing, pj?: ApiProductionJob): Costing {
  if (!pj) return { ...c, production_job_id: null }
  return {
    ...c,
    production_job_id: pj.id,
    status: (pj.mes_status as StatusName) || c.status,
    job_number_assigned: pj.job_number ?? c.job_number_assigned,   // mirrors the canonical numeric (§0.7)
    job_number_source: pj.job_number_source ?? c.job_number_source,
    job_number_locked: pj.job_number_locked ?? c.job_number_locked,
    sap_retired: pj.sap_retired ?? c.sap_retired,
    // WO v4.29 — surface the pj's sign-off state (the source of truth) so each box reflects signed +
    // timestamp immediately, not only once BOTH are in.
    pre_job_signoff_sales_at: pj.pre_job_signoff_sales_at ?? c.pre_job_signoff_sales_at,
    pre_job_signoff_sales_by: pj.pre_job_signoff_sales_by ?? c.pre_job_signoff_sales_by,
    pre_job_signoff_production_at: pj.pre_job_signoff_production_at ?? c.pre_job_signoff_production_at,
    pre_job_signoff_production_by: pj.pre_job_signoff_production_by ?? c.pre_job_signoff_production_by,
    pre_job_confirmed_at: pj.pre_job_confirmed_at ?? c.pre_job_confirmed_at,
  }
}

export function CostingsProvider({ children }: { children: ReactNode }) {
  const toast = useToast()
  const { activeBranch } = useAppData()
  const [mode, setMode] = useState<Mode>('loading')
  const [costings, setCostings] = useState<Costing[]>(costingsMock.costings)
  const [acceptStage, setAcceptStageState] = useState<Record<string, AcceptStage>>({})
  const catalogueCacheRef = useRef<ChassisCatalogue | null>(null)

  const setStage = useCallback((key: string, stage: AcceptStage) => {
    setAcceptStageState((s) => ({ ...s, [key]: stage }))
  }, [])

  // refetch() = reads only (calcs spine ⋈ production-jobs). No autologin (§3.5).
  const refetch = useCallback(async () => {
    try {
      const [calcs, pjs, cards] = await Promise.all([
        apiGet<LiveCalculation[]>('/api/calculations?limit=100'),
        apiGet<ApiProductionJob[]>('/api/production-jobs?limit=200'),
        // §0.21 — the live Pre-Job Card summaries; tolerate an older backend (→ no supersede).
        apiGet<PrejobCardSummary[]>('/api/prejob-cards/summaries').catch(() => [] as PrejobCardSummary[]),
      ])
      if (!Array.isArray(calcs)) {
        // Malformed (non-array) response — treat as unreachable; keep the demo seed.
        setCostings(costingsMock.costings)
        setMode('mock')
        return
      }
      // A valid array — even an empty one — is REAL backend state: render it live. A
      // freshly-wiped / blank-slate backend therefore shows an EMPTY Costings list, not
      // the bundled demo rows. (Only a genuine fetch failure → the catch below → mock.)
      const pjByCalc = new Map((pjs ?? []).map((p) => [p.calculation_record_id, p]))
      const cardByCalc = new Map((cards ?? []).map((s) => [s.calculation_id, s]))
      const rows = calcs.map((c) => ({
        ...mergeProductionJob(liveToCosting(c), pjByCalc.get(c.id)),
        prejob_card: cardByCalc.get(c.id) ?? null,
      }))
      setCostings(rows)
      setMode('live')
    } catch {
      // Backend unreachable / unauthorised → keep the seed, run in mock mode.
      setCostings(costingsMock.costings)
      setMode('mock')
    }
  }, [])

  // Bootstrap once on mount (auth already established by the shell gate + AuthGate).
  useEffect(() => {
    void refetch()
  }, [refetch])

  // Branch-changed signal (WO v4.18 §4.4): refetch on a real switch only.
  const prevBranchId = useRef<number | null | undefined>(undefined)
  useEffect(() => {
    const id = activeBranch?.id ?? null
    const prev = prevBranchId.current
    prevBranchId.current = id
    if (prev === undefined || prev === null || id === null) return
    if (prev !== id) void refetch()
  }, [activeBranch?.id, refetch])

  const statusCounts = useMemo(() => {
    // Mock mode trusts the bundled status_counts (fuller 40-row population); live
    // derives counts from the live rows.
    return mode === 'mock' ? costingsMock.status_counts : deriveStatusCounts(costings)
  }, [mode, costings])

  // ── live helpers ──────────────────────────────────────────────────────────
  // POST to a production-job lifecycle action, then refetch. Re-throws nothing —
  // errors surface via handleApiError (422 amber w/ detail, 403 red, etc.).
  const pjPost = useCallback(
    async (c: Costing, path: string, body?: unknown) => {
      const id = c.production_job_id
      if (id == null) {
        toast.push({ kind: 'warn', message: 'No production job exists for this costing yet.' })
        return
      }
      try {
        await apiPost(`/api/production-jobs/${id}/${path}`, body)
        await refetch()
      } catch (e) {
        // WO v4.36a §0.5 — a VIN clash / dealer / customer conflict from the planning-ack now returns 409
        // with remediation text; surface it as a toast here (handleApiError re-throws 409 for blocking-modal
        // callers — this path wants the legible message inline, not a modal).
        if (e instanceof ApiError && e.status === 409) {
          toast.push({ kind: 'warn', message: e.detail || 'That conflicts with the current chassis state.' })
        } else {
          handleApiError(e, toast.push)
        }
      }
    },
    [refetch, toast],
  )

  // POST to a legacy calculation action (chassis-eta / schedule-repair /
  // pre-job-confirm — no production-jobs equivalent; now CSRF-safe via lib/api).
  const legacyPost = useCallback(
    async (c: Costing, path: string, body?: unknown) => {
      const id = c.calculation_id
      if (id == null) return
      try {
        await apiPost(`/api/calculations/${id}/${path}`, body)
        await refetch()
      } catch (e) {
        handleApiError(e, toast.push)
      }
    },
    [refetch, toast],
  )

  // ── Work Order v4 mutators ──────────────────────────────────────────────────

  // Accept = sequential two-call (§0.2): legacy /accept (idempotent) then
  // /production-jobs/from-calculation (201 new / 200 existing). Both legs idempotent,
  // so this doubles as "Retry job creation" on a partial row (accepted, no job).
  const acceptCosting = useCallback(
    async (ref: Costing) => {
      const key = rowKey(ref)
      if (mode !== 'live') {
        setCostings((prev) =>
          prev.map((c) =>
            rowKey(c) === key && c.status === 'Pending'
              ? {
                  ...c,
                  status: 'Accepted' as StatusName,
                  accepted_at: new Date().toISOString(),
                  actions_available: ['view', 'pre_job_card'],
                }
              : c,
          ),
        )
        return
      }
      const cId = ref.calculation_id
      if (cId == null) return
      const row = costings.find((c) => rowKey(c) === key) ?? ref
      setStage(key, 'accepting')
      let accepted = !!row && row.status !== 'Pending'
      try {
        if (!accepted) {
          await apiPost(`/api/calculations/${cId}/accept`) // step 1 — skip if already accepted (retry)
          accepted = true
        }
        setStage(key, 'creating_job')
        await apiPost(`/api/production-jobs/from-calculation/${cId}`) // step 2
        setStage(key, 'done')
        await refetch()
      } catch (e) {
        // RT6 — a 409 is the body family's insulation rule refusing this costing (accept, or its job): show the
        // sentence ("Re-open it, Remove, save, then accept."). A refused accept leaves the costing Pending — not a
        // partial row.
        if (e instanceof ApiError && e.status === 409) {
          setStage(key, accepted ? 'partial' : 'idle')
          toast.push({ kind: 'error', message: e.detail || 'This costing cannot be accepted.' })
          await refetch()
          return
        }
        setStage(key, 'partial') // step 1 ok but step 2 failed → accepted calc, no job
        handleApiError(e, toast.push)
        await refetch() // reflect the partial state so the Retry button renders
      }
    },
    [mode, costings, refetch, toast, setStage],
  )

  // Decline (legacy-dashboard parity): one POST to the legacy /decline endpoint — sets
  // status='declined' (the list endpoint maps it to the 'Rejected' pill) + stores the reason.
  const declineCosting = useCallback(
    async (ref: Costing, reason: string) => {
      if (mode !== 'live') {
        setCostings((prev) =>
          prev.map((c) =>
            rowKey(c) === rowKey(ref) && c.status === 'Pending'
              ? { ...c, status: 'Rejected' as StatusName, actions_available: ['view'] }
              : c,
          ),
        )
        return
      }
      const cId = ref.calculation_id
      if (cId == null) return
      try {
        await apiPost(`/api/calculations/${cId}/decline`, { reason })
        toast.push({ kind: 'ok', message: `Costing ${staffLabel(ref.quote_number, ref.version, ref.rev)} declined.` })
        await refetch()
      } catch (e) {
        handleApiError(e, toast.push)
      }
    },
    [mode, refetch, toast],
  )

  const firePreJobCard = useCallback(
    async (ref: Costing) => {
      if (mode === 'live') {
        await pjPost(ref, 'pre-job-card')
        return
      }
      setCostings((prev) =>
        prev.map((c) =>
          rowKey(c) === rowKey(ref) && c.status === 'Accepted'
            ? {
                ...c,
                status: 'Pre-Job Sent' as StatusName,
                pre_job_sent_at: new Date().toISOString(),
                pre_job_recipients: ['BURT (Sales Rep)', 'Pieter Coetzee (Production Manager)'],
                pre_job_awaiting_from: ['Pieter Coetzee (Production Manager)'],
                actions_available: ['view', 'view_pre_job_status'],
              }
            : c,
        ),
      )
    },
    [mode, pjPost],
  )

  const confirmPreJobCard = useCallback(
    async (ref: Costing) => {
      if (mode === 'live') {
        await legacyPost(ref, 'pre-job-confirm') // superseded by dual sign-off; kept for back-compat
        return
      }
      setCostings((prev) =>
        prev.map((c) =>
          rowKey(c) === rowKey(ref) && c.status === 'Pre-Job Sent'
            ? {
                ...c,
                status: 'Pre-Job Confirmed' as StatusName,
                pre_job_confirmed_at: new Date().toISOString(),
                job_number_assigned: c.quote_number.replace(/^Q-/, ''),
                actions_available: ['view', 'view_in_planning'],
              }
            : c,
        ),
      )
    },
    [mode, legacyPost],
  )

  const signoffPreJob = useCallback(
    async (ref: Costing, role: 'sales' | 'production', attestation: string, by: string) => {
      if (mode === 'live') {
        await pjPost(ref, 'pre-job-signoff', { role, attestation }) // server records the actor from the session
        return
      }
      setCostings((prev) =>
        prev.map((c) => {
          if (rowKey(c) !== rowKey(ref) || c.status !== 'Pre-Job Sent') return c
          const now = new Date().toISOString()
          const next: Costing = {
            ...c,
            ...(role === 'sales'
              ? {
                  pre_job_signoff_sales_at: now,
                  pre_job_signoff_sales_by: by,
                  pre_job_signoff_sales_attestation: attestation,
                }
              : {
                  pre_job_signoff_production_at: now,
                  pre_job_signoff_production_by: by,
                  pre_job_signoff_production_attestation: attestation,
                }),
          }
          // Auto-progress to Planning when both signoffs are in (transient
          // pre_job_confirmed in the same in-memory transaction).
          if (next.pre_job_signoff_sales_at && next.pre_job_signoff_production_at) {
            next.status = 'Planning'
            next.pre_job_confirmed_at = now
            next.job_number_assigned = c.quote_number.replace(/^Q-/, '')
            next.actions_available = ['view']
          }
          return next
        }),
      )
    },
    [mode, pjPost],
  )

  const ackPlanning = useCallback(
    async (ref: Costing, by: string, payload: ChassisEtaPayload | null = null, notes: string | null = null) => {
      if (mode === 'live') {
        // WO v4.29 D2: planning-ack captures the chassis ETA + rich chassis data in one step,
        // replacing the deadlocked legacy /api/calculations/{id}/chassis-eta call (ADR 0016).
        await pjPost(ref, 'planning-ack', {
          chassis_eta: payload?.chassis_eta || null,
          notes,
          chassis_vin: payload?.chassis_vin,
          chassis_model: payload?.chassis_model,
          customer_dealer: payload?.customer_dealer,
          dealer_id: payload?.dealer_id ?? null,       // §0.3 — structured chassis supplier → chassis_records.dealer_id
          tail_lift_code: payload?.tail_lift_code,
          // WO v4.36b — chassis-field unification (record_planning_ack persists these onto chassis_records)
          customer_name: payload?.customer_name,
          contact_person: payload?.contact_person,
          telephone: payload?.telephone,
          description: payload?.description,
          chassis_notes: payload?.chassis_notes,
          chassis_inhouse_bom: payload?.chassis_inhouse_bom,
          job_number: payload?.job_number,             // §0.8 — override (backend ignores if unchanged/locked/retired)
        })
        return
      }
      setCostings((prev) =>
        prev.map((c) =>
          rowKey(c) === rowKey(ref) && c.status === 'Planning' && !c.planning_acknowledged_at
            ? {
                ...c,
                planning_acknowledged_at: new Date().toISOString(),
                planning_acknowledged_by: by,
              }
            : c,
        ),
      )
    },
    [mode, pjPost],
  )

  // Work Order v4.2 — chassis ETA capture (rich VIN/BOM). No production-jobs
  // endpoint for the rich data → stays on the legacy calc route (CSRF-safe now).
  const captureChassisEta = useCallback(
    async (ref: Costing, payload: ChassisEtaPayload, by: string) => {
      if (mode === 'live') {
        await legacyPost(ref, 'chassis-eta', payload)
        return
      }
      setCostings((prev) =>
        prev.map((c) => {
          if (rowKey(c) !== rowKey(ref) || c.status !== 'Planning') return c
          const now = new Date().toISOString()
          const merged = {
            ...(c.chassis_data ?? {}),
            ...(payload.chassis_vin       !== undefined ? { chassis_vin: payload.chassis_vin } : {}),
            ...(payload.chassis_model     !== undefined ? { chassis_model: payload.chassis_model } : {}),
            ...(payload.customer_dealer   !== undefined ? { customer_dealer: payload.customer_dealer } : {}),
            ...(payload.dealer_id         !== undefined ? { dealer_id: payload.dealer_id } : {}),
            ...(payload.dealer_name       !== undefined ? { dealer_name: payload.dealer_name } : {}),
            ...(payload.tail_lift_code    !== undefined ? { tail_lift_code: payload.tail_lift_code } : {}),
            ...(payload.chassis_inhouse_bom !== undefined ? { chassis_inhouse_bom: payload.chassis_inhouse_bom } : {}),
          }
          return {
            ...c,
            chassis_eta: payload.chassis_eta,
            chassis_eta_captured_at: now,
            chassis_eta_captured_by: by,
            chassis_data: merged,
          }
        }),
      )
    },
    [mode, legacyPost],
  )

  const loadChassisCatalogue = useCallback(async (): Promise<ChassisCatalogue | null> => {
    if (catalogueCacheRef.current) return catalogueCacheRef.current
    try {
      const data = await apiGet<ChassisCatalogue>('/api/chassis/catalogue')
      catalogueCacheRef.current = data
      return data
    } catch {
      return null
    }
  }, [])

  // Work Order v4.3 — mark chassis received. The production-jobs endpoint marks
  // receipt (no payload); there is no server un-tick, so un-tick stays mock-only.
  const markChassisReceived = useCallback(
    async (ref: Costing, receivedAt: string | null, by: string) => {
      if (mode === 'live') {
        if (receivedAt === null) {
          toast.push({ kind: 'warn', message: 'Un-ticking chassis receipt isn’t available in live mode yet.' })
          return
        }
        await pjPost(ref, 'chassis-received')
        return
      }
      setCostings((prev) =>
        prev.map((c) =>
          rowKey(c) === rowKey(ref)
            ? {
                ...c,
                chassis_received_at: receivedAt,
                chassis_received_by: receivedAt ? by : null,
              }
            : c,
        ),
      )
    },
    [mode, pjPost, toast],
  )

  const scheduleRepairPhases = useCallback(
    async (ref: Costing, phases: RepairPhaseInsertion[]) => {
      if (mode === 'live') {
        await legacyPost(ref, 'schedule-repair', {
          phases: phases.map((p) => ({
            phase: p.phase,
            bay_id: p.bay_assignment,
            estimated_hours: p.estimated_hours,
          })),
        })
        return
      }
      setCostings((prev) =>
        prev.map((c) =>
          rowKey(c) === rowKey(ref)
            ? {
                ...c,
                repair_phases: phases.map((p) => ({
                  phase: p.phase,
                  bay_id: p.bay_assignment,
                  estimated_hours: p.estimated_hours,
                })),
              }
            : c,
        ),
      )
    },
    [mode, legacyPost],
  )

  const value = useMemo<CostingsValue>(
    () => ({
      mode,
      costings,
      statusCounts,
      refresh: refetch,
      acceptStage,
      firePreJobCard,
      confirmPreJobCard,
      scheduleRepairPhases,
      acceptCosting,
      declineCosting,
      signoffPreJob,
      ackPlanning,
      captureChassisEta,
      loadChassisCatalogue,
      markChassisReceived,
    }),
    [
      mode, costings, statusCounts, refetch, acceptStage,
      firePreJobCard, confirmPreJobCard, scheduleRepairPhases, acceptCosting, declineCosting,
      signoffPreJob, ackPlanning, captureChassisEta, loadChassisCatalogue, markChassisReceived,
    ],
  )

  return <CostingsContext.Provider value={value}>{children}</CostingsContext.Provider>
}

export function useCostings(): CostingsValue {
  const ctx = useContext(CostingsContext)
  if (!ctx) throw new Error('useCostings must be used within CostingsProvider')
  return ctx
}

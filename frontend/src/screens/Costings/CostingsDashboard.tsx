import { useEffect, useMemo, useRef, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import {
  Search,
  Plus,
  Eye,
  Send,
  Pencil,
  Wrench,
  Truck,
  Filter,
  RadioTower,
  Database,
  ThumbsUp,
  ThumbsDown,
  RotateCw,
  Trash2,
  Undo2,
} from 'lucide-react'
import { useCostings } from '../../store/CostingsContext'
import { useAppData } from '../../store/AppDataContext'
import { Toast } from '../../components/ui/overlays'
import { apiDelete, apiGet, apiPost } from '../../lib/api'
import { ALL_STATUSES, liveToCosting, type Costing, type LiveCalculation, type StatusName } from '../../data/costingsData'
import { Tooltip } from '../../components/ui/Tooltip'
import { Card } from '../../components/ui/primitives'
import { STATUS_STYLES, StatusPillCosting, statusFilterTooltipKey } from './statusPalette'
import { CostingsKpiStrip } from './CostingsKpiStrip'
import { PreJobCardModal } from './PreJobCardModal'
import { FlagBadges } from '../../components/Flag/FlagBadge'   // WO v4.36b §3.2 — job flags (ETA / sign-off / stale)
import { useFlaggedJobs } from '../../hooks/useFlags'
import { RepairPhasePanel } from './RepairPhasePanel'
import { AcceptModal } from './AcceptModal'
import { DeclineModal } from './DeclineModal'
import { BottleneckIndicator } from './BottleneckIndicator'
import { zarShort, dmy, lengthSuffix } from '../../lib/format'
import { Spinner } from '../../components/ui/feedback'

// The costings dashboard — full-page on /costings, which is now the ONLY place it renders.
//
// It used to take an `embedded` prop (WO v4.31 §3.3 / §0.13) for a compressed copy below the
// calculator on /costings/new: smaller title, no New-Costing self-link, its own root testid.
// That embed was removed on 18 Aug (Michael) — it duplicated this page and ambushed anyone
// scrolling inside an unfinished costing — so the prop and its five branches went with it.
export function CostingsDashboard() {
  const nav = useNavigate()
  // v1.49 (Michael, 19 Aug): after "Approve & Save" the calculator sends the
  // user here with ?highlight=<quote>. Scroll that row into view and pulse it
  // for a few seconds, then drop the param so a reload does not re-pulse.
  const [searchParams, setSearchParams] = useSearchParams()
  const highlightQuote = searchParams.get('highlight')
  const [pulsing, setPulsing] = useState<string | null>(null)
  const highlightRef = useRef<HTMLTableRowElement | null>(null)
  const { mode, costings, statusCounts, acceptStage, refresh, scheduleRepairPhases, acceptCosting, declineCosting } = useCostings()
  const { profile, hasPermission, isAdmin, sessionUsername } = useAppData()
  // v1.49 — right-click delete. ctxMenu holds the row the menu was opened on;
  // confirmRow moves it into the confirmation step. Deleting is irreversible, so
  // nothing happens on the menu click itself.
  const [ctxMenu, setCtxMenu] = useState<{ c: Costing; x: number; y: number } | null>(null)
  const [confirmRow, setConfirmRow] = useState<Costing | null>(null)
  const [deleting, setDeleting] = useState(false)
  const [toast, setToast] = useState('')
  // v1.49 — the "Deleted" pill. Soft-deleted costings are NOT in `costings`
  // (the server withholds them), so this view fetches its own rows.
  const [showDeleted, setShowDeleted] = useState(false)
  const [deletedRows, setDeletedRows] = useState<Costing[]>([])
  const [filter, setFilter] = useState<Set<StatusName>>(new Set())

  // v1.50 (Michael, 20 Aug) — the delete right-click is no longer admin-only.
  // Internal Sales holds `costings.delete_own_draft` and may delete its OWN
  // costing while it is still an untouched draft.
  //
  // Per-ROW, not per-user: the same person may delete one row on the board and
  // not the next, so this cannot be hoisted into a single boolean the way the
  // admin gate was. Evaluated at render time on the row under the cursor.
  //
  // The server re-applies all of this in api_delete_calculation and is the
  // authority — this only decides whether to offer the menu, so that a user is
  // never shown an action that will refuse. Deleted rows are excluded because
  // the only action there is Restore, which stays admin-only.
  const canDeleteOwnDraft = hasPermission('costings.delete_own_draft')
  const canDeleteRow = (c: Costing): boolean => {
    if (showDeleted) return isAdmin
    if (isAdmin) return true
    if (!canDeleteOwnDraft) return false
    return (
      !!sessionUsername && c.created_by === sessionUsername &&
      c.status === 'Pending' &&
      !c.pre_job_sent_at && !c.pre_job_confirmed_at
    )
  }

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 3200)
    return () => clearTimeout(t)
  }, [toast])

  useEffect(() => {
    if (!highlightQuote) return
    setPulsing(highlightQuote)
    // The row may not be rendered yet (list still refetching) - retry briefly.
    let tries = 0
    const tick = window.setInterval(() => {
      const el = highlightRef.current
      if (el) {
        el.scrollIntoView({ behavior: 'smooth', block: 'center' })
        window.clearInterval(tick)
      } else if (++tries > 20) {
        window.clearInterval(tick)
      }
    }, 150)
    const off = window.setTimeout(() => {
      setPulsing(null)
      const next = new URLSearchParams(searchParams)
      next.delete('highlight')
      setSearchParams(next, { replace: true })
    }, 6000)
    return () => { window.clearInterval(tick); window.clearTimeout(off) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [highlightQuote])

  async function doDelete(c: Costing) {
    if (!c.calculation_id) {
      setToast('This costing is not live — nothing to delete')
      setConfirmRow(null)
      return
    }
    setDeleting(true)
    try {
      await apiDelete(`/api/calculations/${c.calculation_id}`)
      setConfirmRow(null)
      // Refetch rather than splicing the row out locally: the KPI strip and the
      // status filter chips are derived from the SAME fetch, so a local removal
      // would leave the counts one ahead of the table.
      await refresh()
      setToast(`Deleted ${c.quote_number}`)
    } catch (e: any) {
      // The server refuses with 409 (scheduled work) or, since v1.50, 403 (not
      // your draft any more) and a sentence written for this dialog — show it
      // verbatim rather than inventing wording. The 409 cases in particular are
      // ones the client cannot evaluate at all (a Pre-Job Card, a production job).
      setToast(e?.detail || e?.message || 'Could not delete this costing')
      setConfirmRow(null)
    } finally {
      setDeleting(false)
    }
  }

  async function loadDeleted() {
    try {
      const rows = await apiGet<LiveCalculation[]>('/api/calculations?filter=deleted&limit=100')
      setDeletedRows(rows.map(liveToCosting))
    } catch {
      setDeletedRows([])
      setToast('Could not load deleted costings')
    }
  }

  useEffect(() => { if (showDeleted) void loadDeleted() }, [showDeleted])

  async function doRestore(c: Costing) {
    if (!c.calculation_id) return
    try {
      await apiPost(`/api/calculations/${c.calculation_id}/restore`, {})
      await Promise.all([loadDeleted(), refresh()])
      setToast(`Restored ${c.quote_number}`)
    } catch (e: any) {
      setToast(e?.detail || e?.message || 'Could not restore this costing')
    }
  }
  const [q, setQ] = useState('')
  // Default scope is "mine" so the demo opens on Burt's own work, but flip to
  // "all" automatically once Live mode confirms — the FastAPI session user (the
  // autologin 'admin' user) rarely matches the React profile's rep code, so
  // "mine" would filter the live list to nothing.
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const [userPickedScope, setUserPickedScope] = useState(false)
  useEffect(() => {
    if (mode === 'live' && !userPickedScope) setScope('all')
  }, [mode, userPickedScope])

  // v1.39.1 backport (Item 4): refetch when the dashboard mounts so a costing saved
  // in the /mes/calculator iframe (or changed out-of-band) appears on return. The
  // CostingsProvider otherwise loads once at app-mount + on branch switch only, so the
  // list showed stale after "save → navigate back to the dashboard". `refresh` is a
  // stable useCallback, so this runs once per mount (no loop).
  useEffect(() => { void refresh() }, [refresh])
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [preJobTarget, setPreJobTarget] = useState<Costing | null>(null)
  const [repairTarget, setRepairTarget] = useState<Costing | null>(null)
  const [acceptTarget, setAcceptTarget] = useState<Costing | null>(null)
  const [declineTarget, setDeclineTarget] = useState<Costing | null>(null)   // legacy ✗ parity (3 Jul)

  const canViewAll = hasPermission('costings.view_all')
  const canCreate = hasPermission('costings.create')
  const canPreJob = hasPermission('costings.pre_job_card')
  const { map: jobFlags } = useFlaggedJobs()   // WO v4.36b §3.2 — {job_id → Flag[]}; row keyed by production_job_id
  const canAccept = hasPermission('costings.accept')

  const filtered = useMemo(() => {
    const ql = q.trim().toLowerCase()
    return costings.filter((c) => {
      // "My costings" only makes sense in Mock mode for the Sales Rep demo
      // profile (Burt). In Live mode the data's created_by is the FastAPI
      // username (e.g. 'admin'), unrelated to the React profile — the auto
      // scope-flip above sets scope='all' on first Live load so nothing's
      // hidden, but if the user manually picks "Mine" we honour it.
      if (scope === 'mine' && mode === 'mock' && profile.id === 'rep_burt' && c.created_by !== 'BURT') {
        return false
      }
      if (filter.size && !filter.has(c.status)) return false
      if (!ql) return true
      return (
        c.customer_name.toLowerCase().includes(ql) ||
        c.quote_number.toLowerCase().includes(ql) ||
        c.body_type.toLowerCase().includes(ql) ||
        (c.contact_name ?? '').toLowerCase().includes(ql)
      )
    })
  }, [costings, q, filter, scope, profile, mode])

  // v1.49 — the Deleted view swaps the table's source. The status chips and the
  // mine/all scope describe LIVE work, so they are not applied to a recycle bin.
  const rows = showDeleted ? deletedRows : filtered

  function toggleStatus(s: StatusName) {
    setFilter((prev) => {
      const next = new Set(prev)
      next.has(s) ? next.delete(s) : next.add(s)
      return next
    })
  }

  function toggleSelect(qn: string) {
    setSelected((prev) => {
      const next = new Set(prev)
      next.has(qn) ? next.delete(qn) : next.add(qn)
      return next
    })
  }

  // WO v4.33 §0.19 — bulk Pre-Job send DROPPED: the preview-and-edit flow is per-card
  // (template choice + section edits + signer selection can't be batched). Single-card only.

  return (
    <div className="p-4" data-testid="costings-dashboard">
      {/* Header */}
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <Tooltip k="costings_dashboard.header_title">
          <h1 className="flex items-center gap-2 text-xl font-bold text-body">
            Costings
            <ModePill mode={mode} />
          </h1>
        </Tooltip>
        <div className="flex flex-wrap items-center gap-2">
          {canViewAll && (
            <div className="flex overflow-hidden rounded-md border border-line bg-white text-xs">
              <Tooltip k="costings_dashboard.filter_my_costings">
                <button
                  onClick={() => { setScope('mine'); setUserPickedScope(true) }}
                  className={`flex items-center gap-1 px-3 py-1.5 ${
                    scope === 'mine' ? 'bg-primary text-white' : 'text-body hover:bg-surface-alt'
                  }`}
                >
                  <Filter size={13} /> My costings
                </button>
              </Tooltip>
              <button
                onClick={() => { setScope('all'); setUserPickedScope(true) }}
                className={`px-3 py-1.5 ${scope === 'all' ? 'bg-primary text-white' : 'text-body hover:bg-surface-alt'}`}
              >
                All
              </button>
            </div>
          )}
          {canCreate && (
            <Tooltip k="costings_dashboard.create_new_costing_button">
              <Link
                to="/costings/new"
                className="flex items-center gap-1 rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-white hover:bg-primary-dark"
              >
                <Plus size={15} /> New Costing
              </Link>
            </Tooltip>
          )}
        </div>
      </div>

      {/* WO v4.31 §3.4 — the 5 metric KPI tiles (dashboard top; both embed contexts inherit). */}
      <CostingsKpiStrip />

      {/* Status filter chips */}
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <button
          onClick={() => setFilter(new Set())}
          className={`flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold ${
            filter.size === 0
              ? 'border-primary bg-primary text-white'
              : 'border-line bg-white text-body hover:bg-surface-alt'
          }`}
        >
          All
          <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${filter.size === 0 ? 'bg-white/20' : 'bg-surface-alt text-muted'}`}>
            {statusCounts.Total}
          </span>
        </button>
        {ALL_STATUSES.map((s) => {
          const on = filter.has(s)
          const style = STATUS_STYLES[s]
          return (
            <Tooltip key={s} k={statusFilterTooltipKey(s)}>
              <button
                onClick={() => toggleStatus(s)}
                className={`flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold transition ${
                  on
                    ? `${style.pillBg} ${style.pillText} ${style.border}`
                    : 'border-line bg-white text-body hover:bg-surface-alt'
                }`}
              >
                <span className={`h-2 w-2 rounded-full ${on ? 'bg-white/80' : style.pillBg}`} />
                {s}
                <span className={`rounded-full px-1.5 py-0.5 text-[10px] ${on ? 'bg-white/20' : 'bg-surface-alt text-muted'}`}>
                  {statusCounts[s] ?? 0}
                </span>
              </button>
            </Tooltip>
          )
        })}
        {/* v1.49 — the recycle bin. Deliberately set apart from the status
            chips: those filter live work, this REPLACES the table with rows the
            server does not otherwise send. Admin-only, like the delete itself. */}
        {isAdmin && (
          <button
            data-testid="costing-deleted-pill"
            onClick={() => { setShowDeleted((v) => !v); setCtxMenu(null) }}
            className={`ml-2 flex items-center gap-1 rounded-full border px-3 py-1 text-xs font-semibold transition ${
              showDeleted
                ? 'border-status-red/40 bg-status-red/10 text-status-red'
                : 'border-line bg-white text-muted hover:bg-surface-alt'
            }`}
          >
            <Trash2 size={12} /> Deleted{showDeleted && deletedRows.length ? ` (${deletedRows.length})` : ''}
          </button>
        )}
      </div>

      {/* Search */}
      <Tooltip k="costings_dashboard.search_box">
        <div className="mb-3 flex items-center gap-2 rounded-md border border-line bg-white px-3 py-2">
          <Search size={16} className="text-muted" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Search customer, contact, quote number, body type…"
            className="flex-1 text-sm outline-none"
          />
          {q && (
            <button onClick={() => setQ('')} className="text-xs text-muted hover:text-body">
              clear
            </button>
          )}
        </div>
      </Tooltip>

      {/* Bulk-action bar — WO v4.33 §0.19: bulk Pre-Job send dropped (per-card preview flow);
          the selection bar stays for future bulk actions but carries no Pre-Job button. */}
      {selected.size > 0 && (
        <div className="mb-3 flex items-center gap-2 rounded-md border border-primary bg-primary-light px-3 py-2 text-sm">
          <span className="font-semibold text-primary">{selected.size} selected</span>
          <span className="text-xs text-primary/80">
            Pre-Job Cards are sent per costing (open a row's Send action) — bulk send was retired in v4.33.
          </span>
          <button onClick={() => setSelected(new Set())} className="ml-auto text-xs text-primary hover:underline">
            Clear
          </button>
        </div>
      )}

      {/* Table */}
      <Card className="p-0">
        <div className="overflow-x-auto">
          <table className="w-full text-sm" data-testid="costings-table">
            <thead className="bg-primary text-left text-white">
              <tr>
                <th className="px-2 py-2"></th>
                <Tooltip k="costings_dashboard.column_quote_number"><th className="px-3 py-2 font-semibold">Quote #</th></Tooltip>
                <Tooltip k="costings_dashboard.column_customer"><th className="px-3 py-2 font-semibold">Customer</th></Tooltip>
                {/* Nadie WO (16 Jul): attention-of snapshot (0035) — tells 12 Hino George quotes apart at a glance */}
                <Tooltip k="costings_dashboard.column_contact"><th className="px-3 py-2 font-semibold">Contact</th></Tooltip>
                <Tooltip k="costings_dashboard.column_body_type"><th className="px-3 py-2 font-semibold">Body type</th></Tooltip>
                <Tooltip k="costings_dashboard.column_extras_count"><th className="px-3 py-2 text-center font-semibold">Extras</th></Tooltip>
                <Tooltip k="costings_dashboard.column_created_by"><th className="px-3 py-2 font-semibold">Rep</th></Tooltip>
                <Tooltip k="costings_dashboard.column_created_date"><th className="px-3 py-2 font-semibold">Created</th></Tooltip>
                <th className="px-3 py-2 text-right font-semibold">Selling</th>
                <Tooltip k="costings_dashboard.column_status_badge"><th className="px-3 py-2 font-semibold">Status</th></Tooltip>
                <th className="px-3 py-2 font-semibold">Actions</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((c, i) => (
                <tr
                  key={c.quote_number}
                  ref={c.quote_number === pulsing ? highlightRef : undefined}
                  data-testid="costing-row"
                  data-highlighted={c.quote_number === pulsing ? 'true' : undefined}
                  className={`cursor-pointer border-b border-line hover:bg-primary-light/40 ${
                    c.quote_number === pulsing
                      ? 'animate-pulseRing bg-primary-light/60 ring-2 ring-primary'
                      : i % 2 ? 'bg-surface-alt' : 'bg-white'
                  }`}
                  onClick={() => nav(`/costings/${encodeURIComponent(c.quote_number)}`)}
                  onContextMenu={(e) => {
                    // The browser menu is only suppressed for someone who has
                    // an action on THIS row — everyone else keeps normal
                    // right-click behaviour (v1.50: no longer "admin", see
                    // canDeleteRow).
                    if (!canDeleteRow(c)) return
                    e.preventDefault()
                    e.stopPropagation()      // the row's own onClick would navigate away
                    setCtxMenu({ c, x: e.clientX, y: e.clientY })
                  }}
                >
                  <td className="px-2 py-2" onClick={(e) => e.stopPropagation()}>
                    <input
                      type="checkbox"
                      checked={selected.has(c.quote_number)}
                      onChange={() => toggleSelect(c.quote_number)}
                      className="h-4 w-4 cursor-pointer"
                    />
                  </td>
                  <td className="px-3 py-2 font-mono text-xs font-semibold">{c.quote_number}</td>
                  {/* Nadie (20 Aug) — the END USER (the customer's own customer,
                      snapshotted on the costing in #141) in brackets after the
                      customer, so a reseller's quotes tell themselves apart on the
                      board.

                      With no end user this cell is byte-identical to before the
                      feature existed — and that is asserted on the ATTRIBUTES, not
                      just the text. The truncation and the title belong to the
                      bracketed pair, so they are applied ONLY when there is one:
                      hung on the cell unconditionally, they clipped long CUSTOMER
                      names that had always rendered in full ("360 DEGREES CARRIERS
                      (PTY) LTD" → "360 DEGREES CARRIERS (PTY)…") and put a tooltip
                      on every row. Nadie asked for the end user to be visible, not
                      for the customer column to start hiding things.

                      When there IS an end user, max-w + truncate keep the pair on
                      one line — the row must never wrap — and title carries the
                      untruncated value. */}
                  {c.end_user_company ? (
                    <td data-testid="costing-customer"
                        className="max-w-[260px] truncate px-3 py-2"
                        title={`${c.customer_name} (${c.end_user_company})`}>
                      {c.customer_name}
                      <span className="text-muted"> ({c.end_user_company})</span>
                    </td>
                  ) : (
                    <td data-testid="costing-customer" className="px-3 py-2">
                      {c.customer_name}
                    </td>
                  )}
                  <td className="max-w-[150px] truncate px-3 py-2" title={c.contact_name ?? undefined}>
                    {c.contact_name ?? ''}
                  </td>
                  <td className="px-3 py-2">
                    <span>{c.body_type.replace(/\s*\(REPAIR\)$/i, '')}{lengthSuffix(c.body_length)}</span>
                    {c.requires_chassis && (
                      <Tooltip text="Requires chassis">
                        <span className="ml-1 inline-flex">
                          <Truck size={12} className="text-muted" />
                        </span>
                      </Tooltip>
                    )}
                    {c.quote_type === 'Repair' && (
                      <span className="ml-1 inline-flex items-center rounded bg-[#7E22CE]/10 px-1.5 py-0.5 text-[10px] font-bold uppercase text-[#7E22CE]">
                        Repair
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-center">
                    {c.extras_count > 0 ? (
                      <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-surface-alt text-[11px] font-bold text-muted">
                        {c.extras_count}
                      </span>
                    ) : (
                      <span className="text-muted">—</span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs">{c.created_by}</td>
                  <td className="px-3 py-2 text-xs text-muted">{dmy(c.created_at)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{zarShort(c.selling_zar)}</td>
                  <td className="px-3 py-2">
                    <StatusPillCosting
                      status={c.status}
                      pulsing={c.status === 'Planning' && !c.planning_acknowledged_at}
                    />
                    {c.production_job_id != null && (jobFlags.get(c.production_job_id)?.length ?? 0) > 0 && (
                      <div className="mt-1">
                        <FlagBadges flags={jobFlags.get(c.production_job_id)} domain="jobs" entityId={c.production_job_id} />
                      </div>
                    )}
                    {mode === 'live' && c.status === 'Accepted' && !c.production_job_id && (
                      <Tooltip text="Accepted in the orderbook, but the production job hasn't been created yet.">
                        <span className="ml-1 inline-flex items-center rounded bg-status-amber/15 px-1.5 py-0.5 text-[10px] font-bold uppercase text-status-amber">
                          job pending
                        </span>
                      </Tooltip>
                    )}
                    {c.status === 'Pre-Job Sent' && !c.prejob_card && (
                      // §0.21 — the legacy bottleneck dot reads job-level signoff columns the
                      // new flow never writes; suppress it once a Pre-Job Card supersedes them.
                      <BottleneckIndicator
                        salesAt={c.pre_job_signoff_sales_at ?? null}
                        productionAt={c.pre_job_signoff_production_at ?? null}
                      />
                    )}
                  </td>
                  <td className="px-3 py-2" onClick={(e) => e.stopPropagation()}>
                    <div className="flex flex-wrap items-center gap-1">
                      {/* v1.39.1 (Michael) — View opens the full /results report. 3 Jul: now IN-SHELL
                          (/costings/results/:id iframes the report under the MES chrome) — the old
                          direct link stranded the user on the legacy page with no MES menu. Mock rows
                          (no calculation_id) still fall back to the React costing detail. */}
                      <Tooltip text={c.calculation_id ? 'Open the full costing report' : 'Open the costing detail'}>
                        {c.calculation_id ? (
                          <Link
                            to={`/costings/results/${c.calculation_id}`}
                            className="flex items-center gap-1 rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-primary hover:bg-primary-light"
                          >
                            <Eye size={12} /> View
                          </Link>
                        ) : (
                          <Link
                            to={`/costings/${encodeURIComponent(c.quote_number)}`}
                            className="flex items-center gap-1 rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-primary hover:bg-primary-light"
                          >
                            <Eye size={12} /> View
                          </Link>
                        )}
                      </Tooltip>
                      {canAccept && c.status === 'Pending' && (
                        <Tooltip k="costings_dashboard.accept_button">
                          <button
                            onClick={() => setAcceptTarget(c)}
                            className="flex items-center gap-1 rounded-md bg-[#2563EB] px-2 py-1 text-xs font-semibold text-white hover:opacity-90"
                          >
                            <ThumbsUp size={12} /> Accept
                          </button>
                        </Tooltip>
                      )}
                      {/* Legacy-dashboard parity (Michael, 3 Jul) — the ✗ "Decline this calculation"
                          restored on the MES surface. Reason required; the row moves to the Rejected pill. */}
                      {canAccept && c.status === 'Pending' && (
                        <Tooltip text="Decline this calculation — asks for a reason, then marks it Rejected.">
                          <button
                            data-testid="costing-decline"
                            onClick={() => setDeclineTarget(c)}
                            className="flex items-center gap-1 rounded-md bg-status-red px-2 py-1 text-xs font-semibold text-white hover:opacity-90"
                          >
                            <ThumbsDown size={12} /> Decline
                          </button>
                        </Tooltip>
                      )}
                      {mode === 'live' && c.status === 'Accepted' && !c.production_job_id ? (
                        <Tooltip text="The costing was accepted but its production job wasn't created — retry (safe, idempotent).">
                          <button
                            onClick={() => acceptCosting(c.quote_number)}
                            disabled={acceptStage[c.quote_number] === 'accepting' || acceptStage[c.quote_number] === 'creating_job'}
                            className="flex items-center gap-1 rounded-md bg-status-amber px-2 py-1 text-xs font-semibold text-white hover:opacity-90 disabled:opacity-50"
                          >
                            {acceptStage[c.quote_number] === 'accepting' || acceptStage[c.quote_number] === 'creating_job'
                              ? <Spinner size={12} />
                              : <RotateCw size={12} />} Retry job creation
                          </button>
                        </Tooltip>
                      ) : canPreJob && c.status === 'Accepted' && (mode !== 'live' || c.production_job_id) ? (
                        <Tooltip k="costings_dashboard.pre_job_card_button">
                          <button
                            onClick={() => setPreJobTarget(c)}
                            className="flex items-center gap-1 rounded-md bg-status-amber px-2 py-1 text-xs font-semibold text-white hover:opacity-90"
                          >
                            <Send size={12} /> Pre-Job Card
                          </button>
                        </Tooltip>
                      ) : null}
                      {/* v1.39.1 backport (Item 1): (a) gate on status only — the live FastAPI created_by
                          ('admin') never equals the persona id ('ADMIN'), so the button never rendered;
                          (b) wire Edit → /costings/new?edit=<calculation_id>. LiveCalculator threads ?edit=
                          onto the /mes/calculator iframe src; the legacy calc JS (calculator.js:2112) loads
                          that calculation for editing. Same ?edit=<id> contract as v4.37.1 #57 on main. */}
                      {c.status === 'Pending' && (
                        <Tooltip text={c.calculation_id ? 'Reopen this costing to edit' : 'Edit available on live costings only'}>
                          <button
                            onClick={() => c.calculation_id && nav(`/costings/new?edit=${c.calculation_id}`)}
                            disabled={!c.calculation_id}
                            className="flex items-center gap-1 rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-body hover:bg-surface-alt disabled:opacity-50"
                          >
                            <Pencil size={12} /> Edit
                          </button>
                        </Tooltip>
                      )}
                      {c.status === 'Repair' && (
                        <button
                          onClick={() => setRepairTarget(c)}
                          className="flex items-center gap-1 rounded-md bg-[#7E22CE] px-2 py-1 text-xs font-semibold text-white hover:opacity-90"
                        >
                          <Wrench size={12} /> Schedule
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={11} className="px-4 py-12 text-center text-sm text-muted">
                    No costings match the current filters.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </Card>

      <PreJobCardModal
        costing={preJobTarget}
        onClose={() => setPreJobTarget(null)}
        onConfirm={async () => {
          // WO v4.33 §0.21 — the modal's Submit-for-Check drives the pre_job_sent transition
          // server-side; the parent just refreshes the list (no legacy firePreJobCard).
          await refresh()
          setPreJobTarget(null)
        }}
      />
      <RepairPhasePanel
        costing={repairTarget}
        onClose={() => setRepairTarget(null)}
        onSchedule={async (c, phases) => {
          await scheduleRepairPhases(c.quote_number, phases)
          setRepairTarget(null)
        }}
      />
      <AcceptModal
        costing={acceptTarget}
        onClose={() => setAcceptTarget(null)}
        onConfirm={async (c) => {
          await acceptCosting(c.quote_number)
          setAcceptTarget(null)
        }}
      />
      <DeclineModal
        costing={declineTarget}
        onClose={() => setDeclineTarget(null)}
        onConfirm={async (c, reason) => {
          await declineCosting(c.quote_number, reason)
          setDeclineTarget(null)
        }}
      />

      {/* v1.49 — the row right-click menu. Same scrim + fixed-position idiom as
          ChassisModelSelect, so both context menus behave identically. It only
          opens for a row canDeleteRow() allowed, so no entry here needs its own
          second gate beyond Restore's admin check. */}
      {ctxMenu && (
        <>
          <div className="fixed inset-0 z-[70]" data-testid="costing-ctx-scrim"
               onClick={() => setCtxMenu(null)}
               onContextMenu={(e) => { e.preventDefault(); setCtxMenu(null) }} />
          <div data-testid="costing-ctx"
               className="fixed z-[71] w-56 rounded-md border border-line bg-white py-1 shadow-xl"
               style={{ left: Math.min(ctxMenu.x, window.innerWidth - 240),
                        top: Math.min(ctxMenu.y, window.innerHeight - 80) }}>
            <div className="px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted">
              {ctxMenu.c.quote_number}
            </div>
            {showDeleted && isAdmin ? (
              <button data-testid="costing-ctx-restore"
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-body hover:bg-surface-alt"
                      onClick={() => { const c = ctxMenu.c; setCtxMenu(null); void doRestore(c) }}>
                <Undo2 size={14} /> Restore to the board
              </button>
            ) : (
              <button data-testid="costing-ctx-delete"
                      className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-sm text-status-red hover:bg-status-red/10"
                      onClick={() => { setConfirmRow(ctxMenu.c); setCtxMenu(null) }}>
                <Trash2 size={14} /> Delete costing…
              </button>
            )}
          </div>
        </>
      )}

      {/* The confirmation. Deliberately a second, explicit step: the menu click
          only opens this, so a mis-aimed right-click can never delete anything. */}
      {confirmRow && (
        <div className="fixed inset-0 z-[80] flex items-center justify-center bg-black/40 p-4"
             data-testid="costing-delete-confirm">
          <div className="w-full max-w-md rounded-lg border border-line bg-white p-5 shadow-xl">
            <div className="mb-2 flex items-center gap-2 text-status-red">
              <Trash2 size={18} />
              <h2 className="text-base font-bold">Delete this costing?</h2>
            </div>
            <p className="mb-1 text-sm text-body">
              <strong>{confirmRow.quote_number}</strong> — {confirmRow.customer_name}
            </p>
            <p className="mb-4 text-sm text-muted">
              It comes off the costings board. Nothing is destroyed — it stays
              available under the <strong>Deleted</strong> pill and can be restored
              from there. If it has a Pre-Job Card or is already scheduled into
              production, the delete is refused and nothing changes.
            </p>
            <div className="flex justify-end gap-2">
              <button data-testid="costing-delete-cancel"
                      className="rounded-md border border-line bg-white px-3 py-2 text-sm font-semibold text-body hover:bg-surface-alt"
                      onClick={() => setConfirmRow(null)} disabled={deleting}>
                Cancel
              </button>
              <button data-testid="costing-delete-confirm-btn"
                      className="rounded-md bg-status-red px-3 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-50"
                      onClick={() => doDelete(confirmRow)} disabled={deleting}>
                {deleting ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </div>
        </div>
      )}

      <Toast message={toast} show={!!toast} />
    </div>
  )
}

function ModePill({ mode }: { mode: 'live' | 'mock' | 'loading' }) {
  if (mode === 'loading') {
    return (
      <span className="rounded-full bg-surface-alt px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-muted">
        Loading…
      </span>
    )
  }
  const live = mode === 'live'
  return (
    <Tooltip text={live ? 'Live data from /api/calculations' : 'Bundled mock data (FastAPI app unreachable)'}>
      <span
        className={`flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
          live ? 'bg-status-green/15 text-status-green' : 'bg-surface-alt text-muted'
        }`}
      >
        {live ? <RadioTower size={11} /> : <Database size={11} />}
        {live ? 'Live' : 'Mock'}
      </span>
    </Tooltip>
  )
}

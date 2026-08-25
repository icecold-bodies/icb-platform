import { Fragment, useEffect, useState, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import {
  ArrowLeft,
  Printer,
  Send,
  Wrench,
  Truck,
  CheckCircle2,
  Circle,
  XCircle,
  AlertCircle,
  ShieldCheck,
  Lock,
  ChevronDown,
  ChevronRight,
  ClipboardList,
  User,
  UserCheck,
  MessageSquare,
  MapPin,
  CalendarDays,
  Banknote,
  Package,
  Star,
  Building2,
  FileText,
} from 'lucide-react'
import { useCostings } from '../../store/CostingsContext'
import { apiGet, apiPost } from '../../lib/api'
import { useAppData } from '../../store/AppDataContext'
import { Card, SectionTitle, StatusPill } from '../../components/ui/primitives'
import { Toast } from '../../components/ui/overlays'
import { Tooltip } from '../../components/ui/Tooltip'
import { zar, dmy, hhmm, lengthSuffix } from '../../lib/format'
import { ExportOptionsModal } from './ExportOptionsModal'
// v1.39.1 backport (Item 5+7): demoBom/demoBomTotal removed — the BOM is now fetched live (see LiveBom below).
import { styleForStatus, prettyStatus, StatusPillCosting } from './statusPalette'
import { PreJobCardModal } from './PreJobCardModal'
import { RepairPhasePanel } from './RepairPhasePanel'
import { PreJobSignoffModal } from './PreJobSignoffModal'
import { BottleneckIndicator } from './BottleneckIndicator'
import { RepairQuoteModeModal, type RepairQuoteMode } from './RepairQuoteModeModal'
import { liveToCosting, type Costing, type LiveCalculation, type PrejobCardSummary } from '../../data/costingsData'
import type { Status } from '../../data/types'

// v1.45 — a validated reference is a POINTER at a saved costing (label +
// fingerprint), never a copy of it. Unrelated to the admin "BOM Snapshots".
type ValidatedRef = {
  id: number
  calculation_id: number
  label: string
  created_by: string | null
  created_at: string | null
  active: boolean
  reference_total: number
}

export function CostingDetail() {
  const { quote = '' } = useParams<{ quote: string }>()
  const nav = useNavigate()
  const { mode, costings, refresh, scheduleRepairPhases, signoffPreJob, markChassisReceived } = useCostings()
  const { hasPermission, profile } = useAppData()
  const [toast, setToast] = useState('')
  const [preJobOpen, setPreJobOpen] = useState(false)
  const [repairOpen, setRepairOpen] = useState(false)
  const [signoffRole, setSignoffRole] = useState<'sales' | 'production' | null>(null)
  const [chassisReceivedDate, setChassisReceivedDate] = useState('')
  // v1.51 — the repair quotation's print mode. Held here and SYNCED from the
  // costing once it loads (the row arrives asynchronously, so initialising from
  // it would freeze the default in place on a cold open).
  const [quoteModeOpen, setQuoteModeOpen] = useState(false)
  const [quoteMode, setQuoteMode] = useState<RepairQuoteMode>('breakdown')
  // v1.44 R5b — Export (Excel/Word/PDF) with the shared options dialog.
  const [exportOpen, setExportOpen] = useState(false)
  const [savedRatio, setSavedRatio] = useState<number | null>(null)
  // v1.45 — the costing's Attention contact pre-fills the email recipient.
  const [contactEmail, setContactEmail] = useState('')
  // v1.45 Validated references — Nadie can mark an ACCEPTED costing she has
  // balanced against her Excel, and retire the reference again from here. This
  // is the §8 "costing detail page of the reference costing" surface; the
  // calculator carries the same action for a costing she has just computed.
  const [validatedRef, setValidatedRef] = useState<ValidatedRef | null>(null)
  const [vrefBusy, setVrefBusy] = useState(false)

  // v1.49 — a soft-deleted costing is NOT in the live list (the server withholds
  // it), but the Deleted pill navigates here. Fall back to the deleted list so
  // the page renders — with export and quotation withheld and a Deleted badge —
  // instead of "not found". `costings` itself stays live-only: many consumers
  // (KPIs, planning, production) rely on that.
  const [deletedFallback, setDeletedFallback] = useState<Costing | null>(null)
  const liveHit = costings.find((x) => x.quote_number === decodeURIComponent(quote))
  useEffect(() => {
    if (liveHit || mode !== 'live') { setDeletedFallback(null); return }
    let alive = true
    apiGet<LiveCalculation[]>('/api/calculations?filter=deleted&limit=200')
      .then((rows) => {
        if (!alive) return
        const hit = rows.map(liveToCosting).find((x) => x.quote_number === decodeURIComponent(quote))
        setDeletedFallback(hit ?? null)
      })
      .catch(() => { if (alive) setDeletedFallback(null) })
    return () => { alive = false }
  }, [liveHit, mode, quote])
  const c = liveHit ?? deletedFallback ?? undefined
  // §0.21 — the live Pre-Job Card summary rides on the costing (CostingsContext merges
  // /api/prejob-cards/summaries into every row). When present it supersedes the legacy
  // job-level sign-off widget; one card → one sign-off surface across all costings views.
  const prejobCard = c?.prejob_card ?? null

  // The mode this quote was last downloaded in, once the row is in hand. Not a
  // dependency on `c` itself: the context refreshes the whole list on a timer,
  // and re-seeding on every refresh would throw away a choice made since.
  const storedQuoteMode = c?.repair_quote_print_mode
  useEffect(() => {
    if (storedQuoteMode) setQuoteMode(storedQuoteMode as RepairQuoteMode)
  }, [storedQuoteMode])

  useEffect(() => {
    if (!toast) return
    const t = setTimeout(() => setToast(''), 2200)
    return () => clearTimeout(t)
  }, [toast])

  // v1.39.1 backport (Item 6): refetch on mount so a pre-job sign-off / approval done
  // elsewhere (the /prejob/:id/signoff deep-link page, the outstanding-signoffs admin
  // page, or another tab) is reflected when this costing detail is opened. CostingsContext
  // otherwise loads once at app mount. `refresh` is a stable useCallback (runs once per mount).
  useEffect(() => { void refresh() }, [refresh])

  // v1.45 — is THIS costing already a validated reference? One cheap filtered
  // read; a failure just leaves the panel in its "not a reference yet" state.
  const calcId = c?.calculation_id
  useEffect(() => {
    if (!calcId) { setValidatedRef(null); return }
    let cancelled = false
    void apiGet<ValidatedRef[]>(`/api/validated-references?calculation_id=${calcId}`)
      .then((rows) => { if (!cancelled) setValidatedRef(rows[0] ?? null) })
      .catch(() => { if (!cancelled) setValidatedRef(null) })
    return () => { cancelled = true }
  }, [calcId])

  if (!c) {
    return (
      <div className="p-6">
        <Link to="/costings" className="mb-4 inline-flex items-center gap-1 text-sm text-primary">
          <ArrowLeft size={14} /> Back to Costings
        </Link>
        <Card>
          <p className="text-sm text-muted">Costing <span className="font-mono">{quote}</span> not found in the current data set.</p>
        </Card>
      </div>
    )
  }

  const style = styleForStatus(c.status)
  const canPreJob = hasPermission('costings.pre_job_card')

  // v1.45 — mark/retire a validated reference (§5, §8). Offered on ACCEPTED
  // costings only: an accepted costing is one Nadie has stood behind, which is
  // the same bar as "balanced with my Excel".
  const canManageRefs = hasPermission('costings.validated_refs_manage')
  const canMarkRef = canManageRefs && c.status === 'Accepted' && !!c.calculation_id

  async function markValidatedReference() {
    if (!c || !c.calculation_id) return
    const suggested = `${c.body_type}${lengthSuffix(c.body_length)}`.trim()
    // The SPA shell is not the calculator embed iframe, so a native prompt is
    // safe here — the banked silent-death trap is specific to that iframe.
    const label = window.prompt('Name this validated reference:', suggested)
    if (label === null) return
    if (!label.trim()) { setToast('A name is required'); return }
    setVrefBusy(true)
    try {
      const ref = await apiPost<ValidatedRef>('/api/validated-references', {
        calculation_id: c.calculation_id, label: label.trim(),
      })
      setValidatedRef(ref)
      setToast(`Marked as validated reference "${ref.label}"`)
    } catch (err) {
      setToast(err instanceof Error ? err.message : 'Could not mark this costing')
    } finally {
      setVrefBusy(false)
    }
  }

  async function retireValidatedReference() {
    if (!validatedRef) return
    setVrefBusy(true)
    try {
      const ref = await apiPost<ValidatedRef>(
        `/api/validated-references/${validatedRef.id}/retire`)
      setValidatedRef(ref)
      setToast('Validated reference retired')
    } catch (err) {
      setToast(err instanceof Error ? err.message : 'Could not retire it')
    } finally {
      setVrefBusy(false)
    }
  }

  return (
    <div className="p-4">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <div>
          <Link to="/costings" className="mb-1 inline-flex items-center gap-1 text-xs text-primary">
            <ArrowLeft size={12} /> Back to Costings
          </Link>
          <h1 className="flex flex-wrap items-center gap-3 text-xl font-bold text-body">
            <span className="font-mono">{c.quote_number}</span>
            <StatusPillCosting
              status={c.status}
              pulsing={c.status === 'Planning' && !c.planning_acknowledged_at}
            />
            {c.quote_type === 'Repair' && (
              <span className="rounded bg-[#7E22CE]/10 px-2 py-0.5 text-[11px] font-bold uppercase text-[#7E22CE]">Repair</span>
            )}
            {/* v1.50 (Lezette, 22 Aug) — the R-series number the quotation
                prints as its Document Number. It was issued at save since
                v1.47 but shown nowhere; this is where sales lands after
                saving a repair, so it is the first place it must appear. */}
            {c.repair_document_number && (
              <span
                data-testid="repair-doc-number"
                title="Repair document number — printed on the quotation as Document Number. Issued once, on first save, and never changes."
                className="rounded border border-[#7E22CE]/40 px-2 py-0.5 text-[11px] font-bold text-[#7E22CE]"
              >
                {c.repair_document_number}
              </span>
            )}
            {c.deleted_at && (
              <span data-testid="deleted-badge"
                    title={`Deleted ${c.deleted_by ? 'by ' + c.deleted_by + ' ' : ''}on ${c.deleted_at}. Export and quotation are unavailable — Duplicate to make a new costing, or ask an admin to restore it.`}
                    className="rounded bg-status-red/10 px-2 py-0.5 text-[11px] font-bold uppercase text-status-red">Deleted</span>
            )}
            {c.status === 'Pre-Job Sent' && !prejobCard && (
              <BottleneckIndicator
                salesAt={c.pre_job_signoff_sales_at ?? null}
                productionAt={c.pre_job_signoff_production_at ?? null}
                size="md"
              />
            )}
          </h1>
          <p className="text-sm text-muted">{c.customer_name} · {c.body_type}{lengthSuffix(c.body_length)}</p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          {canPreJob && c.status === 'Accepted' && (
            <button
              onClick={() => setPreJobOpen(true)}
              className="flex items-center gap-1 rounded-md bg-status-amber px-3 py-2 text-sm font-semibold text-white hover:opacity-90"
            >
              <Send size={14} /> Send Pre-Job Card
            </button>
          )}
          {/* v1.45 — mark this accepted costing as a validated reference, or
              retire the reference it already is. Hidden without the permission. */}
          {canMarkRef && !validatedRef?.active && (
            <button
              data-testid="vref-mark-btn"
              disabled={vrefBusy}
              onClick={() => void markValidatedReference()}
              className="flex items-center gap-1 rounded-md border border-line bg-white px-3 py-2 text-sm font-semibold text-body hover:bg-surface-alt disabled:opacity-50"
            >
              <Star size={14} /> Mark as validated reference
            </button>
          )}
          {validatedRef?.active && (
            <span
              data-testid="vref-badge"
              className="flex items-center gap-2 rounded-md border border-status-green bg-status-green/10 px-3 py-2 text-sm font-semibold text-status-green"
            >
              <Star size={14} /> Validated reference: {validatedRef.label}
              {canManageRefs && (
                <button
                  data-testid="vref-retire-btn"
                  disabled={vrefBusy}
                  onClick={() => void retireValidatedReference()}
                  className="ml-1 text-xs font-normal underline disabled:opacity-50"
                >
                  Retire
                </button>
              )}
            </span>
          )}
          {c.status === 'Repair' && (
            <button
              onClick={() => setRepairOpen(true)}
              className="flex items-center gap-1 rounded-md bg-[#7E22CE] px-3 py-2 text-sm font-semibold text-white hover:opacity-90"
            >
              <Wrench size={14} /> Schedule into MES
            </button>
          )}
          {/* v1.48 — the customer-facing repair quotation on the ICB letterhead.
              Gated on the server's has_repair_quote, not on quote_type: a
              Calculator 2 repair tick also reads as 'Repair' here but has a
              body, and the download endpoint refuses it with 409. */}
          {c.has_repair_quote && c.calculation_id && !c.deleted_at && (
            <button
              data-testid="repair-quote-btn"
              /* v1.51 — the print mode is chosen at download time, so the button
                 ASKS rather than fetching. The chooser opens on whatever this
                 quote was last downloaded as, which makes a re-download one
                 extra click and reproduces the document the customer has. */
              onClick={() => setQuoteModeOpen(true)}
              title="The customer-facing quotation on the ICB letterhead"
              className="flex items-center gap-1 rounded-md border border-line bg-white px-3 py-2 text-sm font-semibold text-body hover:bg-surface-alt"
            >
              <FileText size={14} /> Repair quotation (PDF)
            </button>
          )}
          <RepairQuoteModeModal
            open={quoteModeOpen}
            selected={quoteMode}
            onClose={() => setQuoteModeOpen(false)}
            onPick={(m) => {
              setQuoteMode(m)
              setQuoteModeOpen(false)
              window.open(
                `/api/calculations/${c.calculation_id}/repair-quote.pdf?mode=${encodeURIComponent(m)}`,
                '_blank',
                'noopener',
              )
            }}
          />
          {/* v1.49 (Michael, 19 Aug) — a DELETED costing gets no Export and no
              quotation. The server refuses both (rule 1), but a button that
              exists and then errors with raw JSON is not a rule the user can
              see. Duplicate remains the way to a new costing from it. */}
          {!c.deleted_at && <button
            data-testid="export-open-btn"
            onClick={async () => {
              if (!c.calculation_id) {
                setToast('Export is available on live (saved) costings only')
                return
              }
              // R3b default: the ratio saved on this costing pre-ticks the dialog;
              // its Attention contact pre-fills the email recipient (v1.45).
              try {
                const r = await apiGet<{
                  saved_result?: { ratio_value?: number | null }; contact_email?: string | null
                }>(`/api/calculations/${c.calculation_id}`)
                setSavedRatio(r.saved_result?.ratio_value ?? null)
                setContactEmail(r.contact_email ?? '')
              } catch {
                setSavedRatio(null)
                setContactEmail('')
              }
              setExportOpen(true)
            }}
            className="flex items-center gap-1 rounded-md border border-line bg-white px-3 py-2 text-sm font-semibold text-body hover:bg-surface-alt"
          >
            <Package size={14} /> Export
          </button>}
          <button
            onClick={() =>
              c.calculation_id
                ? window.open(`/results/${c.calculation_id}`, '_blank', 'noopener')
                : setToast('Print / PDF is available on live (saved) costings only')
            }
            className="flex items-center gap-1 rounded-md bg-primary px-3 py-2 text-sm font-semibold text-white hover:bg-primary-dark"
          >
            <Printer size={14} /> Print costing PDF (MES style)
          </button>
        </div>
      </div>

      <div className="mb-4 grid gap-4 lg:grid-cols-3">
        {/* v1.42 (Michael 17 Jul) — "Quotation / Configuration Overview": header band with icon
            tile + status badge, icon-labelled fields in divided columns, Body options as a
            one-per-line checklist. Plain div (not Card) so the header band can bleed edge-to-edge
            (Card's built-in p-4 can't be unset — Tailwind orders p-0 before p-4). */}
        <div className="overflow-hidden rounded-lg border border-line bg-white shadow-sm transition-shadow duration-200 hover:shadow-md lg:col-span-2">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-line px-5 py-4">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-primary/10 text-primary">
                <ClipboardList size={20} />
              </div>
              <div>
                <h2 className="text-[15px] font-bold leading-tight text-body">Quotation / Configuration Overview</h2>
                <p className="mt-0.5 text-xs text-muted">Summary of customer, build type and body options</p>
              </div>
            </div>
            <StatusBadgeSoft status={c.status} />
          </div>

          <div className="grid gap-x-6 gap-y-5 px-5 py-5 sm:grid-cols-2 lg:grid-cols-3 lg:gap-x-0">
            <div className="space-y-4 lg:pr-6">
              <InfoField icon={<User size={13} strokeWidth={2.5} />} label="Customer" value={c.customer_name} />
              <InfoField icon={<Truck size={13} strokeWidth={2.5} />} label="Body type" value={`${c.body_type}${lengthSuffix(c.body_length)}`} />
              <InfoField icon={<MapPin size={13} strokeWidth={2.5} />} label="Site" value={c.site} />
            </div>

            <div className="space-y-4 lg:border-l lg:border-line lg:px-6">
              {c.contact_name && (
                <InfoField accent="amber" icon={<UserCheck size={13} strokeWidth={2.5} />} label="Attention" value={c.contact_name} />
              )}
              {/* v1.47 lane B — the END USER this body is for (the customer's customer).
                  Snapshot-driven and optional: absent → the row does not render at all. */}
              {c.end_user_company && (
                <InfoField accent="amber" icon={<Building2 size={13} strokeWidth={2.5} />} label="End user" value={c.end_user_company} />
              )}
              <InfoField accent="amber" icon={<MessageSquare size={13} strokeWidth={2.5} />} label="Quote type" value={c.quote_type} />
              <InfoField
                accent="amber"
                icon={<Truck size={13} strokeWidth={2.5} />}
                label="Chassis"
                value={c.requires_chassis ? (c.chassis_supplied_by === 'in-house' ? 'In-house' : 'Customer supplied') : 'Not required'}
              />
              <InfoField
                accent="amber"
                icon={<CalendarDays size={13} strokeWidth={2.5} />}
                label="Created"
                value={`${dmy(c.created_at)} ${hhmm(c.created_at)}`}
                sub={`by ${c.created_by}`}
              />
            </div>

            <BodyOptionsPanel calculationId={c.calculation_id ?? null} mode={mode} />
          </div>

          {((c.extras_list && c.extras_list.length > 0)
            || (c.quote_type === 'Repair' && (c.repair_scope || c.repair_type))) && (
            <div className="space-y-4 border-t border-line px-5 py-4">
              {c.extras_list && c.extras_list.length > 0 && (
                <div>
                  <div className="mb-1.5 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-primary">
                    <Package size={13} strokeWidth={2.5} /> Extras ({c.extras_count})
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {c.extras_list.map((x) => (
                      <span key={x} className="rounded-full border border-line bg-surface-alt px-2.5 py-0.5 text-xs font-medium text-body">{x}</span>
                    ))}
                  </div>
                </div>
              )}

              {c.quote_type === 'Repair' && (c.repair_scope || c.repair_type) && (
                <div className="rounded-md border border-[#7E22CE]/30 bg-[#7E22CE]/5 p-3">
                  <div className="mb-1 text-xs font-semibold uppercase tracking-wide text-[#7E22CE]">Repair scope</div>
                  {/* v1.47 — TYPE OF REPAIR is required on the repair surface, the work
                      description is optional, so the block must render on either. */}
                  {c.repair_type && (
                    <p className="text-sm text-body"><strong>Type: </strong>{c.repair_type}</p>
                  )}
                  {c.repair_scope && <p className="text-sm text-body">{c.repair_scope}</p>}
                  {c.repair_phase_entry && (
                    <p className="mt-2 text-xs text-muted"><strong>Phase entry plan: </strong>{c.repair_phase_entry}</p>
                  )}
                </div>
              )}
            </div>
          )}
        </div>

        <div className="overflow-hidden rounded-lg border border-line bg-white shadow-sm transition-shadow duration-200 hover:shadow-md">
          <div className="flex items-center gap-3 border-b border-line px-5 py-4">
            <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-status-green/10 text-status-green">
              <Banknote size={20} />
            </div>
            <div>
              <h2 className="text-[15px] font-bold leading-tight text-body">Cost Summary</h2>
              <p className="mt-0.5 text-xs text-muted">Manufacturing cost & selling price build-up</p>
            </div>
          </div>
          <div className="px-5 py-4">
            {/* v1.39.1 (Michael) — full cost review as per the /results report: manufacturing cost, cost/m²,
                margin, ratio, discount, net + SELLING PRICE. Live rows read the saved_result (the costing-object
                c.cost_zar/markup_pct are 0 — never populated from the calc); mock rows keep the legacy fallback. */}
            <CostSummary
              calculationId={c.calculation_id ?? null}
              mode={mode}
              fallback={
                <dl className="space-y-2 text-sm">
                  <TotalRow label="Cost" value={c.cost_zar} />
                  {(c.discount_amount ?? 0) > 0 ? (
                    <>
                      <TotalRow label="Before discount" value={c.gross_selling_zar ?? c.selling_zar} muted />
                      <TotalRow label="Discount" valueText={`- ${zar(c.discount_amount ?? 0)}`} muted />
                      <TotalRow label="Net total" value={c.selling_zar} highlight />
                    </>
                  ) : (
                    <TotalRow label="Selling price" value={c.selling_zar} highlight />
                  )}
                  <TotalRow label="Gross profit" value={c.gross_profit_zar} muted />
                  <TotalRow label="Markup" valueText={`${c.markup_pct}%`} muted />
                </dl>
              }
            />
          </div>
        </div>
      </div>

      {prejobCard ? (
        /* §0.21 — a Pre-Job Card row exists → it IS the single sign-off surface. */
        <PreJobCardStatusPanel card={prejobCard} onView={() => setPreJobOpen(true)} />
      ) : (c.status === 'Pre-Job Sent' || c.pre_job_signoff_sales_at || c.pre_job_signoff_production_at || c.pre_job_confirmed_at) ? (
        <Tooltip k="costings_detail.prejob_signoff_section">
          {/* WO v4.29 — keep this section visible AFTER confirmation so the sign-off provenance
              (who + when, both roles) is retained on the record, not just while awaiting.
              §0.21: LEGACY path only — renders when no prejob_cards row supersedes it (rows
              in-flight at the v4.33 cutover complete here; new cards never reach this). */}
          <Card data-testid="prejob-legacy-signoff" className={`mb-4 ${c.pre_job_signoff_sales_at && c.pre_job_signoff_production_at ? 'border-status-green' : 'border-status-amber'}`}>
            <SectionTitle>Pre-Job Card sign-offs</SectionTitle>
            <p className="mb-3 text-xs text-muted">
              {c.pre_job_signoff_sales_at && c.pre_job_signoff_production_at
                ? 'Both sign-offs confirmed — retained below for the record (who signed off and when).'
                : 'Two role-gated sign-offs required. When BOTH are confirmed the job auto-moves to Planning status and appears on the Planning Board (Unscheduled lane).'}
            </p>
            <div className="space-y-2">
              <SignoffCheck
                role="sales"
                label="Sales Rep confirms client requirements are correct"
                at={c.pre_job_signoff_sales_at ?? null}
                by={c.pre_job_signoff_sales_by ?? null}
                canSign={hasPermission('costings.signoff_sales')}
                userName={profile.name}
                userRole={profile.role}
                onTick={() => setSignoffRole('sales')}
              />
              <SignoffCheck
                role="production"
                label="Production confirms feasibility & capacity"
                at={c.pre_job_signoff_production_at ?? null}
                by={c.pre_job_signoff_production_by ?? null}
                canSign={hasPermission('costings.signoff_production')}
                userName={profile.name}
                userRole={profile.role}
                onTick={() => setSignoffRole('production')}
              />
            </div>
          </Card>
        </Tooltip>
      ) : null}

      <Card className="mb-4 p-0">
        <div className="p-4 pb-2"><SectionTitle>Bill of materials</SectionTitle></div>
        <LiveBom calculationId={c.calculation_id ?? null} mode={mode} />
      </Card>

      {/* v4.3 — Chassis-received tick box (only after chassis ETA captured) */}
      {c.chassis_eta && (
        <Tooltip k="costings_detail.chassis_received_tick">
          <Card className={`mb-4 border-l-4 ${c.chassis_received_at ? 'border-status-green' : 'border-status-amber'}`}>
            <SectionTitle>Chassis received</SectionTitle>
            <div className="flex flex-wrap items-start gap-4">
              <Tooltip text={hasPermission('production.chassis_received') ? (c.chassis_received_at ? 'Un-tick (mistake correction)' : 'Tick to mark chassis received') : 'Requires Planning role'}>
              <button
                type="button"
                disabled={!hasPermission('production.chassis_received')}
                onClick={async () => {
                  const by = profile.id === 'rep_burt' ? 'BURT' : profile.id
                  if (c.chassis_received_at) {
                    await markChassisReceived(c.quote_number, null, by)
                    setToast(`Chassis-received tick removed`)
                  } else {
                    const dateIso = chassisReceivedDate || new Date().toISOString().slice(0, 10)
                    await markChassisReceived(c.quote_number, dateIso, by)
                    setToast(`Chassis received recorded for ${c.quote_number}`)
                  }
                }}
                className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-md border-2 transition disabled:cursor-not-allowed disabled:opacity-50 ${
                  c.chassis_received_at
                    ? 'border-status-green bg-status-green text-white'
                    : 'border-status-amber bg-white text-status-amber hover:bg-status-amber/10'
                }`}
              >
                {c.chassis_received_at ? <CheckCircle2 size={22} /> : <Circle size={22} />}
              </button>
              </Tooltip>
              <div className="flex-1 min-w-[260px]">
                {c.chassis_received_at ? (
                  <div className="space-y-1 text-sm">
                    <div className="font-semibold text-status-green">Chassis received and confirmed.</div>
                    <div className="text-xs text-muted">
                      <ShieldCheck size={11} className="mr-1 inline-block text-status-green" />
                      Received on <strong>{dmy(c.chassis_received_at)}</strong> · ticked by <strong>{c.chassis_received_by}</strong>
                    </div>
                    {c.chassis_eta && (
                      <div className="text-xs text-muted">
                        Planner ETA was {dmy(c.chassis_eta)} —
                        {(() => {
                          const eta = new Date(c.chassis_eta + 'T00:00:00Z').getTime()
                          const got = new Date(c.chassis_received_at + 'T00:00:00Z').getTime()
                          const days = Math.round((got - eta) / 86_400_000)
                          if (days === 0) return ' on time.'
                          if (days < 0) return ` ${Math.abs(days)} day${Math.abs(days) === 1 ? '' : 's'} early.`
                          return ` ${days} day${days === 1 ? '' : 's'} late.`
                        })()}
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="space-y-2">
                    <p className="text-sm text-body">
                      Tick the box when the chassis physically arrives at Icecold.
                      Planner ETA: <strong>{dmy(c.chassis_eta)}</strong> (captured by {c.chassis_eta_captured_by ?? '—'}).
                    </p>
                    <label className="block text-xs text-muted">
                      <span className="font-semibold">Received date</span>
                      <input
                        type="date"
                        value={chassisReceivedDate || new Date().toISOString().slice(0, 10)}
                        max={new Date().toISOString().slice(0, 10)}
                        disabled={!hasPermission('production.chassis_received')}
                        onChange={(e) => setChassisReceivedDate(e.target.value)}
                        className="mt-1 rounded-md border border-line bg-white px-2 py-1 text-sm disabled:bg-surface-alt"
                      />
                      <span className="ml-2 text-[10px] text-muted">(defaults to today; adjust if chassis arrived earlier)</span>
                    </label>
                    {!hasPermission('production.chassis_received') && (
                      <p className="text-[11px] text-muted">
                        <Lock size={11} className="mr-1 inline-block" /> Requires Planning role.
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          </Card>
        </Tooltip>
      )}

      <Card>
        <SectionTitle>Status history</SectionTitle>
        {mode === 'live' && c.production_job_id
          ? <LiveTimeline pjId={c.production_job_id}
              refreshKey={`${c.status}|${prejobCard?.status ?? ''}|${c.pre_job_confirmed_at ?? ''}|${c.chassis_received_at ?? ''}`} />
          : <StatusTimeline c={c} statusHex={style.hex} />}
      </Card>

      <PreJobCardModal
        costing={preJobOpen ? c : null}
        onClose={() => setPreJobOpen(false)}
        onConfirm={async () => {
          // WO v4.33 §0.21 — submit drives pre_job_sent server-side; just refresh + navigate.
          await refresh()
          setPreJobOpen(false)
          setToast(`Pre-Job Card sent for check`)
          nav('/costings')
        }}
      />
      <RepairPhasePanel
        costing={repairOpen ? c : null}
        onClose={() => setRepairOpen(false)}
        onSchedule={async (target, phases) => {
          await scheduleRepairPhases(target.quote_number, phases)
          setRepairOpen(false)
          setToast(`Repair plan inserted into MES (${phases.length} phase${phases.length === 1 ? '' : 's'})`)
        }}
      />

      <ExportOptionsModal
        open={exportOpen}
        verb="Export"
        ratioOptions={[]}
        defaultRatio={savedRatio}
        defaultEmail={contactEmail}
        onEmail={async ({ format, detail, ratios, to, note }) => {
          await apiPost(`/results/${c.calculation_id}/export/email`,
                        { format, detail, ratios, to, note })
        }}
        onClose={() => setExportOpen(false)}
        onConfirm={({ format, detail, ratios }) => {
          // Same-page download via a transient anchor (no popup tab): the GET
          // responds with Content-Disposition attachment.
          const a = document.createElement('a')
          a.href = `/results/${c.calculation_id}/export/${format}?detail=${detail}&ratios=${ratios.join(',')}`
          document.body.appendChild(a)
          a.click()
          a.remove()
          setExportOpen(false)
        }}
      />

      <PreJobSignoffModal
        open={!!signoffRole}
        role={signoffRole ?? 'sales'}
        costing={c}
        userName={profile.name}
        userRoleLabel={profile.role}
        onClose={() => setSignoffRole(null)}
        onConfirm={async (attestation) => {
          const r = signoffRole!
          // Use the rep_code where we have one (Burt -> 'BURT'), else profile.id.
          const by = profile.id === 'rep_burt' ? 'BURT' : profile.id
          await signoffPreJob(c.quote_number, r, attestation, by)
          setSignoffRole(null)
          setToast(`Sign-off recorded (${r === 'sales' ? 'Sales Rep' : 'Production'})`)
        }}
      />

      <Toast message={toast} show={!!toast} />
    </div>
  )
}

// WO v4.33 §0.21 — the new-flow status panel. Reads prejob_cards (the source of truth) and is
// the SINGLE sign-off surface once a card exists; "View Pre-Job Card" reopens the same modal
// (read-only when sent/confirmed), and the email/PDF helpers re-run the §0.11/§3.6 routes.
function PreJobCardStatusPanel({ card, onView }: { card: PrejobCardSummary; onView: () => void }) {
  const rejected = card.status === 'draft' && !!card.reject_reason
  const pill: { s: Status; label: string } =
    card.status === 'pre_job_confirmed' ? { s: 'GREEN', label: 'Pre-Job Confirmed' }
      : card.status === 'sent_for_check' ? { s: 'AMBER', label: 'Sent for check' }
        : rejected ? { s: 'RED', label: 'Rejected — back at draft' }
          : { s: 'GREY', label: 'Draft' }
  const border = pill.s === 'GREEN' ? 'border-status-green' : pill.s === 'RED' ? 'border-status-red' : 'border-status-amber'

  return (
    <Tooltip k="costings_detail.prejob_signoff_section">
      <Card data-testid="prejob-status-panel" className={`mb-4 ${border}`}>
        <div className="mb-2 flex flex-wrap items-center gap-2">
          <SectionTitle>Pre-Job Card</SectionTitle>
          <StatusPill status={pill.s} label={pill.label} />
        </div>
        <p className="mb-3 text-xs text-muted">
          The live Pre-Job Card record — both checks below drive confirmation (§0.21 supersedes
          the legacy job-level sign-off).
        </p>
        {rejected && (
          <div className="mb-3 rounded-md border border-status-red/40 bg-status-red/5 p-2 text-xs text-status-red">
            {card.reject_reason}
          </div>
        )}
        <div className="space-y-2">
          <SignoffRow label="Sales Rep" at={card.sales_rep_signoff_at} who={card.sales_rep_username} />
          <SignoffRow label="Planner" at={card.planner_signoff_at} who={card.planner_username} />
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button data-testid="prejob-panel-view" onClick={onView}
            className="rounded-md bg-primary px-3 py-1.5 text-sm font-semibold text-white hover:bg-primary-dark">
            View Pre-Job Card →
          </button>
          {/* v1.39.3 — mailto "Open email draft" removed; server-side SMTP is the sole email path. */}
          <button onClick={() => window.open(`/api/prejob-cards/${card.id}/pdf`, '_blank')}
            className="flex items-center gap-1 rounded-md border border-line px-3 py-1.5 text-sm hover:bg-surface-alt">
            <Printer size={14} /> Download PDF
          </button>
        </div>
      </Card>
    </Tooltip>
  )
}

function SignoffRow({ label, at, who }: { label: string; at: string | null; who: string | null }) {
  const signed = !!at
  return (
    <div className={`flex items-center gap-3 rounded-md border p-3 ${signed ? 'border-status-green/40 bg-status-green/5' : 'border-line bg-white'}`}>
      <span className={`flex h-6 w-6 shrink-0 items-center justify-center rounded-full ${signed ? 'bg-status-green text-white' : 'bg-surface-alt text-muted'}`}>
        {signed ? <CheckCircle2 size={16} /> : <Circle size={14} />}
      </span>
      <div className="flex-1 text-sm">
        <span className="font-semibold text-body">{label}:</span>{' '}
        {signed
          ? <span className="text-status-green">{who ?? '—'} · {dmy(at!)} {hhmm(at!)}</span>
          : <span className="text-muted">awaiting sign-off{who ? ` — assigned: ${who}` : ' — unassigned'}</span>}
      </div>
    </div>
  )
}

function SignoffCheck({
  role,
  label,
  at,
  by,
  canSign,
  userName,
  userRole,
  onTick,
}: {
  role: 'sales' | 'production'
  label: string
  at: string | null
  by: string | null
  canSign: boolean
  userName: string
  userRole: string
  onTick: () => void
}) {
  const signed = !!at
  const tooltipKey =
    role === 'sales'
      ? 'costings_detail.prejob_signoff_sales_check'
      : 'costings_detail.prejob_signoff_production_check'
  const requiredRole = role === 'sales' ? 'Sales Rep' : 'Production Manager'
  return (
    <Tooltip k={tooltipKey}>
      <div className={`rounded-md border p-3 ${signed ? 'border-status-green/40 bg-status-green/5' : 'border-line bg-white'}`}>
        <label className={`flex items-start gap-3 ${signed ? '' : canSign ? 'cursor-pointer' : 'cursor-not-allowed opacity-70'}`}>
          <button
            type="button"
            disabled={signed || !canSign}
            onClick={onTick}
            className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded border ${
              signed
                ? 'border-status-green bg-status-green text-white'
                : canSign
                  ? 'border-primary bg-white text-primary hover:bg-primary-light'
                  : 'border-line bg-surface-alt text-muted'
            }`}
          >
            {signed ? <CheckCircle2 size={16} /> : !canSign ? <Lock size={13} /> : null}
          </button>
          <div className="flex-1">
            <div className={`text-sm font-semibold ${signed ? 'text-status-green' : 'text-body'}`}>{label}</div>
            {!signed && (canSign ? (
              <div className="mt-1 text-xs text-muted">
                You are signed in as <strong>{userName}</strong> ({userRole}). Click the box to open the formal attestation modal.
              </div>
            ) : (
              <div className="mt-1 text-xs text-muted">
                Disabled — requires <strong>{requiredRole}</strong> role to sign off. You are signed in as {userName} ({userRole}).
              </div>
            ))}
          </div>
          {/* WO v4.29 — signed-off stamp to the RIGHT of the label (date + time + who) */}
          {signed && (
            <div className="shrink-0 self-center text-right text-xs text-muted">
              <div className="font-semibold text-status-green">
                <ShieldCheck size={12} className="mr-1 inline-block" /> Signed by {by}
              </div>
              <div className="tabular-nums">{dmy(at)} {hhmm(at!)}</div>
            </div>
          )}
        </label>
      </div>
    </Tooltip>
  )
}

// v1.42 QCO — icon-labelled field for the Quotation/Configuration Overview card.
// Accent alternates per column (blue = identity/build, amber = commercial/provenance)
// to mirror the ratified reference design.
function InfoField({
  icon,
  label,
  value,
  sub,
  accent = 'blue',
}: {
  icon: ReactNode
  label: string
  value: ReactNode
  sub?: string
  accent?: 'blue' | 'amber'
}) {
  return (
    <div>
      <div className={`mb-1 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider ${accent === 'amber' ? 'text-status-amber' : 'text-primary'}`}>
        {icon}
        {label}
      </div>
      <div className="text-sm font-semibold leading-snug text-body">{value}</div>
      {sub && <div className="mt-0.5 text-xs text-muted">{sub}</div>}
    </div>
  )
}

// Soft-tinted status badge (10% bg / 25% border of the status hex) for the card
// header band — the reference design's "Active" pill. The page h1 keeps the solid
// StatusPillCosting (incl. the Planning pulse); this one stays static.
function StatusBadgeSoft({ status }: { status: string }) {
  const s = styleForStatus(status)
  return (
    <span
      className="inline-flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-xs font-semibold"
      style={{ backgroundColor: `${s.hex}1A`, borderColor: `${s.hex}40`, color: s.hex }}
    >
      <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: s.hex }} />
      {prettyStatus(status)}
    </span>
  )
}

function TotalRow({
  label,
  value,
  valueText,
  highlight,
  muted,
  accentGreen,
}: {
  label: string
  value?: number
  valueText?: string
  highlight?: boolean
  muted?: boolean
  accentGreen?: boolean
}) {
  return (
    <div className="flex items-center justify-between">
      <dt className={muted ? 'text-muted' : 'text-body'}>{label}</dt>
      <dd
        className={`tabular-nums ${
          highlight ? 'text-lg font-bold text-primary' : accentGreen ? 'font-semibold text-status-green' : 'font-semibold'
        }`}
      >
        {valueText ?? (value != null ? zar(value) : '—')}
      </dd>
    </div>
  )
}

function StatusTimeline({ c, statusHex }: { c: Costing; statusHex: string }) {
  const steps = [
    {
      label: 'Created',
      at: c.created_at,
      kind: 'done' as const,
      detail: `by ${c.created_by}`,
    },
    {
      label: 'Accepted',
      at: c.accepted_at,
      kind: (c.accepted_at || c.status === 'Repair' || c.status === 'Pre-Job Sent' || c.status === 'Pre-Job Confirmed' ? 'done' : c.status === 'Rejected' ? 'rejected' : 'pending') as 'done' | 'pending' | 'rejected',
      detail: c.status === 'Rejected' ? c.rejection_reason : undefined,
    },
    {
      label: 'Pre-Job Sent',
      at: c.pre_job_sent_at,
      kind: (c.pre_job_sent_at ? 'done' : c.status === 'Repair' ? 'skipped' : 'pending') as 'done' | 'pending' | 'skipped',
    },
    {
      label: 'Pre-Job Confirmed',
      at: c.pre_job_confirmed_at,
      kind: (c.pre_job_confirmed_at ? 'done' : c.status === 'Repair' ? 'skipped' : 'pending') as 'done' | 'pending' | 'skipped',
      detail: c.job_number_assigned ? `Job number ${c.job_number_assigned} issued` : undefined,
    },
  ]
  return (
    <ol className="space-y-3">
      {steps.map((s, i) => {
        const Icon =
          s.kind === 'done'
            ? CheckCircle2
            : s.kind === 'rejected'
              ? XCircle
              : s.kind === 'skipped'
                ? Circle
                : AlertCircle
        const colour =
          s.kind === 'done'
            ? 'text-status-green'
            : s.kind === 'rejected'
              ? 'text-status-red'
              : s.kind === 'skipped'
                ? 'text-muted'
                : 'text-status-amber'
        return (
          <li key={i} className="flex items-start gap-3">
            <Icon size={20} className={colour} />
            <div className="flex-1">
              <div className="text-sm font-semibold text-body" style={s.kind === 'done' ? { color: statusHex } : undefined}>
                {s.label}
              </div>
              {s.at && <div className="text-xs text-muted">{dmy(s.at)} {hhmm(s.at)}</div>}
              {s.detail && <div className="text-xs text-muted">{s.detail}</div>}
            </div>
          </li>
        )
      })}
    </ol>
  )
}

function mm(thicknessM: number): string {
  return `${Math.round(thicknessM * 1000)} mm`
}

function titleCase(s: string): string {
  return s.charAt(0) + s.slice(1).toLowerCase()
}

function BodyOptionsPanel({ calculationId, mode }: { calculationId: number | null; mode: string }) {
  const [data, setData] = useState<BodyOptionsDisplay | null | undefined>(undefined)
  const [err, setErr] = useState(false)
  useEffect(() => {
    if (mode !== 'live' || calculationId == null) return
    let alive = true
    apiGet<{ body_options_display?: BodyOptionsDisplay | null }>(`/api/calculations/${calculationId}`)
      .then((r) => { if (alive) setData(r.body_options_display ?? null) })
      .catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [calculationId, mode])

  if (mode !== 'live' || calculationId == null || err || data === undefined) return null

  // v1.42 QCO — one checklist row per component (rear door / front / sides / roof /
  // floor / floor type) so each reads at a glance; replaces the compacted " · " line.
  // Row text stays byte-identical to the v1.42.0 format — the journey asserts on it.
  const CheckRow = ({ label, detail }: { label: string; detail: string }) => (
    <li className="flex items-start gap-2 animate-fadeIn">
      <CheckCircle2 size={15} className="mt-[3px] shrink-0 text-primary" />
      <span>
        <span className="font-semibold">{label}</span>
        {` — ${detail}`}
      </span>
    </li>
  )

  return (
    <div data-testid="body-options-panel" className="lg:border-l lg:border-line lg:pl-6">
      <div className="mb-2 flex items-center gap-1.5 text-[11px] font-bold uppercase tracking-wider text-primary">
        <Wrench size={13} strokeWidth={2.5} />
        Body options
      </div>
      {data === null ? (
        <p data-testid="body-options-not-recorded" className="flex items-start gap-2 text-xs text-muted">
          <Circle size={13} className="mt-0.5 shrink-0" />
          Body options not recorded on this costing.
        </p>
      ) : (
        <ul className="space-y-2 text-sm text-body">
          {data.rear_door && (
            <CheckRow
              label="Rear door"
              detail={`${data.rear_door.door_type} · ${data.rear_door.insulation} ${mm(data.rear_door.thickness_m)}`}
            />
          )}
          {data.panels.map((p) => (
            <CheckRow key={p.location} label={titleCase(p.location)} detail={`${p.insulation} ${mm(p.thickness_m)}`} />
          ))}
          {data.floor_type && <CheckRow label="Floor type" detail={data.floor_type} />}
        </ul>
      )}
    </div>
  )
}

// v1.39.1 backport (Item 5+7) — the REAL bill of materials, laid out to match the LEGACY costings Results
// page (Costing model/app/templates/results.html): grouped by category (first-seen order) with an uppercase
// category band, the full legacy column set (Material / SAP Code / Formula / Qty / Unit / Unit Price / Waste% /
// Line Cost), a dim per-category subtotal, and a single emphasised grand-total band. Fetches saved_result.items[]
// from GET /api/calculations/{id} keyed on calculation_id (LiveTimeline pattern), filters soft-excluded rows.
// Graceful fallback (not-live / no id / fetch error / no items → a soft message, never fake numbers).
interface BomRow {
  category?: string | null
  bom_id?: number
  material: string
  material_code?: string | null
  unit?: string | null
  formula?: string | null
  quantity?: number
  unit_price?: number
  waste_pct?: number | null
  line_cost?: number
  excluded?: boolean
}

// v1.42 — Body options panel: door type / insulation / floor type as selected on
// the quote, derived server-side (see body_options_display on GET
// /api/calculations/{id}). Read-only summary; scope is door+insulation+floor-type
// only — fittings/extras stay in the BOM table above.
interface BodyOptionsDisplay {
  rear_door: { door_type: string; insulation: string; thickness_m: number } | null
  panels: Array<{ location: string; insulation: string; thickness_m: number }>
  floor_type: string | null
}

interface SavedResult {
  items?: BomRow[]
  category_totals?: Record<string, number>
  grand_total?: number
  cost_per_sqm?: number
  profit_margin?: number
  profit_amount?: number
  ratio_label?: string
  ratio_amount?: number
  selling_price?: number
  discount_kind?: string
  discount_input?: number
  discount_amount?: number
  net_total?: number
}

function CostSummary({
  calculationId,
  mode,
  fallback,
}: {
  calculationId: number | null
  mode: string
  fallback: ReactNode
}) {
  const [sr, setSr] = useState<SavedResult | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    if (calculationId == null) return
    let alive = true
    apiGet<{ saved_result?: SavedResult }>(`/api/calculations/${calculationId}`)
      .then((r) => { if (alive) setSr(r.saved_result ?? null) })
      .catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [calculationId])

  if (mode !== 'live' || calculationId == null || err) return <>{fallback}</>
  if (!sr) return <p className="py-1 text-sm text-muted">Loading cost summary…</p>

  const disc = sr.discount_amount ?? 0
  const money = (v?: number) => zar(v ?? 0, { decimals: true })
  return (
    <dl className="space-y-2 text-sm">
      {sr.cost_per_sqm != null && <TotalRow label="Cost per m²" valueText={money(sr.cost_per_sqm)} muted />}
      <TotalRow label="Total manufacturing" valueText={money(sr.grand_total)} />
      {!!sr.profit_amount && (
        <TotalRow label={`Profit margin (${sr.profit_margin}%)`} valueText={`+ ${money(sr.profit_amount)}`} accentGreen />
      )}
      {!!sr.ratio_amount && (
        <TotalRow label={`Ratio (${sr.ratio_label})`} valueText={`+ ${money(sr.ratio_amount)}`} accentGreen />
      )}
      {sr.selling_price != null ? (
        <TotalRow label="Selling price" valueText={money(sr.selling_price)} highlight />
      ) : (
        <TotalRow label="Total manufacturing cost" valueText={money(sr.grand_total)} highlight />
      )}
      {disc > 0 && (
        <>
          <TotalRow
            label={`Discount${sr.discount_kind === 'percent' ? ` (${sr.discount_input}%)` : ''}`}
            valueText={`− ${money(disc)}`}
            accentGreen
          />
          <TotalRow label="Net total" valueText={money(sr.net_total)} highlight />
        </>
      )}
    </dl>
  )
}

function LiveBom({ calculationId, mode }: { calculationId: number | null; mode: string }) {
  const [rows, setRows] = useState<BomRow[] | null>(null)
  const [catTotals, setCatTotals] = useState<Record<string, number>>({})
  const [total, setTotal] = useState<number | null>(null)
  const [err, setErr] = useState(false)
  // v1.39.1 (Michael's :8006 pass) — per-category collapse. Empty Set = all OPEN (matches the
  // initial view he reviewed); a category key (g.cat) in the set hides that category's rows + subtotal.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set())
  const toggleCat = (cat: string) =>
    setCollapsed((s) => {
      const n = new Set(s)
      if (n.has(cat)) n.delete(cat)
      else n.add(cat)
      return n
    })
  useEffect(() => {
    if (calculationId == null) return
    let alive = true
    apiGet<{ saved_result?: SavedResult }>(`/api/calculations/${calculationId}`)
      .then((r) => {
        if (!alive) return
        const items = (r.saved_result?.items ?? []).filter((l) => !l.excluded)
        setRows(items)
        setCatTotals(r.saved_result?.category_totals ?? {})
        setTotal(r.saved_result?.grand_total ?? items.reduce((s, l) => s + (l.line_cost ?? 0), 0))
      })
      .catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [calculationId])

  if (mode !== 'live' || calculationId == null)
    return <p className="px-4 py-3 text-sm text-muted">The full bill of materials is available on live (saved) costings.</p>
  if (err) return <p className="px-4 py-3 text-sm text-muted">Bill of materials unavailable — couldn’t load the costing detail.</p>
  if (rows == null) return <p className="px-4 py-3 text-sm text-muted">Loading bill of materials…</p>
  if (rows.length === 0) return <p className="px-4 py-3 text-sm text-muted">No bill-of-materials lines recorded on this costing.</p>

  // Group by category preserving first-seen order (matches the legacy ns.current_cat break detection —
  // categories are contiguous runs in array order, never re-sorted).
  const groups: { cat: string; items: BomRow[] }[] = []
  const index = new Map<string, number>()
  for (const it of rows) {
    const cat = it.category ?? 'Uncategorised'
    let gi = index.get(cat)
    if (gi == null) { gi = groups.length; index.set(cat, gi); groups.push({ cat, items: [] }) }
    groups[gi].items.push(it)
  }
  const subtotalFor = (g: { cat: string; items: BomRow[] }) =>
    catTotals[g.cat] ?? g.items.reduce((s, l) => s + (l.line_cost ?? 0), 0)

  // v1.39.1 (Michael) — Collapse all / Expand all toggle (mirrors the legacy calculator's COLLAPSE ALL).
  const allCollapsed = groups.length > 0 && groups.every((g) => collapsed.has(g.cat))
  const setAll = (collapse: boolean) =>
    setCollapsed(collapse ? new Set(groups.map((g) => g.cat)) : new Set())

  return (
    <div className="overflow-x-auto">
      <div className="flex justify-end px-1 pb-2">
        <button
          onClick={() => setAll(!allCollapsed)}
          className="inline-flex items-center gap-1 rounded-md border border-line bg-white px-2.5 py-1 text-xs font-semibold text-primary hover:bg-primary-light"
        >
          {allCollapsed ? <ChevronDown size={13} /> : <ChevronRight size={13} />}
          {allCollapsed ? 'Expand all' : 'Collapse all'}
        </button>
      </div>
      <table className="w-full text-sm">
        <thead className="bg-primary text-left text-white">
          <tr>
            <th className="px-3 py-2 font-semibold">Category</th>
            <th className="px-3 py-2 font-semibold">Material</th>
            <th className="px-3 py-2 font-semibold">SAP Code</th>
            <th className="px-3 py-2 font-semibold">Formula</th>
            <th className="px-3 py-2 text-right font-semibold">Qty</th>
            <th className="px-3 py-2 font-semibold">Unit</th>
            <th className="px-3 py-2 text-right font-semibold">Unit Price</th>
            <th className="px-3 py-2 text-right font-semibold">Waste&nbsp;%</th>
            <th className="px-3 py-2 text-right font-semibold">Line Cost</th>
          </tr>
        </thead>
        <tbody>
          {groups.map((g) => (
            <Fragment key={g.cat}>
              {/* Category band — uppercase mono label; click to collapse/expand (results.html category header) */}
              <tr
                className="cursor-pointer select-none bg-surface-alt hover:bg-surface-alt/70"
                onClick={() => toggleCat(g.cat)}
              >
                <td
                  colSpan={collapsed.has(g.cat) ? 8 : 9}
                  className="px-3 py-2 font-mono text-[11px] font-semibold uppercase tracking-wider text-primary"
                >
                  <span className="inline-flex items-center gap-1.5">
                    {collapsed.has(g.cat) ? <ChevronRight size={13} /> : <ChevronDown size={13} />}
                    {g.cat}
                  </span>
                </td>
                {/* v1.39.1 (Michael) — a COLLAPSED category still shows its total on the band row. */}
                {collapsed.has(g.cat) && (
                  <td className="px-3 py-2 text-right text-xs font-semibold tabular-nums text-primary">
                    {zar(subtotalFor(g), { decimals: true })}
                  </td>
                )}
              </tr>
              {!collapsed.has(g.cat) && (
                <>
                  {g.items.map((l, i) => (
                    <tr key={`${l.bom_id ?? l.material_code ?? l.material}-${i}`} className="border-t border-line">
                      <td className="px-3 py-2" />
                      <td className="px-3 py-2 text-body">{l.material}</td>
                      <td className="px-3 py-2 font-mono text-xs text-muted">{l.material_code ?? '—'}</td>
                      <td className="px-3 py-2 font-mono text-xs text-muted">{l.formula ?? ''}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {(l.quantity ?? 0).toLocaleString('en-ZA', { minimumFractionDigits: 4, maximumFractionDigits: 4 })}
                      </td>
                      <td className="px-3 py-2 text-xs text-muted">{l.unit ?? ''}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{zar(l.unit_price ?? 0, { decimals: true })}</td>
                      <td className="px-3 py-2 text-right tabular-nums text-muted">{l.waste_pct ? `${l.waste_pct}%` : ''}</td>
                      <td className="px-3 py-2 text-right font-semibold tabular-nums">{zar(l.line_cost ?? 0, { decimals: true })}</td>
                    </tr>
                  ))}
                  {/* Per-category subtotal — dim right-aligned label + accent value */}
                  <tr className="border-t border-line bg-surface-alt/40">
                    <td colSpan={8} className="px-3 py-1.5 text-right text-xs text-muted">{g.cat} subtotal</td>
                    <td className="px-3 py-1.5 text-right text-xs font-semibold tabular-nums text-primary">{zar(subtotalFor(g), { decimals: true })}</td>
                  </tr>
                </>
              )}
            </Fragment>
          ))}
          {/* Grand total band */}
          <tr className="border-t-2 border-primary bg-primary/5">
            <td colSpan={8} className="px-3 py-2.5 text-sm font-bold uppercase text-body">Total manufacturing cost</td>
            <td className="px-3 py-2.5 text-right text-base font-bold tabular-nums text-primary">{zar(total ?? 0, { decimals: true })}</td>
          </tr>
        </tbody>
      </table>
    </div>
  )
}

// WO v4.19 — live lifecycle timeline from the production-job (derived from its
// timestamp columns server-side). Falls back to the derived StatusTimeline when
// there's no production_job (pre-accept) or the API is unreachable.
const TIMELINE_LABELS: Record<string, string> = {
  accepted: 'Accepted into production',
  pre_job_sent: 'Pre-Job Card sent',
  pre_job_signoff_sales: 'Sales sign-off',
  pre_job_signoff_production: 'Production sign-off',
  pre_job_confirmed: 'Pre-Job confirmed',
  planning_ack: 'Planning acknowledged',
  chassis_received: 'Chassis received',
}

// v1.39.3 — `refreshKey` refetches the timeline when the costing's lifecycle changes (accept /
// sign-off / confirm / chassis-received). Without it the Status-history card fetched once on mount
// and went stale after an on-page action — the parent's refresh() updates `c` but not this
// independent fetch (Michael: "Approve → bottom section stale, needs manual refresh").
function LiveTimeline({ pjId, refreshKey }: { pjId: number; refreshKey?: string }) {
  const [events, setEvents] = useState<{ event_type: string; occurred_at: string; actor: string | null }[] | null>(null)
  const [err, setErr] = useState(false)
  useEffect(() => {
    let alive = true
    apiGet<{ event_type: string; occurred_at: string; actor: string | null }[]>(`/api/production-jobs/${pjId}/timeline`)
      .then((e) => { if (alive) setEvents(e) })
      .catch(() => { if (alive) setErr(true) })
    return () => { alive = false }
  }, [pjId, refreshKey])

  if (err) return <p className="text-xs text-muted">Live timeline unavailable.</p>
  if (!events) return <p className="text-xs text-muted">Loading timeline…</p>
  if (events.length === 0) return <p className="text-xs text-muted">No lifecycle events recorded yet.</p>
  return (
    <ol className="space-y-3">
      {events.map((e, i) => (
        <li key={i} className="flex items-start gap-3">
          <CheckCircle2 size={20} className="text-status-green" />
          <div className="flex-1">
            <div className="text-sm font-semibold text-body">
              {TIMELINE_LABELS[e.event_type] ?? e.event_type.replace(/_/g, ' ')}
            </div>
            <div className="text-xs text-muted">
              {dmy(e.occurred_at)} {hhmm(e.occurred_at)}{e.actor ? ` · ${e.actor}` : ''}
            </div>
          </div>
        </li>
      ))}
    </ol>
  )
}

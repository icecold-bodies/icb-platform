// CockpitSlotDetail.tsx — Duplicated from PlanningBoard's private LiveSlotDetail for the additive
// Planning Cockpit. Identical content + behaviour; the ONLY difference is it renders inline inside the
// persistent right-hand inspector pane instead of inside a SidePanel overlay. KEEP IN SYNC with
// PlanningBoard.tsx; never edit the original (demo-frozen).
import { useState } from 'react'
import { CheckCircle2, Truck, AlertTriangle } from 'lucide-react'
import { StatusPill } from '../../../components/ui/primitives'
import { Spinner } from '../../../components/ui/feedback'
import { zar, dmy } from '../../../lib/format'
import { getChassisState, type PlanningSlot } from '../../../lib/types'
import { JobCardSections } from '../JobCardSections'
import { SlotStageClock } from './slotProgress'

export function CockpitSlotDetail({
  slot,
  canTick,
  canRevert,
  onMarkReceived,
  onRevert,
  onReject,
  onViewProduction,
  hideSections,
  clockLastUpdated,
}: {
  slot: PlanningSlot
  canTick: boolean
  canRevert: boolean
  onMarkReceived: () => void | Promise<void>
  onRevert: (reason: string) => void | Promise<void>
  onReject: (reason: string) => void | Promise<void>
  onViewProduction: () => void
  // 3 Jul — the standardized Plan drawer hides enrichment sections its own tabs already cover
  // (the planning BOM: the drawer's Bill of Materials tab shows the LIVE costing sheet instead).
  hideSections?: ReadonlyArray<'chassis' | 'bom' | 'bay'>
  // v1.40.6 thresholds WO — the board-fetch moment the stage clock ticks from (prop, not
  // context: the embedded drawer node mounts outside the cockpit's tree).
  clockLastUpdated?: Date | null
}) {
  const job = slot.job!
  const cs = getChassisState(job)
  const receivedAt = job.chassis_received_signal ?? job.chassis_received_at
  const receivedVia = job.chassis_received_source === 'vcl' ? 'via VCL'
    : job.chassis_received_source === 'legacy' ? 'legacy record' : null
  const [busy, setBusy] = useState(false)
  const [revertReason, setRevertReason] = useState('')
  const [revertBusy, setRevertBusy] = useState(false)
  async function tick() {
    setBusy(true)
    try { await onMarkReceived() } finally { setBusy(false) }
  }
  async function doRevert() {
    setRevertBusy(true)
    try { await onRevert(revertReason) } finally { setRevertBusy(false) }
  }
  // v1.49 — Reject. Two-step on purpose: unlike Re-plan this also declines the
  // costing, so the reason is mandatory and the button only arms once typed.
  const [rejectReason, setRejectReason] = useState('')
  const [rejectArmed, setRejectArmed] = useState(false)
  const [rejectBusy, setRejectBusy] = useState(false)
  async function doReject() {
    setRejectBusy(true)
    try { await onReject(rejectReason) } finally { setRejectBusy(false); setRejectArmed(false) }
  }
  return (
    <div className="space-y-3 text-sm">
      <div className="text-lg font-semibold text-body">{job.customer}</div>
      {job.body_type && <div className="text-muted">{job.body_type}</div>}
      <div className="flex items-center gap-2">
        <StatusPill status="GREEN" label={(job.status ?? 'scheduled').replace(/_/g, ' ')} />
      </div>
      <div className="grid grid-cols-2 gap-2 rounded-md bg-surface-alt p-3">
        <div><div className="text-xs text-muted">Slot</div>{slot.bay} · {slot.week_key}</div>
        <div><div className="text-xs text-muted">Selling</div>{job.selling_zar != null ? zar(job.selling_zar) : '—'}</div>
      </div>

      {/* v1.40.6 — elapsed-vs-threshold stage clock (renders only when the board served progress) */}
      <SlotStageClock progress={slot.progress} lastUpdated={clockLastUpdated ?? null} />

      <div className="rounded-md border border-line p-3">
        {cs === 'received' ? (
          <div className="flex items-center gap-2 text-status-green">
            <CheckCircle2 size={18} />
            <span className="font-semibold">
              Chassis received{receivedAt ? ` ${dmy(receivedAt)}` : ''}{receivedVia ? ` · ${receivedVia}` : ''}
            </span>
          </div>
        ) : (
          <div className="space-y-2">
            <div className="flex items-center gap-2 text-status-amber">
              {cs === 'eta_committed' ? <Truck size={18} /> : <AlertTriangle size={18} />}
              <span className="font-semibold">
                {cs === 'eta_committed'
                  ? `Chassis ETA ${job.chassis_eta ? dmy(job.chassis_eta) : ''} — not yet received (Path B)`
                  : 'No chassis ETA committed yet'}
              </span>
            </div>
            {canTick ? (
              <button
                onClick={tick}
                disabled={busy}
                className="flex w-full items-center justify-center gap-2 rounded-md bg-primary py-2 font-semibold text-white hover:bg-primary-dark disabled:opacity-60"
              >
                {busy ? <Spinner size={14} /> : <CheckCircle2 size={14} />} Mark chassis received
              </button>
            ) : (
              <div className="text-xs text-muted">Only the Production role can mark a chassis received.</div>
            )}
          </div>
        )}
      </div>

      {canRevert && (
        <div className="space-y-2 rounded-md border border-line p-3" data-testid="cockpit-revert-section">
          <div className="text-xs font-semibold uppercase text-muted">Re-plan</div>
          <textarea
            value={revertReason}
            onChange={(e) => setRevertReason(e.target.value.slice(0, 500))}
            maxLength={500}
            rows={2}
            placeholder="Why move this back? (optional)"
            className="w-full rounded-md border border-line bg-surface p-2 text-sm"
          />
          <button
            onClick={doRevert}
            disabled={revertBusy}
            title="Move this job off the board, back to the Unscheduled pool (chassis + sign-offs kept)"
            className="flex w-full items-center justify-center gap-2 rounded-md border border-status-amber py-2 font-semibold text-status-amber hover:bg-status-amber/10 disabled:opacity-60"
          >
            {revertBusy ? <Spinner size={14} /> : <span aria-hidden>↩</span>} Move back to Unscheduled
          </button>
        </div>
      )}

      {/* v1.49 — Reject. The sanctioned, and only, way out of scheduled work: a
          costing with a live production job cannot be deleted from the costings
          board, deliberately. Sits below Re-plan as its stronger sibling — revert
          keeps the job as work ICB still intends to do, this says it is not
          happening. */}
      {canRevert && (
        <div className="space-y-2 rounded-md border border-status-red/40 p-3" data-testid="cockpit-reject-section">
          <div className="text-xs font-semibold uppercase text-status-red">Reject</div>
          <p className="text-[11px] text-muted">
            Drops this job from the board and marks its costing <strong>Rejected</strong>.
            The costing can then be deleted. Nothing on the floor is erased.
          </p>
          <textarea
            value={rejectReason}
            onChange={(e) => setRejectReason(e.target.value.slice(0, 500))}
            maxLength={500}
            rows={2}
            placeholder="Why is this job not happening? (required)"
            data-testid="cockpit-reject-reason"
            className="w-full rounded-md border border-line bg-surface p-2 text-sm"
          />
          {!rejectArmed ? (
            <button
              onClick={() => setRejectArmed(true)}
              disabled={!rejectReason.trim()}
              data-testid="cockpit-reject-job"
              title={rejectReason.trim()
                ? 'Reject this job — its costing becomes Rejected'
                : 'A reason is required before a job can be rejected'}
              className="flex w-full items-center justify-center gap-2 rounded-md border border-status-red py-2 font-semibold text-status-red hover:bg-status-red/10 disabled:opacity-50"
            >
              <span aria-hidden>✕</span> Reject job
            </button>
          ) : (
            <div className="flex gap-2">
              <button onClick={() => setRejectArmed(false)} disabled={rejectBusy}
                      data-testid="cockpit-reject-cancel"
                      className="flex-1 rounded-md border border-line py-2 text-sm font-semibold text-body hover:bg-surface-alt">
                Cancel
              </button>
              <button onClick={doReject} disabled={rejectBusy}
                      data-testid="cockpit-reject-confirm"
                      className="flex flex-1 items-center justify-center gap-2 rounded-md bg-status-red py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60">
                {rejectBusy ? <Spinner size={14} /> : null} Confirm reject
              </button>
            </div>
          )}
        </div>
      )}

      {/* WO v4.31 §3.2 — job-card enrichment: chassis (latest VCL) + BOM lines + bay context. Read-only. */}
      <JobCardSections jobId={job.id} hide={hideSections} />

      <button onClick={onViewProduction}
        title="Open the Production Dashboard focused on this job"
        className="w-full rounded-md bg-primary py-2 font-semibold text-white hover:bg-primary-dark"
        data-testid="cockpit-view-in-production">View in Production</button>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { ThumbsDown, X } from 'lucide-react'
import { Modal } from '../../components/ui/overlays'
import { Spinner } from '../../components/ui/feedback'
import { zar, dmy } from '../../lib/format'
import { StatusPillCosting } from './statusPalette'
import type { Costing } from '../../data/costingsData'

/**
 * Decline a Pending costing from the dashboard (Michael, 3 Jul — the legacy dashboard's ✗
 * "Decline this calculation" restored on the MES surface). Mirrors AcceptModal; the reason is
 * REQUIRED (the legacy results page rule: min 5 characters — the backend 400s on empty) and is
 * stored on the record (decline_reason) + shown in the Rejected pill's history on /results.
 */
export function DeclineModal({
  costing,
  onClose,
  onConfirm,
}: {
  costing: Costing | null
  onClose: () => void
  onConfirm: (c: Costing, reason: string) => void | Promise<void>
}) {
  const [busy, setBusy] = useState(false)
  const [reason, setReason] = useState('')
  useEffect(() => { setBusy(false); setReason('') }, [costing])
  const valid = reason.trim().length >= 5
  return (
    <Modal open={!!costing} onClose={onClose} className="max-w-lg">
      {costing && (
        <div data-testid="decline-modal">
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-status-red/15 text-status-red">
              <ThumbsDown size={20} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-body">Decline this costing</h3>
              <p className="text-xs text-muted">Moves the costing from Pending to Declined (the red Rejected pill).</p>
            </div>
          </div>

          <div className="mb-3 rounded-md border border-line bg-surface-alt p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono font-semibold">{costing.quote_number}</span>
              <StatusPillCosting status={costing.status} />
            </div>
            <div className="mt-1 text-body">{costing.customer_name}</div>
            <div className="text-xs text-muted">{costing.body_type} · Created {dmy(costing.created_at)}</div>
            <div className="mt-2 border-t border-line pt-2 text-sm">
              Quote total: <span className="font-semibold tabular-nums">{zar(costing.selling_zar)}</span>
            </div>
          </div>

          <label className="mb-4 block text-sm">
            <span className="font-semibold text-body">Why is this costing being declined? <span className="text-status-red">*</span></span>
            <textarea
              data-testid="decline-reason"
              autoFocus rows={3} value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="min 5 characters — recorded on the costing and shown on the summary page"
              className="mt-1 w-full rounded-md border border-line px-2 py-1.5 text-sm"
            />
          </label>

          <div className="flex justify-end gap-2">
            <button onClick={onClose} disabled={busy} className="rounded-md border border-line px-4 py-2 text-sm disabled:opacity-50">Cancel</button>
            <button
              data-testid="decline-confirm"
              onClick={async () => { setBusy(true); await onConfirm(costing, reason.trim()) }}
              disabled={busy || !valid}
              className="flex items-center gap-1 rounded-md bg-status-red px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-60"
            >
              {busy ? <Spinner size={14} /> : <X size={14} />} {busy ? 'Declining…' : 'Decline costing'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

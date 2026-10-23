import { useEffect, useState } from 'react'
import { Check, ThumbsUp } from 'lucide-react'
import { Modal } from '../../components/ui/overlays'
import { Spinner } from '../../components/ui/feedback'
import { zar, dmy } from '../../lib/format'
import { StatusPillCosting } from './statusPalette'
import type { Costing } from '../../data/costingsData'
import { staffLabel } from '../../lib/revisions'

/**
 * Move a Pending costing to Accepted from the dashboard, without re-opening
 * the wizard. Work Order v4 §5.1.
 */
export function AcceptModal({
  costing,
  onClose,
  onConfirm,
}: {
  costing: Costing | null
  onClose: () => void
  onConfirm: (c: Costing) => void | Promise<void>
}) {
  // Spans both legs of the accept chicken-and-egg (legacy /accept → from-calculation).
  const [busy, setBusy] = useState(false)
  useEffect(() => setBusy(false), [costing])
  // RT10 — a revision that is not the latest live one of its quote (the server's is_latest)
  const older = !!costing && costing.is_latest === false && costing.latest_rev != null
  const rev = costing ? (costing.rev ?? Math.max((costing.version ?? 1) - 1, 0)) : 0
  return (
    <Modal open={!!costing} onClose={onClose} className="max-w-lg">
      {costing && (
        <div>
          <div className="mb-3 flex items-center gap-2">
            <div className="flex h-10 w-10 items-center justify-center rounded-full bg-[#2563EB]/15 text-[#2563EB]">
              <ThumbsUp size={20} />
            </div>
            <div>
              <h3 className="text-lg font-bold text-body">Confirm customer acceptance</h3>
              <p className="text-xs text-muted">Step 2 — moves the costing from Pending to Accepted.</p>
            </div>
          </div>

          <div className="mb-3 rounded-md border border-line bg-surface-alt p-3 text-sm">
            <div className="flex items-center justify-between">
              <span className="font-mono font-semibold">{staffLabel(costing.quote_number, costing.version, costing.rev)}</span>
              <StatusPillCosting status={costing.status} />
            </div>
            <div className="mt-1 text-body">{costing.customer_name}</div>
            <div className="text-xs text-muted">{costing.body_type} · Created {dmy(costing.created_at)}</div>
            <div className="mt-2 border-t border-line pt-2 text-sm">
              Quote total: <span className="font-semibold tabular-nums">{zar(costing.selling_zar)}</span>
            </div>
          </div>

          <p className="mb-4 text-sm text-body">
            Confirm that customer <strong>{costing.customer_name}</strong> has accepted quote
            {' '}<strong className="font-mono">{staffLabel(costing.quote_number, costing.version, costing.rev)}</strong>. This unlocks the
            Pre-Job Card button on this row.
          </p>
          {/* RT10 (RULING_1, G1) — Accept on a revision that is NOT the latest live one asks first, in one plain line;
              the button names the REV that will be accepted. (Decline does not ask.) */}
          {older && (
            <p data-testid="accept-older-line" className="mb-4 rounded-md border border-status-amber/40 bg-status-amber/10 px-3 py-2 text-sm text-body">
              This is REV {rev}. REV {costing.latest_rev} is the latest. Accept REV {rev} anyway?
            </p>
          )}

          <div className="flex justify-end gap-2">
            <button onClick={onClose} disabled={busy} className="rounded-md border border-line px-4 py-2 text-sm disabled:opacity-50">Cancel</button>
            <button
              onClick={async () => { setBusy(true); await onConfirm(costing) }}
              disabled={busy}
              className="flex items-center gap-1 rounded-md bg-[#2563EB] px-4 py-2 text-sm font-semibold text-white hover:opacity-90 disabled:opacity-70"
            >
              {busy ? <Spinner size={14} /> : <Check size={14} />} {busy ? 'Accepting…' : older ? `Accept REV ${rev}` : 'Confirm acceptance'}
            </button>
          </div>
        </div>
      )}
    </Modal>
  )
}

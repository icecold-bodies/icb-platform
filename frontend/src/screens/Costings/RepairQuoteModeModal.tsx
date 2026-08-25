/**
 * "How much of the costing should the customer see?" (v1.51)
 *
 * Lezette test-drove R-2001/R-2002 against the old system's quote and the gap
 * was not the numbers — it was that the MES document prints the full costing
 * breakdown where the old one prints the WORK, with the money stated once in
 * the totals block. Rather than pick a winner, the choice is made at download
 * time, because all three documents are real: a summary for the customer who
 * wants a price, the old system's shape for everyone else, and the itemized
 * one for the customer who asks what each part costs.
 *
 * The chosen mode is stored on the quote by the download endpoint, so the next
 * download — from here, the calculator or the results page — reproduces the
 * document the customer already has.
 */
export type RepairQuoteMode = 'summary' | 'breakdown' | 'itemized'

export const REPAIR_QUOTE_MODES: {
  value: RepairQuoteMode
  label: string
  note: string
}[] = [
  { value: 'summary', label: 'Summary', note: 'One line per repair section. No item detail.' },
  {
    value: 'breakdown',
    label: 'Breakdown  (recommended)',
    note: 'Every line described, no prices per line. Matches the old system.',
  },
  { value: 'itemized', label: 'Itemized', note: 'Quantity, unit price and line total on every line.' },
]

export function RepairQuoteModeModal({
  open,
  selected,
  onPick,
  onClose,
}: {
  open: boolean
  selected: RepairQuoteMode
  onPick: (mode: RepairQuoteMode) => void
  onClose: () => void
}) {
  if (!open) return null
  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
      data-testid="repair-quote-mode-modal"
    >
      <div
        className="w-full max-w-md rounded-lg bg-white p-5 shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <h3 className="text-base font-bold text-body">Repair quotation</h3>
        <p className="mt-1 text-sm text-muted">
          How much of the costing should the customer see?
        </p>
        <div className="mt-4 flex flex-col gap-2">
          {REPAIR_QUOTE_MODES.map((m) => (
            <button
              key={m.value}
              type="button"
              data-testid={`repair-quote-mode-${m.value}`}
              onClick={() => onPick(m.value)}
              className={`rounded-md border px-3 py-2 text-left hover:bg-primary-light/40 ${
                m.value === selected ? 'border-primary bg-primary-light/30' : 'border-line bg-white'
              }`}
            >
              <span className="block text-sm font-semibold text-body">{m.label}</span>
              <span className="block text-xs text-muted">{m.note}</span>
            </button>
          ))}
        </div>
        <div className="mt-4 flex justify-end">
          <button
            type="button"
            onClick={onClose}
            className="rounded-md border border-line px-3 py-2 text-sm font-semibold text-body hover:bg-surface-alt"
          >
            Cancel
          </button>
        </div>
      </div>
    </div>
  )
}

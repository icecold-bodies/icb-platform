import { useEffect, useState } from 'react'
import { FileDown, FileSpreadsheet, FileText, AlertCircle } from 'lucide-react'
import { Modal } from '../../components/ui/overlays'

/**
 * v1.44 R3 — the ONE export-options dialog for both entry points: the live
 * calculator embed ("Preview") and the approved costing ("Export").
 *
 * Choices: format (Excel / Word / PDF), detail (categories+totals — the
 * default — or categories, totals + line items), and any set of ratios from
 * the calculator's dropdown list (default = the ratio currently selected on
 * the page / saved on the record). Each ticked ratio becomes its own
 * "TOTAL COST @ {r}" line in the document — totals never combine two ratios.
 */
export type ExportFormat = 'excel' | 'word' | 'pdf'
export type ExportDetail = 'totals' | 'items'
export interface RatioOpt { value: number; label: string }
export interface ExportSelection {
  format: ExportFormat
  detail: ExportDetail
  ratios: number[]
}

// Fallback ONLY — normally the ratio list arrives from the calculator page's
// #f-ratio select (embed) which is parity-locked against the backend's
// canonical services.document_context.RATIO_OPTIONS by test_preview_formats.py.
export const FALLBACK_RATIOS: RatioOpt[] = [
  { value: 0.3, label: '30%' }, { value: 0.325, label: '32.5%' },
  { value: 0.35, label: '35%' }, { value: 0.375, label: '37.5%' },
  { value: 0.4, label: '40%' }, { value: 0.425, label: '42.5%' },
  { value: 0.45, label: '45%' }, { value: 0.475, label: '47.5%' },
  { value: 0.5, label: '50%' }, { value: 0.525, label: '52.5%' },
  { value: 0.55, label: '55%' }, { value: 0.575, label: '57.5%' },
  { value: 0.6, label: '60%' }, { value: 0.625, label: '62.5%' },
  { value: 0.65, label: '65%' }, { value: 0.675, label: '67.5%' },
  { value: 0.7, label: '70%' },
]

const FORMATS: { key: ExportFormat; label: string; icon: typeof FileText }[] = [
  { key: 'excel', label: 'Excel', icon: FileSpreadsheet },
  { key: 'word', label: 'Word', icon: FileText },
  { key: 'pdf', label: 'PDF', icon: FileDown },
]

export function ExportOptionsModal({
  open,
  verb,
  ratioOptions,
  defaultRatio,
  disabledNote,
  initialFormat,
  onClose,
  onConfirm,
}: {
  open: boolean
  /** "Preview" on the live calculator embed; "Export" on approved costings. */
  verb: 'Preview' | 'Export'
  ratioOptions: RatioOpt[]
  /** The ratio currently selected on the page / saved on the record. */
  defaultRatio: number | null
  /** When set, the confirm button is disabled and this note shows (e.g. "Calculate first"). */
  disabledNote?: string
  initialFormat?: ExportFormat
  onClose: () => void
  onConfirm: (sel: ExportSelection) => void
}) {
  const [format, setFormat] = useState<ExportFormat>(initialFormat ?? 'excel')
  const [detail, setDetail] = useState<ExportDetail>('totals')
  const [ticked, setTicked] = useState<Set<number>>(new Set())

  // Re-arm defaults each time the dialog opens (R3b: default = page's ratio).
  useEffect(() => {
    if (!open) return
    setFormat(initialFormat ?? 'excel')
    setDetail('totals')
    setTicked(new Set(defaultRatio != null ? [defaultRatio] : []))
  }, [open, defaultRatio, initialFormat])

  const toggle = (v: number) =>
    setTicked((s) => {
      const n = new Set(s)
      if (n.has(v)) n.delete(v)
      else n.add(v)
      return n
    })

  const opts = ratioOptions.length ? ratioOptions : FALLBACK_RATIOS

  return (
    <Modal open={open} onClose={onClose} className="max-w-md">
      <h3 className="mb-1 text-lg font-bold text-body">{verb} costing document</h3>
      <p className="mb-4 text-xs text-muted">
        Pick a format and what to include. Each ticked ratio gets its own
        “TOTAL COST @ ratio” line — totals are never combined across ratios.
      </p>

      <div className="mb-4">
        <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">Format</div>
        <div className="flex gap-2">
          {FORMATS.map(({ key, label, icon: Icon }) => (
            <button
              key={key}
              data-testid={`export-fmt-${key}`}
              onClick={() => setFormat(key)}
              className={`flex flex-1 items-center justify-center gap-1.5 rounded-md border px-3 py-2 text-sm font-semibold ${
                format === key
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-line bg-white text-body hover:bg-surface-alt'
              }`}
            >
              <Icon size={15} /> {label}
            </button>
          ))}
        </div>
      </div>

      <div className="mb-4">
        <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">Detail</div>
        <label className="mb-1 flex cursor-pointer items-center gap-2 text-sm text-body">
          <input type="radio" name="export-detail" checked={detail === 'totals'}
                 onChange={() => setDetail('totals')} />
          Categories + totals
        </label>
        <label className="flex cursor-pointer items-center gap-2 text-sm text-body">
          <input type="radio" name="export-detail" data-testid="export-detail-items"
                 checked={detail === 'items'} onChange={() => setDetail('items')} />
          Categories, totals + line items
        </label>
      </div>

      <div className="mb-4">
        <div className="mb-1.5 text-[11px] font-bold uppercase tracking-wider text-muted">
          Ratios <span className="normal-case font-normal">(one TOTAL COST line each)</span>
        </div>
        <div className="grid max-h-40 grid-cols-4 gap-x-2 gap-y-1 overflow-y-auto rounded-md border border-line bg-surface-alt p-2">
          {opts.map((r) => (
            <label key={r.value} className="flex cursor-pointer items-center gap-1.5 text-sm tabular-nums text-body">
              <input
                type="checkbox"
                data-testid={`export-ratio-${r.label}`}
                checked={ticked.has(r.value)}
                onChange={() => toggle(r.value)}
              />
              {r.label}
            </label>
          ))}
        </div>
        {ticked.size === 0 && (
          <p className="mt-1 text-[11px] text-muted">
            No ratio ticked — the document totals stop at materials + margin.
          </p>
        )}
      </div>

      {disabledNote && (
        <p className="mb-3 flex items-start gap-1.5 rounded-md border border-status-amber/40 bg-status-amber/5 p-2 text-xs text-status-amber">
          <AlertCircle size={13} className="mt-0.5 shrink-0" /> {disabledNote}
        </p>
      )}

      <div className="flex justify-end gap-2">
        <button onClick={onClose} className="rounded-md border border-line px-4 py-2 text-sm">Cancel</button>
        <button
          data-testid="export-confirm"
          disabled={!!disabledNote}
          onClick={() => onConfirm({ format, detail, ratios: [...ticked].sort((a, b) => a - b) })}
          className="rounded-md bg-primary px-4 py-2 text-sm font-semibold text-white hover:bg-primary-dark disabled:cursor-not-allowed disabled:opacity-50"
        >
          {verb}
        </button>
      </div>
    </Modal>
  )
}

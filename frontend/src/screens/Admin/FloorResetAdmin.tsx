// v1.41.0 §9 P1 — admin-only Production Flow floor reset (M5, admin.floor-reset).
// The old demo "↺ Reset" cleared the SHARED floor from /plan for everyone; it died with
// the header strip. This is its deliberate replacement: permission-tagged, typed-confirm,
// journaled as a floor_events 'floor_reset' row. DB/chassis state is untouched by design.
import { useEffect, useState } from 'react'
import { AlertTriangle, RotateCcw } from 'lucide-react'

import { apiGet, apiPost } from '../../lib/api'
import { useToast } from '../../components/ui/toast'

const PHRASE = 'RESET'

export function FloorResetAdmin() {
  const toast = useToast()
  const [typed, setTyped] = useState('')
  const [busy, setBusy] = useState(false)
  const [info, setInfo] = useState<{ version: number; updated_at: string | null } | null>(null)

  const refresh = () =>
    apiGet<{ version: number; updated_at: string | null }>('/api/plan/floor-state')
      .then((r) => setInfo({ version: r.version ?? 0, updated_at: r.updated_at }))
      .catch(() => setInfo(null))
  useEffect(() => { void refresh() }, [])

  const doReset = async () => {
    setBusy(true)
    try {
      const r = await apiPost<{ version: number }>('/api/plan/floor-reset', { confirm: true })
      toast.push({ kind: 'ok', message: `Floor reset — journaled as write #${r.version}.` })
      setTyped('')
      void refresh()
    } catch (e) {
      toast.push({ kind: 'error', message: e instanceof Error ? e.message : 'Reset failed' })
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="max-w-xl" data-testid="floor-reset-admin">
      <h2 className="mb-1 text-lg font-semibold text-body">Floor reset</h2>
      <p className="mb-4 text-sm text-muted">
        Clears the shared Production Flow floor on <span className="font-mono">/plan</span> —
        Panels Ready, bay tracks, merge blocks and the QC strip — for <b>every</b> planner.
        Scheduled V/P slots, chassis records and QC inspections are not touched. The action is
        journaled (who + when) in the floor event log.
      </p>
      <div className="rounded-lg border border-status-red/40 bg-status-red/5 p-4">
        <div className="mb-2 flex items-center gap-2 text-status-red">
          <AlertTriangle size={16} />
          <span className="text-sm font-bold uppercase tracking-wide">Danger — shared state</span>
        </div>
        <p className="mb-3 text-sm text-body">
          Type <span className="rounded bg-surface-alt px-1 font-mono font-bold">{PHRASE}</span> to
          enable the button.
        </p>
        <div className="flex items-center gap-2">
          <input
            value={typed}
            onChange={(e) => setTyped(e.target.value)}
            placeholder={PHRASE}
            data-testid="floor-reset-confirm-input"
            className="w-36 rounded border border-line px-2 py-1.5 font-mono text-sm"
          />
          <button
            onClick={doReset}
            disabled={typed !== PHRASE || busy}
            data-testid="floor-reset-button"
            className="flex items-center gap-1.5 rounded-md bg-status-red px-3 py-1.5 text-sm font-semibold text-white disabled:cursor-not-allowed disabled:opacity-40"
          >
            <RotateCcw size={14} /> {busy ? 'Resetting…' : 'Reset the floor'}
          </button>
        </div>
        {info && (
          <p className="mt-3 text-xs text-muted">
            Floor document: write #{info.version}
            {info.updated_at ? ` · last change ${new Date(info.updated_at).toLocaleString()}` : ''}
          </p>
        )}
      </div>
    </div>
  )
}

/** WO v4.34 §3.7 — the chassis-type DDM dropdown, shared by the Pre-Job Card modal, the Planning
 * ack panel, and Chassis +New/edit. ONE controlled vocabulary (replaces free-text + the old
 * hardcoded frontend list) so chassis_records.make + token substitution stay consistent. Stores the
 * human display string ("Isuzu FTR 850 AMT (MY22)") — not the code — so it reads cleanly in every
 * consumer. An off-list current value (legacy free-text) is preserved as a selectable option, so
 * editing an existing record never silently drops a value the DDM doesn't yet contain.
 *
 * Admin right-click (Michael, 3 Jul): the dropdown offers "Add…" / "Edit…" jumping straight to the
 * /admin/chassis-models CRUD (new tab — the form being edited keeps its state). The list refetches
 * on window focus, so a type added over there appears here on return without a reload. */
import { useCallback, useEffect, useState } from 'react'

import { apiGet } from '../../lib/api'
import { useRefetchOnFocus } from '../../lib/useRefetchOnFocus'
import { useAppData } from '../../store/AppDataContext'
import type { ChassisModel } from './types'

let _cache: ChassisModel[] | null = null     // module-level — shared across all mounted dropdowns

export function useChassisModels(): ChassisModel[] {
  const [models, setModels] = useState<ChassisModel[]>(_cache ?? [])
  const load = useCallback(() => {
    apiGet<ChassisModel[]>('/api/chassis-records/models')
      .then((r) => { _cache = r; setModels(r) })
      .catch(() => { /* dropdown falls back to the preserved current value only */ })
  }, [])
  useEffect(() => { if (!_cache) load(); else setModels(_cache) }, [load])
  useRefetchOnFocus(load)   // pick up admin adds/edits made in another tab
  return models
}

export function chassisModelLabel(m: ChassisModel): string {
  return `${m.make} ${m.model}`.trim()
}

const ADMIN_PAGE = '/mes-app/admin/chassis-models'

export function ChassisModelSelect({
  value, onChange, disabled, testid,
}: {
  value: string | null | undefined
  onChange: (v: string) => void
  disabled?: boolean
  testid?: string
}) {
  const models = useChassisModels()
  const { isAdmin } = useAppData()
  const [menu, setMenu] = useState<{ x: number; y: number } | null>(null)
  const labels = models.map(chassisModelLabel)
  const cur = (value ?? '').trim()
  const offList = cur && !labels.includes(cur)      // legacy free-text not in the DDM — keep it selectable

  return (
    <>
      <select
        data-testid={testid}
        value={cur}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        onContextMenu={(e) => {
          if (!isAdmin) return                      // the admin page is require_admin — don't lead others there
          e.preventDefault()
          setMenu({ x: e.clientX, y: e.clientY })
        }}
        className="mt-1 w-full rounded-md border border-line bg-white px-2 py-1.5 text-sm text-body disabled:bg-surface-alt"
      >
        <option value="">— select chassis type —</option>
        {offList && <option value={cur}>{cur} (current)</option>}
        {models.map((m) => (
          <option key={m.code} value={chassisModelLabel(m)}>{chassisModelLabel(m)}</option>
        ))}
      </select>
      {menu && (
        <>
          <div className="fixed inset-0 z-[70]" data-testid="chassis-model-ctx-scrim"
               onClick={() => setMenu(null)} onContextMenu={(e) => { e.preventDefault(); setMenu(null) }} />
          <div data-testid="chassis-model-ctx" className="fixed z-[71] w-52 rounded-md border border-line bg-white py-1 shadow-xl"
               style={{ left: Math.min(menu.x, window.innerWidth - 220), top: Math.min(menu.y, window.innerHeight - 90) }}>
            <button data-testid="chassis-model-ctx-add"
                    className="block w-full px-3 py-1.5 text-left text-sm text-body hover:bg-surface-alt"
                    onClick={() => { setMenu(null); window.open(`${ADMIN_PAGE}?new=1`, '_blank') }}>
              ＋ Add chassis type…
            </button>
            <button data-testid="chassis-model-ctx-edit"
                    className="block w-full px-3 py-1.5 text-left text-sm text-body hover:bg-surface-alt"
                    onClick={() => { setMenu(null); window.open(ADMIN_PAGE, '_blank') }}>
              ✎ Edit chassis types…
            </button>
          </div>
        </>
      )}
    </>
  )
}

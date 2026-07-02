// WO A09 — Combined Cockpit (Rapid Prototype Phase).
// One integrated page (handover §2, top → bottom): the A06 Production Flow
// dashboard (header + 6 KPIs) → the LIVE MES Planning Cockpit (week × slot
// grid, Unscheduled rail, Inspector, filters, week nav, summary — the existing
// component, embedded, dock hidden) → Panels ready → Pre-Assembly → Merge →
// Parking. Single component tree, no iframe; the planner mounts into the A06
// shell via a React portal so the §2 stacking order lives in one column.
//
// Wiring (§3/§4): the Job is the spine. "Panels ready" is DERIVED from the
// same live PlanningContext board the cockpit mutates — scheduling a job onto
// a V-x/P-x slot books its cut on that machine; the panel-set surfaces here
// and vanishes on unschedule. Readiness: the MES has no Vacuum/Press
// cut-complete event yet, so per the companion Pre-Assembly handover's
// RATIFIED D2, `ready` uses the scheduled-readiness proxy with this mapping
// as the single hook for the future panels_cut signal (documented deviation
// from §4.4 until that event exists). §4.3 guards live in the engine: a
// started job's body is never yanked and its panel never resurrects.
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import './productionFlow.css'
import { initProductionFlow } from './productionFlowEngine'
import { usePlanning } from '../../store/PlanningContext'
import { PlanningCockpit } from '../Planning/cockpit/PlanningCockpit'
import type { PlanningBoardView } from '../../lib/types'

interface FlowApi {
  cleanup: () => void
  setPanels: (list: unknown[]) => void
  plannerSlot: HTMLElement | null
}

// Board → PanelSet contract (§4.1). Method/origin from the slot machine
// (V-x → Vacuum, P-x → Press); length parsed from the body-type text (the
// planning job carries no numeric length), fallback 5.4 m.
function boardToPanels(board: PlanningBoardView) {
  const seen = new Set<number>()
  const panels: unknown[] = []
  for (const s of board.slots) {
    const j = s.job
    if (!j || seen.has(j.id)) continue
    const bay = s.bay || ''
    const isV = bay.startsWith('V-'), isP = bay.startsWith('P-')
    if (!isV && !isP) continue
    seen.add(j.id)
    const bt = j.body_type || ''
    const m = bt.match(/(\d+(?:[.,]\d+)?)\s*m\b/i)
    const len = m ? parseFloat(m[1].replace(',', '.')) : 5.4
    // Fallback '' when the job carries no body_type (the card template appends "body" itself).
    const type = bt.replace(/(\d+(?:[.,]\d+)?)\s*m\b/i, '').trim().replace(/^[-·,\s]+/, '')
    panels.push({
      id: 'PS-' + j.job_number,
      job: j.job_number,
      cust: j.customer,
      len: Number.isFinite(len) && len > 0 ? len : 5.4,
      type,
      method: isV ? 'Vacuum' : 'Press',
      origin: bay,
      ready: true,   // D2 readiness proxy (scheduled) — future: the real panels_cut signal
    })
  }
  return panels
}

export function PlanCombined() {
  const ref = useRef<HTMLDivElement>(null)
  const [api, setApi] = useState<FlowApi | null>(null)
  const { board, mode } = usePlanning()

  useEffect(() => {
    if (!ref.current) return
    const inst = initProductionFlow(ref.current) as FlowApi
    setApi(inst)
    return () => { inst.cleanup(); setApi(null) }
  }, [])

  // Live link: every board change (schedule / move / unschedule / window nav /
  // focus refetch) re-derives the Panels-ready set. In mock/offline mode the
  // floor keeps its seed and the cockpit shows its own offline notice.
  useEffect(() => {
    if (!api || mode !== 'live') return
    api.setPanels(boardToPanels(board))
  }, [api, board, mode])

  return (
    <>
      <div ref={ref} className="a06-flow" data-testid="plan-combined" />
      {api?.plannerSlot &&
        createPortal(
          <div className="zone" style={{ overflow: 'hidden' }} data-testid="plan-embedded-cockpit">
            <div style={{ height: '76vh' }}>
              <PlanningCockpit embedded />
            </div>
          </div>,
          api.plannerSlot,
        )}
    </>
  )
}

// WO A06 — Production Flow prototype (Rapid Prototype Phase).
// NATIVE in-page implementation of the approved mockup ("A06 - Production Flow
// v0.3 (job detail).html"): the mockup's own CSS (productionFlow.css, scoped
// under .a06-flow) + engine (productionFlowEngine.ts, ported verbatim) run
// against a plain mount node. Pixel/behaviour fidelity is inherited from the
// mockup's source; isolation from the rest of the MES is total (own module,
// own scoped styles, no shared state, static seed data per spec Appendix A).
// Live-data binding (spec §10) is the next phase.
import { useEffect, useRef } from 'react'
import './productionFlow.css'
import { initProductionFlow } from './productionFlowEngine'

export function PlanProductionFlow() {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!ref.current) return
    return initProductionFlow(ref.current)
  }, [])

  return <div ref={ref} className="a06-flow" data-testid="plan-production-flow" />
}

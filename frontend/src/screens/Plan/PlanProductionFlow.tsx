// WO A06 — Production Flow prototype (Rapid Prototype Phase).
// The BA's A06 spec is the source of truth; the approved HTML mockup
// (`A06 - Production Flow v0.3 (job detail).html`) is served verbatim as a
// static asset and embedded here full-bleed under the new "Plan" menu. This
// keeps the prototype pixel-identical to the mockup (its own CSS/JS/animations/
// pointer-drag engine run unmodified) and fully isolated — no existing MES
// screen, route, or backend logic is touched. Live-data binding (spec §10)
// comes in a later phase; the mockup ships with the §Appendix-A seed data.
const PLAN_URL = '/static/plan/production-flow.html'

export function PlanProductionFlow() {
  return (
    <div className="h-full w-full bg-[#EEF1F5]" data-testid="plan-production-flow">
      <iframe
        title="Production Flow"
        src={PLAN_URL}
        data-testid="plan-production-flow-frame"
        className="block h-full w-full border-0"
      />
    </div>
  )
}

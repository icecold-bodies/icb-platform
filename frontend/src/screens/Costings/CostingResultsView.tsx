import { Link, useParams } from 'react-router-dom'
import { ArrowLeft, ExternalLink, FileText } from 'lucide-react'

/**
 * In-shell costing summary (Michael, 3 Jul). The dashboard's View button used to hard-navigate
 * to the legacy /results/{id} page — outside the React app, no MES menu, no way back but the URL
 * bar. Same cure as the calculator (LiveCalculator, WO v4.7): embed the legacy page in an iframe
 * under the MES chrome. ?skin=mes serves the results_mes.html wrapper (theme-mes.css overlay);
 * the plain /results/{id} route stays pristine and remains reachable via "Open full page".
 */
export function CostingResultsView() {
  const { id } = useParams<{ id: string }>()
  const src = `/results/${encodeURIComponent(id ?? '')}?skin=mes`
  return (
    <div className="flex h-[calc(100vh-96px)] flex-col" data-testid="costing-results-view">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-line bg-surface-alt px-4 py-2 text-sm">
        <div className="flex items-center gap-2">
          <FileText size={15} className="text-primary" />
          <span className="font-semibold text-body">Costing summary</span>
          <span className="font-mono text-xs text-muted">#{id}</span>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/costings"
                className="flex items-center gap-1 rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-body hover:bg-surface-alt">
            <ArrowLeft size={12} /> Back to costings
          </Link>
          <a href={`/results/${encodeURIComponent(id ?? '')}`} target="_blank" rel="noreferrer"
             className="flex items-center gap-1 rounded-md border border-line bg-white px-2 py-1 text-xs font-semibold text-primary hover:bg-primary-light">
            <ExternalLink size={12} /> Open full page
          </a>
        </div>
      </div>
      <iframe
        title={`Costing summary ${id}`}
        src={src}
        data-testid="costing-results-iframe"
        className="w-full flex-1 border-0 bg-white"
      />
    </div>
  )
}

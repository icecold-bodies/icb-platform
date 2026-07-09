/** Admin "Master Data" module — grouped sidebar + the active sub-screen (v1.40.6 overhaul;
 * WO v4.26 origin). Sidebar = ADMIN_GROUPS (Monitor & operate / System administration /
 * Manufacturing data), each item an icon + title + frozen displayId badge. Visibility:
 * admins see everything; a QC-capable non-admin sees QC; anyone else sees exactly the
 * items whose `admin.<key>` permission the BA has granted (AppDataContext denies unknown
 * admin.* keys by default — the permissive fallback does NOT apply to this namespace). */
import type { ComponentType } from 'react'
import { NavLink, Navigate, useParams } from 'react-router-dom'

import { EmptyState } from '../../components/ui/feedback'
import { useAppData } from '../../store/AppDataContext'
import { AdminCrudTable } from './AdminCrudTable'
import { PrejobTemplatesAdmin } from './PrejobTemplatesAdmin'
import { OutstandingPrejobSignoffsPage } from './OutstandingPrejobSignoffsPage'
import { CustomersAdmin } from './CustomersAdmin'
import { OrphanChassisAdmin } from './OrphanChassisAdmin'
import { MergeChassisAdmin } from './MergeChassisAdmin'
import { HealthCheckAdmin } from './HealthCheck'   // WO v4.36b §3.3
import { QcInspector } from './QcInspector'         // WO v4.36c §3.2
import { FeedbackInbox } from './FeedbackInbox'     // v1.40.6 — joins the module (was an orphan route)
import { ADMIN_GROUPS, ADMIN_RESOURCES } from './adminResources'

// WO v4.33.1 §3.1 — custom (non-CRUD) admin screens dispatch by resource key. A future custom
// admin resource adds ONE entry here + a `custom: true` config in adminResources (the documented
// pattern — replaces the previous single hardcoded PrejobTemplatesAdmin render).
const CUSTOM_ADMIN_SCREENS: Record<string, ComponentType> = {
  'prejob-templates': PrejobTemplatesAdmin,
  'prejob-signoffs': OutstandingPrejobSignoffsPage,
  customers: CustomersAdmin,                       // WO v4.34.1 §3.5
  'orphan-chassis': OrphanChassisAdmin,            // WO v4.36a §3.6
  'merge-chassis': MergeChassisAdmin,              // WO v4.36a §3.6 STEP 6
  'health-check': HealthCheckAdmin,                // WO v4.36b §3.3
  'qc': QcInspector,                               // WO v4.36c §3.2 — Kenny's QC inbox + inspection form
  feedback: FeedbackInbox,                         // v1.40.6 — WO v4.38 inbox, now inside Master Data
}

// WO v4.36c §3.2 — QC inspection is reachable by the QC-capable roles, not only admin; every OTHER
// admin resource stays admin-only until the BA grants its admin.<key> permission (v1.40.6). (The
// /api/qc/* and /api/admin/* endpoints enforce server-side regardless.)
const QC_ROLES = new Set(['admin', 'qc_inspector', 'planner', 'production'])

export function AdminModule() {
  const { isAdmin, apiMode, sessionRole, hasPermission } = useAppData()
  const { resource } = useParams<{ resource: string }>()
  const canQc = !!sessionRole && QC_ROLES.has(sessionRole)
  const qcOnly = !isAdmin && canQc                 // a QC-capable non-admin defaults to /admin/qc

  // v1.40.6 — per-item visibility: admin wildcard → QC-role exception → granted admin.<key>.
  const canSee = (k: string) =>
    isAdmin || (k === 'qc' && canQc) || hasPermission(ADMIN_RESOURCES[k].permKey)

  if (apiMode !== 'loading' && resource && resource in ADMIN_RESOURCES && !canSee(resource)) {
    return (
      <div className="p-4">
        <EmptyState title="Admin access required"
                    hint="Master-data administration is restricted to admin users." />
      </div>
    )
  }
  if (!resource || !(resource in ADMIN_RESOURCES)) {
    return <Navigate to={qcOnly ? '/admin/qc' : '/admin/health-check'} replace />
  }
  const cfg = ADMIN_RESOURCES[resource]
  const CustomScreen = cfg.custom ? (CUSTOM_ADMIN_SCREENS[resource] ?? PrejobTemplatesAdmin) : null

  return (
    <div className="flex gap-4 p-4">
      <aside className="w-56 shrink-0">
        <h1 className="mb-3 px-1 text-sm font-bold uppercase tracking-wide text-muted">Master data</h1>
        <nav className="space-y-4">
          {ADMIN_GROUPS.map((group) => {
            const visible = group.items.filter(canSee)
            if (visible.length === 0) return null
            return (
              <div key={group.id} data-testid={`admin-group-${group.id}`}>
                {/* Michael 9 Jul — group headings pop: bold, brand blue, small accent chip. */}
                <div className="mb-1.5 flex items-center gap-1.5 border-b border-primary/15 px-1 pb-1 text-xs font-bold uppercase tracking-wider text-primary">
                  <span className="h-2 w-2 rounded-sm bg-primary/80" aria-hidden />
                  {group.label}
                </div>
                <div className="space-y-0.5">
                  {visible.map((k) => {
                    const item = ADMIN_RESOURCES[k]
                    const Icon = item.icon
                    return (
                      <NavLink key={k} to={`/admin/${k}`} data-testid={`admin-nav-${k}`}
                        className={({ isActive }) =>
                          `flex items-center gap-2 rounded-md px-2.5 py-2 text-sm transition-colors ${
                            isActive ? 'bg-primary text-white shadow-sm' : 'text-body hover:bg-surface-alt'}`}>
                        {({ isActive }) => (
                          <>
                            <Icon size={15} className={`shrink-0 ${isActive ? 'text-white' : 'text-muted'}`} />
                            <span className="min-w-0 flex-1 truncate">{item.title}</span>
                            <span title={item.permKey}
                              className={`shrink-0 rounded border px-1 font-mono text-[9px] leading-4 ${
                                isActive ? 'border-white/40 bg-white/10 text-white'
                                         : 'border-line bg-surface-alt text-muted'}`}>
                              {item.displayId}
                            </span>
                          </>
                        )}
                      </NavLink>
                    )
                  })}
                </div>
              </div>
            )
          })}
        </nav>
        <p className="mt-4 px-1 text-xs text-muted">
          Badges are each page's permanent tag — quote them when asking for a page to be
          added to a role.
        </p>
      </aside>
      <main className="min-w-0 flex-1">
        {CustomScreen
          ? <CustomScreen key={resource} />
          : <AdminCrudTable key={resource} config={cfg} />}
      </main>
    </div>
  )
}

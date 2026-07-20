import { useState, useRef, useEffect } from 'react'
import { NavLink } from 'react-router-dom'
import {
  Tablet,
  LayoutGrid,
  Factory,
  BarChart3,
  CheckSquare,
  Snowflake,
  Info,
  FileText,
  Plus,
  ChevronDown,
  User,
  Crown,
  ShieldCheck,
  LogOut,
  Building2,
  Truck,
  AlertTriangle,
  Workflow,
  type LucideIcon,
} from 'lucide-react'
import { useAppData, type BranchRef } from '../../store/AppDataContext'
import { API_BASE } from '../../lib/api'
import { Tooltip } from '../ui/Tooltip'
import { Spinner } from '../ui/feedback'
import { costingsMock, type PermissionKey } from '../../data/costingsData'
import { useFlagSummary } from '../../hooks/useFlags'   // WO v4.36b §3.2 — nav aggregate flag badge

interface NavEntry {
  to: string
  label: string
  icon: LucideIcon
  k: string
  perm?: PermissionKey | PermissionKey[]  // any one of these grants access
  adminOnly?: boolean                     // WO v4.25 — gate on AppData.isAdmin (no perm key)
}

const NAV_LINKS: NavEntry[] = [
  // Chronological order: create the costing first, then it lands in the dashboard.
  { to: '/costings/new',     label: 'New Costing',  icon: Plus,          k: 'nav.new_costing',          perm: 'costings.create' },
  { to: '/costings',         label: 'Costings',     icon: FileText,      k: 'nav.costings',             perm: ['costings.view_own', 'costings.view_all'] },
  // 3 Jul (Michael) — the "Planning" menu (Board + Cockpit dropdown) is RETIRED: the Plan module
  // below is the planning surface now. /planning and /planning/cockpit redirect to /plan (App.tsx);
  // the cockpit COMPONENT lives on, embedded inside /plan. Restore point: git history of this file.
  // WO A06 (Rapid Prototype Phase) — the top-level "Plan" module = the Production Flow prototype
  // (planner grid → Panels ready → Pre-Assembly → Merge → Parking → QC).
  { to: '/plan',             label: 'Plan',         icon: Workflow,      k: 'nav.plan' },
  // Work Order v4.11 — Materials, Buying & Stores (flat entries; the repo nav has
  // no dropdown groups). DEMO: like the Management tab (v4.8), these four are left
  // un-gated so any presenter sees them without switching demo profiles. The
  // permission model is still wired up — the screens' actions and the role-
  // separation acceptance run still rely on it. To re-gate for production, restore
  // the `perm` fields: '/materials' + '/materials?tab=forecast' → 'materials.view',
  // '/materials/suggestions' → 'materials.raise_pr', '/stores/reconciliation' →
  // 'materials.count'.
  // 20 Jul (Michael) — the four Materials/Stores entries are HIDDEN for now (module
  // not in day-to-day use yet). Routes stay live for direct URLs; only the menu is
  // trimmed. Restore point: uncomment these four lines + their icon imports above.
  // { to: '/materials',                label: 'Materials',      icon: Package,         k: 'nav.materials_dashboard' },
  // { to: '/materials/suggestions',    label: 'Suggestions',    icon: ListChecks,      k: 'nav.materials_suggestions' },
  // { to: '/materials?tab=forecast',   label: 'Forecast',       icon: CalendarClock,   k: 'nav.materials_forecast' },
  // { to: '/stores/reconciliation',    label: 'Reconciliation', icon: ClipboardCheck,  k: 'nav.stores_reconciliation' },
  // WO v4.28 — Chassis lifecycle module (viewable by any authenticated user).
  { to: '/chassis',          label: 'Chassis',      icon: Truck,         k: 'nav.chassis' },
  { to: '/tablet/vacuum',    label: 'Shop Floor',   icon: Tablet,        k: 'nav.tablet_vacuum',        perm: 'tablet.signoff' },
  { to: '/kanban/pre-assy',  label: 'Kanban',       icon: LayoutGrid,    k: 'nav.kanban',               perm: ['kanban.team_lead', 'production.view'] },
  { to: '/production',       label: 'Production',   icon: Factory,       k: 'nav.production_dashboard', perm: 'production.view' },
  // v4.8 — Management tab is visible to every profile in the demo so any
  // presenter can walk through it without flipping to Owner. In production
  // this would re-gate behind `management.view`.
  { to: '/management',       label: 'Management',   icon: BarChart3,     k: 'nav.management_dashboard' },
  // WO v4.36c.1 — repointed from the retired /qc mock to the REAL QC inbox (/admin/qc). qc_inspector's
  // only nav path there (the Admin nav below is adminOnly; the AdminModule→/admin/qc redirect can't fire
  // without first reaching /admin/*). Gated on qc.signoff (Kenny + admin).
  { to: '/admin/qc',         label: 'QC',           icon: CheckSquare,   k: 'nav.qc',                   perm: 'qc.signoff' },
  // WO v4.26 — master-data admin CRUD module; admin users only (live session role).
  // v1.40.6 — lands on Health Check (Michael's Master-Data WO: the Admin landing page).
  { to: '/admin/health-check', label: 'Admin',      icon: ShieldCheck,   k: 'nav.admin',                adminOnly: true },
]

const PROFILE_ICONS: Record<string, LucideIcon> = {
  User,
  Factory,
  Crown,
  ShieldCheck,
}

function entryVisible(entry: NavEntry, has: (k: PermissionKey) => boolean, isAdmin: boolean): boolean {
  if (entry.adminOnly) return isAdmin
  if (!entry.perm) return true
  const perms = Array.isArray(entry.perm) ? entry.perm : [entry.perm]
  return perms.some(has)
}

export function TopNav({ dark = false }: { dark?: boolean }) {
  const { tooltipsEnabled, setTooltipsEnabled, profile, setProfile, hasPermission, isAdmin, apiMode, sessionUsername, activeBranch, accessibleBranches, switchBranch } = useAppData()
  const visibleLinks = NAV_LINKS.filter((l) => entryVisible(l, hasPermission, isAdmin))
  // v1.40.2 — the demo profile switcher is for the literal `admin` ACCOUNT only (Michael's
  // rule): real staff who merely hold admin RIGHTS must not see it — it changes the displayed
  // identity, never the real session, and misled testing (6 Jul A9930 incident). In mock mode
  // (dev/demo without a backend) it stays available to any presenter.
  const allowProfileSwitch = apiMode !== 'live' || sessionUsername === 'admin'
  const { summary } = useFlagSummary()   // WO v4.36b §3.2 — aggregate flag count → Health Check (§3.3)

  return (
    <header
      data-testid="top-nav"
      className={`flex items-center gap-1 px-4 ${
        dark ? 'bg-slate-950 text-slate-200' : 'bg-primary text-white'
      }`}
    >
      <div className="flex items-center gap-2 py-2 pr-4 font-bold">
        <Snowflake size={20} />
        <span className="hidden sm:inline">ICB&nbsp;MES</span>
      </div>
      <nav className="flex flex-1 items-center gap-0.5 overflow-x-auto">
        {visibleLinks.map((entry) =>
          (
            <Tooltip key={entry.to} k={entry.k}>
              <NavLink
                to={entry.to}
                data-testid={`nav-${entry.k.replace('nav.', '')}`}
                className={({ isActive }) =>
                  `flex items-center gap-1.5 whitespace-nowrap rounded-md px-3 py-2 text-sm font-medium transition ${
                    isActive ? 'bg-white/20' : 'hover:bg-white/10'
                  }`
                }
              >
                <entry.icon size={16} />
                {entry.label}
              </NavLink>
            </Tooltip>
          ),
        )}
      </nav>
      <div className="flex items-center gap-2 py-2 pl-4">
        {/* WO v4.36b §3.2 — aggregate "N attention items" badge → Health Check dashboard (§3.3). Hidden
            when clean or when the flag API is unavailable (mock mode). */}
        {summary && summary.total > 0 && (
          <NavLink
            to="/admin/health-check"
            data-testid="nav-flag-badge"
            title={`${summary.total} attention item${summary.total === 1 ? '' : 's'} — open Health Check`}
            className="flex items-center gap-1.5 rounded-md bg-status-red/25 px-2.5 py-1.5 text-xs font-bold text-white ring-1 ring-status-red/40 transition hover:bg-status-red/40"
          >
            <AlertTriangle size={14} />
            <span className="tabular-nums">{summary.total}</span>
            <span className="hidden md:inline">attention</span>
          </NavLink>
        )}
        {apiMode === 'live' && activeBranch && (
          <BranchPicker
            active={activeBranch}
            branches={accessibleBranches.length ? accessibleBranches : [activeBranch]}
            onSwitch={switchBranch}
            dark={dark}
          />
        )}
        <Tooltip text={tooltipsEnabled ? 'Hide demo tooltips' : 'Show demo tooltips'}>
          <button
            onClick={() => setTooltipsEnabled(!tooltipsEnabled)}
            aria-pressed={tooltipsEnabled}
            className={`flex items-center gap-1.5 rounded-md px-2.5 py-1.5 text-xs font-semibold transition ${
              tooltipsEnabled ? 'bg-white/20 text-white' : 'bg-white/5 text-white/60 hover:bg-white/10'
            }`}
          >
            <Info size={14} /> Tips {tooltipsEnabled ? 'on' : 'off'}
          </button>
        </Tooltip>
        <UserSwitcher
          profile={profile}
          onChange={setProfile}
          profiles={costingsMock.demo_user_profiles}
          dark={dark}
          allowSwitch={allowProfileSwitch}
        />
      </div>
    </header>
  )
}

// (3 Jul — PlanningNavDropdown + PlanningMenuItem removed with the retired "Planning" menu;
//  see git history. The WO v4.36d split-button pattern lives on in this file's history too.)

function UserSwitcher({
  profile,
  profiles,
  onChange,
  dark,
  allowSwitch,
}: {
  profile: ReturnType<typeof useAppData>['profile']
  profiles: typeof costingsMock.demo_user_profiles
  onChange: (p: typeof profile) => void
  dark: boolean
  allowSwitch: boolean
}) {
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', h)
    return () => window.removeEventListener('mousedown', h)
  }, [open])
  const Icon = PROFILE_ICONS[profile.icon] ?? User
  const initials = profile.name
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join('')
    .toUpperCase()
  return (
    <div ref={ref} className="relative">
      <Tooltip text={allowSwitch ? 'Switch demo user profile' : 'Account menu'}>
        <button
          onClick={() => setOpen((o) => !o)}
          className="flex items-center gap-2 rounded-md px-2 py-1 text-left hover:bg-white/10"
          aria-haspopup="menu"
          aria-expanded={open}
        >
          <div className="hidden text-right sm:block">
            <div className="text-sm font-semibold leading-tight">{profile.name}</div>
            <div className="text-[11px] opacity-80">{profile.role}</div>
          </div>
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-white/20 text-xs font-bold">
            {initials}
          </div>
          <ChevronDown size={14} className="opacity-70" />
        </button>
      </Tooltip>
      {open && (
        <div
          role="menu"
          className={`absolute right-0 top-full z-50 mt-1 flex max-h-[80vh] w-64 flex-col overflow-hidden rounded-md border shadow-2xl ${
            dark ? 'border-slate-700 bg-slate-900 text-slate-100' : 'border-line bg-white text-body'
          }`}
        >
          {/* v1.40.2 — profile switching is a literal-`admin`-account demo tool; everyone
              else gets their real identity + Sign out only (the fake-identity list misled
              live testing). */}
          <div className={`shrink-0 px-3 py-2 text-[11px] font-bold uppercase tracking-wide ${dark ? 'text-slate-400' : 'text-muted'}`}>
            {allowSwitch ? 'Demo · switch user profile' : 'Signed in'}
          </div>
          {!allowSwitch && (
            <div className="px-3 pb-2 text-sm">
              <div className="font-semibold">{profile.name}</div>
              <div className={`text-xs ${dark ? 'text-slate-400' : 'text-muted'}`}>{profile.role}</div>
            </div>
          )}
          {allowSwitch && (
          <div className="min-h-0 flex-1 overflow-y-auto">
          {profiles.map((p) => {
            const PIcon = PROFILE_ICONS[p.icon] ?? User
            const active = p.id === profile.id
            return (
              <button
                key={p.id}
                onClick={() => {
                  onChange(p)
                  setOpen(false)
                }}
                className={`flex w-full items-center gap-3 px-3 py-2 text-left text-sm ${
                  active
                    ? dark
                      ? 'bg-slate-800'
                      : 'bg-primary-light text-primary'
                    : dark
                      ? 'hover:bg-slate-800'
                      : 'hover:bg-surface-alt'
                }`}
              >
                <PIcon size={18} />
                <div className="flex-1">
                  <div className="font-semibold">{p.name}</div>
                  <div className={`text-xs ${active ? 'text-primary/70' : dark ? 'text-slate-400' : 'text-muted'}`}>{p.role}</div>
                </div>
                {active && <span className="text-[10px] font-bold uppercase">Current</span>}
              </button>
            )
          })}
          <div className={`border-t px-3 py-2 text-[11px] ${dark ? 'border-slate-700 text-slate-500' : 'border-line text-muted'}`}>
            Switching re-renders the nav and action buttons based on each role's permissions.
          </div>
          </div>
          )}
          {/* v1.40.1 — real logout, PINNED below the scroll area so it is always visible even when
              the profile list overflows: a FULL-PAGE nav to /logout deletes the server session and
              lands on /login as a whole page, tearing the SPA down (no stale chrome/data). */}
          <button
            role="menuitem"
            data-testid="sign-out"
            onClick={() => { window.location.href = `${API_BASE}/logout` }}
            className={`flex w-full shrink-0 items-center gap-3 border-t px-3 py-2.5 text-left text-sm font-semibold ${
              dark ? 'border-slate-700 text-red-300 hover:bg-slate-800' : 'border-line text-status-red hover:bg-surface-alt'
            }`}
          >
            <LogOut size={18} /> Sign out
          </button>
        </div>
      )}
    </div>
  )
}

// Branch picker (WO v4.18 §4.3) — replaces the v4.17 read-only badge. Selecting
// a branch POSTs /api/session/branch via AppDataContext.switchBranch, which
// fires the active-branch-changed signal that re-scopes Planning + Materials.
// No permission gate; hidden in mock mode (rendered only when apiMode==='live').
function BranchPicker({
  active,
  branches,
  onSwitch,
  dark,
}: {
  active: BranchRef
  branches: BranchRef[]
  onSwitch: (id: number) => Promise<void>
  dark: boolean
}) {
  const [open, setOpen] = useState(false)
  const [busyId, setBusyId] = useState<number | null>(null)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const h = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false)
    }
    window.addEventListener('mousedown', h)
    return () => window.removeEventListener('mousedown', h)
  }, [open])

  async function pick(id: number) {
    if (id === active.id) {
      setOpen(false)
      return
    }
    setBusyId(id)
    try {
      await onSwitch(id)
    } finally {
      setBusyId(null)
      setOpen(false)
    }
  }

  return (
    <div ref={ref} className="relative hidden sm:block">
      <Tooltip text="Switch active branch — refreshes Planning Board and Materials views">
        <button
          onClick={() => setOpen((o) => !o)}
          aria-haspopup="menu"
          aria-expanded={open}
          className="flex items-center gap-1 rounded-md bg-white/10 px-2 py-1 text-xs font-semibold hover:bg-white/20"
        >
          {busyId != null ? <Spinner size={12} /> : <Building2 size={13} />}
          {active.code}
          <ChevronDown size={12} className="opacity-70" />
        </button>
      </Tooltip>
      {open && (
        <div
          role="menu"
          className={`absolute right-0 top-full z-50 mt-1 w-56 overflow-hidden rounded-md border shadow-2xl ${
            dark ? 'border-slate-700 bg-slate-900 text-slate-100' : 'border-line bg-white text-body'
          }`}
        >
          <div className={`px-3 py-2 text-[11px] font-bold uppercase tracking-wide ${dark ? 'text-slate-400' : 'text-muted'}`}>
            Active branch
          </div>
          {branches.map((b) => {
            const isActive = b.id === active.id
            return (
              <button
                key={b.id}
                onClick={() => pick(b.id)}
                disabled={busyId != null}
                className={`flex w-full items-center gap-2 px-3 py-2 text-left text-sm disabled:opacity-60 ${
                  isActive
                    ? dark
                      ? 'bg-slate-800'
                      : 'bg-primary-light text-primary'
                    : dark
                      ? 'hover:bg-slate-800'
                      : 'hover:bg-surface-alt'
                }`}
              >
                <Building2 size={15} />
                <div className="flex-1">
                  <div className="font-semibold">{b.code}</div>
                  <div className={`text-xs ${isActive ? 'text-primary/70' : dark ? 'text-slate-400' : 'text-muted'}`}>{b.name}</div>
                </div>
                {busyId === b.id && <Spinner size={12} />}
                {isActive && busyId == null && <span className="text-[10px] font-bold uppercase">Current</span>}
              </button>
            )
          })}
        </div>
      )}
    </div>
  )
}

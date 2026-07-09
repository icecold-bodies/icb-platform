// slotProgress.tsx — the V/P stage clock (v1.40.6 thresholds WO).
//
// The board serves each scheduled V/P slot's stage-clock inputs (SlotStageProgress):
// threshold hours + a SERVER-computed elapsed_hours at fetch time. The UI ticks forward
// from the fetch moment (PlanningContext.lastUpdated) — the client's absolute clock
// never meets the server's, so skew can't bend a bar. Color language mirrors
// AgeingPill/KanbanTV: green under 75%, amber approaching (75–100%), red over.
import { useEffect, useState } from 'react'
import { Clock } from 'lucide-react'

import type { SlotStageProgress } from '../../../lib/types'

export type ProgressTone = 'pending' | 'green' | 'amber' | 'red'

/** Elapsed hours as of NOW = server elapsed at fetch + wall time since the fetch. */
export function elapsedNowHours(p: SlotStageProgress, lastUpdated: Date | null, nowMs: number): number {
  const fetchedMs = lastUpdated ? lastUpdated.getTime() : nowMs
  return p.elapsed_hours + Math.max(0, nowMs - fetchedMs) / 3_600_000
}

export function progressTone(elapsedH: number, thresholdH: number): ProgressTone {
  if (elapsedH < 0) return 'pending'          // scheduled day hasn't started yet
  if (thresholdH <= 0) return 'green'
  const pct = elapsedH / thresholdH
  if (pct > 1) return 'red'
  if (pct >= 0.75) return 'amber'
  return 'green'
}

// Static class strings (Tailwind JIT — never compose these dynamically).
export const TONE_BAR: Record<ProgressTone, string> = {
  pending: 'bg-transparent',
  green: 'bg-status-green',
  amber: 'bg-status-amber',
  red: 'bg-status-red',
}
const TONE_TEXT: Record<ProgressTone, string> = {
  pending: 'text-muted',
  green: 'text-status-green',
  amber: 'text-status-amber',
  red: 'text-status-red',
}

export function pctClamped(elapsedH: number, thresholdH: number): number {
  if (elapsedH <= 0 || thresholdH <= 0) return 0
  return Math.min(100, (elapsedH / thresholdH) * 100)
}

const DAY_NAMES = ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']

/** "Starts Thu 07:00" copy for a clock that hasn't begun (started_at is display-only). */
export function startsCopy(p: SlotStageProgress): string {
  const d = new Date(p.started_at)
  const day = Number.isNaN(d.getTime()) ? '' : `${DAY_NAMES[d.getDay()]} `
  return `Starts ${day}${p.workday_start}`
}

function fmtH(h: number): string {
  return `${(Math.round(h * 10) / 10).toFixed(1)}h`
}

/** The drawer line: "Vacuum clock · 3.4h of 8h (43%)" — self-ticking (60s) while mounted. */
export function SlotStageClock({ progress, lastUpdated }: {
  progress: SlotStageProgress | null | undefined
  lastUpdated: Date | null
}) {
  const [nowMs, setNowMs] = useState(() => Date.now())
  useEffect(() => {
    const t = setInterval(() => setNowMs(Date.now()), 60_000)
    return () => clearInterval(t)
  }, [])
  if (!progress) return null
  const elapsed = elapsedNowHours(progress, lastUpdated, nowMs)
  const tone = progressTone(elapsed, progress.threshold_hours)
  return (
    <div data-testid="slot-stage-clock" data-tone={tone}
         className="flex items-center gap-2 rounded-md bg-surface-alt p-3">
      <Clock size={16} className={TONE_TEXT[tone]} />
      <div className="min-w-0 flex-1">
        <div className="text-xs text-muted">{progress.label} clock</div>
        {tone === 'pending' ? (
          <div className="text-sm font-semibold text-body">{startsCopy(progress)}</div>
        ) : (
          <div className={`text-sm font-semibold tabular-nums ${TONE_TEXT[tone]}`}>
            {fmtH(elapsed)} of {fmtH(progress.threshold_hours)}
            {' '}({Math.round((elapsed / progress.threshold_hours) * 100)}%)
            {tone === 'red' ? ' — over threshold' : ''}
          </div>
        )}
      </div>
      {tone !== 'pending' && (
        <div className="h-1.5 w-24 shrink-0 overflow-hidden rounded-full bg-line/60">
          <div className={`h-full ${TONE_BAR[tone]}`}
               style={{ width: `${pctClamped(elapsed, progress.threshold_hours)}%` }} />
        </div>
      )}
    </div>
  )
}

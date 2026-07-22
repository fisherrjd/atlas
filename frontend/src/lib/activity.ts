import type { Project, ProjectStatus } from '@/types'

export type Freshness = 'fresh' | 'cooling' | 'dormant'

const DAY = 24 * 60 * 60 * 1000

export function lastPush(project: Project): string | null {
  const dates = project.repos.map((r) => r.pushed_at).filter((d): d is string => d !== null)
  if (dates.length === 0) return null
  return dates.reduce((a, b) => (a > b ? a : b))
}

export function daysSincePush(project: Project): number | null {
  const last = lastPush(project)
  if (last === null) return null
  return Math.floor((Date.now() - new Date(last).getTime()) / DAY)
}

/** Reality signal, derived from synced pushed_at — null for repo-less projects. */
export function freshness(project: Project): Freshness | null {
  const days = daysSincePush(project)
  if (days === null) return null
  if (days < 30) return 'fresh'
  if (days < 90) return 'cooling'
  return 'dormant'
}

/** Intent (column) vs reality (pushes) mismatch hints. */
export function mismatch(project: Project): 'stale' | 'moving' | null {
  const f = freshness(project)
  if (f === null) return null
  const status: ProjectStatus = project.status
  if (status === 'active' && f === 'dormant') return 'stale'
  if ((status === 'idea' || status === 'paused') && f === 'fresh') return 'moving'
  return null
}

export function relativeDays(days: number | null): string {
  if (days === null) return 'no pushes'
  if (days === 0) return 'pushed today'
  if (days === 1) return 'pushed yesterday'
  if (days < 30) return `pushed ${days}d ago`
  if (days < 365) return `pushed ${Math.floor(days / 30)}mo ago`
  return `pushed ${Math.floor(days / 365)}y ago`
}

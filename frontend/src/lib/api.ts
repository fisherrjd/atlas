import type {
  BoardData,
  Project,
  ProjectStatus,
  Repo,
  SyncResult,
  Task,
  TaskStatus,
} from '@/types'

export class ApiError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function req<T>(url: string, options?: RequestInit): Promise<T> {
  const r = await fetch(url, {
    headers: { 'Content-Type': 'application/json' },
    ...options,
  })
  if (!r.ok) {
    const body = await r.json().catch(() => ({ detail: r.statusText }))
    throw new ApiError(r.status, (body as { detail?: string }).detail ?? r.statusText)
  }
  return r.json() as Promise<T>
}

export const api = {
  board: () => req<BoardData>('/api/board'),

  createProject: (body: {
    name: string
    description?: string
    status?: ProjectStatus
    repos?: string[]
  }) => req<Project>('/api/projects', { method: 'POST', body: JSON.stringify(body) }),
  project: (id: number) => req<Project>(`/api/projects/${id}`),
  updateProject: (id: number, patch: { name?: string; description?: string; notes?: string }) =>
    req<Project>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  moveProject: (id: number, status: ProjectStatus, index: number) =>
    req<Project>(`/api/projects/${id}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ status, index }),
    }),
  deleteProject: (id: number) =>
    req<{ detail: string }>(`/api/projects/${id}`, { method: 'DELETE' }),

  repos: (unassigned = false) => req<Repo[]>(`/api/repos${unassigned ? '?unassigned=true' : ''}`),
  assignRepo: (projectId: number, fullName: string) =>
    req<Project>(`/api/projects/${projectId}/repos`, {
      method: 'POST',
      body: JSON.stringify({ full_name: fullName }),
    }),
  unassignRepo: (projectId: number, fullName: string) =>
    req<{ detail: string }>(`/api/projects/${projectId}/repos/${fullName}`, { method: 'DELETE' }),

  addTask: (projectId: number, title: string) =>
    req<Task>(`/api/projects/${projectId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  updateTask: (id: number, title: string) =>
    req<Task>(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  moveTask: (id: number, status: TaskStatus, index: number) =>
    req<Task>(`/api/tasks/${id}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ status, index }),
    }),
  deleteTask: (id: number) => req<{ detail: string }>(`/api/tasks/${id}`, { method: 'DELETE' }),

  sync: () => req<SyncResult>('/api/sync', { method: 'POST' }),
}

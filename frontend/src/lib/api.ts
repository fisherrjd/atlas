import type {
  BoardData,
  Column,
  NowProject,
  Project,
  ProjectStatus,
  Repo,
  SyncResult,
  Task,
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
  board: (includeArchived = false) =>
    req<BoardData>(`/api/board${includeArchived ? '?include_archived=true' : ''}`),
  now: () => req<NowProject[]>('/api/now'),

  createProject: (body: {
    name: string
    description?: string
    status?: ProjectStatus
    repos?: string[]
  }) => req<Project>('/api/projects', { method: 'POST', body: JSON.stringify(body) }),
  project: (id: number) => req<Project>(`/api/projects/${id}`),
  updateProject: (id: number, patch: { name?: string; description?: string; notes?: string }) =>
    req<Project>(`/api/projects/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  setProjectStatus: (id: number, status: ProjectStatus) =>
    req<Project>(`/api/projects/${id}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ status }),
    }),
  setArchived: (id: number, archived: boolean) =>
    req<Project>(`/api/projects/${id}/archive`, {
      method: 'PATCH',
      body: JSON.stringify({ archived }),
    }),
  deleteProject: (id: number) =>
    req<{ detail: string }>(`/api/projects/${id}`, { method: 'DELETE' }),

  addColumn: (projectId: number, name: string) =>
    req<Column>(`/api/projects/${projectId}/columns`, {
      method: 'POST',
      body: JSON.stringify({ name }),
    }),
  renameColumn: (id: number, name: string) =>
    req<Column>(`/api/columns/${id}`, { method: 'PATCH', body: JSON.stringify({ name }) }),
  moveColumn: (id: number, index: number) =>
    req<Column>(`/api/columns/${id}/move`, { method: 'PATCH', body: JSON.stringify({ index }) }),
  deleteColumn: (id: number) =>
    req<{ detail: string }>(`/api/columns/${id}`, { method: 'DELETE' }),

  repos: (unassigned = false) => req<Repo[]>(`/api/repos${unassigned ? '?unassigned=true' : ''}`),
  assignRepo: (projectId: number, fullName: string) =>
    req<Project>(`/api/projects/${projectId}/repos`, {
      method: 'POST',
      body: JSON.stringify({ full_name: fullName }),
    }),
  unassignRepo: (projectId: number, fullName: string) =>
    req<{ detail: string }>(`/api/projects/${projectId}/repos/${fullName}`, { method: 'DELETE' }),

  addTask: (columnId: number, title: string) =>
    req<Task>(`/api/columns/${columnId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ title }),
    }),
  updateTask: (id: number, title: string) =>
    req<Task>(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify({ title }) }),
  moveTask: (id: number, columnId: number, index: number) =>
    req<Task>(`/api/tasks/${id}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ column_id: columnId, index }),
    }),
  deleteTask: (id: number) => req<{ detail: string }>(`/api/tasks/${id}`, { method: 'DELETE' }),

  sync: () => req<SyncResult>('/api/sync', { method: 'POST' }),
}

import type {
  BoardData,
  Column,
  NowProject,
  Project,
  ProjectStatus,
  Repo,
  SyncResult,
  Task,
  TaskComment,
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
  setArchived: (id: number, archived: boolean, github = false) =>
    req<Project>(`/api/projects/${id}/archive`, {
      method: 'PATCH',
      body: JSON.stringify({ archived, github }),
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

  repos: (unassigned = false, archived = false) => {
    const params = new URLSearchParams()
    if (unassigned) params.set('unassigned', 'true')
    if (archived) params.set('archived', 'true')
    const qs = params.toString()
    return req<Repo[]>(`/api/repos${qs ? `?${qs}` : ''}`)
  },
  assignRepo: (projectId: number, fullName: string) =>
    req<Project>(`/api/projects/${projectId}/repos`, {
      method: 'POST',
      body: JSON.stringify({ full_name: fullName }),
    }),
  unassignRepo: (projectId: number, fullName: string) =>
    req<{ detail: string }>(`/api/projects/${projectId}/repos/${fullName}`, { method: 'DELETE' }),

  addTask: (columnId: number, title: string, description = '', source = '') =>
    req<Task>(`/api/columns/${columnId}/tasks`, {
      method: 'POST',
      body: JSON.stringify({ title, description, source }),
    }),
  updateTask: (id: number, patch: { title?: string; description?: string; agent?: string }) =>
    req<Task>(`/api/tasks/${id}`, { method: 'PATCH', body: JSON.stringify(patch) }),
  moveTask: (id: number, columnId: number, index: number) =>
    req<Task>(`/api/tasks/${id}/move`, {
      method: 'PATCH',
      body: JSON.stringify({ column_id: columnId, index }),
    }),
  deleteTask: (id: number) => req<{ detail: string }>(`/api/tasks/${id}`, { method: 'DELETE' }),

  taskComments: (taskId: number) => req<TaskComment[]>(`/api/tasks/${taskId}/comments`),
  addComment: (taskId: number, author: string, body: string) =>
    req<TaskComment>(`/api/tasks/${taskId}/comments`, {
      method: 'POST',
      body: JSON.stringify({ author, body }),
    }),

  sync: () => req<SyncResult>('/api/sync', { method: 'POST' }),

  heimdall: <T>(
    route: 'health' | 'pulses' | 'tickets' | 'suppressions' | 'personas',
    limit = 50,
  ) => req<T>(`/api/heimdall/${route}?limit=${limit}`),
  heimdallAvatars: () =>
    req<{ file: string; assigned_to: string | null }[]>('/api/heimdall/avatars'),
  heimdallJob: (id: string) =>
    req<{ status: string; detail: string }>(`/api/heimdall/agent-jobs/${id}`),
  heimdallEditPersona: (name: string, patch: Record<string, unknown>) =>
    req<{ detail: string; git_warning: string | null }>(`/api/heimdall/personas/${name}`, {
      method: 'POST',
      body: JSON.stringify(patch),
    }),
  heimdallCreatePersona: (body: {
    name: string
    role: string
    purpose: string
    model?: string
    effort?: string
  }) => req<{ job: string }>('/api/heimdall/personas', { method: 'POST', body: JSON.stringify(body) }),
}

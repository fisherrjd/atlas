export type ProjectStatus = 'idea' | 'backlog' | 'active' | 'paused' | 'done'
export type TaskStatus = 'todo' | 'doing' | 'done'

export interface Repo {
  full_name: string
  project_id: number | null
  name: string
  owner: string
  description: string
  language: string | null
  pushed_at: string | null
  url: string
  archived: number
  synced_at: string
}

export interface Task {
  id: number
  project_id: number
  title: string
  status: TaskStatus
  sort_order: number
  created_at: string
  updated_at: string
}

export interface Project {
  id: number
  name: string
  description: string
  status: ProjectStatus
  sort_order: number
  notes: string
  created_at: string
  updated_at: string
  repos: Repo[]
  tasks?: Task[]
  task_counts?: { total: number; done: number }
}

export interface BoardData {
  projects: Project[]
  last_synced_at: string | null
}

export interface SyncResult {
  created: number
  updated: number
  archived_count: number
}

export const PROJECT_STATUSES: ProjectStatus[] = ['idea', 'backlog', 'active', 'paused', 'done']
export const TASK_STATUSES: TaskStatus[] = ['todo', 'doing', 'done']

export const STATUS_LABELS: Record<ProjectStatus, string> = {
  idea: 'Idea',
  backlog: 'Backlog',
  active: 'Active',
  paused: 'Paused',
  done: 'Done',
}

export const TASK_STATUS_LABELS: Record<TaskStatus, string> = {
  todo: 'Todo',
  doing: 'Doing',
  done: 'Done',
}

export type ProjectStatus = 'idea' | 'backlog' | 'active' | 'paused' | 'done'

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
  column_id: number
  title: string
  description: string
  source: string
  sort_order: number
  created_at: string
  updated_at: string
  comment_count?: number
}

export interface TaskComment {
  id: number
  task_id: number
  author: string
  body: string
  created_at: string
}

export interface Column {
  id: number
  project_id: number
  name: string
  sort_order: number
  is_done: number
  tasks: Task[]
}

export interface Project {
  id: number
  name: string
  description: string
  status: ProjectStatus
  sort_order: number
  notes: string
  archived: number
  created_at: string
  updated_at: string
  repos: Repo[]
  columns?: Column[]
  task_counts?: { total: number; done: number }
}

export interface NowTask extends Task {
  column_name: string
}

export interface NowProject extends Omit<Project, 'repos' | 'columns'> {
  tasks: NowTask[]
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

export const STATUS_LABELS: Record<ProjectStatus, string> = {
  idea: 'Idea',
  backlog: 'Backlog',
  active: 'Active',
  paused: 'Paused',
  done: 'Done',
}

<script setup lang="ts">
import {
  ArchiveIcon,
  ArchiveRestoreIcon,
  ArrowLeftIcon,
  BotIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  FileTextIcon,
  GripVerticalIcon,
  MessageSquareTextIcon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
  XIcon,
} from '@lucide/vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import draggable from 'vuedraggable'
import MarkdownView from '@/components/content/MarkdownView.vue'
import SaveIndicator from '@/components/SaveIndicator.vue'
import ConfirmDialog from '@/components/states/ConfirmDialog.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select'
import { Separator } from '@/components/ui/separator'
import { Skeleton } from '@/components/ui/skeleton'
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs'
import { Textarea } from '@/components/ui/textarea'
import { useSync } from '@/composables/useSync'
import { api, ApiError } from '@/lib/api'
import { daysSincePush, freshness, relativeDays } from '@/lib/activity'
import type { Column, Project, ProjectStatus, Repo, Task, TaskComment } from '@/types'
import { PROJECT_STATUSES, STATUS_LABELS } from '@/types'

const route = useRoute()
const router = useRouter()
const projectId = Number(route.params.id)

const project = ref<Project | null>(null)
const columns = ref<Column[]>([])
const loading = ref(true)
const { syncTick } = useSync()

const pushed = computed(() =>
  project.value ? relativeDays(daysSincePush(project.value)) : '',
)
const dot = computed(() => (project.value ? freshness(project.value) : null))

const DOT_CLASS = {
  fresh: 'bg-emerald-500',
  cooling: 'bg-amber-500',
  dormant: 'bg-stone-400',
} as const

async function load() {
  try {
    const p = await api.project(projectId)
    project.value = p
    columns.value = p.columns ?? []
    notes.value = p.notes
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to load project')
    router.push('/')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(syncTick, load)

// ── Status ───────────────────────────────────────────────────────────────────

async function setStatus(status: ProjectStatus) {
  if (!project.value) return
  const previous = project.value.status
  project.value.status = status
  try {
    await api.setProjectStatus(projectId, status)
  } catch (e) {
    project.value.status = previous
    toast.error(e instanceof ApiError ? e.message : 'Status change failed')
  }
}

// ── Edit / delete project ────────────────────────────────────────────────────

const editOpen = ref(false)
const editName = ref('')
const editDescription = ref('')

function openEdit() {
  if (!project.value) return
  editName.value = project.value.name
  editDescription.value = project.value.description
  editOpen.value = true
}

async function saveEdit() {
  if (!project.value || !editName.value.trim()) return
  try {
    const p = await api.updateProject(projectId, {
      name: editName.value.trim(),
      description: editDescription.value.trim(),
    })
    project.value = p
    columns.value = p.columns ?? []
    editOpen.value = false
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Save failed')
  }
}

const archiveOpen = ref(false)
const archiveGithub = ref(false)

function toggleArchived() {
  if (!project.value) return
  if (project.value.repos.length > 0) {
    archiveGithub.value = false
    archiveOpen.value = true
  } else {
    doArchive()
  }
}

async function doArchive() {
  if (!project.value) return
  const next = !project.value.archived
  try {
    const p = await api.setArchived(projectId, next, archiveGithub.value)
    project.value = { ...project.value, archived: p.archived, repos: p.repos }
    archiveOpen.value = false
    const gh = archiveGithub.value ? ` (+${p.repos.length} on GitHub)` : ''
    toast.success(next ? `Archived — hidden from the grid${gh}` : `Restored to the grid${gh}`)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Archive failed')
  }
}

async function deleteProject() {
  try {
    await api.deleteProject(projectId)
    toast.success('Project deleted')
    router.push('/')
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Delete failed')
  }
}

// ── Repos ────────────────────────────────────────────────────────────────────

const addRepoOpen = ref(false)
const unassigned = ref<Repo[]>([])
const repoToAdd = ref<string>()

watch(addRepoOpen, async (open) => {
  if (!open) return
  repoToAdd.value = undefined
  unassigned.value = await api.repos(true).catch(() => [])
})

async function addRepo() {
  if (!repoToAdd.value) return
  try {
    const p = await api.assignRepo(projectId, repoToAdd.value)
    project.value = p
    addRepoOpen.value = false
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to add repo')
  }
}

async function removeRepo(fullName: string) {
  try {
    await api.unassignRepo(projectId, fullName)
    await load()
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to remove repo')
  }
}

// archived repos hide behind a muted toggle — visible chips are live repos only
const liveRepos = computed(() => project.value?.repos.filter((r) => !r.archived) ?? [])
const archivedRepoList = computed(() => project.value?.repos.filter((r) => r.archived) ?? [])
const showArchivedRepos = ref(false)

// ── Columns ──────────────────────────────────────────────────────────────────

interface ColumnChangeEvent {
  moved?: { element: Column; newIndex: number }
}

async function onColumnReorder(event: ColumnChangeEvent) {
  if (!event.moved) return
  try {
    await api.moveColumn(event.moved.element.id, event.moved.newIndex)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Reorder failed')
    await load()
  }
}

const addingColumn = ref(false)
const newColumnName = ref('')

async function addColumn() {
  const name = newColumnName.value.trim()
  if (!name) return
  try {
    const col = await api.addColumn(projectId, name)
    columns.value.push({ ...col, tasks: [] })
    newColumnName.value = ''
    addingColumn.value = false
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to add column')
  }
}

const renamingId = ref<number | null>(null)
const renameValue = ref('')

function startRename(col: Column) {
  renamingId.value = col.id
  renameValue.value = col.name
  nextTick(() => {
    const el = document.getElementById(`rename-${col.id}`)
    el?.focus()
  })
}

async function saveRename(col: Column) {
  const name = renameValue.value.trim()
  renamingId.value = null
  if (!name || name === col.name) return
  const previous = col.name
  col.name = name
  try {
    await api.renameColumn(col.id, name)
  } catch (e) {
    col.name = previous
    toast.error(e instanceof ApiError ? e.message : 'Rename failed')
  }
}

async function removeColumn(col: Column) {
  try {
    await api.deleteColumn(col.id)
    columns.value = columns.value.filter((c) => c.id !== col.id)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Delete failed')
  }
}

// ── Tasks ────────────────────────────────────────────────────────────────────

const addingTaskFor = ref<number | null>(null)
const newTaskTitle = ref('')

function startAddTask(col: Column) {
  addingTaskFor.value = col.id
  newTaskTitle.value = ''
  nextTick(() => {
    const el = document.getElementById(`add-task-${col.id}`)
    el?.focus()
  })
}

async function addTask(col: Column) {
  const title = newTaskTitle.value.trim()
  if (!title) {
    addingTaskFor.value = null
    return
  }
  try {
    const t = await api.addTask(col.id, title)
    col.tasks.push(t)
    newTaskTitle.value = ''
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to add task')
  }
}

interface TaskChangeEvent {
  added?: { element: Task; newIndex: number }
  moved?: { element: Task; newIndex: number }
}

async function onTaskChange(col: Column, event: TaskChangeEvent) {
  const change = event.added ?? event.moved
  if (!change) return
  try {
    await api.moveTask(change.element.id, col.id, change.newIndex)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Move failed')
    await load()
  }
}

async function removeTask(col: Column, task: Task) {
  try {
    await api.deleteTask(task.id)
    col.tasks = col.tasks.filter((t) => t.id !== task.id)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Delete failed')
  }
}

// ── Task detail (title + description body; source badge shows who filed it) ───

const taskDetail = ref<Task | null>(null)
const taskTitle = ref('')
const taskDescription = ref('')
const taskAgent = ref('')
const taskTab = ref('preview')

function openTask(task: Task) {
  taskDetail.value = task
  taskTitle.value = task.title
  taskDescription.value = task.description
  taskAgent.value = task.agent ?? ''
  taskTab.value = task.description.trim() ? 'preview' : 'write'
  comments.value = []
  newComment.value = ''
  loadComments(task.id)
}

// assignee picker: implementer personas via the heimdall proxy; when that's
// unreachable the picker degrades to a free-text input
const implementers = ref<{ name: string; character: string | null }[]>([])
onMounted(async () => {
  try {
    const personas = await api.heimdall<{ name: string; role: string; character: string | null }[]>(
      'personas',
    )
    implementers.value = personas.filter((p) => p.role === 'implementer')
  } catch {
    implementers.value = []
  }
})

// ── Comments (thread with the filing persona; the orc loop answers) ───────────

const comments = ref<TaskComment[]>([])
const commentsLoading = ref(false)
const newComment = ref('')

async function loadComments(taskId: number) {
  commentsLoading.value = true
  try {
    comments.value = await api.taskComments(taskId)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to load comments')
  } finally {
    commentsLoading.value = false
  }
}

async function postComment() {
  if (!taskDetail.value || !newComment.value.trim()) return
  try {
    const c = await api.addComment(taskDetail.value.id, 'jade', newComment.value.trim())
    comments.value.push(c)
    newComment.value = ''
    for (const col of columns.value) {
      const t = col.tasks.find((x) => x.id === c.task_id)
      if (t) t.comment_count = (t.comment_count ?? 0) + 1
    }
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to post comment')
  }
}

async function saveTask() {
  if (!taskDetail.value || !taskTitle.value.trim()) return
  try {
    const t = await api.updateTask(taskDetail.value.id, {
      title: taskTitle.value.trim(),
      description: taskDescription.value,
      agent: taskAgent.value.trim(),
    })
    for (const c of columns.value) {
      const i = c.tasks.findIndex((x) => x.id === t.id)
      if (i >= 0) c.tasks[i] = t
    }
    taskDetail.value = null
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Save failed')
  }
}

// ── Notes (debounced autosave) ────────────────────────────────────────────────

const notes = ref('')
const notesTab = ref('write')
const noteState = ref<'saved' | 'saving' | 'error'>('saved')
let noteTimer: ReturnType<typeof setTimeout> | undefined

watch(notes, (value) => {
  if (!project.value || value === project.value.notes) return
  noteState.value = 'saving'
  clearTimeout(noteTimer)
  noteTimer = setTimeout(async () => {
    try {
      const p = await api.updateProject(projectId, { notes: value })
      if (project.value) project.value.notes = p.notes
      noteState.value = 'saved'
    } catch {
      noteState.value = 'error'
    }
  }, 750)
})
</script>

<template>
  <div v-if="loading" class="space-y-4">
    <Skeleton class="h-10 w-64" />
    <Skeleton class="h-64 w-full" />
  </div>

  <div v-else-if="project" class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="space-y-1">
        <div class="flex items-center gap-3">
          <Button variant="ghost" size="icon-sm" aria-label="Back to projects" @click="router.push('/')">
            <ArrowLeftIcon />
          </Button>
          <h1
            class="bg-gradient-to-r from-foreground to-foreground/60 bg-clip-text text-2xl font-bold tracking-tight text-transparent"
          >
            {{ project.name }}
          </h1>
          <span
            v-if="dot"
            class="size-2.5 rounded-full"
            :class="DOT_CLASS[dot]"
            :title="`${dot} — ${pushed}`"
          />
          <Select :model-value="project.status" @update:model-value="setStatus($event as ProjectStatus)">
            <SelectTrigger class="h-7 w-28 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem v-for="s in PROJECT_STATUSES" :key="s" :value="s">
                {{ STATUS_LABELS[s] }}
              </SelectItem>
            </SelectContent>
          </Select>
        </div>
        <p v-if="project.description" class="pl-11 text-sm text-muted-foreground">
          {{ project.description }}
        </p>
      </div>
      <div class="flex items-center gap-1">
        <Badge v-if="project.archived" variant="secondary">archived</Badge>
        <Button variant="ghost" size="sm" @click="openEdit">
          <PencilIcon />
          Edit
        </Button>
        <Button variant="ghost" size="sm" @click="toggleArchived">
          <ArchiveRestoreIcon v-if="project.archived" />
          <ArchiveIcon v-else />
          {{ project.archived ? 'Restore' : 'Archive' }}
        </Button>
        <ConfirmDialog
          destructive
          :title="`Delete ${project.name}?`"
          description="Columns, tasks, and notes are deleted; linked repos return to the unassigned pool."
          confirm-label="Delete"
          @confirm="deleteProject"
        >
          <Button variant="ghost" size="sm" class="text-destructive">
            <Trash2Icon />
            Delete
          </Button>
        </ConfirmDialog>
      </div>
    </div>

    <!-- Repos (archived ones stay hidden behind the toggle) -->
    <div class="flex flex-wrap items-center gap-2">
      <div
        v-for="repo in showArchivedRepos ? project.repos : liveRepos"
        :key="repo.full_name"
        class="flex items-center gap-1.5 rounded-md border bg-card px-2 py-1 text-xs"
        :class="repo.archived ? 'opacity-60' : ''"
      >
        <a
          :href="repo.url"
          target="_blank"
          rel="noopener"
          class="flex items-center gap-1 font-medium hover:text-primary"
        >
          {{ repo.full_name }}
          <ExternalLinkIcon class="size-3" />
        </a>
        <span v-if="repo.language" class="text-muted-foreground">{{ repo.language }}</span>
        <ArchiveIcon v-if="repo.archived" class="size-3 text-muted-foreground" title="archived on GitHub" />
        <button
          class="text-muted-foreground hover:text-destructive"
          :aria-label="`Remove ${repo.full_name}`"
          @click="removeRepo(repo.full_name)"
        >
          <XIcon class="size-3" />
        </button>
      </div>
      <button
        v-if="archivedRepoList.length"
        class="text-xs text-muted-foreground underline decoration-dotted underline-offset-2 hover:text-foreground"
        @click="showArchivedRepos = !showArchivedRepos"
      >
        {{ showArchivedRepos ? 'hide archived' : `+${archivedRepoList.length} archived` }}
      </button>
      <Button variant="outline" size="xs" @click="addRepoOpen = true">
        <PlusIcon />
        Add repo
      </Button>
    </div>

    <Separator />

    <!-- Kanban -->
    <div class="flex items-start gap-3 overflow-x-auto pb-4">
      <draggable
        :list="columns"
        item-key="id"
        handle=".col-drag"
        class="flex items-start gap-3"
        ghost-class="opacity-40"
        @change="onColumnReorder"
      >
        <template #item="{ element: col }">
          <div class="flex w-64 shrink-0 flex-col rounded-lg border bg-muted/40">
            <div class="group/col flex items-center gap-1.5 px-2 py-2">
              <GripVerticalIcon class="col-drag size-3.5 shrink-0 cursor-grab text-muted-foreground" />
              <Input
                v-if="renamingId === col.id"
                :id="`rename-${col.id}`"
                v-model="renameValue"
                class="h-6 text-sm"
                @keyup.enter="saveRename(col)"
                @keyup.esc="renamingId = null"
                @blur="saveRename(col)"
              />
              <template v-else>
                <h3 class="text-sm font-semibold">{{ col.name }}</h3>
                <CheckCircle2Icon
                  v-if="col.is_done"
                  class="size-3 text-muted-foreground"
                  title="tasks here count as done"
                />
                <Badge variant="secondary" class="text-[10px]">{{ col.tasks.length }}</Badge>
                <span class="ml-auto flex items-center gap-1 opacity-0 transition-opacity group-hover/col:opacity-100">
                  <button
                    class="text-muted-foreground hover:text-foreground"
                    :aria-label="`Rename ${col.name}`"
                    @click="startRename(col)"
                  >
                    <PencilIcon class="size-3" />
                  </button>
                  <button
                    class="text-muted-foreground hover:text-destructive"
                    :aria-label="`Delete ${col.name}`"
                    @click="removeColumn(col)"
                  >
                    <XIcon class="size-3.5" />
                  </button>
                </span>
              </template>
            </div>
            <draggable
              :list="col.tasks"
              group="tasks"
              item-key="id"
              class="flex min-h-10 flex-col gap-1.5 p-2 pt-0"
              ghost-class="opacity-40"
              @change="(e: TaskChangeEvent) => onTaskChange(col, e)"
            >
              <template #item="{ element: task }">
                <div
                  class="group flex cursor-grab items-center gap-2 rounded-md border bg-card px-2.5 py-1.5 text-sm"
                  :class="col.is_done ? 'text-muted-foreground line-through' : ''"
                  @click="openTask(task)"
                >
                  <span class="flex-1">{{ task.title }}</span>
                  <FileTextIcon
                    v-if="task.description"
                    class="size-3 shrink-0 text-muted-foreground"
                    title="has details"
                  />
                  <span
                    v-if="task.comment_count"
                    class="flex shrink-0 items-center gap-0.5 text-[10px] text-muted-foreground"
                    :title="`${task.comment_count} comment${task.comment_count === 1 ? '' : 's'}`"
                  >
                    <MessageSquareTextIcon class="size-3" />
                    {{ task.comment_count }}
                  </span>
                  <Badge v-if="task.source" variant="secondary" class="shrink-0 text-[9px]">
                    {{ task.source }}
                  </Badge>
                  <Badge
                    v-if="task.agent"
                    variant="outline"
                    class="shrink-0 gap-0.5 text-[9px]"
                    :title="`assigned to ${task.agent}`"
                  >
                    <BotIcon class="size-2.5" />
                    {{ task.agent }}
                  </Badge>
                  <button
                    class="text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                    :aria-label="`Delete ${task.title}`"
                    @click.stop="removeTask(col, task)"
                  >
                    <XIcon class="size-3.5" />
                  </button>
                </div>
              </template>
            </draggable>
            <div class="p-2 pt-0">
              <Input
                v-if="addingTaskFor === col.id"
                :id="`add-task-${col.id}`"
                v-model="newTaskTitle"
                placeholder="Task title…"
                class="h-7 text-sm"
                @keyup.enter="addTask(col)"
                @keyup.esc="addingTaskFor = null"
                @blur="addTask(col)"
              />
              <Button
                v-else
                variant="ghost"
                size="xs"
                class="w-full justify-start text-muted-foreground"
                @click="startAddTask(col)"
              >
                <PlusIcon />
                Add task
              </Button>
            </div>
          </div>
        </template>
      </draggable>

      <div class="w-56 shrink-0">
        <Input
          v-if="addingColumn"
          id="add-column"
          v-model="newColumnName"
          placeholder="Column name…"
          class="h-8 text-sm"
          @keyup.enter="addColumn"
          @keyup.esc="addingColumn = false"
        />
        <Button
          v-else
          variant="outline"
          size="sm"
          class="w-full justify-start text-muted-foreground"
          @click="addingColumn = true; newColumnName = ''"
        >
          <PlusIcon />
          Add column
        </Button>
      </div>
    </div>

    <Separator />

    <!-- Notes -->
    <div class="space-y-2">
      <div class="flex items-center gap-2">
        <h2 class="text-lg font-semibold tracking-tight">Notes</h2>
        <SaveIndicator :state="noteState" />
        <Tabs v-model="notesTab" class="ml-auto">
          <TabsList class="h-8">
            <TabsTrigger value="write" class="px-2.5 text-xs">Write</TabsTrigger>
            <TabsTrigger value="preview" class="px-2.5 text-xs">Preview</TabsTrigger>
          </TabsList>
        </Tabs>
      </div>
      <Textarea
        v-if="notesTab === 'write'"
        v-model="notes"
        placeholder="Plans, links, markdown…"
        class="min-h-40 font-mono text-sm"
      />
      <div v-else class="min-h-40 rounded-md border bg-card px-4 py-3">
        <MarkdownView v-if="notes.trim()" :source="notes" />
        <p v-else class="text-sm text-muted-foreground">Nothing to preview yet.</p>
      </div>
    </div>

    <!-- Edit dialog -->
    <Dialog v-model:open="editOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Edit project</DialogTitle>
        </DialogHeader>
        <div class="space-y-4">
          <div class="space-y-2">
            <Label for="edit-name">Name</Label>
            <Input id="edit-name" v-model="editName" @keyup.enter="saveEdit" />
          </div>
          <div class="space-y-2">
            <Label for="edit-desc">Description</Label>
            <Input id="edit-desc" v-model="editDescription" />
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="editOpen = false">Cancel</Button>
          <Button :disabled="!editName.trim()" @click="saveEdit">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Archive confirm (projects with repos: offers GitHub write-back) -->
    <Dialog v-model:open="archiveOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>{{ project.archived ? 'Restore' : 'Archive' }} {{ project.name }}?</DialogTitle>
          <DialogDescription>
            {{
              project.archived
                ? 'Brings the card back to the grid.'
                : 'Hides the card from the grid — find it again under the Archived filter.'
            }}
          </DialogDescription>
        </DialogHeader>
        <div class="flex items-center gap-2">
          <Checkbox id="archive-gh" v-model="archiveGithub" />
          <Label for="archive-gh" class="font-normal">
            Also {{ project.archived ? 'unarchive' : 'archive' }}
            {{ project.repos.length }} repo{{ project.repos.length === 1 ? '' : 's' }} on GitHub
          </Label>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="archiveOpen = false">Cancel</Button>
          <Button @click="doArchive">{{ project.archived ? 'Restore' : 'Archive' }}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Task detail dialog -->
    <Dialog :open="taskDetail !== null" @update:open="(v) => !v && (taskDetail = null)">
      <DialogContent class="flex max-h-[90vh] flex-col sm:max-w-2xl lg:max-w-3xl">
        <DialogHeader>
          <DialogTitle class="flex items-center gap-2">
            Task
            <Badge v-if="taskDetail?.source" variant="secondary" class="text-[10px]">
              filed by {{ taskDetail.source }}
            </Badge>
          </DialogTitle>
        </DialogHeader>
        <div class="flex min-h-0 flex-1 flex-col gap-4 overflow-y-auto">
          <div class="shrink-0 space-y-2">
            <Label for="task-title">Title</Label>
            <Input id="task-title" v-model="taskTitle" @keyup.enter="saveTask" />
          </div>
          <div class="shrink-0 space-y-1.5">
            <Label for="task-agent">Assignee</Label>
            <Select
              v-if="implementers.length"
              :model-value="taskAgent || 'unassigned'"
              @update:model-value="taskAgent = $event === 'unassigned' ? '' : ($event as string)"
            >
              <SelectTrigger id="task-agent" class="h-8 w-64 text-sm">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="unassigned">unassigned</SelectItem>
                <SelectItem v-for="p in implementers" :key="p.name" :value="p.name">
                  {{ p.character ? `${p.character} (${p.name})` : p.name }}
                </SelectItem>
              </SelectContent>
            </Select>
            <Input
              v-else
              id="task-agent"
              v-model="taskAgent"
              placeholder="agent name (blank = unassigned)"
              class="h-8 w-64 text-sm"
            />
            <p class="text-xs text-muted-foreground">
              Routes the loop: an assigned task in Todo gets picked up; in Staffed the
              assignee is the agent that executes it.
            </p>
          </div>
          <div class="flex min-h-0 flex-1 flex-col space-y-2">
            <div class="flex shrink-0 items-center gap-2">
              <Label>Details</Label>
              <Tabs v-model="taskTab" class="ml-auto">
                <TabsList class="h-7">
                  <TabsTrigger value="write" class="px-2 text-xs">Write</TabsTrigger>
                  <TabsTrigger value="preview" class="px-2 text-xs">Preview</TabsTrigger>
                </TabsList>
              </Tabs>
            </div>
            <Textarea
              v-if="taskTab === 'write'"
              v-model="taskDescription"
              placeholder="Evidence, acceptance criteria, links… (markdown)"
              class="min-h-48 flex-1 font-mono text-xs"
            />
            <div v-else class="min-h-48 flex-1 overflow-y-auto rounded-md border bg-card px-4 py-3">
              <MarkdownView v-if="taskDescription.trim()" :source="taskDescription" />
              <p v-else class="text-sm text-muted-foreground">No details yet.</p>
            </div>
          </div>
          <div class="shrink-0 space-y-2">
            <Label>Comments</Label>
            <div v-for="c in comments" :key="c.id" class="rounded-md border bg-card px-3 py-2">
              <div class="flex items-center gap-2">
                <Badge variant="secondary" class="text-[9px]">{{ c.author }}</Badge>
                <span class="text-[10px] text-muted-foreground">{{ c.created_at }}</span>
              </div>
              <div class="mt-1.5 text-sm">
                <MarkdownView :source="c.body" />
              </div>
            </div>
            <p v-if="!comments.length && !commentsLoading" class="text-sm text-muted-foreground">
              No comments yet — ask the filing persona a question and the loop will answer here.
            </p>
            <Textarea
              v-model="newComment"
              placeholder="Write a comment… (markdown)"
              class="min-h-16 text-sm"
            />
            <div class="flex justify-end">
              <Button size="sm" :disabled="!newComment.trim()" @click="postComment">Comment</Button>
            </div>
          </div>
        </div>
        <DialogFooter>
          <Button variant="ghost" @click="taskDetail = null">Cancel</Button>
          <Button :disabled="!taskTitle.trim()" @click="saveTask">Save</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>

    <!-- Add repo dialog -->
    <Dialog v-model:open="addRepoOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Add a repo</DialogTitle>
          <DialogDescription>Unassigned repos only — sync first if one's missing.</DialogDescription>
        </DialogHeader>
        <Select v-model="repoToAdd">
          <SelectTrigger class="w-full">
            <SelectValue placeholder="Pick a repo" />
          </SelectTrigger>
          <SelectContent>
            <SelectItem v-for="r in unassigned" :key="r.full_name" :value="r.full_name">
              {{ r.full_name }}
            </SelectItem>
          </SelectContent>
        </Select>
        <DialogFooter>
          <Button variant="ghost" @click="addRepoOpen = false">Cancel</Button>
          <Button :disabled="!repoToAdd" @click="addRepo">Add</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  </div>
</template>

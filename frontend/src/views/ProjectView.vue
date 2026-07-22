<script setup lang="ts">
import {
  ArchiveIcon,
  ArchiveRestoreIcon,
  ArrowLeftIcon,
  CheckCircle2Icon,
  ExternalLinkIcon,
  GripVerticalIcon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
  XIcon,
} from '@lucide/vue'
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import draggable from 'vuedraggable'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
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
import { Textarea } from '@/components/ui/textarea'
import { useSync } from '@/composables/useSync'
import { api, ApiError } from '@/lib/api'
import { daysSincePush, freshness, relativeDays } from '@/lib/activity'
import type { Column, Project, ProjectStatus, Repo, Task } from '@/types'
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

async function toggleArchived() {
  if (!project.value) return
  const next = !project.value.archived
  try {
    const p = await api.setArchived(projectId, next)
    project.value.archived = p.archived
    toast.success(next ? 'Archived — hidden from the grid' : 'Restored to the grid')
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Archive failed')
  }
}

const deleteOpen = ref(false)

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

// ── Notes (debounced autosave) ────────────────────────────────────────────────

const notes = ref('')
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
          <h1 class="text-2xl font-bold tracking-tight">{{ project.name }}</h1>
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
        <Button variant="ghost" size="sm" class="text-destructive" @click="deleteOpen = true">
          <Trash2Icon />
          Delete
        </Button>
      </div>
    </div>

    <!-- Repos -->
    <div class="flex flex-wrap items-center gap-2">
      <div
        v-for="repo in project.repos"
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
                >
                  <span class="flex-1">{{ task.title }}</span>
                  <button
                    class="text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                    :aria-label="`Delete ${task.title}`"
                    @click="removeTask(col, task)"
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
        <span class="text-xs text-muted-foreground">
          {{ noteState === 'saving' ? 'Saving…' : noteState === 'error' ? 'Save failed — still editing locally' : 'Saved' }}
        </span>
      </div>
      <Textarea
        v-model="notes"
        placeholder="Plans, links, whatever…"
        class="min-h-40 font-mono text-sm"
      />
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

    <!-- Delete confirm -->
    <Dialog v-model:open="deleteOpen">
      <DialogContent>
        <DialogHeader>
          <DialogTitle>Delete {{ project.name }}?</DialogTitle>
          <DialogDescription>
            Columns, tasks, and notes are deleted; linked repos return to the unassigned pool.
          </DialogDescription>
        </DialogHeader>
        <DialogFooter>
          <Button variant="ghost" @click="deleteOpen = false">Cancel</Button>
          <Button variant="destructive" @click="deleteProject">Delete</Button>
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

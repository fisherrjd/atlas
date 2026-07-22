<script setup lang="ts">
import {
  ArchiveIcon,
  ArrowLeftIcon,
  ExternalLinkIcon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
  XIcon,
} from '@lucide/vue'
import { computed, onMounted, reactive, ref, watch } from 'vue'
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
import type { Project, Repo, Task, TaskStatus } from '@/types'
import { STATUS_LABELS, TASK_STATUSES, TASK_STATUS_LABELS } from '@/types'

const route = useRoute()
const router = useRouter()
const projectId = Number(route.params.id)

const project = ref<Project | null>(null)
const loading = ref(true)
const { syncTick } = useSync()

const taskColumns = reactive<Record<TaskStatus, Task[]>>({ todo: [], doing: [], done: [] })

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
    notes.value = p.notes
    for (const status of TASK_STATUSES) {
      taskColumns[status] = (p.tasks ?? []).filter((t) => t.status === status)
    }
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to load project')
    router.push('/')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(syncTick, load)

// ── Edit / delete ─────────────────────────────────────────────────────────────

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
    project.value = await api.updateProject(projectId, {
      name: editName.value.trim(),
      description: editDescription.value.trim(),
    })
    editOpen.value = false
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Save failed')
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
    project.value = await api.assignRepo(projectId, repoToAdd.value)
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

// ── Tasks ────────────────────────────────────────────────────────────────────

const newTask = ref('')

async function addTask() {
  const title = newTask.value.trim()
  if (!title) return
  try {
    const t = await api.addTask(projectId, title)
    taskColumns.todo.push(t)
    newTask.value = ''
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to add task')
  }
}

interface TaskChangeEvent {
  added?: { element: Task; newIndex: number }
  moved?: { element: Task; newIndex: number }
}

async function onTaskChange(status: TaskStatus, event: TaskChangeEvent) {
  const change = event.added ?? event.moved
  if (!change) return
  try {
    await api.moveTask(change.element.id, status, change.newIndex)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Move failed')
    await load()
  }
}

async function removeTask(status: TaskStatus, task: Task) {
  try {
    await api.deleteTask(task.id)
    taskColumns[status] = taskColumns[status].filter((t) => t.id !== task.id)
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
      project.value = await api.updateProject(projectId, { notes: value })
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
    <Skeleton class="h-40 w-full" />
  </div>

  <div v-else-if="project" class="space-y-6">
    <div class="flex flex-wrap items-start justify-between gap-3">
      <div class="space-y-1">
        <div class="flex items-center gap-3">
          <Button variant="ghost" size="icon-sm" aria-label="Back to board" @click="router.push('/')">
            <ArrowLeftIcon />
          </Button>
          <h1 class="text-2xl font-bold tracking-tight">{{ project.name }}</h1>
          <span
            v-if="dot"
            class="size-2.5 rounded-full"
            :class="DOT_CLASS[dot]"
            :title="`${dot} — ${pushed}`"
          />
          <Badge variant="secondary">{{ STATUS_LABELS[project.status] }}</Badge>
        </div>
        <p v-if="project.description" class="pl-11 text-sm text-muted-foreground">
          {{ project.description }}
        </p>
      </div>
      <div class="flex items-center gap-1">
        <Button variant="ghost" size="sm" @click="openEdit">
          <PencilIcon />
          Edit
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

    <!-- Task kanban -->
    <div class="space-y-3">
      <div class="flex items-center gap-3">
        <h2 class="text-lg font-semibold tracking-tight">Tasks</h2>
        <form class="flex flex-1 items-center gap-2" @submit.prevent="addTask">
          <Input v-model="newTask" placeholder="Add a task…" class="h-8 max-w-sm text-sm" />
          <Button type="submit" size="sm" variant="outline" :disabled="!newTask.trim()">Add</Button>
        </form>
      </div>
      <div class="grid gap-3 sm:grid-cols-3">
        <div
          v-for="status in TASK_STATUSES"
          :key="status"
          class="rounded-lg border bg-muted/40"
        >
          <div class="flex items-center gap-2 px-3 py-2">
            <h3 class="text-sm font-medium">{{ TASK_STATUS_LABELS[status] }}</h3>
            <Badge variant="secondary" class="text-[10px]">{{ taskColumns[status].length }}</Badge>
          </div>
          <draggable
            :list="taskColumns[status]"
            group="tasks"
            item-key="id"
            class="flex min-h-16 flex-col gap-1.5 p-2 pt-0"
            ghost-class="opacity-40"
            @change="(e: TaskChangeEvent) => onTaskChange(status, e)"
          >
            <template #item="{ element }">
              <div
                class="group flex cursor-grab items-center gap-2 rounded-md border bg-card px-2.5 py-1.5 text-sm"
                :class="status === 'done' ? 'text-muted-foreground line-through' : ''"
              >
                <span class="flex-1">{{ element.title }}</span>
                <button
                  class="text-muted-foreground opacity-0 transition-opacity hover:text-destructive group-hover:opacity-100"
                  :aria-label="`Delete ${element.title}`"
                  @click="removeTask(status, element)"
                >
                  <XIcon class="size-3.5" />
                </button>
              </div>
            </template>
          </draggable>
        </div>
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
            Tasks and notes are deleted; linked repos return to the unassigned pool.
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

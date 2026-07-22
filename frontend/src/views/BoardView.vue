<script setup lang="ts">
import { PlusIcon } from '@lucide/vue'
import { onMounted, reactive, ref, watch } from 'vue'
import { toast } from 'vue-sonner'
import type { ColumnChangeEvent } from '@/components/BoardColumn.vue'
import BoardColumn from '@/components/BoardColumn.vue'
import { Button } from '@/components/ui/button'
import { Checkbox } from '@/components/ui/checkbox'
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
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
import { Skeleton } from '@/components/ui/skeleton'
import { useSync } from '@/composables/useSync'
import { api, ApiError } from '@/lib/api'
import type { Project, ProjectStatus, Repo } from '@/types'
import { PROJECT_STATUSES, STATUS_LABELS } from '@/types'

const loading = ref(true)
const lastSyncedAt = ref<string | null>(null)
const columns = reactive<Record<ProjectStatus, Project[]>>({
  idea: [],
  backlog: [],
  active: [],
  paused: [],
  done: [],
})

const { syncTick } = useSync()

async function load() {
  try {
    const data = await api.board()
    lastSyncedAt.value = data.last_synced_at
    for (const status of PROJECT_STATUSES) {
      columns[status] = data.projects.filter((p) => p.status === status)
    }
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to load board')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(syncTick, load)

async function onColumnChange(status: ProjectStatus, event: ColumnChangeEvent) {
  // vuedraggable already applied the optimistic move to the arrays
  const change = event.added ?? event.moved
  if (!change) return
  try {
    await api.moveProject(change.element.id, status, change.newIndex)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Move failed')
    await load()
  }
}

// ── New project dialog ────────────────────────────────────────────────────────

const dialogOpen = ref(false)
const newName = ref('')
const newDescription = ref('')
const newStatus = ref<ProjectStatus>('idea')
const unassigned = ref<Repo[]>([])
const pickedRepos = ref<Set<string>>(new Set())

watch(dialogOpen, async (open) => {
  if (!open) return
  newName.value = ''
  newDescription.value = ''
  newStatus.value = 'idea'
  pickedRepos.value = new Set()
  unassigned.value = await api.repos(true).catch(() => [])
})

function toggleRepo(fullName: string, checked: boolean) {
  const next = new Set(pickedRepos.value)
  if (checked) next.add(fullName)
  else next.delete(fullName)
  pickedRepos.value = next
}

async function createProject() {
  if (!newName.value.trim()) return
  try {
    await api.createProject({
      name: newName.value.trim(),
      description: newDescription.value.trim(),
      status: newStatus.value,
      repos: [...pickedRepos.value],
    })
    dialogOpen.value = false
    toast.success(`Created ${newName.value.trim()}`)
    await load()
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Create failed')
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1 class="text-2xl font-bold tracking-tight">Board</h1>
        <p v-if="lastSyncedAt" class="text-xs text-muted-foreground">
          last synced {{ new Date(lastSyncedAt).toLocaleString() }}
        </p>
      </div>
      <Dialog v-model:open="dialogOpen">
        <DialogTrigger as-child>
          <Button size="sm">
            <PlusIcon />
            New project
          </Button>
        </DialogTrigger>
        <DialogContent class="max-h-[85vh] overflow-y-auto">
          <DialogHeader>
            <DialogTitle>New project</DialogTitle>
            <DialogDescription>
              Group one or more repos, or start a repo-less idea.
            </DialogDescription>
          </DialogHeader>
          <div class="space-y-4">
            <div class="space-y-2">
              <Label for="np-name">Name</Label>
              <Input id="np-name" v-model="newName" placeholder="osrs-ge" @keyup.enter="createProject" />
            </div>
            <div class="space-y-2">
              <Label for="np-desc">Description</Label>
              <Input id="np-desc" v-model="newDescription" placeholder="optional" />
            </div>
            <div class="space-y-2">
              <Label>Column</Label>
              <Select v-model="newStatus">
                <SelectTrigger class="w-full">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem v-for="s in PROJECT_STATUSES" :key="s" :value="s">
                    {{ STATUS_LABELS[s] }}
                  </SelectItem>
                </SelectContent>
              </Select>
            </div>
            <div v-if="unassigned.length" class="space-y-2">
              <Label>Repos (unassigned)</Label>
              <div class="max-h-48 space-y-1.5 overflow-y-auto rounded-md border p-2">
                <div v-for="r in unassigned" :key="r.full_name" class="flex items-center gap-2">
                  <Checkbox
                    :id="`np-${r.full_name}`"
                    :model-value="pickedRepos.has(r.full_name)"
                    @update:model-value="(v: boolean | 'indeterminate') => toggleRepo(r.full_name, v === true)"
                  />
                  <Label :for="`np-${r.full_name}`" class="text-xs font-normal">
                    {{ r.full_name }}
                  </Label>
                </div>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="ghost" @click="dialogOpen = false">Cancel</Button>
            <Button :disabled="!newName.trim()" @click="createProject">Create</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>

    <div v-if="loading" class="flex gap-4">
      <Skeleton v-for="i in 5" :key="i" class="h-72 w-64 shrink-0" />
    </div>
    <div v-else class="flex items-start gap-4 overflow-x-auto pb-4">
      <BoardColumn
        v-for="status in PROJECT_STATUSES"
        :key="status"
        :status="status"
        :label="STATUS_LABELS[status]"
        :projects="columns[status]"
        @change="onColumnChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { LayoutGridIcon, PlusIcon, ZapIcon } from '@lucide/vue'
import { computed, onMounted, ref, watch } from 'vue'
import { RouterLink, useRouter } from 'vue-router'
import { toast } from 'vue-sonner'
import ProjectCard from '@/components/ProjectCard.vue'
import FilterBar from '@/components/data/FilterBar.vue'
import SearchInput from '@/components/data/SearchInput.vue'
import EmptyState from '@/components/states/EmptyState.vue'
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
import { lastPush } from '@/lib/activity'
import type { NowProject, Project, ProjectStatus, Repo } from '@/types'
import { PROJECT_STATUSES, STATUS_LABELS } from '@/types'

const router = useRouter()
const loading = ref(true)
const lastSyncedAt = ref<string | null>(null)
const projects = ref<Project[]>([])
const nowProjects = ref<NowProject[]>([])
const search = ref('')
const filter = ref<'all' | 'archived' | ProjectStatus>('all')

const { syncTick } = useSync()

async function load() {
  try {
    const [data, now] = await Promise.all([api.board(true), api.now()])
    lastSyncedAt.value = data.last_synced_at
    projects.value = data.projects
    nowProjects.value = now
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Failed to load projects')
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(syncTick, load)

// focus, not inventory: cap the band, rank in-flight work first
const NOW_LIMIT = 6

const nowVisible = computed(() => {
  const latestTask = (p: NowProject) =>
    p.tasks.reduce((max, t) => (t.updated_at > max ? t.updated_at : max), '')
  return [...nowProjects.value]
    .sort((a, b) => {
      if ((a.tasks.length > 0) !== (b.tasks.length > 0)) return a.tasks.length ? -1 : 1
      const la = latestTask(a)
      const lb = latestTask(b)
      if (la !== lb) return lb.localeCompare(la)
      return a.name.localeCompare(b.name)
    })
    .slice(0, NOW_LIMIT)
})

const nowOverflow = computed(() => Math.max(0, nowProjects.value.length - NOW_LIMIT))

const counts = computed(() => {
  const live = projects.value.filter((p) => !p.archived)
  const c: Record<string, number> = {
    all: live.length,
    archived: projects.value.length - live.length,
  }
  for (const s of PROJECT_STATUSES) {
    c[s] = live.filter((p) => p.status === s).length
  }
  return c
})

const visible = computed(() => {
  const q = search.value.trim().toLowerCase()
  return projects.value
    .filter((p) =>
      filter.value === 'archived'
        ? p.archived
        : !p.archived && (filter.value === 'all' || p.status === filter.value),
    )
    .filter(
      (p) =>
        q === '' ||
        p.name.toLowerCase().includes(q) ||
        p.description.toLowerCase().includes(q) ||
        // archived repo names only count as a match on the Archived tab
        p.repos.some(
          (r) =>
            (filter.value === 'archived' || !r.archived) &&
            r.full_name.toLowerCase().includes(q),
        ),
    )
    .sort((a, b) => {
      const pa = lastPush(a)
      const pb = lastPush(b)
      if (pa !== pb) return (pb ?? '').localeCompare(pa ?? '')
      return a.name.localeCompare(b.name)
    })
})

const filtersActive = computed(() => search.value.trim() !== '' || filter.value !== 'all')

// archived repos live ONLY here: loaded on demand when the Archived tab opens
const archivedRepos = ref<Repo[]>([])
watch(filter, async (f) => {
  if (f === 'archived') {
    archivedRepos.value = await api.repos(false, true).catch(() => [])
  }
})

const projectName = (id: number | null) => projects.value.find((p) => p.id === id)?.name

function clearFilters() {
  search.value = ''
  filter.value = 'all'
}

async function setStatus(project: Project, status: ProjectStatus) {
  const previous = project.status
  project.status = status // optimistic
  try {
    await api.setProjectStatus(project.id, status)
  } catch (e) {
    project.status = previous
    toast.error(e instanceof ApiError ? e.message : 'Status change failed')
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
    const created = await api.createProject({
      name: newName.value.trim(),
      description: newDescription.value.trim(),
      status: newStatus.value,
      repos: [...pickedRepos.value],
    })
    dialogOpen.value = false
    toast.success(`Created ${created.name}`)
    router.push(`/p/${created.id}`)
  } catch (e) {
    toast.error(e instanceof ApiError ? e.message : 'Create failed')
  }
}
</script>

<template>
  <div class="space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h1
          class="bg-gradient-to-r from-foreground to-foreground/60 bg-clip-text text-2xl font-bold tracking-tight text-transparent"
        >
          Projects
        </h1>
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
              <Label>Status</Label>
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

    <FilterBar :count="visible.length" :active="filtersActive" @clear="clearFilters">
      <SearchInput v-model="search" placeholder="Search projects…" />
      <div class="flex flex-wrap items-center gap-1">
        <Button
          v-for="s in ['all', ...PROJECT_STATUSES, 'archived'] as const"
          :key="s"
          :variant="filter === s ? 'secondary' : 'ghost'"
          size="xs"
          @click="filter = s"
        >
          {{ s === 'all' ? 'All' : s === 'archived' ? 'Archived' : STATUS_LABELS[s] }}
          <span class="text-muted-foreground">{{ counts[s] }}</span>
        </Button>
      </div>
    </FilterBar>

    <!-- Now: active projects and what's actually in flight -->
    <section
      v-if="!loading && nowProjects.length && filter === 'all' && !search.trim()"
      class="space-y-3 rounded-xl border bg-muted/40 p-4 shadow-[inset_0_1px_6px_rgb(0_0_0/0.12)]"
    >
      <div class="flex items-center gap-2">
        <ZapIcon class="size-4 text-primary" />
        <h2 class="text-base font-semibold tracking-wide">Now</h2>
        <Badge variant="secondary" class="text-[10px]">{{ nowProjects.length }}</Badge>
      </div>
      <div class="grid gap-2.5 [grid-template-columns:repeat(auto-fill,minmax(230px,1fr))]">
        <RouterLink
          v-for="p in nowVisible"
          :key="p.id"
          :to="`/p/${p.id}`"
          class="card-hover group block rounded-lg border border-l-[3px] !border-l-primary bg-card p-2.5"
        >
          <span class="text-sm font-medium transition-colors group-hover:text-primary">
            {{ p.name }}
          </span>
          <ul v-if="p.tasks.length" class="mt-1.5 space-y-1">
            <li v-for="t in p.tasks.slice(0, 4)" :key="t.id" class="flex items-center gap-2 text-xs">
              <span class="size-1.5 shrink-0 rounded-full bg-primary/70" />
              <span class="truncate">{{ t.title }}</span>
              <span class="ml-auto shrink-0 text-[10px] text-muted-foreground">
                {{ t.column_name }}
              </span>
            </li>
            <li v-if="p.tasks.length > 4" class="pl-3.5 text-[10px] text-muted-foreground">
              +{{ p.tasks.length - 4 }} more
            </li>
          </ul>
          <p v-else class="mt-1.5 text-xs italic text-muted-foreground/60">
            nothing in flight —
            <span class="underline decoration-dotted underline-offset-2">add a task</span>
          </p>
        </RouterLink>
      </div>
      <button
        v-if="nowOverflow > 0"
        class="text-xs text-muted-foreground underline decoration-dotted underline-offset-2 transition-colors hover:text-foreground"
        @click="filter = 'active'"
      >
        +{{ nowOverflow }} more active
      </button>
    </section>

    <div v-if="!loading" class="flex items-center gap-2 pt-1">
      <LayoutGridIcon class="size-4 text-muted-foreground" />
      <h2 class="text-base font-semibold tracking-wide">All projects</h2>
      <Badge variant="secondary" class="text-[10px]">{{ visible.length }}</Badge>
    </div>

    <div v-if="loading" class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <Skeleton v-for="i in 8" :key="i" class="h-28" />
    </div>
    <EmptyState
      v-else-if="visible.length === 0"
      title="No projects match"
      description="Try a sync, or clear the search."
    >
      <template #action>
        <Button variant="outline" size="sm" @click="clearFilters">Clear filters</Button>
      </template>
    </EmptyState>
    <div v-else class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
      <ProjectCard
        v-for="(p, i) in visible"
        :key="p.id"
        class="rise-in"
        :style="{ animationDelay: `${Math.min(i, 8) * 40}ms` }"
        :project="p"
        @click="router.push(`/p/${p.id}`)"
        @set-status="(s) => setStatus(p, s)"
      />
    </div>

    <!-- Archived repos: the only place they appear anywhere in the app -->
    <section v-if="filter === 'archived' && archivedRepos.length" class="space-y-2 pt-2">
      <h2 class="text-base font-semibold tracking-wide">Archived repos</h2>
      <div class="rounded-md border">
        <div
          v-for="r in archivedRepos"
          :key="r.full_name"
          class="flex items-center gap-2 border-b px-3 py-1.5 text-xs last:border-b-0"
        >
          <a :href="r.url" target="_blank" class="truncate hover:underline">{{ r.full_name }}</a>
          <span v-if="r.language" class="text-muted-foreground">{{ r.language }}</span>
          <RouterLink
            v-if="r.project_id !== null && projectName(r.project_id)"
            :to="`/p/${r.project_id}`"
            class="ml-auto shrink-0 text-muted-foreground hover:underline"
          >
            in {{ projectName(r.project_id) }}
          </RouterLink>
        </div>
      </div>
    </section>
  </div>
</template>

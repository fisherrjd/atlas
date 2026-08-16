<script setup lang="ts">
import { EyeIcon, RefreshCwIcon, Volume2Icon, VolumeXIcon } from '@lucide/vue'
import { onMounted, onUnmounted, ref } from 'vue'
import { toast } from 'vue-sonner'
import EmptyState from '@/components/states/EmptyState.vue'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card } from '@/components/ui/card'
import { Skeleton } from '@/components/ui/skeleton'
import { api, ApiError } from '@/lib/api'

// read-only mirror of the orchestrator's state — traits are edited in its repo
interface Pulse {
  id: number
  pulse_type: string
  persona: string
  started_at: string
  status: string
  num_turns: number | null
  summary: string
  error: string | null
}

interface Ticket {
  id: number
  kind: string
  persona: string
  repo: string | null
  title: string
  severity: string
  state: string
  pr_url: string | null
  updated_at: string
}

interface Suppression {
  id: number
  fingerprint: string | null
  pattern: string | null
  reason: string
  hits: number
  expires_at: string | null
}

interface Persona {
  name: string
  description: string
  model: string
  effort: string
  timeout_s: number
  tools: string[]
  role: string
  avatar: string | null
}

const loading = ref(true)
const unreachable = ref(false)
const name = ref('Heimdall')
const pulses = ref<Pulse[]>([])
const tickets = ref<Ticket[]>([])
const suppressions = ref<Suppression[]>([])
const personas = ref<Persona[]>([])
const headerAvatarOk = ref(true)

// event chimes: opt-out persists; browsers reject play() before the first
// user interaction, so failures are swallowed rather than fought
const soundOn = ref(localStorage.getItem('heimdall-sound') !== 'off')
function toggleSound() {
  soundOn.value = !soundOn.value
  localStorage.setItem('heimdall-sound', soundOn.value ? 'on' : 'off')
}
function playChime(sound: 'ticket' | 'pr-open' | 'fail') {
  if (!soundOn.value) return
  new Audio(`/api/heimdall/sounds/${sound}.wav`).play().catch(() => {})
}

let knownTickets: Map<number, string> | null = null
function chimeOnChanges(next: Ticket[]) {
  if (knownTickets !== null) {
    for (const t of next) {
      const prev = knownTickets.get(t.id)
      if (prev === undefined) playChime('ticket')
      else if (prev !== t.state && t.state === 'in_pr') playChime('pr-open')
      else if (prev !== t.state && t.state === 'rejected') playChime('fail')
    }
  }
  knownTickets = new Map(next.map((t) => [t.id, t.state]))
}

async function load(silent = false) {
  if (!silent) loading.value = true
  unreachable.value = false
  try {
    const [health, p, t, s, per] = await Promise.all([
      api.heimdall<{ name: string }>('health'),
      api.heimdall<Pulse[]>('pulses'),
      api.heimdall<Ticket[]>('tickets'),
      api.heimdall<Suppression[]>('suppressions'),
      api.heimdall<Persona[]>('personas'),
    ])
    name.value = health.name
    pulses.value = p
    chimeOnChanges(t)
    tickets.value = t
    suppressions.value = s
    personas.value = per
  } catch (e) {
    unreachable.value = true
    if (e instanceof ApiError && e.status !== 502) toast.error(e.message)
  } finally {
    if (!silent) loading.value = false
  }
}

const POLL_MS = 30_000
let pollTimer: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  load()
  pollTimer = setInterval(() => load(true), POLL_MS)
})
onUnmounted(() => clearInterval(pollTimer))

const STATUS_CLASS: Record<string, string> = {
  ok: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  clean: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  'dry-run': 'bg-muted text-muted-foreground',
  'skipped-lock': 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  error: 'bg-destructive/15 text-destructive',
  timeout: 'bg-destructive/15 text-destructive',
  running: 'bg-primary/15 text-primary',
}

const STATE_CLASS: Record<string, string> = {
  open: 'bg-sky-500/15 text-sky-600 dark:text-sky-400',
  staffed: 'bg-primary/15 text-primary',
  in_pr: 'bg-amber-500/15 text-amber-600 dark:text-amber-400',
  merged: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400',
  rejected: 'bg-destructive/15 text-destructive',
}
</script>

<template>
  <div class="space-y-6">
    <div class="flex flex-wrap items-center gap-3">
      <div class="flex items-center gap-2">
        <img
          v-if="headerAvatarOk"
          :src="'/api/heimdall/avatars/heimdall.png'"
          alt=""
          class="size-8 rounded-md shadow-sm [image-rendering:pixelated]"
          @error="headerAvatarOk = false"
        />
        <span
          v-else
          class="grid size-8 place-items-center rounded-md bg-gradient-to-br from-primary to-primary/60 text-primary-foreground shadow-sm"
        >
          <EyeIcon class="size-4" />
        </span>
        <div>
          <h1
            class="bg-gradient-to-r from-foreground to-foreground/60 bg-clip-text text-2xl font-bold tracking-tight text-transparent"
          >
            {{ name }}
          </h1>
          <p class="text-xs text-muted-foreground">
            the watchman — read-only; traits live in the orchestrator repo
          </p>
        </div>
      </div>
      <div class="ml-auto flex items-center gap-1">
        <Button
          variant="ghost"
          size="sm"
          :title="soundOn ? 'Mute event chimes' : 'Unmute event chimes'"
          @click="toggleSound"
        >
          <Volume2Icon v-if="soundOn" />
          <VolumeXIcon v-else />
        </Button>
        <Button variant="ghost" size="sm" :disabled="loading" @click="load()">
          <RefreshCwIcon :class="loading ? 'animate-spin' : ''" />
          Refresh
        </Button>
      </div>
    </div>

    <div v-if="loading" class="space-y-3">
      <Skeleton class="h-24 w-full" />
      <Skeleton class="h-40 w-full" />
    </div>

    <EmptyState
      v-else-if="unreachable"
      title="Heimdall is unreachable"
      description="The orchestrator's display API (:3050 on eldo) isn't answering — is the orchestrator-api unit running?"
    >
      <template #action>
        <Button variant="outline" size="sm" @click="load">Retry</Button>
      </template>
    </EmptyState>

    <template v-else>
      <!-- Personas -->
      <section class="space-y-2">
        <h2 class="text-base font-semibold tracking-wide">Personas</h2>
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          <Card v-for="p in personas" :key="p.name" class="gap-2 p-3">
            <div class="flex items-center gap-2">
              <img
                v-if="p.avatar"
                :src="`/api/heimdall/avatars/${p.avatar}`"
                alt=""
                class="size-7 rounded [image-rendering:pixelated]"
              />
              <span class="text-sm font-medium">{{ p.name }}</span>
              <Badge variant="secondary" class="text-[10px]">{{ p.model }}</Badge>
              <Badge variant="outline" class="text-[10px]">{{ p.effort }}</Badge>
              <span class="ml-auto text-[10px] text-muted-foreground">
                {{ Math.round(p.timeout_s / 60) }}m cap
              </span>
            </div>
            <p class="line-clamp-2 text-xs text-muted-foreground">{{ p.description }}</p>
            <div class="flex flex-wrap gap-1">
              <Badge v-for="t in p.tools" :key="t" variant="outline" class="text-[9px] font-mono">
                {{ t }}
              </Badge>
            </div>
          </Card>
        </div>
      </section>

      <!-- Recent pulses -->
      <section class="space-y-2">
        <h2 class="text-base font-semibold tracking-wide">Recent pulses</h2>
        <div class="rounded-md border">
          <div
            v-for="p in pulses"
            :key="p.id"
            class="flex items-center gap-2 border-b px-3 py-1.5 text-xs last:border-b-0"
          >
            <span class="w-32 shrink-0 text-muted-foreground">{{ p.started_at }}</span>
            <span class="w-24 shrink-0 font-medium">{{ p.pulse_type }}</span>
            <span
              class="w-20 shrink-0 rounded px-1.5 py-0.5 text-center text-[10px] font-medium"
              :class="STATUS_CLASS[p.status] ?? 'bg-muted'"
            >
              {{ p.status }}
            </span>
            <span v-if="p.num_turns !== null" class="shrink-0 text-muted-foreground">
              {{ p.num_turns }}t
            </span>
            <span class="truncate text-muted-foreground">{{ p.summary || p.error }}</span>
          </div>
          <p v-if="!pulses.length" class="px-3 py-2 text-xs text-muted-foreground">
            No pulses yet.
          </p>
        </div>
      </section>

      <!-- Tickets -->
      <section class="space-y-2">
        <h2 class="text-base font-semibold tracking-wide">Tickets</h2>
        <div class="rounded-md border">
          <div
            v-for="t in tickets"
            :key="t.id"
            class="flex items-center gap-2 border-b px-3 py-1.5 text-xs last:border-b-0"
          >
            <span class="w-14 shrink-0 font-mono text-muted-foreground">orc#{{ t.id }}</span>
            <span
              class="w-16 shrink-0 rounded px-1.5 py-0.5 text-center text-[10px] font-medium"
              :class="STATE_CLASS[t.state] ?? 'bg-muted'"
            >
              {{ t.state }}
            </span>
            <Badge variant="outline" class="shrink-0 text-[9px]">{{ t.severity }}</Badge>
            <span class="truncate">{{ t.title }}</span>
            <a
              v-if="t.pr_url"
              :href="t.pr_url"
              target="_blank"
              class="shrink-0 text-primary hover:underline"
            >
              PR
            </a>
            <Badge variant="secondary" class="ml-auto shrink-0 text-[9px]">{{ t.persona }}</Badge>
          </div>
          <p v-if="!tickets.length" class="px-3 py-2 text-xs text-muted-foreground">
            No tickets yet.
          </p>
        </div>
      </section>

      <!-- Suppressions -->
      <section class="space-y-2">
        <h2 class="text-base font-semibold tracking-wide">Suppressions</h2>
        <div class="rounded-md border">
          <div
            v-for="s in suppressions"
            :key="s.id"
            class="flex items-center gap-2 border-b px-3 py-1.5 text-xs last:border-b-0"
          >
            <span class="font-mono">{{ s.fingerprint ?? `/${s.pattern}/` }}</span>
            <span v-if="s.reason" class="truncate text-muted-foreground">{{ s.reason }}</span>
            <span class="ml-auto shrink-0 text-muted-foreground">{{ s.hits }} hits</span>
            <span v-if="s.expires_at" class="shrink-0 text-muted-foreground">
              until {{ s.expires_at }}
            </span>
          </div>
          <p v-if="!suppressions.length" class="px-3 py-2 text-xs text-muted-foreground">
            No suppressions — add with <code class="font-mono">orc suppress</code>.
          </p>
        </div>
      </section>
    </template>
  </div>
</template>

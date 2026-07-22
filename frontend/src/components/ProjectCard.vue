<script setup lang="ts">
import { TrendingUpIcon, TriangleAlertIcon } from '@lucide/vue'
import { computed } from 'vue'
import { Badge } from '@/components/ui/badge'
import { Card } from '@/components/ui/card'
import { daysSincePush, freshness, mismatch, relativeDays } from '@/lib/activity'
import type { Project } from '@/types'

const props = defineProps<{ project: Project }>()

const dot = computed(() => freshness(props.project))
const hint = computed(() => mismatch(props.project))
const pushed = computed(() => relativeDays(daysSincePush(props.project)))
const languages = computed(() => {
  const langs = props.project.repos
    .map((r) => r.language)
    .filter((l): l is string => l !== null)
  return [...new Set(langs)].slice(0, 2)
})

const DOT_CLASS = {
  fresh: 'bg-emerald-500',
  cooling: 'bg-amber-500',
  dormant: 'bg-stone-400',
} as const
</script>

<template>
  <Card class="cursor-pointer gap-2 p-3 transition-colors hover:border-ring/60">
    <div class="flex items-center gap-2">
      <span
        v-if="dot"
        class="size-2 shrink-0 rounded-full"
        :class="DOT_CLASS[dot]"
        :title="`${dot} — ${pushed}`"
      />
      <span class="truncate text-sm font-medium">{{ project.name }}</span>
      <TriangleAlertIcon
        v-if="hint === 'stale'"
        class="ml-auto size-3.5 shrink-0 text-amber-600"
        title="In Active, but no pushes in 90+ days"
      />
      <TrendingUpIcon
        v-else-if="hint === 'moving'"
        class="ml-auto size-3.5 shrink-0 text-emerald-600"
        title="Parked here, but pushed within 30 days"
      />
    </div>
    <p v-if="project.description" class="line-clamp-2 text-xs text-muted-foreground">
      {{ project.description }}
    </p>
    <div class="flex flex-wrap items-center gap-1.5">
      <Badge v-for="lang in languages" :key="lang" variant="secondary" class="text-[10px]">
        {{ lang }}
      </Badge>
      <Badge v-if="project.repos.length > 1" variant="outline" class="text-[10px]">
        {{ project.repos.length }} repos
      </Badge>
      <Badge
        v-if="project.task_counts && project.task_counts.total > 0"
        variant="outline"
        class="text-[10px]"
      >
        {{ project.task_counts.done }}/{{ project.task_counts.total }} tasks
      </Badge>
      <span v-if="project.repos.length" class="ml-auto text-[10px] text-muted-foreground">
        {{ pushed }}
      </span>
    </div>
  </Card>
</template>

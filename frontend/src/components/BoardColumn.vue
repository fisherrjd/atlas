<script setup lang="ts">
import draggable from 'vuedraggable'
import { useRouter } from 'vue-router'
import { Badge } from '@/components/ui/badge'
import ProjectCard from '@/components/ProjectCard.vue'
import type { Project, ProjectStatus } from '@/types'

const props = defineProps<{
  status: ProjectStatus
  label: string
  projects: Project[]
}>()

export interface ColumnChangeEvent {
  added?: { element: Project; newIndex: number }
  moved?: { element: Project; newIndex: number; oldIndex: number }
  removed?: { element: Project; oldIndex: number }
}

const emit = defineEmits<{
  change: [status: ProjectStatus, event: ColumnChangeEvent]
}>()

const router = useRouter()

function onChange(event: ColumnChangeEvent) {
  emit('change', props.status, event)
}
</script>

<template>
  <div class="flex w-64 shrink-0 flex-col rounded-lg border bg-muted/40">
    <div class="flex items-center gap-2 px-3 py-2.5">
      <h2 class="text-sm font-semibold">{{ label }}</h2>
      <Badge variant="secondary" class="text-[10px]">{{ projects.length }}</Badge>
    </div>
    <draggable
      :list="projects"
      group="board"
      item-key="id"
      class="flex min-h-24 flex-1 flex-col gap-2 overflow-y-auto p-2 pt-0"
      ghost-class="opacity-40"
      @change="onChange"
    >
      <template #item="{ element }">
        <ProjectCard :project="element" @click="router.push(`/p/${element.id}`)" />
      </template>
    </draggable>
  </div>
</template>

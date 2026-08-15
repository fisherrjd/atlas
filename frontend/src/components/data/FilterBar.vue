<script setup lang="ts">
import { Button } from '@/components/ui/button'

// layout shell for search + filter controls; the parent owns the state
// and decides when filters count as "active".
defineProps<{
  /** matching row count, shown on the right */
  count?: number
  /** show the Clear button */
  active?: boolean
}>()

const emit = defineEmits<{ clear: [] }>()
</script>

<template>
  <div class="flex flex-wrap items-center gap-2">
    <slot />
    <div class="ml-auto flex items-center gap-2">
      <Button v-if="active" variant="ghost" size="xs" @click="emit('clear')">Clear</Button>
      <p v-if="count !== undefined" class="text-xs text-muted-foreground tabular-nums">
        {{ count }} result{{ count === 1 ? '' : 's' }}
      </p>
    </div>
  </div>
</template>

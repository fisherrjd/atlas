<script setup lang="ts">
import { SearchIcon, XIcon } from '@lucide/vue'
import { Input } from '@/components/ui/input'

defineProps<{ placeholder?: string }>()
const model = defineModel<string>({ default: '' })
</script>

<template>
  <div class="relative w-full max-w-xs">
    <SearchIcon
      class="pointer-events-none absolute top-1/2 left-2.5 size-4 -translate-y-1/2 text-muted-foreground"
    />
    <Input v-model="model" :placeholder="placeholder ?? 'Search…'" class="px-8" />
    <button
      v-if="model"
      class="absolute top-1/2 right-2 -translate-y-1/2 rounded p-0.5 text-muted-foreground transition-colors hover:text-foreground"
      aria-label="Clear search"
      @click="model = ''"
    >
      <XIcon class="size-3.5" />
    </button>
  </div>
</template>

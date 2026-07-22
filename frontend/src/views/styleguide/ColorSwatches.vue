<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { useTheme } from '@/composables/useTheme'
import { THEME_TOKENS } from '@/lib/themes'

const { theme, mode } = useTheme()
const values = ref<Record<string, string>>({})

function readTokens() {
  const style = getComputedStyle(document.documentElement)
  const next: Record<string, string> = {}
  for (const token of THEME_TOKENS) {
    next[token] = style.getPropertyValue(`--${token}`).trim()
  }
  values.value = next
}

// swatch colors are live CSS; the text readouts need a re-read after the
// data-theme / .dark mutation lands
onMounted(readTokens)
watch([theme, mode], () => requestAnimationFrame(readTokens))

const hasForeground = (token: string) =>
  (THEME_TOKENS as readonly string[]).includes(`${token}-foreground`)
</script>

<template>
  <div class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4">
    <div v-for="token in THEME_TOKENS" :key="token" class="overflow-hidden rounded-lg border">
      <div
        class="flex h-14 items-center justify-center border-b"
        :style="{ backgroundColor: `hsl(var(--${token}))` }"
      >
        <span
          v-if="hasForeground(token)"
          class="text-lg font-medium"
          :style="{ color: `hsl(var(--${token}-foreground))` }"
        >
          Aa
        </span>
      </div>
      <div class="space-y-0.5 bg-card p-2">
        <p class="font-mono text-xs font-medium">--{{ token }}</p>
        <p class="font-mono text-xs text-muted-foreground">{{ values[token] }}</p>
      </div>
    </div>
  </div>
</template>

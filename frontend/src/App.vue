<script setup lang="ts">
import { CompassIcon, RefreshCwIcon } from '@lucide/vue'
import { RouterLink, RouterView, useRoute } from 'vue-router'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { Button } from '@/components/ui/button'
import { Toaster } from '@/components/ui/sonner'
import { useSync } from '@/composables/useSync'
import { useTheme } from '@/composables/useTheme'

const { syncing, runSync } = useSync()
const { theme, mode } = useTheme()
const route = useRoute()

// Projects stays lit on project detail pages too
function isActive(to: string) {
  if (to === '/') return route.path === '/' || route.path.startsWith('/p/')
  return route.path === to || route.path.startsWith(`${to}/`)
}
</script>

<template>
  <div class="flex min-h-screen flex-col bg-background text-foreground">
    <header class="sticky top-0 z-40 border-b bg-background/80 backdrop-blur">
      <div class="mx-auto flex h-14 w-full max-w-7xl items-center gap-5 px-4">
        <RouterLink to="/" class="flex shrink-0 items-center gap-2 font-semibold tracking-tight">
          <span
            class="grid size-6 place-items-center rounded-md bg-gradient-to-br from-primary to-primary/60 text-primary-foreground shadow-sm"
          >
            <CompassIcon class="size-3.5" />
          </span>
          Atlas
        </RouterLink>
        <nav class="flex items-center gap-4 text-sm text-muted-foreground">
          <RouterLink
            v-for="link in [
              { to: '/', label: 'Projects' },
              { to: '/heimdall', label: 'Heimdall' },
            ]"
            :key="link.to"
            :to="link.to"
            class="relative py-1 whitespace-nowrap transition-colors hover:text-foreground"
            :class="
              isActive(link.to)
                ? 'text-foreground after:absolute after:-bottom-0.5 after:left-0 after:h-0.5 after:w-full after:rounded-full after:bg-primary'
                : ''
            "
          >
            {{ link.label }}
          </RouterLink>
        </nav>
        <div class="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" :disabled="syncing" @click="runSync">
            <RefreshCwIcon :class="syncing ? 'animate-spin' : ''" />
            Sync
          </Button>
          <ThemeToggle />
        </div>
      </div>
    </header>
    <main class="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
      <RouterView v-slot="{ Component }">
        <Transition name="page" mode="out-in">
          <component :is="Component" />
        </Transition>
      </RouterView>
    </main>
    <footer class="border-t">
      <div
        class="mx-auto flex w-full max-w-7xl items-center justify-between px-4 py-4 text-xs text-muted-foreground"
      >
        <span>atlas — built from app-template</span>
        <span class="inline-flex items-center gap-1.5" title="current theme">
          <span class="size-1.5 rounded-full bg-primary" />
          {{ theme }} · {{ mode }}
        </span>
      </div>
    </footer>
    <Toaster position="bottom-right" />
  </div>
</template>

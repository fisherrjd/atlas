<script setup lang="ts">
import { RefreshCwIcon } from '@lucide/vue'
import { RouterLink, RouterView } from 'vue-router'
import ThemePicker from '@/components/ThemePicker.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { Button } from '@/components/ui/button'
import { Toaster } from '@/components/ui/sonner'
import { useSync } from '@/composables/useSync'

const { syncing, runSync } = useSync()
</script>

<template>
  <div class="flex min-h-screen flex-col bg-background text-foreground">
    <header class="border-b bg-card">
      <div class="mx-auto flex h-14 w-full max-w-7xl items-center gap-6 px-4">
        <RouterLink to="/" class="font-semibold tracking-tight">Atlas</RouterLink>
        <nav class="flex items-center gap-4 text-sm text-muted-foreground">
          <RouterLink
            to="/"
            class="transition-colors hover:text-foreground"
            active-class="text-foreground"
          >
            Board
          </RouterLink>
          <RouterLink
            to="/styleguide"
            class="transition-colors hover:text-foreground"
            active-class="text-foreground"
          >
            Styleguide
          </RouterLink>
        </nav>
        <div class="ml-auto flex items-center gap-1">
          <Button variant="ghost" size="sm" :disabled="syncing" @click="runSync">
            <RefreshCwIcon :class="syncing ? 'animate-spin' : ''" />
            Sync
          </Button>
          <ThemePicker />
          <ThemeToggle />
        </div>
      </div>
    </header>
    <main class="mx-auto w-full max-w-7xl flex-1 px-4 py-8">
      <RouterView />
    </main>
    <footer class="border-t">
      <div class="mx-auto w-full max-w-7xl px-4 py-4 text-xs text-muted-foreground">
        atlas — built from app-template
      </div>
    </footer>
    <Toaster position="bottom-right" />
  </div>
</template>

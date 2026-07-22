<script setup lang="ts">
import ThemePicker from '@/components/ThemePicker.vue'
import ThemeToggle from '@/components/ThemeToggle.vue'
import { Separator } from '@/components/ui/separator'
import ColorSwatches from './ColorSwatches.vue'
import ComponentGallery from './ComponentGallery.vue'
import TypeScale from './TypeScale.vue'
</script>

<template>
  <div class="space-y-10">
    <div class="flex flex-wrap items-center justify-between gap-4">
      <div class="space-y-1">
        <h1 class="text-3xl font-bold tracking-tight">Styleguide</h1>
        <p class="text-muted-foreground">
          Live view of the current theme. Edit
          <code class="rounded bg-muted px-1.5 py-0.5 font-mono text-xs">src/assets/themes/*.css</code>
          and watch this page repaint.
        </p>
      </div>
      <div class="flex items-center gap-1">
        <ThemePicker />
        <ThemeToggle />
      </div>
    </div>

    <section class="space-y-4">
      <h2 class="text-xl font-semibold tracking-tight">Colors</h2>
      <ColorSwatches />
    </section>

    <Separator />

    <section class="space-y-4">
      <h2 class="text-xl font-semibold tracking-tight">Typography</h2>
      <TypeScale />
    </section>

    <Separator />

    <section class="space-y-4">
      <h2 class="text-xl font-semibold tracking-tight">Components</h2>
      <ComponentGallery />
    </section>
  </div>
</template>

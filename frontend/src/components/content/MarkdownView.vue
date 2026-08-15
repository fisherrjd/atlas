<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'

// markdown → sanitized HTML, styled by .md-prose (assets/index.css).
// safe for user-supplied content thanks to DOMPurify.
const props = defineProps<{ source: string }>()

const html = computed(() => DOMPurify.sanitize(marked.parse(props.source, { async: false })))
</script>

<template>
  <div class="md-prose" v-html="html" />
</template>

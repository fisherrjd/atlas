import { ref } from 'vue'
import { toast } from 'vue-sonner'
import { api, ApiError } from '@/lib/api'

// module-scope singleton: the header button triggers it, views watch syncTick
const syncing = ref(false)
const syncTick = ref(0)

export function useSync() {
  async function runSync() {
    if (syncing.value) return
    syncing.value = true
    try {
      const r = await api.sync()
      toast.success(`Synced: ${r.created} new, ${r.updated} updated`)
      syncTick.value++
    } catch (e) {
      toast.error(e instanceof ApiError ? e.message : 'Sync failed')
    } finally {
      syncing.value = false
    }
  }
  return { syncing, syncTick, runSync }
}

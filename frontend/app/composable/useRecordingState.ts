// frontend/app/composable/useRecordingState.ts
import { ref, onMounted, onBeforeUnmount, watch } from 'vue'
import { useProjectStore } from '@/stores/project'

export function useRecordingState(pollMs = 1000, backendBase?: string) {
  const project = useProjectStore()
  const base = ref(backendBase ?? project.backendUrl) // allow override

  const active = ref(false)
  const count = ref(0)
  const elapsed_ms = ref(0)
  let timer: number | null = null

  async function tick() {
    try {
      const r = await fetch(`${base.value}/record/state`, { cache: 'no-store' })
      if (!r.ok) return
      const s = await r.json()
      active.value = !!s.active
      count.value = Number(s.count || 0)
      elapsed_ms.value = Number(s.elapsed_ms || 0)
    } catch { /* ignore */ }
  }

  function start() {
    if (timer) return
    timer = window.setInterval(tick, pollMs)
    tick()
  }
  function stop() {
    if (timer) { clearInterval(timer); timer = null }
  }

  // If backend URL can change at runtime, keep it in sync
  watch(() => project.backendUrl, (v) => { if (!backendBase) base.value = v })

  onMounted(start)
  onBeforeUnmount(stop)

  return { active, count, elapsed_ms, refresh: tick, start, stop }
}

<template>
  <div class="transport">
    <button class="btn" @click="store.stop()" title="Stop" aria-label="Stop">
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 6h12v12H6z" />
      </svg>
    </button>

    <button class="btn" v-if="!store.player.playing" @click="store.play()" title="Play" aria-label="Play">
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M8 5v14l11-7z" />
      </svg>
    </button>

    <button class="btn" v-else @click="store.pause()" title="Pause" aria-label="Pause">
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M6 19h4V5H6v14zm8-14v14h4V5h-4z" />
      </svg>
    </button>

    <button class="btn" @click="exportCsv" title="Export blended trajectory as CSV" aria-label="Export CSV">
      <svg class="icon" viewBox="0 0 24 24" aria-hidden="true">
        <path d="M5 20h14v-2H5v2zM12 3l5 5h-3v6h-4V8H7l5-5z" />
      </svg>
    </button>

    <div class="time">{{ (marker / 1000).toFixed(2) }}s</div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useProjectStore } from '@/stores/project'
const store = useProjectStore()

// Smooth, drift-corrected marker
const marker = computed(() => store.uiMarkerMs ?? store.player.t_ms)

/** 전체 타임라인 길이(ms) 추정 (lengthMs 있으면 그걸 우선) */
function getDurationMs(): number {
  let maxMs = store.lengthMs || 0
  for (const c of store.clips) {
    const s = store.sources[c.sourceId]
    if (!s) continue
    const frames = Math.max(1, c.outFrame - c.inFrame)
    const dur = frames * s.dt * 1000
    const end = Math.max(0, c.t0) + dur
    if (end > maxMs) maxMs = end
  }
  return Math.ceil(maxMs)
}

/** 기본 샘플 간격(ms): 모든 source의 최소 dt */
function getDefaultStepMs(): number {
  const dts = Object.values(store.sources).map(s => s.dt * 1000)
  if (dts.length === 0) return 33 /* fallback 30Hz */
  const ms = Math.max(1, Math.min(...dts))  // 최소 dt (>=1ms)
  return ms
}

async function exportCsv() {
  const t0_ms = 0
  const t1_ms = getDurationMs()
  const step_ms = getDefaultStepMs()

  const url = `${store.backendUrl}/motion/export_csv`
  const body = JSON.stringify({ t0_ms, t1_ms, step_ms, include_header: true })

  const res = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body
  })
  if (!res.ok) {
    const msg = await res.text().catch(() => 'Export failed')
    throw new Error(`Export failed: ${msg}`)
  }

  const blob = await res.blob()
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  const ts = new Date().toISOString().replace(/[:.]/g, '-')
  a.download = `trajectory_${ts}.csv`
  document.body.appendChild(a)
  a.click()
  URL.revokeObjectURL(a.href)
  a.remove()
}
</script>

<style scoped>
.transport {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding-bottom: 8px;
  background: var(--bg-1);
  border: 0 solid var(--line-1);
  border-radius: 10px;
}

.btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--bg-2);
  color: var(--text-0);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 16px;
  cursor: pointer;
}

.btn:focus-visible {
  outline: 2px solid var(--line-2);
  outline-offset: 2px;
}

.icon {
  width: 20px;
  height: 20px;
  fill: currentColor;
}

.time {
  color: var(--text-1);
  padding-left: 8px;
}
</style>

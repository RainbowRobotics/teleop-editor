<template>
  <div v-if="open" class="crop-dialog-backdrop" @click.self="onClose">
    <div class="crop-dialog">
      <div class="header">
        <div class="title">{{ source?.name || 'Source' }}</div>
        <button class="ghost" @click="onClose">✕</button>
      </div>

      <div class="meta">
        <div>Frames: {{ totalFrames }}</div>
        <div>dt: {{ source?.dt?.toFixed(3) }} s</div>
        <div>Duration: {{ (totalMs / 1000).toFixed(2) }} s</div>
      </div>

      <div ref="bar" class="mini-bar" @mousedown="onBarMouseDown" @mousemove="onBarMouseMove" @mouseup="onBarMouseUp"
        @mouseleave="onBarMouseUp">
        <div class="bar-bg"></div>

        <!-- 그래프 -->
        <canvas ref="sigCanvas" class="sig-canvas"></canvas>

        <!-- 선택 박스 -->
        <div class="sel" :style="{
          left: Math.round(selLeft) + 'px',
          width: Math.round(selWidth) + 'px'
        }">
          <div class="handle left" @mousedown.stop="onHandleDown('left', $event)"></div>
          <div class="handle right" @mousedown.stop="onHandleDown('right', $event)"></div>
        </div>

        <!-- 틱 -->
        <div class="ticks">
          <div v-for="x in tickXs" :key="x" class="tick" :style="{ left: Math.round(x) + 'px' }"></div>
        </div>
      </div>

      <div class="info">
        <div>In: frame {{ inFrame }} ({{ (inMs / 1000).toFixed(2) }}s)</div>
        <div>Out: frame {{ outFrame }} ({{ (outMs / 1000).toFixed(2) }}s)</div>
        <div>Len: {{ Math.max(0, (outMs - inMs) / 1000).toFixed(2) }}s</div>
      </div>

      <div class="actions">
        <button class="ghost" @click="onClose">Cancel</button>
        <button class="primary" @click="onConfirm">Add as Clip</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, reactive, ref, watch, nextTick } from 'vue'
import { useProjectStore, type Source } from '@/stores/project'

/* ------------ store ------------ */
const project = useProjectStore()

/* ------------ v-model ------------ */
const open = defineModel<boolean>('open', { required: true })
const sourceId = defineModel<string | null>('sourceId', { default: null })

/* ------------ source refs ------------ */
const source = computed<Source | null>(() => {
  if (!sourceId.value) return null
  return project.sources[sourceId.value] || null
})

const totalFrames = computed(() => source.value?.frames.length ?? 0)
const totalMs = computed(() => (source.value ? source.value.dt * totalFrames.value * 1000 : 0))

/* ------------ mini bar DOM / width ------------ */
const bar = ref<HTMLElement | null>(null)
const barW = ref(0)
const sigCanvas = ref<HTMLCanvasElement | null>(null)

let barRO: ResizeObserver | null = null
let sigRaf: number | undefined

function measureBarNow() {
  const el = bar.value
  if (!el) return
  const rect = el.getBoundingClientRect()
  barW.value = Math.max(0, Math.floor(rect.width))
}

let barROEntry: ResizeObserverEntry | null = null
function setupBarObserver() {
  if (!bar.value) return
  barRO = new ResizeObserver((entries) => {
    for (const entry of entries) {
      if (entry.target === bar.value) {
        barROEntry = entry
        barW.value = Math.max(0, Math.floor(entry.contentRect.width))
        scheduleSig()
      }
    }
  })
  barRO.observe(bar.value)
}

/* ------------ frames <-> px ------------ */
const pxPerFrame = computed(() => {
  const tf = totalFrames.value
  return tf > 0 ? barW.value / tf : 1
})

/* ------------ selection ------------ */
const inFrame = ref(0)
const outFrame = ref(0) // [in, out)

watch(source, (s) => {
  if (!s) return
  inFrame.value = 0
  outFrame.value = s.frames.length
  // 선택이 바뀌면 즉시 다시 그림
  scheduleSig()
})

const selLeft = computed(() => inFrame.value * pxPerFrame.value)
const selWidth = computed(() => Math.max(0, (outFrame.value - inFrame.value) * pxPerFrame.value))

const inMs = computed(() => (source.value ? inFrame.value * source.value.dt * 1000 : 0))
const outMs = computed(() => (source.value ? outFrame.value * source.value.dt * 1000 : 0))

/* ------------ ticks (1s 간격) ------------ */
const tickXs = computed(() => {
  const s = source.value
  if (!s || barW.value <= 0) return []
  const durMs = s.frames.length * s.dt * 1000
  const xs: number[] = []
  const stepMs = 1000
  for (let t = 0; t <= durMs + 0.1; t += stepMs) {
    const frameAt = Math.min(s.frames.length, Math.round(t / (s.dt * 1000)))
    const x = frameAt * pxPerFrame.value
    if (x <= barW.value) xs.push(x)
  }
  return xs
})

/* ------------ snapping ------------ */
const snap = reactive({ enabled: true })
function toFrameDelta(dxPx: number) {
  const f = dxPx / pxPerFrame.value
  return snap.enabled ? Math.round(f) : f
}

/* ------------ drag state ------------ */
type DragMode = 'none' | 'range' | 'left' | 'right'
const drag: { mode: DragMode; startX: number; startIn: number; startOut: number } = reactive({
  mode: 'none',
  startX: 0,
  startIn: 0,
  startOut: 0,
})

function onBarMouseDown(e: MouseEvent) {
  if (!bar.value || totalFrames.value <= 0) return
  drag.mode = 'range'
  drag.startX = e.clientX
  drag.startIn = inFrame.value
  drag.startOut = outFrame.value
}

function onBarMouseMove(e: MouseEvent) {
  if (drag.mode === 'none' || !bar.value || totalFrames.value <= 0) return
  const dx = e.clientX - drag.startX

  if (drag.mode === 'range') {
    let df = toFrameDelta(dx)
    let newIn = drag.startIn + df
    let newOut = drag.startOut + df
    // clamp
    if (newIn < 0) { newOut += -newIn; newIn = 0 }
    if (newOut > totalFrames.value) {
      const overshoot = newOut - totalFrames.value
      newIn -= overshoot; newOut = totalFrames.value
    }
    if (newOut - newIn < 1) newOut = newIn + 1
    inFrame.value = Math.round(newIn)
    outFrame.value = Math.round(newOut)
  } else if (drag.mode === 'left') {
    const df = toFrameDelta(dx)
    let nf = drag.startIn + df
    nf = Math.min(nf, outFrame.value - 1)
    nf = Math.max(0, nf)
    inFrame.value = Math.round(nf)
  } else if (drag.mode === 'right') {
    const df = toFrameDelta(dx)
    let nf = drag.startOut + df
    nf = Math.max(nf, inFrame.value + 1)
    nf = Math.min(totalFrames.value, nf)
    outFrame.value = Math.round(nf)
  }
}

function onBarMouseUp() { drag.mode = 'none' }
function onHandleDown(which: 'left' | 'right', e: MouseEvent) {
  e.preventDefault()
  drag.mode = which
  drag.startX = e.clientX
  drag.startIn = inFrame.value
  drag.startOut = outFrame.value
}

/* ------------ Alt = snap off ------------ */
function onKeyDown(e: KeyboardEvent) { if (e.altKey) snap.enabled = false }
function onKeyUp(e: KeyboardEvent) { if (!e.altKey) snap.enabled = true }

/* ------------ drawing ------------ */
const allJointCache = new Map<string, Float32Array>()  // key: `${sourceId}:${N}` → interleaved [24 * N]

function scheduleSig() {
  if (sigRaf) cancelAnimationFrame(sigRaf)
  sigRaf = requestAnimationFrame(drawSignal)
}

function drawSignal() {
  const el = sigCanvas.value
  const s = source.value
  if (!el || !s || barW.value <= 0) return

  const cssW = barW.value
  const cssH = el.clientHeight || 120
  const dpr = Math.max(1, window.devicePixelRatio || 1)

  el.width = Math.max(1, Math.round(cssW * dpr))
  el.height = Math.max(1, Math.round(cssH * dpr))

  const ctx = el.getContext('2d')!
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
  ctx.clearRect(0, 0, cssW, cssH)

  // grid
  ctx.strokeStyle = getCss('--line-2', '#2b3446')
  ctx.lineWidth = 1
  ctx.beginPath()
  for (let i = 1; i < 4; i++) { const x = (cssW / 4) * i + 0.5; ctx.moveTo(x, 0); ctx.lineTo(x, cssH) }
  ctx.stroke()

  // 샘플 수: 너비에 맞춰 충분히 촘촘하게
  const frames = s.frames
  const F = frames.length
  const N = Math.max(2, Math.min(2000, Math.floor(cssW))) // px당~1

  // interleaved [24*N] 버퍼 만들기 (조인트별 개별 정규화)
  const buf = new Float32Array(24 * N)

  for (let j = 0; j < 24; j++) {
    const off = j * N

    // 1) 다운샘플(선형보간)
    for (let i = 0; i < N; i++) {
      const u = (i * (F - 1)) / (N - 1)              // [0..F-1]
      const i0 = Math.floor(u)
      const i1 = Math.min(F - 1, i0 + 1)
      const t = u - i0
      const v0 = Number(frames[i0]?.[j]) || 0
      const v1 = Number(frames[i1]?.[j]) || 0
      buf[off + i] = v0 * (1 - t) + v1 * t
    }

    // 2) 정규화(0..1)
    let mn = Infinity, mx = -Infinity
    for (let i = 0; i < N; i++) {
      const v = buf[off + i] ?? 0
      if (v < mn) mn = v
      if (v > mx) mx = v
    }
    const span = Math.max(1e-6, mx - mn)
    for (let i = 0; i < N; i++) {
      buf[off + i] = ((buf[off + i] ?? 0) - mn) / span
    }
  }

  // 그림 스타일(라운드 조인/캡)
  ctx.lineJoin = 'round'
  ctx.lineCap = 'round'

  const baseColor = getCss('--text-dim', '#9aa3af')
  const hiColor = getCss('--accent', '#4fa3ff')
  const sel = project.graphJointIndex ?? 0

  const draw = (j: number, color: string, alpha: number, lw: number) => {
    const off = j * N
    ctx.save()
    ctx.globalAlpha = alpha
    ctx.strokeStyle = color
    ctx.lineWidth = lw
    ctx.beginPath()
    for (let i = 0; i < N; i++) {
      const t = i / (N - 1)
      const x = t * (cssW - 1)
      const y = (1 - (buf[off + i] ?? 0)) * (cssH - 20) + 10
      if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y)
    }
    ctx.stroke()
    ctx.restore()
  }

  for (let j = 0; j < 24; j++) if (j !== sel) draw(j, baseColor, 0.28, 1)
  draw(sel, hiColor, 1.0, 2)
}


/* ------------ utils ------------ */
function getCss(varName: string, fallback: string) {
  return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || fallback
}

const onWinResize = () => { measureBarNow(); scheduleSig() }

/* ------------ lifecycle ------------ */
onMounted(async () => {
  window.addEventListener('keydown', onKeyDown)
  window.addEventListener('keyup', onKeyUp)
  window.addEventListener('resize', onWinResize)

  await nextTick()
  setupBarObserver()

  // 다이얼로그가 열릴 때 즉시 측정 & 그림
  watch(open, (v) => {
    if (v) {
      nextTick(() => {
        measureBarNow()
        scheduleSig()
      })
    }
  }, { immediate: true })

  // source 변경 시에도 즉시 갱신
  watch(source, () => {
    nextTick(() => {
      measureBarNow()
      scheduleSig()
    })
  })
})

onBeforeUnmount(() => {
  window.removeEventListener('keydown', onKeyDown)
  window.removeEventListener('keyup', onKeyUp)
  window.removeEventListener('resize', onWinResize)

  try { barRO?.disconnect() } catch { }
  if (sigRaf) cancelAnimationFrame(sigRaf)
})

/* ------------ confirm ------------ */
const emit = defineEmits<{ (e: 'close'): void; (e: 'added'): void }>()
function onClose() {
  open.value = false
  emit('close')
}
function onConfirm() {
  const s = source.value
  if (!s) return
  project.addClipFromSource(s.id, {
    inFrame: inFrame.value,
    outFrame: outFrame.value,
    t0: project.lengthMs,
    name: s.name,
  })
  emit('added')
  onClose()
}
</script>

<style scoped>
/* layout */
.crop-dialog-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, .6);
  display: grid;
  place-items: center;
  z-index: 1000;
}

.crop-dialog {
  width: min(960px, 92vw);
  background: var(--bg-1);
  color: var(--text-0);
  border: 1px solid var(--line-1);
  border-radius: 12px;
  box-shadow: var(--shadow);
  padding: 14px;
  box-sizing: border-box;
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}

.title {
  font-weight: 600;
  letter-spacing: .2px;
}

.meta {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-1);
  margin-bottom: 8px;
}

/* mini bar */
.mini-bar {
  position: relative;
  width: 100%;
  height: 120px;
  /* 조금 여유 있게 */
  border: 1px solid var(--line-1);
  border-radius: 8px;
  background: var(--bg-2);
  margin-bottom: 10px;
  overflow: hidden;
  box-sizing: border-box;
  cursor: default;
  user-select: none;
}

.bar-bg {
  position: absolute;
  inset: 0;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), transparent);
}

/* graph canvas */
.sig-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  display: block;
  /* inline-canvas 줄바꿈 이슈 방지 */
  pointer-events: none;
}

/* selection */
.sel {
  position: absolute;
  top: 34px;
  height: 52px;
  background: rgba(79, 163, 255, .22);
  border: 1px solid rgba(79, 163, 255, .6);
  border-radius: 6px;
  box-sizing: border-box;
}

.handle {
  position: absolute;
  top: -4px;
  width: 8px;
  height: 60px;
  background: rgba(79, 163, 255, .95);
  border-radius: 4px;
  cursor: ew-resize;
}

.handle.left {
  left: -4px;
}

.handle.right {
  right: -4px;
}

/* ticks */
.ticks .tick {
  position: absolute;
  top: 8px;
  width: 1px;
  height: 16px;
  background: var(--line-2);
}

/* info & actions */
.info {
  display: flex;
  gap: 16px;
  font-size: 12px;
  color: var(--text-1);
  margin-bottom: 8px;
}

.actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

button.ghost {
  background: transparent;
  color: var(--text-1);
  border: 1px solid var(--line-1);
  border-radius: 8px;
  padding: 6px 10px;
}

button.primary {
  background: var(--accent);
  color: #0f1115;
  border: 0;
  border-radius: 8px;
  padding: 6px 12px;
  font-weight: 600;
}

button.primary:hover {
  filter: brightness(1.06);
}
</style>

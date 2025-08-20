<template>
  <div ref="timelineContainer" class="panel timeline-panel" tabindex="0">
    <div class="panel-title timeline-title">
      <span>Timeline</span>

      <!-- Joint + RMS controls -->
      <div class="joint-controls">
        <label class="lbl">Joint</label>
        <select v-model.number="project.graphJointIndex" :disabled="isRms"
          :title="isRms ? 'RMS 모드에서는 개별 조인트 선택이 비활성화됩니다.' : '표시할 조인트를 선택합니다.'">
          <option v-for="i in 24" :key="i - 1" :value="i - 1">#{{ i - 1 }}</option>
        </select>

        <label class="lbl">RMS</label>
        <label class="switch" :title="isRms ? '모든 조인트의 포지션 RMS' : '개별 조인트 값'">
          <input type="checkbox" :checked="isRms"
            @change="project.setGraphMode(($event.target as HTMLInputElement).checked ? 'rms' : 'joint')" />
          <span class="slider"></span>
        </label>
      </div>
    </div>

    <v-stage :config="{ width: Math.max(1, stageWidth), height: totalTimelineHeight }" @wheel="onWheel"
      @mousedown="onMouseDown" @mousemove="onMouseMove" @dblclick="onDblClick" @dbltap="onDblClick"
      @contextmenu="onContextMenu">
      <v-layer :key="'base-' + sparksVersion">
        <!-- 배경 -->
        <v-rect :config="{ x: 0, y: 0, width: stageWidth, height: totalTimelineHeight }" />

        <!-- 세로 그리드 -->
        <template v-for="t in ticks" :key="'grid-x-' + t.x">
          <v-line :config="{
            points: [t.x + timelineOffsetPx, 0, t.x + timelineOffsetPx, totalTimelineHeight],
            stroke: '#2a3242', strokeWidth: 1
          }" />
        </template>

        <!-- 가로 그리드 -->
        <template v-for="gy in gridRows" :key="'grid-y-' + gy">
          <v-line :config="{
            points: [0, gy, stageWidth, gy],
            stroke: '#253044', strokeWidth: 1
          }" />
        </template>

        <!-- 상단 바 -->
        <v-rect :config="{ x: 0, y: timelineY, width: stageWidth, height: timelineY, fill: '#2b3446' }" />

        <!-- 눈금 + 라벨 -->
        <template v-for="t in ticks" :key="'tick-' + t.x">
          <v-line :config="{
            points: [t.x + timelineOffsetPx, timelineY - 5, t.x + timelineOffsetPx, timelineY + 25],
            stroke: '#9aa3af', strokeWidth: 1
          }" />
          <v-text :config="{
            x: t.x + timelineOffsetPx + 2, y: timelineY + 28, text: t.label,
            fontSize: 10, fill: '#c8d0dc'
          }" />
        </template>

        <!-- 클립 바 -->
        <template v-for="clip in viewClips" :key="clip.id">
          <v-rect :config="{
            x: clipX(clip) + timelineOffsetPx,
            y: timelineY + 50 + clip.track * rowH,
            width: clipW(clip),
            height: rowH * 0.8,
            fill:
              project.selectedClipId === clip.id
                ? '#7ad1ff'
                : clip.dragging
                  ? '#ff9f4f'
                  : clip.hover
                    ? '#6fb8ff'
                    : '#4fa3ff',
            stroke: project.selectedClipId === clip.id ? '#ffffff' : undefined,
            strokeWidth: project.selectedClipId === clip.id ? 2 : 0,
            cornerRadius: 4
          }" />
          <v-text :config="{
            x: clipX(clip) + timelineOffsetPx + 4,
            y: timelineY + 52 + clip.track * rowH,
            text: sources[clip.sourceId]?.name || clip.id,
            fontSize: 12, fill: '#0f1115'
          }" />
        </template>

        <!-- 스파클라인 -->
        <template v-for="clip in viewClips" :key="'spark-'+clip.id+'-'+sparksVersion">
          <v-line :config="{
            points: sparkPointsForClip(clip),
            stroke: 'rgba(255,255,255,.7)', strokeWidth: 1,
            lineCap: 'round', lineJoin: 'round', listening: false
          }" />
        </template>

        <!-- 스냅 가이드 -->
        <v-line v-if="snapGuideXPx !== null" :config="{
          points: [snapGuideXPx, 0, snapGuideXPx, totalTimelineHeight],
          stroke: '#ffd166', strokeWidth: 1, dash: [4, 4]
        }" />

        <!-- 마커 (글로벌 동기화) -->
        <v-line :config="{
          points: [markerXPx + timelineOffsetPx, 0, markerXPx + timelineOffsetPx, totalTimelineHeight],
          stroke: '#ff4040', strokeWidth: 2
        }" />
        <v-text :config="{
          x: markerXPx + timelineOffsetPx + 6, y: 6,
          text: markerLabel, fontSize: 12, fill: '#ff8888'
        }" />
      </v-layer>
    </v-stage>
  </div>

  <!-- Naive UI: Context menu -->
  <n-dropdown trigger="manual" :x="ctx.x" :y="ctx.y" :options="ctx.options" :show="ctx.show" @select="onCtxSelect"
    @clickoutside="ctx.show = false" />

  <SourceCropDialog v-model:open="cropOpen" v-model:sourceId="cropSourceId" mode="edit"
    :initial-in-frame="cropInitialInFrame ?? undefined" :initial-out-frame="cropInitialOutFrame ?? undefined"
    confirm-label="Update Clip" @updated="onCropUpdated" @close="cropOpen = false" />

</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, reactive, watch, nextTick, h } from 'vue'
import { useProjectStore, type Source } from '@/stores/project'
import { storeToRefs } from 'pinia'
import { MotionClient, throttle } from '@/lib/motionClient'
import SourceCropDialog from '@/components/SourceCropDialog.vue'
import { useNotification, NDropdown, NButton } from 'naive-ui'

/* ---------- 레이아웃/상수 ---------- */
const DOF = 24
const timelineY = 20
const rowH = 35
const rowHeight = 40

/* ---------- 컨테이너 & 실제 폭 측정 ---------- */
const timelineContainer = ref<HTMLElement | null>(null)
const stageWidth = ref(1)               // v-stage에 전달하는 실제 content-box width
let contRO: ResizeObserver | null = null

function measureStageWidth() {
  const el = timelineContainer.value
  if (!el) return
  const w = el.clientWidth          // content-box width
  if (w > 0 && w !== stageWidth.value) {
    stageWidth.value = w
    clampOffset()
    genTicks()
    requestSparksRedraw()
  }
}

/* ---------- 스토어 ---------- */
const project = useProjectStore()
const { clips, sources, lengthMs } = storeToRefs(project)
const isRms = computed(() => project.graphJointMode === 'rms')

/* ---------- Motion WS ---------- */
let motion: MotionClient | null = null

/* ---------- 스케일/오프셋 ---------- */
const zoom = ref(0.1)               // px per ms
const timelineOffsetPx = ref(0)

const contentMs = computed(() => {
  if (lengthMs.value > 0) return lengthMs.value
  let maxEnd = 0
  for (const c of clips.value) {
    const s = sources.value[c.sourceId]
    if (!s) continue
    const dur = Math.round((c.outFrame - c.inFrame) * s.dt * 1000)
    maxEnd = Math.max(maxEnd, c.t0 + dur)
  }
  return maxEnd
})
const contentWidthPx = computed(() => contentMs.value * zoom.value)

/* ---------- 마커(글로벌 동기화) ---------- */
const markerXPx = ref(0)
// store의 drift 보정된 마커 사용; 없으면 player.t_ms
const externalMs = computed(() => (project as any).uiMarkerMs ?? project.player.t_ms)
const markerMs = computed(() => Math.max(0, markerXPx.value / zoom.value))
const markerLabel = computed(() =>
  markerMs.value >= 1000 ? `${(markerMs.value / 1000).toFixed(2)} s` : `${Math.round(markerMs.value)} ms`
)
// 재생 중에는 store 마커를 추종(드래그 중 제외)
watch(externalMs, (ms) => {
  if (isMarkerDragging.value) return
  const px = msToPx(ms)
  if (Math.abs(px - markerXPx.value) > 0.5) {
    markerXPx.value = px
    ensureMarkerVisible(px)
  }
})

/* ---------- 마우스 상태 ---------- */
const isMarkerDragging = ref(false)
const isTimelineDragging = ref(false)
let lastPointerX = 0

/* ---------- 클립 드래그/리사이즈 상태 ---------- */
const activeClipId = ref<string | null>(null)
const clipDragMode = ref<'none' | 'move' | 'resize-left' | 'resize-right'>('none')
let clipDragStartX = 0
let clipOriginalT0 = 0
let clipOriginalInFrame = 0
let clipOriginalOutFrame = 0

/* ---------- crop dialog state ---------- */
const cropOpen = ref(false)
const cropSourceId = ref<string | null>(null)
const cropInitialInFrame = ref<number | null>(null)
const cropInitialOutFrame = ref<number | null>(null)
const cropTargetClipId = ref<string | null>(null)

/* ---------- 컨텍스트 메뉴 & Undo 토스트 ---------- */
const notification = useNotification()
type CtxOption = { label: string; key: string }
const ctx = reactive({
  show: false,
  x: 0,
  y: 0,
  targetClipId: null as string | null,
  options: [{ label: '🗑 Delete', key: 'delete' }] as CtxOption[]
})

/* ---------- 좌표 변환 ---------- */
const pxPerMs = computed(() => zoom.value)
const msToPx = (ms: number) => ms * pxPerMs.value
const pxToMs = (px: number) => px / pxPerMs.value

/* ---------- 틱(눈금) ---------- */
type Tick = { x: number; label: string }
const ticks = ref<Tick[]>([])
function niceStep(msPerPx: number) {
  const targetPx = 80
  const wantMs = targetPx / msPerPx
  const base = [1, 2, 5, 10, 20, 50, 100, 200, 500, 1000, 2000, 5000, 10000]
  for (const s of base) if (s >= wantMs) return s
  return 20000
}
function formatMs(ms: number) {
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${Math.round(ms)}ms`
}
function genTicks() {
  const stepMs = niceStep(pxPerMs.value)
  const startVisibleMs = Math.max(0, -timelineOffsetPx.value / pxPerMs.value)
  const endVisibleMs = startVisibleMs + stageWidth.value / pxPerMs.value
  const startMs = Math.floor(startVisibleMs / stepMs) * stepMs
  const list: Tick[] = []
  for (let t = startMs; t <= endVisibleMs + stepMs; t += stepMs) {
    list.push({ x: msToPx(t), label: formatMs(t) })
  }
  ticks.value = list
}

/* ---------- Motion push ---------- */
const pushProject = throttle(() => motion?.setProject(project.toSnapshot()), 80)
const pushSeek = throttle((ms: number) => motion?.seek(Math.round(ms)), 33) // ~30Hz

watch([clips, sources, () => project.lengthMs], pushProject, { deep: true })
watch(markerMs, (ms) => pushSeek(ms))

/* ---------- 스냅 ---------- */
const snapGuideXPx = ref<number | null>(null)
const snap = reactive({ enabled: false, to: 'both' as 'grid' | 'clips' | 'both', thresholdPx: 8 })
function currentGridStepMs() { return niceStep(pxPerMs.value) }
function applySnapMs(candidateMs: number, excludeClipId?: string) {
  if (!snap.enabled) return { ms: candidateMs, guidePx: null }
  const step = currentGridStepMs()
  const gridTarget = Math.round(candidateMs / step) * step
  const clipTargets: number[] = []
  if (snap.to === 'clips' || snap.to === 'both') {
    for (const vc of viewClips.value) {
      if (vc.id === excludeClipId) continue
      clipTargets.push(vc.t0, vc.t0 + vc.durationMs)
    }
  }
  const candidates = [gridTarget, ...clipTargets]
  const thMs = pxToMs(snap.thresholdPx)
  let best = candidateMs, bestDist = Number.POSITIVE_INFINITY
  for (const t of candidates) {
    const d = Math.abs(t - candidateMs)
    if (d < bestDist) { bestDist = d; best = t }
  }
  if (bestDist <= thMs) {
    const guidePx = msToPx(best) + timelineOffsetPx.value
    return { ms: best, guidePx }
  }
  return { ms: candidateMs, guidePx: null }
}

/* ---------- 클립 뷰 모델 ---------- */
type ViewClip = ReturnType<typeof buildViewClips>[number]
const buildViewClips = () => {
  return clips.value.map((c, i) => {
    const s = sources.value[c.sourceId]
    const durationMs = s ? Math.round((c.outFrame - c.inFrame) * s.dt * 1000) : 0
    return { ...c, track: i, durationMs, hover: false, dragging: false }
  })
}
const viewClips = ref<ViewClip[]>([])
function refreshViewClips() {
  const prev = new Map(viewClips.value.map(vc => [vc.id, { hover: vc.hover, dragging: vc.dragging }]))
  viewClips.value = buildViewClips().map(vc => {
    const old = prev.get(vc.id)
    return { ...vc, hover: old?.hover ?? false, dragging: old?.dragging ?? false }
  })
}
const clipX = (clip: ViewClip) => msToPx(clip.t0)
const clipW = (clip: ViewClip) => msToPx(clip.durationMs)

/* ---------- 그리드 Y들 ---------- */
const gridRows = computed(() => {
  const ys: number[] = []
  const startY = timelineY + 50
  const rows = Math.max(1, Math.ceil(totalTimelineHeight.value / rowH))
  for (let i = 0; i <= rows; i++) ys.push(startY + i * rowH)
  ys.unshift(timelineY)
  return ys
})

/* ---------- 오프셋 클램프 ---------- */
function clampOffset() {
  const min = Math.min(0, stageWidth.value - contentWidthPx.value)
  if (timelineOffsetPx.value > 0) timelineOffsetPx.value = 0
  if (timelineOffsetPx.value < min) timelineOffsetPx.value = min
}

/** 마커 가시화 유지 */
function ensureMarkerVisible(markerPx: number, marginPx = 40) {
  const left = -timelineOffsetPx.value
  const right = left + stageWidth.value
  if (markerPx < left + marginPx) {
    timelineOffsetPx.value = -(markerPx - marginPx)
    clampOffset(); genTicks(); requestSparksRedraw()
  } else if (markerPx > right - marginPx) {
    timelineOffsetPx.value = -(markerPx - (right - marginPx))
    clampOffset(); genTicks(); requestSparksRedraw()
  }
}

/* ---------- 이벤트 ---------- */
function onWheel(e: any) {
  if (e.evt.ctrlKey) {
    e.evt.preventDefault()
    const scaleBy = 1.1
    const oldZoom = zoom.value
    const stage = e.target.getStage()
    const pos = stage?.getPointerPosition()
    const mouseX = pos?.x ?? stageWidth.value / 2
    const worldXBefore = (mouseX - timelineOffsetPx.value) / oldZoom

    const old_scale = zoom.value
    if (e.evt.deltaY < 0) zoom.value *= scaleBy
    else zoom.value /= scaleBy
    zoom.value = Math.min(2.0, Math.max(0.005, zoom.value))

    timelineOffsetPx.value = mouseX - worldXBefore * zoom.value
    clampOffset(); genTicks(); requestSparksRedraw()
  }
}

function onMouseDown(e: any) {
  timelineContainer.value?.focus()

  const pos = e.target.getStage().getPointerPosition()
  if (!pos) return
  lastPointerX = pos.x

  const hit = viewClips.value.find((vc) => {
    const x = clipX(vc) + timelineOffsetPx.value
    const y = timelineY + 50 + vc.track * rowH
    return (pos.x >= x && pos.x <= x + clipW(vc) && pos.y >= y && pos.y <= y + rowH * 0.8)
  })

  if (hit) {
    project.setSelectedClip?.(hit.id)
    activeClipId.value = hit.id
    hit.dragging = true
    clipDragStartX = pos.x
    clipOriginalT0 = hit.t0
    clipOriginalInFrame = hit.inFrame
    clipOriginalOutFrame = hit.outFrame
    clipDragMode.value = 'move'
    return
  }

  project.setSelectedClip?.(null)

  if (e.evt.button === 1) {
    isTimelineDragging.value = true
    return
  }

  if (e.evt.button === 0) {
    isMarkerDragging.value = true
    const rawMs = pxToMs(Math.max(0, pos.x - timelineOffsetPx.value))
    const { ms, guidePx } = applySnapMs(rawMs)
    markerXPx.value = msToPx(ms)
    snapGuideXPx.value = guidePx
    genTicks()
  }
}

function onMouseMove(e: any) {
  const stage = e.target.getStage()
  const container = stage.container()
  const pos = stage.getPointerPosition()
  if (!pos) return

  if (activeClipId.value) {
    const vc = viewClips.value.find(v => v.id === activeClipId.value); if (!vc) return
    const src = sources.value[vc.sourceId]; if (!src) return

    const dxPx = pos.x - clipDragStartX
    const dxMs = Math.round(pxToMs(dxPx))

    if (clipDragMode.value === 'move') {
      const candidate = Math.max(0, clipOriginalT0 + dxMs)
      const { ms: snapped, guidePx } = applySnapMs(candidate, vc.id)
      const c = clips.value.find(c => c.id === vc.id)
      if (c) c.t0 = snapped
      snapGuideXPx.value = guidePx
      setCursor(container, 'grabbing')
      refreshViewClips()
      requestSparksRedraw()
    }
    return
  }

  // hover 표시
  let hovering = false
  viewClips.value.forEach(vc => {
    const x = clipX(vc) + timelineOffsetPx.value
    const y = timelineY + 50 + vc.track * rowH
    vc.hover = pos.x >= x && pos.x <= x + clipW(vc) && pos.y >= y && pos.y <= y + rowH * 0.8
    if (vc.hover) hovering = true
  })
  setCursor(container, hovering ? 'grab' : 'default')

  if (isMarkerDragging.value) {
    const rawMs = pxToMs(Math.max(0, pos.x - timelineOffsetPx.value))
    const { ms, guidePx } = applySnapMs(rawMs)
    markerXPx.value = msToPx(ms)
    snapGuideXPx.value = guidePx
    // 일시정지 중이면 로컬 마커도 갱신 (다른 컴포넌트와 동기)
    if (!project.player.playing) {
      (project as any).setLocalMarker?.(Math.round(ms)) ?? (project.player.t_ms = Math.round(ms))
    }
    return
  }
  if (isTimelineDragging.value) {
    const dx = pos.x - lastPointerX
    timelineOffsetPx.value += dx
    lastPointerX = pos.x
    clampOffset(); genTicks(); requestSparksRedraw()
    return
  }
}

function onMouseUp() {
  const wasDraggingMarker = isMarkerDragging.value
  isMarkerDragging.value = false
  isTimelineDragging.value = false
  activeClipId.value = null
  clipDragMode.value = 'none'
  viewClips.value.forEach(v => (v.dragging = false))
  snapGuideXPx.value = null

  // 스크럽 커밋 → 전역 마커 반영
  if (wasDraggingMarker) {
    const ms = Math.max(0, Math.round(markerMs.value))
    if (project.player.playing) {
      project.play(ms).catch((e: any) => console.warn('play(seek) failed:', e))
    } else {
      (project as any).setLocalMarker?.(ms) ?? (project.player.t_ms = ms)
      project.seek(ms)
    }
  }
}

function onDblClick(e: any) {
  const btn = e?.evt?.button
  if (typeof btn === 'number' && btn !== 0) return

  const stage = e.target.getStage?.()
  const pos = stage?.getPointerPosition?.()
  if (!pos) return
  // hit-test for clip under cursor
  const hit = viewClips.value.find((vc) => {
    const x = clipX(vc) + timelineOffsetPx.value
    const y = timelineY + 50 + vc.track * rowH
    return (pos.x >= x && pos.x <= x + clipW(vc) && pos.y >= y && pos.y <= y + rowH * 0.8)
  })
  if (!hit) return
  cropSourceId.value = hit.sourceId
  cropInitialInFrame.value = hit.inFrame
  cropInitialOutFrame.value = hit.outFrame
  cropTargetClipId.value = hit.id
  cropOpen.value = true
}

function onCropUpdated(payload: { inFrame: number, outFrame: number }) {
  const id = cropTargetClipId.value
  if (!id) return
  const c = clips.value.find(c => c.id === id)
  if (c) {
    c.inFrame = payload.inFrame
    c.outFrame = payload.outFrame
  }
}

/** 우클릭 컨텍스트 메뉴 */
function onContextMenu(e: any) {
  e.evt?.preventDefault?.()
  const stage = e.target.getStage?.()
  const pos = stage?.getPointerPosition?.()
  if (!pos) return
  // 어떤 클립 위인지 hit-test
  const hit = viewClips.value.find((vc) => {
    const x = clipX(vc) + timelineOffsetPx.value
    const y = timelineY + 50 + vc.track * rowH
    return (pos.x >= x && pos.x <= x + clipW(vc) && pos.y >= y && pos.y <= y + rowH * 0.8)
  })
  if (!hit) { ctx.show = false; return }
  project.setSelectedClip?.(hit.id)
  ctx.targetClipId = hit.id
  // Naive UI Dropdown은 viewport 좌표를 기대 -> Konva의 원시 이벤트 clientX/Y 사용
  ctx.x = e.evt.clientX
  ctx.y = e.evt.clientY
  ctx.show = true
}

function onCtxSelect(key: string) {
  if (key === 'delete' && ctx.targetClipId) {
    deleteClipById(ctx.targetClipId)
  }
  ctx.show = false
}

/* ---------- 삭제/Undo ---------- */
function deleteClipById(id: string) {
  const removed = project.removeClipWithUndo?.(id)
  const name = sources.value[removed?.sourceId]?.name || 'clip'
  // Naive UI Notification + Undo 버튼
  const n = notification.create({
    type: 'warning',
    title: `'${name}' 클립을 삭제했습니다`,
    content: '복구하시겠습니까?',
    duration: 3500,
    keepAliveOnHover: true,
    action: () =>
      h(NButton, {
        text: true,
        onClick: () => { project.undo?.(); n.destroy(); refreshViewClips(); requestSparksRedraw() }
      }, { default: () => '복구하기' })
  })
  refreshViewClips()
  requestSparksRedraw()
}

let lastCursor = ''
function setCursor(container: HTMLElement, v: string) {
  if (lastCursor !== v) { container.style.cursor = v; lastCursor = v }
}

/* ---------- 초기화 ---------- */
onMounted(async () => {
  await nextTick()

  motion = new MotionClient(project.backendUrl + '/ws/motion')
  motion.connect()

  // 초기 폭 측정: 레이아웃 안정화 프레임까지 재시도
  const tryMeasure = () => {
    measureStageWidth()
    if (stageWidth.value <= 1) requestAnimationFrame(tryMeasure)
  }
  tryMeasure()

  // 컨테이너 ResizeObserver
  contRO = new ResizeObserver(() => measureStageWidth())
  if (timelineContainer.value) contRO.observe(timelineContainer.value)

  window.addEventListener('keyup', (e) => { if (snap.enabled) snap.enabled = false })
  window.addEventListener('mouseup', onMouseUp)
  window.addEventListener('keydown', onKeydown)

  refreshViewClips()
  clampOffset()
  genTicks()
  requestSparksRedraw()

  motion.onOpen(() => {
    motion?.setProject(project.toSnapshot())
    // WS 초기 seek: 현재 전역 마커 위치
    const t = (project as any).uiMarkerMs ?? project.player.t_ms
    motion?.seek(Math.round(t))
  })

    // 백엔드 플레이 상태 폴링 시작 (드리프트 보정에 필요)
    ; (project as any)._ensurePlayPolling?.()
})

onBeforeUnmount(() => {
  try { contRO?.disconnect() } catch { }
  window.removeEventListener('mouseup', onMouseUp)
  window.removeEventListener('keydown', onKeydown)
})

watch(clips, refreshViewClips, { deep: true })
watch(sources, () => { refreshViewClips(); sparkCache.clear(); requestSparksRedraw() }, { deep: true })
watch([() => project.graphJointMode, () => project.graphJointIndex], () => {
  sparkCache.clear()
  requestSparksRedraw()
})

/* ---------- 스파클라인 ---------- */
const SPARK_SAMPLES = 120
type SparkCacheKey = string // `${sourceId}:${mode}:${jointIndex}`
const sparkCache = new Map<SparkCacheKey, Float32Array>()
const sparksVersion = ref(0)
let sparkRaf: number | undefined
function requestSparksRedraw() {
  if (sparkRaf) cancelAnimationFrame(sparkRaf)
  sparkRaf = requestAnimationFrame(() => { sparksVersion.value++ })
}

function computeSignal(frames: number[][], mode: 'joint' | 'rms', jointIndex: number): Float32Array {
  const N = frames.length
  const out = new Float32Array(SPARK_SAMPLES)
  if (!N) return out
  for (let i = 0; i < SPARK_SAMPLES; i++) {
    const a = Math.floor(i * N / SPARK_SAMPLES)
    const b = Math.floor((i + 1) * N / SPARK_SAMPLES)
    let acc = 0, cnt = 0
    for (let k = a; k < Math.max(a + 1, b); k++) {
      const q = frames[k]
      let v = 0
      if (mode === 'joint') {
        v = q?.[jointIndex] ?? 0
      } else {
        let s = 0, cntd = 0
        if (q) {
          for (let d = 0; d < q.length; d++) {
            const val = q[d]
            if (val !== undefined && val !== null) { s += val * val; cntd++ }
          }
        }
        v = cntd ? Math.sqrt(s / cntd) : 0
      }
      acc += v; cnt++
    }
    out[i] = cnt ? acc / cnt : 0
  }
  // 정규화 0..1
  let mn = Infinity, mx = -Infinity
  for (let i = 0; i < out.length; i++) { const v = out[i] ?? 0; if (v < mn) mn = v; if (v > mx) mx = v }
  const span = Math.max(1e-6, mx - mn)
  for (let i = 0; i < out.length; i++) out[i] = ((out[i] ?? 0) - mn) / span
  return out
}

function getSpark(sourceId: string): Float32Array {
  const s = sources.value[sourceId]; if (!s) return new Float32Array(SPARK_SAMPLES)
  const key: SparkCacheKey = `${sourceId}:${project.graphJointMode}:${project.graphJointIndex}`
  const hit = sparkCache.get(key)
  if (hit) return hit
  const sig = computeSignal(s.frames, project.graphJointMode, project.graphJointIndex)
  sparkCache.set(key, sig)
  return sig
}

function sparkPointsForClip(clip: any): number[] {
  const s = sources.value[clip.sourceId]; if (!s) return []
  const sig = getSpark(clip.sourceId)  // [SPARK_SAMPLES]
  const framesTotal = s.frames.length
  const a = clip.inFrame / framesTotal
  const b = clip.outFrame / framesTotal
  const ia = Math.floor(a * SPARK_SAMPLES)
  const ib = Math.max(ia + 2, Math.floor(b * SPARK_SAMPLES))

  const w = clipW(clip)
  const h = rowH * 0.8
  const x0 = clipX(clip) + timelineOffsetPx.value
  const y0 = timelineY + 50 + clip.track * rowH

  const pts: number[] = []
  const span = Math.max(1, ib - ia - 1)
  for (let i = 0; i <= span; i++) {
    const t = i / span
    const idx = Math.min(SPARK_SAMPLES - 1, ia + Math.round(t * (ib - ia)))
    const v = sig[idx] ?? 0 // 0..1
    const x = x0 + t * w
    const y = y0 + (1 - v) * (h - 6) + 3
    pts.push(x, y)
  }
  return pts
}

/* ---------- 총 높이 ---------- */
const totalTimelineHeight = computed(() => project.clips.length * rowHeight + 60)

/* ---------- 키보드 핸들러 ---------- */
function targetIsEditable(e: KeyboardEvent): boolean {
  // 우선 이벤트 타겟, 없으면 activeElement 기준
  const el = (e.target as HTMLElement) || (document.activeElement as HTMLElement) || null
  if (!el) return false

  // contenteditable
  if (el.isContentEditable) return true
  if (el.closest?.('[contenteditable="true"]')) return true

  // 일반 폼 요소
  const tag = el.tagName?.toLowerCase()
  if (tag === 'input' || tag === 'textarea' || tag === 'select') return true

  // WAI-ARIA 역할 기반(리치 텍스트/콤보박스 등)
  const role = el.getAttribute?.('role')
  if (role === 'textbox' || role === 'combobox') return true

  // naive-ui 입력류 컨테이너 내부 여부 (인풋, 셀렉트, 오토컴플릿 등)
  if (el.closest?.('.n-input, .n-base-selection, .n-auto-complete, .n-input-wrapper')) return true

  return false
}

function timelineHasFocus(): boolean {
  const cont = timelineContainer.value
  if (!cont) return false
  const active = (document.activeElement as HTMLElement) || null
  // 컨테이너 자체가 포커스거나, 그 내부(캔버스 등)에 포커스가 있으면 true
  return !!active && (active === cont || cont.contains(active))
}

function onKeydown(e: KeyboardEvent) {
  if (e.altKey) snap.enabled = true

  // 삭제 계열만 처리
  if (e.key !== 'Delete' && e.key !== 'Backspace') return

  // 1) 텍스트/폼 편집 중이면 무시
  if (targetIsEditable(e)) return

  // 2) 타임라인이 포커스일 때만 작동
  if (!timelineHasFocus()) return

  const id = project.selectedClipId
  if (!id) return

  e.preventDefault()
  deleteClipById(id)
}
</script>

<style scoped>
.timeline-panel {
  display: flex;
  flex-direction: column;
  min-width: 0;
  /* ✅ 자식이 줄어들 수 있도록 */
  min-height: 0;
  overflow-y: auto;
  /* ✅ 세로 스크롤 */
  overflow-x: hidden;
  /* ✅ 가로 스크롤 제거 */
  background: var(--bg-2);
  padding: 12px;
  border: 1px solid var(--line-1);
  border-radius: 12px;
  box-shadow: var(--shadow);
}

.timeline-panel:focus {
  outline: none;
}

.timeline-title {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.joint-controls {
  display: flex;
  align-items: center;
  gap: 10px;
}

.lbl {
  font-size: 12px;
  color: var(--text-dim);
}

.joint-controls select {
  background: var(--bg-3);
  color: var(--text-0);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 4px 8px;
  min-width: 72px;
}

.joint-controls select:disabled {
  opacity: .55;
  cursor: not-allowed;
}

/* 작은 토글 스위치 */
.switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
}

.switch input {
  opacity: 0;
  width: 0;
  height: 0;
}

.slider {
  position: absolute;
  cursor: pointer;
  inset: 0;
  background: var(--line-2);
  border-radius: 999px;
  transition: .15s;
}

.slider:before {
  position: absolute;
  content: "";
  height: 14px;
  width: 14px;
  left: 3px;
  top: 3px;
  background: white;
  border-radius: 50%;
  transition: .15s;
}

.switch input:checked+.slider {
  background: var(--accent);
}

.switch input:checked+.slider:before {
  transform: translateX(16px);
}
</style>

<template>
    <div class="inspector panel">
        <div class="panel-title">Blend</div>

        <transition name="toast">
            <div v-if="saved" class="toast ok">
                <span class="dot ok"></span> Saved
            </div>
        </transition>

        <header class="hdr">
            <div class="presets">
                <button v-for="m in MODE_OPTIONS" :key="m" class="chip" :class="{ active: local.mode === m }"
                    @click="local.mode = m" :title="modeTips[m]">
                    <span class="dot" :class="m"></span>
                    {{ m }}
                </button>
            </div>
        </header>

        <div class="grid fill">
            <div class="row">
                <label>In (ms)</label>
                <div class="control">
                    <input type="range" min="0" max="1000" step="10" v-model.number="local.inMs" />
                    <input class="num" type="number" min="0" step="10" v-model.number="local.inMs" />
                </div>
            </div>

            <div class="row">
                <label>Out (ms)</label>
                <div class="control">
                    <input type="range" min="0" max="1000" step="10" v-model.number="local.outMs" />
                    <input class="num" type="number" min="0" step="10" v-model.number="local.outMs" />
                </div>
            </div>

            <!-- ★ Curve 행만 auto | 1fr 그리드 -->
            <div class="row curve-row">
                <label>Curve</label>
                <div class="control curve-ctl">
                    <select v-model="local.curve">
                        <option v-for="c in CURVE_OPTIONS" :key="c" :value="c">{{ c }}</option>
                    </select>
                    <canvas ref="curveCanvas" class="curve" height="36" />
                </div>
            </div>

            <div class="row" :class="{ disabled: local.mode === 'override' }">
                <label>
                    Weight
                    <span class="hint" v-if="local.mode === 'override'">(override에서는 무시)</span>
                </label>
                <div class="control">
                    <input type="range" min="0" max="1" step="0.01" v-model.number="local.weight"
                        :disabled="local.mode === 'override'" />
                    <input class="num" type="number" min="0" max="1" step="0.01" v-model.number="local.weight"
                        :disabled="local.mode === 'override'" />
                </div>
            </div>

            <div class="row" :class="{ disabled: local.mode !== 'override' }">
                <label>
                    Priority
                    <span class="hint" v-if="local.mode !== 'override'">(override에서만 의미)</span>
                </label>
                <div class="control">
                    <input class="num" type="number" step="1" v-model.number="local.priority"
                        :disabled="local.mode !== 'override'" />
                </div>
            </div>
        </div>

        <footer class="ftr">
            <button class="btn ghost" @click="reset">Reset</button>
            <div class="spacer" />
            <button class="btn" @click="apply">Apply</button>
        </footer>
    </div>
</template>

<script setup lang="ts">
import { reactive, computed, watch, ref, onMounted, onBeforeUnmount, nextTick } from 'vue'
import { useProjectStore, type Blend, type BlendMode, type BlendCurve } from '@/stores/project'

const MODE_OPTIONS = ['override', 'crossfade', 'additive'] as const
const CURVE_OPTIONS = ['linear', 'smoothstep', 'easeInOut'] as const

const modeTips: Record<BlendMode, string> = {
    override: '겹칠 때 우선순위로 덮어쓰기',
    crossfade: '겹치는 구간에서 가중합',
    additive: '기본(base)에 가산(+)',
}

const store = useProjectStore()
const clip = computed(() => store.selectedClip)

const curveCanvas = ref<HTMLCanvasElement | null>(null)
let rafId: number | undefined
let ro: ResizeObserver | null = null

const local = reactive<Blend>({
    mode: 'override',
    inMs: 120,
    outMs: 120,
    curve: 'easeInOut',
    weight: 1,
    priority: 0,
})

watch(clip, (c) => {
    if (!c) return
    Object.assign(local, c.blend)
    queueDraw()
}, { immediate: true, deep: true })

watch(() => local.curve, queueDraw)

const saved = ref(false)
let savedTimer: number | undefined
function apply() {
    if (!clip.value) return
    store.updateClipBlend(clip.value.id, { ...local })
    saved.value = true
    if (savedTimer) clearTimeout(savedTimer)
    savedTimer = window.setTimeout(() => { saved.value = false }, 1500)
}
function reset() {
    if (!clip.value) return
    Object.assign(local, clip.value.blend)
    queueDraw()
}

function queueDraw() {
    if (rafId !== undefined) cancelAnimationFrame(rafId)
    rafId = requestAnimationFrame(drawCurve)
}

function drawCurve() {
    const el = curveCanvas.value
    if (!el) return

    // ★ CSS width 100% → 실제 렌더 픽셀 크기 동기화(DPR)
    const dpr = Math.max(1, window.devicePixelRatio || 1)
    const cssW = Math.max(80, el.clientWidth) // 남는폭 그대로
    const cssH = 36
    el.width = Math.round(cssW * dpr)
    el.height = Math.round(cssH * dpr)

    const ctx = el.getContext('2d')!
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0) // 좌표계를 CSS px로
    const w = cssW, h = cssH

    ctx.clearRect(0, 0, w, h)

    // bg
    ctx.fillStyle = getCss('--bg-3', '#1d2430')
    ctx.fillRect(0, 0, w, h)

    // grid
    ctx.strokeStyle = getCss('--line-2', '#2b3446')
    ctx.lineWidth = 1
    ctx.beginPath()
    for (let i = 1; i < 4; i++) {
        const x = (w / 4) * i + 0.5
        ctx.moveTo(x, 0); ctx.lineTo(x, h)
    }
    ctx.stroke()

    // curve
    ctx.lineWidth = 2
    ctx.strokeStyle = getCss('--accent', '#4fa3ff')
    ctx.beginPath()
    const N = 80
    for (let i = 0; i <= N; i++) {
        const t = i / N
        const y = 1 - curveFn(local.curve, t)
        const x = t * w
        const py = y * (h - 6) + 3
        if (i === 0) ctx.moveTo(x, py); else ctx.lineTo(x, py)
    }
    ctx.stroke()
}

function curveFn(curve: BlendCurve, t: number) {
    if (curve === 'linear') return t
    if (curve === 'smoothstep') return t * t * (3 - 2 * t)
    return t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2 // easeInOut
}
function getCss(varName: string, fallback: string) {
    return getComputedStyle(document.documentElement).getPropertyValue(varName).trim() || fallback
}

onMounted(async () => {
    await nextTick()
    // ★ 부모 Pane 폭 변화에도 따라가도록 리사이즈 옵저버
    if (curveCanvas.value) {
        ro = new ResizeObserver(() => queueDraw())
        ro.observe(curveCanvas.value)
    }
    queueDraw()
})
onBeforeUnmount(() => {
    if (rafId !== undefined) cancelAnimationFrame(rafId)
    if (savedTimer) clearTimeout(savedTimer)
    try { ro?.disconnect() } catch { }
})
</script>

<style scoped>
.inspector {
    gap: 8px;
    width: 100%;
    /* ★ Pane 너비 = Inspector 너비 */
}

.hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
}

.presets {
    display: flex;
    gap: 8px;
    flex-wrap: wrap;
}

.chip {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 6px 10px;
    border-radius: 999px;
    background: var(--bg-3);
    border: 1px solid var(--line-2);
    color: var(--text-dim);
    cursor: pointer;
    font-size: 12px;
}

.chip:hover {
    border-color: var(--accent);
    color: var(--text-0);
}

.chip.active {
    border-color: var(--accent);
    color: var(--text-0);
    box-shadow: inset 0 0 0 1px color-mix(in oklab, var(--accent) 30%, transparent);
}

.dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
    box-shadow: 0 0 0 2px rgba(0, 0, 0, .15) inset;
}

.dot.override {
    background: var(--ok);
}

.dot.crossfade {
    background: var(--accent);
}

.dot.additive {
    background: var(--warn);
}

/* 폼 레이아웃 */
.grid {
    display: flex;
    flex-direction: column;
    gap: 10px;
}

.row {
    display: grid;
    grid-template-columns: 100px 1fr;
    gap: 10px;
    align-items: center;
}

.row.disabled {
    opacity: .6;
}

label {
    font-size: 12px;
    color: var(--text-dim);
}

.hint {
    margin-left: 6px;
    font-size: 11px;
    color: var(--text-dim);
    opacity: .85;
}

.control {
    display: flex;
    align-items: center;
    gap: 10px;
}

input[type="range"] {
    flex: 1 1 auto;
    accent-color: var(--accent);
}

.num,
select {
    background: var(--bg-3);
    color: var(--text-0);
    border: 1px solid var(--line-2);
    border-radius: 8px;
    padding: 6px 8px;
}

.num {
    width: 90px;
}

select {
    min-width: 136px;
}

.curve {
    box-sizing: border-box;
    width: 100%;
    height: 36px;
    background: var(--bg-3);
    border: 1px solid var(--line-2);
    border-radius: 8px;
    display: block;
    /* inline 기본값 제거 (잔여 여백 이슈 예방) */
    min-width: 0;
    /* grid 안에서 수축 허용 */
}

/* curve 행의 grid가 자식 수축을 막지 않도록 */
.curve-ctl {
    display: grid;
    grid-template-columns: auto minmax(0, 1fr);
    /* ✅ 1fr 트랙이 0까지 줄어들 수 있게 */
    gap: 10px;
    align-items: center;
    min-width: 0;
    /* 컨테이너도 수축 허용 */
}

/* 혹시 다른 control도 같은 현상이면 공통 적용 */
.control {
    min-width: 0;
}

.ftr {
    display: flex;
    align-items: center;
    gap: 8px;
    padding-top: 10px;
    border-top: 1px solid var(--line-1);
}

.spacer {
    flex: 1 1 auto;
}

.btn {
    background: var(--accent);
    color: #0b1220;
    border: none;
    padding: 8px 12px;
    border-radius: 8px;
    font-weight: 600;
    cursor: pointer;
    box-shadow: var(--shadow);
}

.btn.ghost {
    background: transparent;
    color: var(--text-0);
    border: 1px solid var(--line-2);
}

/* 토스트 */
.toast {
    position: absolute;
    top: 10px;
    right: 12px;
    display: inline-flex;
    align-items: center;
    gap: 8px;
    padding: 6px 10px;
    border-radius: 999px;
    background: rgba(79, 163, 255, .12);
    border: 1px solid var(--line-2);
    color: var(--text-0);
    box-shadow: var(--shadow);
    font-size: 12px;
    z-index: 2;
}

.toast.ok {
    background: rgba(72, 213, 151, .14);
    border-color: color-mix(in oklab, var(--ok) 40%, var(--line-2));
}

.toast .dot {
    width: 8px;
    height: 8px;
    border-radius: 50%;
}

.toast .dot.ok {
    background: var(--ok);
}

.toast-enter-active,
.toast-leave-active {
    transition: opacity .2s, transform .2s;
}

.toast-enter-from,
.toast-leave-to {
    opacity: 0;
    transform: translateY(-6px);
}
</style>

<!-- components/RecordDialog.vue -->
<template>
    <div v-if="open" class="modal">
        <div class="card">
            <div class="hdr">
                <h3>Recording</h3>
                <button class="x" @click="close">✕</button>
            </div>

            <div class="body">
                <div class="row">
                    <span class="lbl">Status</span>
                    <span class="val" :class="{ good: active, bad: !active }">
                        {{ active ? 'Recording…' : 'Idle' }}
                    </span>
                </div>
                <div class="row">
                    <span class="lbl">Elapsed</span>
                    <span class="val mono">{{ elapsedText }}</span>
                </div>
                <div class="row">
                    <span class="lbl">Samples</span>
                    <span class="val mono">{{ count }}</span>
                </div>
                <div v-if="errMsg" class="err">{{ errMsg }}</div>
            </div>

            <div class="ftr">
                <button class="btn" :disabled="active || starting" @click="start">
                    {{ starting ? 'Starting…' : 'Start' }}
                </button>
                <button class="btn danger" :disabled="!active || stopping" @click="stop">
                    {{ stopping ? 'Stopping…' : 'Stop & Save' }}
                </button>
            </div>
        </div>
    </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import { useProjectStore } from '@/stores/project'
import { importCsv } from '@/lib/csvImport'
import { useRecordingState } from '@/composable/useRecordingState'
const { active, count, elapsed_ms } = useRecordingState()

/**
 * Props/Emits
 * - v-model:open controls visibility
 * - No started/stopped emits; UI is driven by backend /api/record/state
 */
const props = defineProps<{ open: boolean }>()
const emit = defineEmits<{ (e: 'update:open', v: boolean): void }>()

/** Pinia store to add the Source after stop */
const store = useProjectStore()

/** UI flags & error */
const starting = ref(false)
const stopping = ref(false)
const errMsg = ref<string | null>(null)

/** Humanized elapsed mm:ss.mmm */
const elapsedText = computed(() => {
    const ms = elapsed_ms.value || 0
    const m = Math.floor(ms / 60000)
    const s = Math.floor((ms % 60000) / 1000)
    const ms3 = Math.floor(ms % 1000).toString().padStart(3, '0')
    return `${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}.${ms3}`
})

/** Start recording (backend authority) */
async function start() {
    errMsg.value = null
    if (active.value) return // already recording
    starting.value = true
    try {
        const res = await fetch(store.backendUrl + '/record/start', { method: 'POST' })
        if (!res.ok) {
            const body = await res.json().catch(() => ({}))
            errMsg.value = body?.detail || `Failed to start (HTTP ${res.status})`
            return
        }
        // Polling will update active/count/elapsed
    } finally {
        starting.value = false
    }
}

/** Stop → download CSV → import → add Source → close */
async function stop() {
    if (!active.value || stopping.value) return
    stopping.value = true
    errMsg.value = null
    try {
        await fetch(store.backendUrl + '/record/stop', { method: 'POST' })

        // Download CSV once
        const res = await fetch(store.backendUrl + '/record/download')
        if (!res.ok) {
            const body = await res.json().catch(() => ({}))
            errMsg.value = body?.detail || `Failed to download CSV (HTTP ${res.status})`
            return
        }
        const blob = await res.blob()
        const fname =
            (res.headers.get('Content-Disposition') || '').match(/filename="([^"]+)"/)?.[1] ||
            'recording.csv'

        // Reuse existing importer and add to sources (no clip)
        const file = new File([blob], fname, { type: 'text/csv' })
        const src = await importCsv(file) // expects { name, jointNames, dt, frames }
        store.addSource(src)

        close()
    } catch (e: any) {
        errMsg.value = e?.message || 'Unexpected error while stopping recording'
    } finally {
        stopping.value = false
    }
}

/** Close dialog */
function close() {
    emit('update:open', false)
}
</script>

<style scoped>
.modal {
    position: fixed;
    inset: 0;
    background: rgba(0, 0, 0, .45);
    display: grid;
    place-items: center;
    z-index: 1000;
}

.card {
    width: 420px;
    background: var(--bg-2, #161a22);
    border: 1px solid var(--line-1, #222938);
    border-radius: 14px;
    box-shadow: 0 12px 30px rgba(0, 0, 0, .5);
}

.hdr {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 14px 16px;
    border-bottom: 1px solid var(--line-1, #222938);
}

.hdr h3 {
    margin: 0;
    font-size: 16px;
    color: var(--text-0, #e8ecf1);
}

.x {
    background: transparent;
    border: 0;
    color: var(--text-1, #c8d0dc);
    font-size: 18px;
    cursor: pointer;
}

.body {
    padding: 14px 16px;
    display: grid;
    gap: 8px;
}

.row {
    display: flex;
    justify-content: space-between;
    color: var(--text-0, #e8ecf1);
}

.lbl {
    opacity: .8
}

.val {
    font-weight: 600
}

.val.good {
    color: var(--good, #6de28c);
}

.val.bad {
    color: var(--bad, #ff5b6e);
}

.mono {
    font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.err {
    margin-top: 6px;
    color: var(--bad, #ff5b6e);
    font-size: 12px;
}

.ftr {
    display: flex;
    gap: 10px;
    justify-content: flex-end;
    padding: 12px 16px;
    border-top: 1px solid var(--line-1, #222938);
}

.btn {
    padding: 8px 12px;
    border-radius: 10px;
    border: 1px solid var(--line-1, #222938);
    background: transparent;
    color: var(--text-0, #e8ecf1);
    font-weight: 600;
}

.btn.danger {
    background: var(--bad, #ff5b6e);
    color: #0f1115;
    border: 0;
}
</style>
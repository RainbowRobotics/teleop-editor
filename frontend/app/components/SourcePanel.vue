<!-- components/SourcePanel.vue -->
<template>
  <div class="panel">
    <div class="panel-header">
      <div class="title">
        <span>Sources</span>
        <span class="count">{{ sourceCount }} items</span>
      </div>
      <div class="actions">
        <button class="btn ghost" @click="onClickImport">
          <svg viewBox="0 0 24 24" class="ico"><path d="M5 20h14a1 1 0 0 0 1-1v-6h-2v5H6v-5H4v6a1 1 0 0 0 1 1Zm7-15.586 3.293 3.293 1.414-1.414L12 1.586 7.293 6.293l1.414 1.414L11 4.414V16h2V4.414Z"/></svg>
          파일 가져오기
        </button>
        <button class="btn primary" :class="{ danger: isRecording }" @click="toggleRecording">
          <svg v-if="!isRecording" viewBox="0 0 24 24" class="ico"><path d="M12 6a4 4 0 0 0-4 4v2H6a2 2 0 0 0-2 2v3h2v-3h2v3h8v-3h2v3h2v-3a2 2 0 0 0-2-2h-2v-2a4 4 0 0 0-4-4Zm0 2a2 2 0 0 1 2 2v2h-4v-2a2 2 0 0 1 2-2Z"/></svg>
          <svg v-else viewBox="0 0 24 24" class="ico"><path d="M8 6h3v12H8zM13 6h3v12h-3z"/></svg>
          {{ isRecording ? '녹화 중지' : '녹화하기' }}
        </button>
      </div>

      <input
        ref="fileEl"
        type="file"
        accept=".csv"
        class="file-input"
        @change="onFileChange"
      />
    </div>

    <ul class="source-list">
      <li v-for="s in sourceArray" :key="s.id" class="card">
        <div class="row">
          <div class="meta">
            <!-- ✅ 이름 인라인 편집 -->
            <div class="name" v-if="editingId !== s.id">
              <button class="name-btn" @click="startEdit(s)">
                {{ s.name || s.id }}
                <svg viewBox="0 0 24 24" class="ico sml"><path d="M3 17.25V21h3.75l11-11L14 6.25l-11 11ZM20.71 7.04a1.003 1.003 0 0 0 0-1.42l-2.34-2.34a1.003 1.003 0 0 0-1.42 0l-1.83 1.83 3.76 3.76 1.83-1.83Z"/></svg>
              </button>
            </div>
            <div class="name-edit" v-else>
              <input
                ref="editInputEl"
                v-model="editingName"
                type="text"
                class="name-input"
                @keydown.enter.prevent="commitEdit()"
                @keydown.esc.prevent="cancelEdit()"
                @blur="commitEdit()"
                placeholder="Enter source name"
              />
              <div class="edit-actions">
                <button class="btn ghost sml" @click="commitEdit">저장</button>
                <button class="btn ghost sml" @click="cancelEdit">취소</button>
              </div>
            </div>

            <div class="sub">
              {{ s.frames?.length || 0 }} frames •
              dt {{ (s.dt ?? 0).toFixed(3) }} s
            </div>
          </div>

          <div class="ops">
            <button class="btn ghost" @click="openCrop(s.id)">
              <svg viewBox="0 0 24 24" class="ico"><path d="M3 5h4V3H3a2 2 0 0 0-2 2v4h2V5Zm14-2v2h4v4h2V5a2 2 0 0 0-2-2h-4ZM3 15H1v4a2 2 0 0 0 2 2h4v-2H3v-4Zm20 0h-2v4h-4v2h4a2 2 0 0 0 2-2v-4ZM8 11h8v2H8v-2Z"/></svg>
              Add as Clip…
            </button>
          </div>
        </div>
      </li>
    </ul>

    <SourceCropDialog
      v-model:open="cropOpen"
      v-model:sourceId="cropSourceId"
      @close="onCropClosed"
      @added="onClipAdded"
    />
  </div>
</template>

<script setup lang="ts">
import { ref, computed, nextTick } from 'vue'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '@/stores/project'
import SourceCropDialog from '@/components/SourceCropDialog.vue'
import { importCsv } from '@/lib/csvImport'

const store = useProjectStore()
const { sources } = storeToRefs(store)

const sourceArray = computed(() => Object.values(sources.value))
const sourceCount = computed(() => sourceArray.value.length)

/* 파일 업로드 */
const fileEl = ref<HTMLInputElement | null>(null)
function onClickImport() {
  fileEl.value?.click()
}
async function onFileChange(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  try {
    const src = await importCsv(file)           // 기본 name = 파일명(확장자 제거)
    const sourceId = store.addSource(src)       // 스토어에 추가
    // 추가 직후 이름을 더 바꾸고 싶으면 아래 예시처럼:
    // store.updateSourceName(sourceId, src.name + '_v1')
    openCrop(sourceId)                          // 바로 크롭 다이얼로그 오픈(선택)
  } catch (err) {
    console.error('CSV import failed:', err)
    alert('CSV를 불러오지 못했습니다.')
  } finally {
    (e.target as HTMLInputElement).value = ''
  }
}

/* 녹화 토글(임시) */
const isRecording = ref(false)
const emit = defineEmits<{ (e: 'record-start'): void; (e: 'record-stop'): void }>()
function toggleRecording() {
  isRecording.value = !isRecording.value
  if (isRecording.value) emit('record-start')
  else emit('record-stop')
}

/* ✅ 인라인 이름 편집 상태 */
const editingId = ref<string | null>(null)
const editingName = ref('')
const editInputEl = ref<HTMLInputElement | null>(null)

function startEdit(s: { id: string; name?: string }) {
  editingId.value = s.id
  editingName.value = s.name || ''
  nextTick(() => editInputEl.value?.focus())
}
function commitEdit() {
  if (!editingId.value) return
  store.updateSourceName(editingId.value, editingName.value)
  editingId.value = null
  editingName.value = ''
}
function cancelEdit() {
  editingId.value = null
  editingName.value = ''
}

/* 크롭 다이얼로그 */
const cropOpen = ref(false)
const cropSourceId = ref<string | null>(null)
function openCrop(id: string) {
  cropSourceId.value = id
  cropOpen.value = true
}
function onCropClosed() {
  cropOpen.value = false
  cropSourceId.value = null
}
function onClipAdded() {
  // 필요하면 타임라인 refresh 트리거(보통 watch(store.clips)로 자동 반영)
}
</script>

<style scoped>
.panel {
  background: var(--bg-1, #11141a);
  border: 1px solid var(--line-1, #222938);
  border-radius: 12px;
  box-shadow: var(--shadow, 0 10px 30px rgba(0,0,0,.35));
  padding: 12px;
}
.panel-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 10px; background-color: var(--bg-1) !important; }
.title { display: flex; align-items: baseline; gap: 10px; font-weight: 600; color: var(--text-0, #e8ecf1); }
.title .count { font-size: 12px; color: var(--text-1, #c8d0dc); }
.actions { display: flex; gap: 8px; }
.file-input { display: none; }

.source-list { display: flex; flex-direction: column; gap: 8px; margin: 0; padding: 0; list-style: none; }
.card {
  background: var(--bg-2, #161a22);
  border: 1px solid var(--line-1, #222938);
  border-radius: 10px; padding: 10px;
  transition: border-color .15s ease, background .15s ease;
}
.card:hover { border-color: var(--line-2, #2b3446); background: #18202a; }

.row { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.meta { display: grid; gap: 4px; min-width: 0; }
.name { color: var(--text-0, #e8ecf1); font-weight: 600; }
.name-btn {
  display: inline-flex; align-items: center; gap: 6px;
  color: inherit; background: transparent; border: 0; padding: 0; cursor: pointer;
}
.name-btn .ico.sml { width: 14px; height: 14px; opacity: .7; }

.name-edit { display: flex; align-items: center; gap: 8px; }
.name-input {
  background: var(--bg-3, #1d2430); color: var(--text-0, #e8ecf1);
  border: 1px solid var(--line-2, #2b3446); border-radius: 8px;
  padding: 6px 8px; width: 120px; min-width: 100px;
}
.edit-actions { display: flex; gap: 6px; }

.sub { color: var(--text-1, #c8d0dc); font-size: 12px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.ops { display: flex; gap: 8px; }

.btn {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-radius: 10px; font-weight: 600;
  border: 1px solid var(--line-1, #222938); color: var(--text-0, #e8ecf1);
  background: transparent; transition: background .15s ease, border-color .15s ease, transform .02s ease;
}
.btn .ico { width: 16px; height: 16px; fill: currentColor; }
.btn:hover { background: rgba(255,255,255,.05); border-color: var(--line-2, #2b3446); }
.btn:active { transform: translateY(1px); }
.btn.primary { background: var(--accent, #4fa3ff); color: #0f1115; border: 0; }
.btn.primary:hover { filter: brightness(1.06); }
.btn.primary.danger { background: var(--bad, #ff5b6e); color: #0f1115; }
.btn.ghost { background: transparent; color: var(--text-1, #c8d0dc); }
.btn.sml { padding: 6px 8px; border-radius: 8px; font-weight: 600; }
</style>

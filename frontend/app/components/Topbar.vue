<!-- components/TopBar.vue -->
<template>
  <div class="topbar">
    <div class="group">
      <span class="brand">Editor</span>
      <button class="btn ghost" @click="onSave">Save</button>
      <button class="btn ghost" @click="onLoadClick">Load</button>
      <input ref="fileEl" type="file" accept=".json" class="hidden" @change="onLoaded" />
    </div>

    <div class="group flex-grow"></div>

    <div class="group">
      <label class="lbl">
        <span class="tooltip-icon">?
          <span class="tooltip-text">
            <strong>UPC</strong>에 세팅된 로컬, 로봇, 퀘스트의 IP 주소를 설정합니다.
          </span>
        </span>
      </label>
    </div>

    <!-- Local IP -->
    <div class="group">
      <label class="lbl">Local</label>
      <input class="ipt" v-model="localAddress" />
    </div>

    <!-- Robot IP -->
    <div class="group">
      <label class="lbl">Robot</label>
      <input class="ipt" v-model="robotAddress" />
      <button class="btn" :class="{ ok: robotConnected }" @click="connectRobot">
        {{ robotConnected ? 'Connected' : 'Connect' }}
      </button>
    </div>

    <!-- Quest IP -->
    <div class="group">
      <label class="lbl">MetaQuest</label>
      <input class="ipt" v-model="questAddress" />
      <button class="btn" :class="questBtnClass" @click="onQuestClick" :aria-label="questBtnText" :title="questBtnText">
        {{ questBtnText }}
        <span v-if="questBtnClass.waiting" class="spinner" aria-hidden="true"></span>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '@/stores/project'

const store = useProjectStore()
const { localAddress, robotAddress, questAddress, robotConnected, questConnected, questTransportUp } = storeToRefs(store)

function connectRobot() { store.connectRobot() }
function onQuestClick() {
  if (questConnected.value || questTransportUp.value) {
    store.stopQuestWS()
    return
  }
  store.connectQuest()
}
function onSave() { store.saveProjectToFile() }

const fileEl = ref<HTMLInputElement | null>(null)
function onLoadClick() { fileEl.value?.click() }
async function onLoaded(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  await store.loadProjectFromFile(file)
    ; (e.target as HTMLInputElement).value = ''
}

const questBtnText = computed(() => {
  if (questConnected.value) return 'Connected'
  if (questTransportUp.value) return 'Waiting…'
  return 'Connect'
})
const questBtnClass = computed(() => ({
  ok: questConnected.value,
  waiting: questTransportUp.value && !questConnected.value
}))
</script>

<style scoped>
.topbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--line-1);
  box-shadow: var(--shadow);
}

.brand {
  font-weight: 700;
  color: var(--text-0);
  margin-right: 8px;
}

.group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.flex-grow {
  flex: 1;
}

.lbl {
  color: var(--text-1);
  font-size: 12px;
}

.ipt {
  background: var(--bg-2);
  color: var(--text-0);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 6px 8px;
  min-width: 180px;
}

.btn {
  background: transparent;
  color: var(--text-0);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 6px 10px;
}

.btn.ok {
  background: rgba(72, 213, 151, .14);
  border-color: rgba(72, 213, 151, .4);
  color: var(--ok);
}

.btn.ghost {
  color: var(--text-1);
}

.hidden {
  display: none;
}

/* Tooltip 스타일 */
.tooltip-icon {
  display: inline-block;
  margin-left: 4px;
  cursor: help;
  position: relative;
  font-weight: bold;
  font-size: 12px;
  color: var(--accent);
  border: 1px solid var(--accent);
  border-radius: 50%;
  width: 14px;
  height: 14px;
  text-align: center;
  line-height: 14px;
}

.tooltip-icon .tooltip-text {
  visibility: hidden;
  width: max-content;
  /* 내용에 맞춰 크기 */
  max-width: 240px;
  /* 최대 너비 제한 */
  background-color: var(--bg-2);
  color: var(--text-0);
  text-align: left;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid var(--line-2);
  position: absolute;
  z-index: 1;
  top: 24px;
  /* 아이콘 아래로 */
  left: 50%;
  /* 가운데 정렬 기준 */
  transform: translateX(-50%);
  /* 가로 가운데 맞춤 */
  opacity: 0;
  transition: opacity 0.2s;
  white-space: normal;
  /* 줄바꿈 허용 */
}

.tooltip-icon:hover .tooltip-text {
  visibility: visible;
  opacity: 1;
}
</style>

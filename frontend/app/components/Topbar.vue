<!-- components/TopBar.vue -->
<template>
  <div class="topbar">
    <!-- Row 1: Brand + Project + Primary Action -->
    <div class="row">
      <div class="group">
        <span class="brand">Editor</span>
        <button class="btn ghost" @click="onSave">Save</button>
        <button class="btn ghost" @click="onLoadClick">Load</button>
        <input ref="fileEl" type="file" accept=".json" class="hidden" @change="onLoaded" />
      </div>

      <div class="group flex-grow"></div>

      <div class="group">
        <!-- Primary Teleop button -->
        <button class="btn" :class="{ info: teleopRunning, disabled: teleopDisabled }" :disabled="teleopDisabled"
          @click="onTeleopClick" :title="teleopTitle">
          <span v-if="teleopBusy" class="spinner"></span>
          {{ teleopRunning ? 'Stop Teleop' : 'Start Teleop' }}
        </button>

        <!-- Settings toggle -->
        <button class="btn ghost" @click="showSettings = !showSettings" :aria-expanded="showSettings" title="Settings">
          ⚙︎
        </button>
      </div>
    </div>

    <!-- Row 2: Status chips (one-click controls) -->
    <div class="row wrap chipbar">
      <div class="chip" :class="robotChipClass" @click="onRobotChipClick" :title="robotTitle">
        <span class="dot"></span>
        <span v-if="robotBusy" class="spinner small"></span>
        Robot
        <span class="mono">
          {{ robotBusy ? robotPhaseLabel : (robotReady ? 'Ready' : (robotConnected ? 'Connected' : 'Offline')) }}
        </span>
      </div>

      <div class="chip" :class="masterChipClass" @click="onMasterChipClick" :title="masterTitle">
        <span class="dot"></span> Master {{ masterConnected ? 'Connected' : 'Offline' }}
      </div>

      <div class="chip" :class="teleopChipClass" @click="onTeleopClick" :title="teleopTitle">
        <span class="dot"></span> Teleop {{ teleopRunning ? 'Running' : 'Stopped' }}
      </div>

      <div class="chip" :class="questChipClass" @click="onQuestClick" :title="questBtnText">
        <span class="dot"></span>
        MetaQuest {{ questConnected ? 'Connected' : (questTransportUp ? 'Waiting…' : 'Offline') }}
        <span v-if="questTransportUp && !questConnected" class="spinner small"></span>
      </div>

      <div class="chip" :class="gripChipClass" @click="onGripSmartClick" :title="gripBtnTitle">
        <span class="dot"></span>
        Gripper
        <span class="mono">{{ gripBtnText }}</span>
        <span v-if="gripperBusy" class="spinner small"></span>
      </div>
    </div>

    <!-- Settings panel (collapsible) -->
    <div v-if="showSettings" class="settings">
      <!-- Helpful hint / tooltip -->
      <div class="tip">
        <span class="tooltip-icon">?
          <span class="tooltip-text">
            <strong>UPC</strong>에 세팅된 로컬, 로봇, 퀘스트, 마스터 장치 정보를 설정합니다.
          </span>
        </span>
        <span class="tip-text">Network & device settings</span>
      </div>

      <div class="grid">
        <!-- Local IP -->
        <label class="lbl">Local</label>
        <input class="ipt" v-model="localAddress" placeholder="e.g. 127.0.0.1" />

        <!-- Robot IP -->
        <label class="lbl">Robot</label>
        <div class="row mini">
          <input class="ipt" v-model="robotAddress" placeholder="e.g. 192.168.x.x" />
          <button class="btn" :class="{ info: robotConnected }" @click="onRobotChipClick">
            {{ robotConnected ? 'Disconnect' : 'Connect' }}
          </button>
        </div>

        <!-- Master device/IP (if your store has it; else local-only binding) -->
        <label class="lbl">Master</label>
        <div class="row mini">
          <input class="ipt" v-model="masterDevice" placeholder="/dev/rby1_master_arm" />
          <button class="btn" :class="{ info: masterConnected }" @click="onMasterChipClick">
            {{ masterConnected ? 'Disconnect' : 'Connect' }}
          </button>
        </div>

        <!-- Teleop mode -->
        <label class="lbl">Teleop Mode</label>
        <select class="ipt" v-model="teleopMode">
          <option value="position">position</option>
          <option value="impedance">impedance</option>
        </select>

        <!-- MetaQuest IP -->
        <label class="lbl">MetaQuest</label>
        <div class="row mini">
          <input class="ipt" v-model="questAddress" placeholder="e.g. 192.168.x.x" />
          <button class="btn" :class="questBtnClass" @click="onQuestClick" :aria-label="questBtnText"
            :title="questBtnText">
            {{ questBtnText }}
          </button>
        </div>

        <!-- Gripper quick test (R / L normalized) -->
        <label class="lbl">Gripper (R/L)</label>
        <div class="row mini">
          <input class="range" type="range" min="0" max="1" step="0.01" v-model.number="gripR" @change="onGripSlide"
            title="Right" />
          <input class="range" type="range" min="0" max="1" step="0.01" v-model.number="gripL" @change="onGripSlide"
            title="Left" />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { storeToRefs } from 'pinia'
import { useProjectStore } from '@/stores/project'

/* ---------------- store bindings ---------------- */
const store = useProjectStore()
const {
  // existing fields you already had
  localAddress, robotAddress, questAddress,
  robotConnected, questConnected, questTransportUp,
} = storeToRefs(store)

// optional (new) modules if you added them earlier
const s: any = store
const gripper = (storeToRefs(store) as any).gripper ?? ref({ connected: false, homed: false, running: false, busy: false, target_n: null })
const teleop = computed(() => s.teleop ?? { running: false, busy: false, mode: 'position' })
const master = computed(() => s.master ?? { connected: false, busy: false, device: '' })
const robotReady = computed(() => (s.robot?.ready ?? robotConnected.value)) // fallback: ready==connected

/* ---------------- local ui state ---------------- */
const showSettings = ref(false)
const fileEl = ref<HTMLInputElement | null>(null)
const masterDevice = computed({
  get: () => (s.master?.device ?? ''),
  set: v => { if (s.master) s.master.device = v }
})

// teleop mode (persist to store if present)
const teleopMode = computed({
  get: () => teleop.value.mode ?? 'position',
  set: (v: string) => { if (s.teleop) s.teleop.mode = v }
})

/* ---------------- status & labels ---------------- */
// Robot chips/classes
const robotBusy = computed(() => s.robot?.busy ?? false)
const robotPhase = computed<null | 'connecting' | 'enabling' | 'disconnecting'>(() => s.robot?.phase ?? null)

// blue when ready, yellow when connected-not-ready, gray when off, dim when busy
const robotChipClass = computed(() => ({
  info: robotReady.value,
  warn: robotConnected.value && !robotReady.value,
  off: !robotConnected.value,
  busy: robotBusy.value,
}))

// dynamic title
const robotTitle = computed(() => {
  if (robotBusy.value) {
    if (robotPhase.value === 'connecting') return 'Working… (connecting)'
    if (robotPhase.value === 'enabling') return 'Working… (enabling)'
    if (robotPhase.value === 'disconnecting') return 'Working… (stopping)'
    return 'Working…'
  }
  return !robotConnected.value ? 'Connect robot'
    : (robotReady.value ? 'Stop & Disconnect' : 'Disconnect')
})

// inline label beside "Robot"
const robotPhaseLabel = computed(() => {
  if (robotPhase.value === 'connecting') return 'Working… (connecting)'
  if (robotPhase.value === 'enabling') return 'Working… (enabling)'
  if (robotPhase.value === 'disconnecting') return 'Working… (stopping)'
  return 'Working…'
})

// Master chip
const masterConnected = computed(() => master.value.connected)
const masterBusy = computed(() => master.value.busy ?? false)
const masterChipClass = computed(() => ({
  info: masterConnected.value,
  off: !masterConnected.value,
  busy: masterBusy.value,
}))
const masterTitle = computed(() => masterConnected.value ? 'Disconnect master' : 'Connect master')

// Teleop
const teleopRunning = computed(() => teleop.value.running)
const teleopBusy = computed(() => teleop.value.busy ?? false)
const teleopDisabled = computed(() =>
  teleopBusy.value || robotBusy.value || !(robotReady.value && masterConnected.value)
)
const teleopTitle = computed(() => teleopRunning.value ? 'Stop teleop' : (teleopDisabled.value ? 'Robot/Master not ready' : 'Start teleop'))
const teleopChipClass = computed(() => ({
  info: teleopRunning.value,
  off: !teleopRunning.value,
  busy: teleopBusy.value,
}))

// Quest
const questBtnText = computed(() => questConnected.value ? 'Connected' : (questTransportUp.value ? 'Waiting…' : 'Connect'))
const questBtnClass = computed(() => ({
  ok: questConnected.value,
  waiting: questTransportUp.value && !questConnected.value,
}))
const questChipClass = computed(() => ({
  info: questConnected.value,
  warn: questTransportUp.value && !questConnected.value,
  off: !questConnected.value && !questTransportUp.value,
}))

// Gripper (one-button states you already set)
const gripperBusy = computed(() => gripper.value.busy)
const isConnected = computed(() => gripper.value.connected)
const isHomed = computed(() => gripper.value.homed)
const isRunning = computed(() => gripper.value.running)
const gripBtnText = computed(() => {
  if (gripperBusy.value) return 'Working…'
  if (!isConnected.value) return 'Connect'
  if (isConnected.value && !isHomed.value) return 'Connected'
  if (isConnected.value && isHomed.value && isRunning.value) return 'Ready'
  return 'Start'
})
const gripBtnTitle = computed(() => {
  if (!isConnected.value) return 'Connect gripper'
  if (isConnected.value && !isHomed.value) return 'Click to Home & Start'
  if (isConnected.value && isHomed.value && isRunning.value) return 'Click to Stop & Disconnect'
  return 'Start gripper'
})
const gripChipClass = computed(() => ({
  warn: isConnected.value && !isHomed.value,
  info: isConnected.value && isHomed.value && isRunning.value,
  ok: isConnected.value && isHomed.value && !isRunning.value,
  off: !isConnected.value,
  busy: gripperBusy.value,
}))

/* ---------------- events ---------------- */
function connectRobot() { store.connectRobot?.() }

function onQuestClick() {
  if (questConnected.value || questTransportUp.value) { store.stopQuestWS?.(); return }
  store.connectQuest?.()
}
function onSave() { store.saveProjectToFile?.() }
function onLoadClick() { fileEl.value?.click() }
async function onLoaded(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  await store.loadProjectFromFile?.(file)
    ; (e.target as HTMLInputElement).value = ''
}

// smart actions: use new APIs if available, otherwise fallback
async function onRobotChipClick() {
  if (typeof s.smartRobot === 'function') { await s.smartRobot(robotAddress.value) }
  else { await connectRobot() }
  await s.refreshRobot?.()
}
async function onMasterChipClick() {
  if (typeof s.smartMaster === 'function') { await s.smartMaster() }
  else { /* optional: toast "wire master in store" */ }
  await s.refreshMaster?.()
}
async function onTeleopClick() {
  if (typeof s.toggleTeleop === 'function') { await s.toggleTeleop() }
  else { /* optional: toast "wire teleop in store" */ }
  await s.refreshTeleop?.()
}

async function onGripSmartClick() { await s.smartGripper?.(); await s.refreshGripper?.() }

// quick gripper sliders in settings
const gripR = ref(0), gripL = ref(0)
async function onGripSlide() {
  if (Array.isArray(gripper.value.target_n)) { gripper.value.target_n = [gripR.value, gripL.value] }
  // if your store has setGripperNormalized([r,l]), call it:
  await s.setGripperNormalized?.([gripR.value, gripL.value])
}

const POLL_MS = 750
let visHandler: (() => void) | null = null

onMounted(async () => {
  // initial state pulls (call only if available to avoid runtime errors)
  await s.refreshRobot?.()
  await s.refreshMaster?.()
  await s.refreshTeleop?.()
  await s.refreshGripper?.()

  store.ensureQuestWS?.()

  // seed slider from current state
  if (Array.isArray(gripper.value.target_n)) {
    gripR.value = gripper.value.target_n[0] ?? 0
    gripL.value = gripper.value.target_n[1] ?? 0
  }

  // kick off periodic refresh
  store.startStatusPolling?.(POLL_MS)

  // pause polling when tab is hidden to save network/CPU
  visHandler = () => {
    if (document.visibilityState === 'visible') {
      store.startStatusPolling?.(POLL_MS) // safe: no double start
    } else {
      store.stopStatusPolling?.()
    }
  }
  document.addEventListener('visibilitychange', visHandler)
})

onUnmounted(() => {
  if (visHandler) document.removeEventListener('visibilitychange', visHandler)
  store.stopStatusPolling?.()
})
</script>

<style scoped>
.topbar {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  background: var(--bg-1);
  border-bottom: 1px solid var(--line-1);
  box-shadow: var(--shadow);
}

/* rows */
.row {
  display: flex;
  align-items: center;
  gap: 12px;
}

.row.wrap {
  flex-wrap: wrap;
}

.row.mini {
  gap: 6px;
}

/* groups */
.group {
  display: flex;
  align-items: center;
  gap: 8px;
}

.flex-grow {
  flex: 1;
}

/* brand & basics */
.brand {
  font-weight: 700;
  color: var(--text-0);
  margin-right: 8px;
}

.lbl {
  color: var(--text-1);
  font-size: 12px;
}

/* inputs/buttons */
.ipt {
  background: var(--bg-2);
  color: var(--text-0);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 6px 8px;
  min-width: 160px;
}

.btn {
  background: transparent;
  color: var(--text-0);
  border: 1px solid var(--line-2);
  border-radius: 8px;
  padding: 6px 10px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
}

.btn.ghost {
  color: var(--text-1);
}

.btn.info {
  background: rgba(64, 156, 255, .14);
  border-color: rgba(64, 156, 255, .4);
  color: #4ea1ff;
}

.btn.disabled {
  opacity: .6;
  pointer-events: none;
}

.hidden {
  display: none;
}

/* chips */
.chipbar {
  gap: 8px;
}

.chip {
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  border-radius: 999px;
  cursor: pointer;
  user-select: none;
  border: 1px solid var(--line-2);
  background: var(--bg-2);
  color: var(--text-0);
}

.chip .dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--line-2);
}

.chip.info .dot {
  background: #4ea1ff;
}

/* blue */
.chip.warn .dot {
  background: #f0c800;
}

/* yellow */
.chip.ok .dot {
  background: var(--ok);
}

/* green */
.chip.off {
  opacity: .8;
}

.chip.busy {
  opacity: .8;
  pointer-events: none;
}

.mono {
  font-variant-numeric: tabular-nums;
  color: var(--text-1);
}

/* settings panel */
.settings {
  border: 1px solid var(--line-2);
  border-radius: 10px;
  background: var(--bg-2);
  padding: 10px;
}

.grid {
  display: grid;
  grid-template-columns: 120px 1fr;
  gap: 10px 12px;
}

@media (max-width: 900px) {
  .grid {
    grid-template-columns: 1fr;
  }
}

.range {
  width: 120px;
}

.tip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  margin: 4px 0 10px;
}

/* small badge-like text beside the ? icon */
.tip .tip-text {
  font-size: 14px;
  font-weight: bold;
  line-height: 1;
  color: var(--text-1);
  /* background: var(--bg-1); */
  /* border: 1px solid var(--line-2); */
  border-radius: 6px;
  /* padding: 4px 8px; */
  user-select: none;
  white-space: nowrap;
}

@media (max-width: 900px) {
  .tip .tip-text {
    font-size: 11px;
  }
}

/* tooltip */
.tooltip-icon {
  display: inline-block;
  margin-right: 8px;
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
  max-width: 240px;
  background-color: var(--bg-1);
  color: var(--text-0);
  text-align: left;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid var(--line-2);
  position: absolute;
  z-index: 1;
  top: 24px;
  left: 50%;
  transform: translateX(-50%);
  opacity: 0;
  transition: opacity .2s;
  white-space: normal;
}

.tooltip-icon:hover .tooltip-text {
  visibility: visible;
  opacity: 1;
}

/* spinner */
.spinner {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 2px solid var(--text-0);
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin .8s linear infinite;
  vertical-align: -2px;
  color: var(--text-0)
}

.spinner.small {
  width: 10px;
  height: 10px;
  border-width: 2px;
}

@keyframes spin {
  to {
    transform: rotate(360deg)
  }
}
</style>
